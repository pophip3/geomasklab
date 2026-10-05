"""Independent polygon-domain oracles, source identity and detached-key trust."""
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
from geomasklab.zonal import features,rasterize,measure_zones,zonal_packet,verify_zonal_packet
from geomasklab.signing import generate_keys,sign_payload,verify_signature


def png(image):
    out=io.BytesIO();image.save(out,'PNG');return out.getvalue()


def square(x1,y1,x2,y2):return [[x1,y1],[x2,y1],[x2,y2],[x1,y2],[x1,y1]]


class Zonal(unittest.TestCase):
    def setUp(self):
        self.bundle=create_evidence(png(Image.new('RGB',(10,8),(40,120,40))),png(Image.new('L',(10,8),255)),
            target='tree',source='Synthetic test mask',aligned=True)

    def test_pixel_center_boundaries_and_hole(self):
        document={'type':'Polygon','coordinates':[square(0,0,8,6),square(2,2,4,4)]}
        record,masks=measure_zones(self.bundle,json.dumps(document).encode())
        row=record['zones'][0];self.assertEqual(row['foreground_pixels'],44)
        self.assertEqual(row['selected_region_pixels'],44);self.assertEqual(row['whole_image_pixels'],80)
        geometry=features({'type':'Polygon','coordinates':[square(.5,.5,3.5,2.5)]})[0][1]
        domain=rasterize(geometry,(10,8));self.assertEqual(domain.histogram()[255],6)
        self.assertEqual(domain.getpixel((0,0)),255);self.assertEqual(domain.getpixel((3,0)),0)

    def test_multipolygon_overlap_is_union_not_parity(self):
        geometry={'type':'MultiPolygon','coordinates':[[square(0,0,6,4)],[square(4,0,8,4)]]}
        record,_=measure_zones(self.bundle,json.dumps(geometry).encode())
        self.assertEqual(record['zones'][0]['foreground_pixels'],32)

    def test_source_scope_intersection_and_empty_zone(self):
        child=recalculate_evidence(self.bundle,scope='right')
        document={'type':'FeatureCollection','features':[
            {'type':'Feature','id':'crossing','geometry':{'type':'Polygon','coordinates':[square(3,0,7,4)]}},
            {'type':'Feature','id':'outside','geometry':{'type':'Polygon','coordinates':[square(-8,-8,-1,-1)]}}]}
        record,_=measure_zones(child,json.dumps(document).encode())
        self.assertEqual(record['zones'][0]['foreground_pixels'],8)
        self.assertIsNone(record['zones'][1]['coverage_of_region'])
        self.assertEqual(record['zones'][1]['coverage_of_image'],0)

    def test_invalid_geometry_and_duplicate_ids_fail(self):
        invalid=[{'type':'Polygon','coordinates':[[[0,0],[4,4],[0,4],[4,0],[0,0]]]},
                 {'type':'Polygon','coordinates':[[[0,0],[4,0],[2,0],[4,4],[0,4],[0,0]]]},
                 {'type':'Polygon','coordinates':[square(0,0,4,4),square(3,3,5,5)]},
                 {'type':'Polygon','coordinates':[square(0,0,4,4),square(1,1,3,3),square(2,2,3.5,3.5)]},
                 {'type':'Polygon','coordinates':[[[0,0],[1,0],[1,float('nan')],[0,0]]]},
                 {'type':'Polygon','coordinates':[square(0,0,4,4)],'crs':{}},
                 {'type':'Point','coordinates':[0,0]}]
        for geometry in invalid:
            with self.subTest(geometry=geometry),self.assertRaises(ValueError):features(geometry)
        feature={'type':'Feature','id':'same','geometry':{'type':'Polygon','coordinates':[square(0,0,4,4)]}}
        with self.assertRaisesRegex(ValueError,'unique'):features({'type':'FeatureCollection','features':[feature,feature]})
        with self.assertRaisesRegex(ValueError,'matching source'):measure_zones(self.bundle,json.dumps(feature).encode(),coordinates='wgs84')

    def test_packet_replays_and_rehashed_measurement_or_domain_changes_fail(self):
        geometry=json.dumps({'type':'Polygon','coordinates':[square(0,0,4,4)]}).encode()
        packet=zonal_packet(self.bundle,geometry);self.assertTrue(verify_zonal_packet(packet)['verified'])
        with zipfile.ZipFile(io.BytesIO(packet)) as archive:original={n:archive.read(n) for n in archive.namelist()}
        for change in ('count','domain','extra'):
            files=dict(original)
            if change=='count':
                record=json.loads(files['zonal.json']);record['zones'][0]['foreground_pixels']+=1
                files['zonal.json']=json.dumps(record).encode()
            elif change=='domain':files['zone-01-domain.png']=png(Image.new('L',(10,8)))
            else:files['extra.txt']=b'extra'
            manifest=json.loads(files['manifest.json'])
            manifest['files']={n:{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()} for n,raw in files.items() if n!='manifest.json'}
            files['manifest.json']=json.dumps(manifest).encode();out=io.BytesIO()
            with zipfile.ZipFile(out,'w') as archive:
                for n,raw in files.items():archive.writestr(n,raw)
            with self.subTest(change=change),self.assertRaises(ValueError):verify_zonal_packet(out.getvalue())

    @unittest.skipUnless(importlib.util.find_spec('rasterio'),'Optional geo extra not installed')
    def test_independent_rasterio_domains_agree_without_boundary_ties(self):
        import rasterio.features
        from affine import Affine
        geometries=[{'type':'Polygon','coordinates':[[[.13,.17],[8.12,.17],[7.21,6.31],[.13,5.12],[.13,.17]]]},
                    {'type':'Polygon','coordinates':[square(.13,.17,8.12,6.31),square(2.1,2.2,4.1,4.2)]},
                    {'type':'MultiPolygon','coordinates':[[square(.1,.1,6.1,4.1)],[square(4.1,.1,8.1,4.1)]]}]
        for geometry in geometries:
            own=rasterize(features(geometry)[0][1],(10,8))
            reference=rasterio.features.rasterize([(geometry,255)],out_shape=(8,10),transform=Affine.identity(),all_touched=False,dtype='uint8')
            self.assertEqual(own.tobytes(),reference.tobytes())


@unittest.skipUnless(importlib.util.find_spec('cryptography'),'Optional signing extra not installed')
class Signing(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('jsonschema'),'Optional schema extra not installed')
    def test_new_schema_resources_validate_generated_records(self):
        from importlib.resources import files
        import jsonschema
        private,public=generate_keys()
        signed=sign_payload(b'artifact',private)
        bundle=create_evidence(png(Image.new('RGB',(2,2))),png(Image.new('L',(2,2),255)),target='solar_panel',source='Synthetic test',aligned=True)
        record,_=measure_zones(bundle,json.dumps({'type':'Polygon','coordinates':[square(0,0,2,2)]}).encode())
        for kind,document in (('signature',signed),('zonal',record)):
            schema=json.loads(files('geomasklab').joinpath('schemas',kind+'-1.0.schema.json').read_text(encoding='utf-8'))
            jsonschema.Draft202012Validator.check_schema(schema)
            jsonschema.Draft202012Validator(schema).validate(document)

    def test_trusted_key_rejects_self_consistent_replacement_and_attacker_key(self):
        private,public=generate_keys();other_private,other_public=generate_keys()
        payload=b'original artifact';signed=sign_payload(payload,private)
        self.assertTrue(verify_signature(payload,signed,public)['verified'])
        with self.assertRaisesRegex(ValueError,'identity'):verify_signature(b'replaced artifact',signed,public)
        replacement=sign_payload(b'replaced artifact',other_private)
        with self.assertRaisesRegex(ValueError,'trusted public key'):verify_signature(b'replaced artifact',replacement,public)
        self.assertTrue(verify_signature(b'replaced artifact',replacement,other_public)['verified'])

    def test_signature_fields_are_cryptographically_bound(self):
        private,public=generate_keys();signed=sign_payload(b'artifact',private)
        forged=dict(signed);forged['software_version']='changed'
        with self.assertRaisesRegex(ValueError,'verification failed'):verify_signature(b'artifact',forged,public)
        forged=dict(signed);forged['signature_base64']='not base64'
        with self.assertRaises(ValueError):verify_signature(b'artifact',forged,public)
        with self.assertRaises(ValueError):verify_signature(b'artifact',signed,b'invalid public PEM')


if __name__=='__main__':unittest.main()
