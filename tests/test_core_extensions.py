"""Independent standard parsing and explicit geospatial edge cases."""
import copy
import hashlib
import importlib.util
import io
import json
import unittest
import zipfile
import _source_package
_source_package.use_local_core()
from PIL import Image
from geomasklab.api import create_evidence,recalculate_evidence
from geomasklab.provenance import provenance_document,verify_provenance
from geomasklab.geospatial import measure_geospatial,geospatial_packet,verify_geospatial_packet


def png(image):
    out=io.BytesIO();image.save(out,'PNG');return out.getvalue()


class Provenance(unittest.TestCase):
    def setUp(self):
        self.bundle=create_evidence(png(Image.new('RGB',(7,5),(40,120,40))),png(Image.new('L',(7,5),255)),
            target='tree',source='Synthetic source',aligned=True)

    def test_mapping_preserves_file_identity_scope_and_parent(self):
        child=recalculate_evidence(self.bundle,scope='right')
        doc=provenance_document(child)
        self.assertTrue(verify_provenance(child,doc)['verified'])
        self.assertEqual(doc['entity']['gml:domain']['gml:selectedRegionPixels'],20)
        self.assertEqual(doc['entity']['gml:parent_evidence']['gml:sha256'],hashlib.sha256(self.bundle).hexdigest())
        self.assertFalse(doc['entity']['gml:parent_evidence']['gml:embedded'])
        forged=copy.deepcopy(doc);forged['entity']['gml:domain']['gml:selectedRegionPixels']=35
        with self.assertRaises(ValueError):verify_provenance(child,forged)
        historical=provenance_document(child,exporter_version='1.0.0.dev6')
        self.assertTrue(verify_provenance(child,historical)['verified'])

    @unittest.skipUnless(importlib.util.find_spec('prov'),'Optional PROV interop extra not installed')
    def test_independent_prov_library_parses_and_roundtrips(self):
        from prov.model import ProvDocument
        doc=provenance_document(recalculate_evidence(self.bundle,scope='right'))
        parsed=ProvDocument.deserialize(content=json.dumps(doc),format='json')
        again=ProvDocument.deserialize(content=parsed.serialize(format='json'),format='json')
        self.assertEqual(parsed,again)
        self.assertGreater(len(parsed.get_records()),20)


@unittest.skipUnless(importlib.util.find_spec('rasterio') and importlib.util.find_spec('pyproj'),
                     'Optional geospatial extra not installed')
class Geospatial(unittest.TestCase):
    def fixture(self,crs='EPSG:32654',transform=None,width=7,height=5,*,color=(40,120,40),nodata=None):
        import numpy as np
        import rasterio
        from affine import Affine
        transform=transform or Affine(.5,0,500000,0,-.5,3950000)
        image=Image.new('RGB',(width,height),color)
        mask=Image.new('L',(width,height));mask.paste(255,(1,1,min(width,5),min(height,4)))
        bundle=create_evidence(png(image),png(mask),target='tree',source='Synthetic georeferenced fixture',aligned=True)
        array=np.array(image).transpose(2,0,1)
        with rasterio.io.MemoryFile() as memory:
            with memory.open(driver='GTiff',width=width,height=height,count=3,dtype='uint8',
                             transform=transform,crs=crs,nodata=nodata) as output:output.write(array)
            raw=memory.read()
        return bundle,raw

    def test_nominal_area_denominators_and_exported_geotiff(self):
        bundle,raster=self.fixture()
        child=recalculate_evidence(bundle,scope='right')
        record,mask=measure_geospatial(child,raster)
        self.assertEqual(record['measurements']['foreground_pixels'],6)
        self.assertEqual(record['measurements']['foreground_area_m2'],1.5)
        self.assertEqual(record['measurements']['selected_region_area_m2'],5.)
        self.assertEqual(record['measurements']['whole_image_area_m2'],8.75)
        self.assertFalse(record['area_model']['ground_area_corrected'])
        self.assertTrue(verify_geospatial_packet(geospatial_packet(child,raster))['verified'])

    @unittest.skipUnless(importlib.util.find_spec('jsonschema'), 'Optional schema extra not installed')
    def test_geospatial_metadata_schema(self):
        from importlib.resources import files
        from jsonschema import Draft202012Validator
        bundle,raster=self.fixture()
        record,_=measure_geospatial(bundle,raster)
        schema=json.loads(files('geomasklab').joinpath('schemas','geospatial-1.0.schema.json').read_text())
        Draft202012Validator(schema).validate(record)

    def test_us_survey_feet_are_read_from_crs(self):
        from affine import Affine
        bundle,raster=self.fixture(crs='EPSG:2263',transform=Affine(1,0,980000,0,-1,200000))
        record,_=measure_geospatial(bundle,raster)
        self.assertAlmostEqual(record['area_model']['pixel_area_m2'],(1200/3937)**2,places=12)

    def test_rotated_nominal_grid_uses_affine_determinant(self):
        from affine import Affine
        bundle,raster=self.fixture(transform=Affine(2,1,500000,.5,-3,3950000))
        record,_=measure_geospatial(bundle,raster)
        self.assertEqual(record['area_model']['pixel_area_m2'],6.5)

    def test_missing_crs_mismatched_pixels_and_nodata_are_rejected(self):
        for crs,error in [(None,'explicit CRS')]:
            bundle,raster=self.fixture(crs=crs)
            with self.assertRaisesRegex(ValueError,error):measure_geospatial(bundle,raster)
        bundle,_=self.fixture();_,raster=self.fixture(color=(50,120,40))
        with self.assertRaisesRegex(ValueError,'RGB pixels'):measure_geospatial(bundle,raster)
        bundle,raster=self.fixture(nodata=40)
        with self.assertRaisesRegex(ValueError,'Nodata'):measure_geospatial(bundle,raster)

    def test_geographic_cell_against_independent_geod_call(self):
        from affine import Affine
        from pyproj import Geod
        bundle,raster=self.fixture(crs='EPSG:4326',transform=Affine(1,0,0,0,-1,1),width=1,height=1)
        record,_=measure_geospatial(bundle,raster,method='geodesic')
        expected=abs(Geod(ellps='WGS84').polygon_area_perimeter([0,1,1,0],[1,1,0,0])[0])
        self.assertAlmostEqual(record['measurements']['whole_image_area_m2'],expected,places=4)
        with self.assertRaisesRegex(ValueError,'projected CRS'):measure_geospatial(bundle,raster,method='nominal')

    def test_mercator_geodesic_area_is_distinct_from_nominal(self):
        from affine import Affine
        bundle,raster=self.fixture(crs='EPSG:3857',transform=Affine(100,0,0,0,-100,8399737),width=7,height=5)
        nominal,_=measure_geospatial(bundle,raster)
        geodesic,_=measure_geospatial(bundle,raster,method='geodesic')
        self.assertLess(geodesic['measurements']['whole_image_area_m2'],.4*nominal['measurements']['whole_image_area_m2'])
        self.assertTrue(verify_geospatial_packet(geospatial_packet(bundle,raster,method='geodesic'))['verified'])

    def test_rehashed_false_area_and_extra_entries_are_rejected(self):
        bundle,raster=self.fixture()
        packet=geospatial_packet(bundle,raster)
        with zipfile.ZipFile(io.BytesIO(packet)) as archive:files={n:archive.read(n) for n in archive.namelist()}
        record=json.loads(files['geospatial.json']);record['measurements']['foreground_area_m2']+=1
        files['geospatial.json']=json.dumps(record).encode()
        manifest=json.loads(files['manifest.json'])
        manifest['files']['geospatial.json']={'sha256':hashlib.sha256(files['geospatial.json']).hexdigest(),'bytes':len(files['geospatial.json'])}
        files['manifest.json']=json.dumps(manifest).encode()
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as archive:
            for name,raw in files.items():archive.writestr(name,raw)
        with self.assertRaisesRegex(ValueError,'area does not replay'):verify_geospatial_packet(out.getvalue())
        files['extra.txt']=b'additional file'
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as archive:
            for name,raw in files.items():archive.writestr(name,raw)
        with self.assertRaisesRegex(ValueError,'five unique'):verify_geospatial_packet(out.getvalue())

    def test_empty_region_has_null_area_ratio(self):
        bundle,raster=self.fixture(width=1,height=5)
        child=recalculate_evidence(bundle,scope='left')
        record,_=measure_geospatial(child,raster)
        self.assertEqual(record['measurements']['selected_region_area_m2'],0)
        self.assertIsNone(record['measurements']['coverage_of_region_area'])
        self.assertTrue(verify_geospatial_packet(geospatial_packet(child,raster))['verified'])

    def test_rehashed_missing_mask_crs_and_malformed_record_fail_cleanly(self):
        import rasterio
        bundle,raster=self.fixture()
        with zipfile.ZipFile(io.BytesIO(geospatial_packet(bundle,raster))) as archive:
            original={n:archive.read(n) for n in archive.namelist()}
        def repack(files):
            manifest=json.loads(files['manifest.json'])
            for name in manifest['files']:
                manifest['files'][name]={'bytes':len(files[name]),'sha256':hashlib.sha256(files[name]).hexdigest()}
            files['manifest.json']=json.dumps(manifest).encode()
            out=io.BytesIO()
            with zipfile.ZipFile(out,'w') as archive:
                for name,raw in files.items():archive.writestr(name,raw)
            return out.getvalue()
        with rasterio.io.MemoryFile(original['mask.tif']) as memory,memory.open() as source:
            pixels=source.read(1);transform=source.transform
        with rasterio.io.MemoryFile() as memory:
            with memory.open(driver='GTiff',width=7,height=5,count=1,dtype='uint8',transform=transform) as output:
                output.write(pixels,1)
            files=dict(original);files['mask.tif']=memory.read()
        with self.assertRaisesRegex(ValueError,'Exported GeoTIFF mask'):verify_geospatial_packet(repack(files))
        for value,error in [(None,'requires area_model'),({'crs_wkt':'invalid'},'valid CRS')]:
            files=dict(original);record=json.loads(files['geospatial.json'])
            if value is None:record['area_model']=None
            else:record['grid']=value
            files['geospatial.json']=json.dumps(record).encode()
            with self.assertRaisesRegex(ValueError,error):verify_geospatial_packet(repack(files))

    def test_geodesic_scope_limits_and_invalid_coordinates(self):
        from affine import Affine
        bundle,raster=self.fixture(crs='EPSG:2263')
        with self.assertRaisesRegex(ValueError,'WGS84 UTM'):measure_geospatial(bundle,raster,method='geodesic')
        bundle,raster=self.fixture(width=1000,height=501)
        with self.assertRaisesRegex(ValueError,'500,000'):measure_geospatial(bundle,raster,method='geodesic')
        bundle,raster=self.fixture(crs='EPSG:4326',transform=Affine(.01,0,0,0,-.01,95))
        with self.assertRaisesRegex(ValueError,'coordinates'):measure_geospatial(bundle,raster,method='geodesic')

    def test_source_requires_explicit_transform(self):
        import numpy as np
        import rasterio
        bundle,_=self.fixture()
        array=np.zeros((3,5,7),np.uint8);array[0]=40;array[1]=120;array[2]=40
        with rasterio.io.MemoryFile() as memory:
            with self.assertWarns(rasterio.errors.NotGeoreferencedWarning):
                with memory.open(driver='GTiff',width=7,height=5,count=3,dtype='uint8',crs='EPSG:32654') as output:
                    output.write(array)
            raw=memory.read()
        with self.assertRaisesRegex(ValueError,'stored affine'):measure_geospatial(bundle,raw)

    def test_row_geodesic_matches_per_pixel_oracle_above_old_limit(self):
        from affine import Affine
        from pyproj import Geod
        bundle,raster=self.fixture(crs='EPSG:4326',transform=Affine(.001,0,-105,0,-.001,40),width=1000,height=501)
        record,_=measure_geospatial(bundle,raster,method='geodesic')
        self.assertEqual(record['measurements']['whole_image_pixels'],501000)
        self.assertGreater(record['measurements']['whole_image_area_m2'],0)
        small,raster=self.fixture(crs='EPSG:4326',transform=Affine(.001,0,-105,0,-.001,40),width=7,height=5)
        measured,_=measure_geospatial(small,raster,method='geodesic')
        import math
        geod=Geod(ellps='WGS84')
        direct=math.fsum(abs(geod.polygon_area_perimeter(
            [-105+x*.001,-105+(x+1)*.001,-105+(x+1)*.001,-105+x*.001],
            [40-y*.001,40-y*.001,40-(y+1)*.001,40-(y+1)*.001])[0]) for y in range(5) for x in range(7))
        self.assertTrue(math.isclose(measured['measurements']['whole_image_area_m2'],direct,rel_tol=1e-9))

    def test_explicit_high_bit_depth_multiband_window_rendering(self):
        import numpy as np
        import rasterio
        import tempfile
        from pathlib import Path
        from affine import Affine
        from geomasklab.raster_input import render_raster
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'four-band.tif'
            values=np.stack([np.full((5,7),v,dtype='uint16') for v in (0,500,1000,1200)])
            transform=Affine(.5,0,500000,0,-.5,3950000)
            with rasterio.open(path,'w',driver='GTiff',width=7,height=5,count=4,dtype='uint16',crs='EPSG:32654',transform=transform) as output:
                output.write(values)
            with self.assertRaisesRegex(ValueError,'explicit'):render_raster(path,bands=[1,2,3])
            image,raster,metadata=render_raster(path,bands=[3,2,1],window=[1,1,3,2],value_range=[0,1000])
            with Image.open(io.BytesIO(image)) as rendered:
                self.assertEqual(rendered.size,(3,2));self.assertEqual(rendered.getpixel((0,0)),(255,128,0))
            self.assertEqual(metadata['transform'],[.5,0,500000.5,0,-.5,3949999.5])
            self.assertFalse(metadata['resampling_performed'])
            with self.assertRaisesRegex(ValueError,'inside'):render_raster(path,bands=[1,2,3],window=[0,0,8,5],value_range=[0,1000])
            with self.assertRaisesRegex(ValueError,'band index'):render_raster(path,bands=[1,2,5],value_range=[0,1000])


if __name__=='__main__':unittest.main()
