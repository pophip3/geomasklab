"""Independent pixel arithmetic and replay boundaries for declared validity."""
import base64
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import _source_package
_source_package.use_local_core()
from PIL import Image
from geomasklab.api import create_evidence, recalculate_evidence
from geomasklab.cli import main
from geomasklab.comparison import compare_bundles
from geomasklab.domain import png
from geomasklab.evidence import bundle_contents, load_verified_bundle, build_bundle
from geomasklab.reference import evaluate_reference, evaluation_packet, verify_reference_packet
from geomasklab.report import build_report
from geomasklab.schema import validate_metadata
from geomasklab.zonal import zonal_packet, verify_zonal_packet
from workbench import server


class ValidityDomains(unittest.TestCase):
    def setUp(self):
        self.image=png(Image.new('RGB',(8,6),(0,0,0)))
        mask=Image.new('L',(8,6));mask.paste(255,(2,1,6,4));self.mask=png(mask)
        valid=Image.new('L',(8,6));valid.paste(255,(0,0,4,6));self.valid=png(valid)
        self.roi={'xyxy':[1,1,7,5],'source':'imported','image_size':[8,6]}
    def create(self,**kwargs):
        return create_evidence(self.image,self.mask,target='building',source='Hand-counted fixture',aligned=True,**kwargs)
    def scoped(self):
        return self.create(valid_mask=self.valid,valid_source='Explicit left-half fixture',roi=self.roi)
    def read(self,payload):
        facts,files=load_verified_bundle(payload)
        return facts,files,json.loads(files['result.json'])
    def test_default_retains_legacy_format_and_geometric_ratios(self):
        facts,files,r=self.read(self.create(roi=self.roi))
        self.assertEqual(facts['schema'],'geoscope-evidence/1.0')
        self.assertNotIn('valid_mask.png',files)
        self.assertNotIn('analysis_config',r)
        self.assertEqual(r['metrics']['pixel_area'],12)
        self.assertEqual(r['metrics']['area_ratio'],12/48)
        self.assertEqual(r['metrics']['scope_area_ratio'],12/24)
    def test_hand_counted_geometric_valid_and_exclusion_denominators(self):
        facts,files,r=self.read(self.scoped());m=r['metrics'];v=m['validity_measurements']
        self.assertEqual(facts['schema'],'geomasklab-evidence/2.0')
        self.assertEqual((m['pixel_area'],m['total_pixels'],m['scope_area_pixels']),(6,48,24))
        self.assertEqual((m['area_ratio'],m['scope_area_ratio']),(6/48,6/24))
        self.assertEqual((v['valid_image_pixels'],v['valid_region_pixels'],v['excluded_region_pixels']),(24,12,12))
        self.assertEqual((v['coverage_of_valid_image'],v['coverage_of_valid_region']),(6/24,6/12))
        self.assertEqual(v['excluded_foreground_pixels'],6)
        self.assertEqual(m['distribution']['roi_inside_pixels'],12)
        self.assertEqual(m['distribution']['roi_outside_pixels'],0)
        self.assertEqual(files['source_mask.png'],self.mask)
        self.assertEqual(files['source_valid_mask.png'],self.valid)
        self.assertEqual(r['analysis_config']['roi'],self.roi)
        self.assertEqual(m['candidate_stats']['total_area_pixels'],6)
    def test_black_image_does_not_infer_invalid_pixels(self):
        facts,_,_=self.read(self.create());self.assertEqual(facts['pixel_area'],12)
    def test_empty_validity_has_null_ratios_and_zero_components(self):
        facts,_,r=self.read(self.create(valid_mask=png(Image.new('L',(8,6))),valid_source='Empty domain fixture'))
        v=r['metrics']['validity_measurements']
        self.assertEqual(facts['pixel_area'],0)
        self.assertIsNone(v['coverage_of_valid_region']);self.assertIsNone(v['coverage_of_valid_image'])
        self.assertEqual(r['metrics']['candidate_stats']['candidate_count'],0)
    def test_complement_excludes_invalid_pixels(self):
        _,files,r=self.read(self.create(valid_mask=self.valid,valid_source='Left-half validity',invert=True))
        self.assertEqual(r['metrics']['pixel_area'],18)
        with Image.open(io.BytesIO(files['mask.png'])) as im:
            self.assertEqual(im.crop((4,0,8,6)).histogram()[255],0)
        self.assertEqual(files['source_mask.png'],self.mask)
    def test_recalculation_preserves_validity_and_resets_review(self):
        parent=self.scoped();child=recalculate_evidence(parent,scope='right')
        _,a,r=self.read(child);_,b,_=self.read(parent)
        self.assertEqual(a['source_valid_mask.png'],b['source_valid_mask.png'])
        self.assertEqual(a['full_mask.png'],b['full_mask.png'])
        self.assertEqual(r['analysis_config']['scope'],'right')
        self.assertEqual(r['metrics']['validity_measurements']['valid_region_pixels'],0)
        self.assertIsNone(r['metrics']['validity_measurements']['coverage_of_valid_region'])
        self.assertEqual(r['semantic_review']['state'],'pending')
        self.assertFalse(r['inference_performed'])
    def test_explicit_reset_and_replace_make_new_versions(self):
        parent=self.scoped()
        _,files,r=self.read(recalculate_evidence(parent,valid_mask=None))
        self.assertNotIn('source_valid_mask.png',files)
        self.assertEqual(r['metrics']['pixel_area'],12)
        self.assertEqual(r['analysis_config']['validity']['policy'],'all_pixels_declared_valid')
        other=Image.new('L',(8,6));other.paste(255,(4,0,8,6))
        _,_,r=self.read(recalculate_evidence(parent,valid_mask=png(other),valid_source='Replacement right-half fixture'))
        self.assertEqual(r['metrics']['pixel_area'],6)
        self.assertEqual(r['version'],2)
        self.assertEqual(self.read(parent)[2]['metrics']['pixel_area'],6)
    def test_validity_source_dimensions_and_binary_values_are_required(self):
        for raw,source in [(self.valid,None),(png(Image.new('L',(2,2),255)),'Wrong size'),(png(Image.new('L',(8,6),123)),'Nonbinary')]:
            with self.subTest(source=source),self.assertRaises(ValueError):self.create(valid_mask=raw,valid_source=source)
        with self.assertRaises(ValueError):self.create(valid_source='Source without mask')
        with self.assertRaises(ValueError):recalculate_evidence(self.scoped(),valid_source='Source without replacement')
    def test_zero_one_validity_normalization_preserves_upload_bytes(self):
        raw=png(Image.new('L',(8,6),1));_,files,r=self.read(self.create(valid_mask=raw,valid_source='0/1 included fixture'))
        self.assertEqual(files['source_valid_mask.png'],raw)
        self.assertEqual(r['metrics']['validity_measurements']['valid_image_pixels'],48)
    def test_rehashed_invalid_numbers_configuration_and_normalization_are_rejected(self):
        _,files,_=self.read(self.scoped())
        for field in ('valid_region_pixels','coverage_of_valid_region','excluded_foreground_pixels'):
            altered=deepcopy(files);r=json.loads(altered['result.json'])
            r['metrics']['validity_measurements'][field]+=1
            altered['result.json']=json.dumps(r).encode();altered['statistics.json']=json.dumps(r['metrics']).encode()
            with self.subTest(field=field),self.assertRaises(ValueError):load_verified_bundle(bundle_contents(altered))
        altered=deepcopy(files);config=json.loads(altered['analysis.json']);config['image_size']=[9,6]
        r=json.loads(altered['result.json']);r['analysis_config']=config
        altered['analysis.json']=json.dumps(config).encode();altered['result.json']=json.dumps(r).encode()
        with self.assertRaises(ValueError):load_verified_bundle(bundle_contents(altered))
        altered=deepcopy(files);altered['valid_mask.png']=png(Image.new('L',(8,6),255))
        with self.assertRaisesRegex(ValueError,'normalization'):load_verified_bundle(bundle_contents(altered))
    def test_manifest_summary_missing_files_and_schema_downgrade_are_rejected(self):
        payload=self.scoped()
        with zipfile.ZipFile(io.BytesIO(payload)) as z:files={n:z.read(n) for n in z.namelist()}
        manifest=json.loads(files['manifest.json']);self.assertEqual(manifest['valid_pixels']['valid_region_pixels'],12)
        for transform in ('summary','downgrade','missing'):
            changed=deepcopy(files);m=deepcopy(manifest)
            if transform=='summary':m['valid_pixels']['valid_region_pixels']=True
            if transform=='downgrade':m['schema']='geoscope-evidence/1.0'
            if transform=='missing':changed.pop('source_valid_mask.png');m['checksums'].pop('source_valid_mask.png')
            changed['manifest.json']=json.dumps(m).encode();output=io.BytesIO()
            with zipfile.ZipFile(output,'w') as z:
                for n,raw in changed.items():z.writestr(n,raw)
            with self.subTest(transform=transform),self.assertRaises(ValueError):load_verified_bundle(output.getvalue())
    def test_reference_uses_exact_valid_region_and_packet_replays(self):
        bundle=self.scoped()
        record,diff=evaluate_reference(bundle,self.mask,source='Hand-counted reference',target='building',independent=False,created_at='2026-10-05')
        self.assertEqual(record['counts'],{'tp':6,'fp':0,'fn':0,'tn':6})
        self.assertEqual(record['evaluated_pixels'],12)
        self.assertEqual(sum(record['counts'].values()),12)
        self.assertTrue(verify_reference_packet(evaluation_packet(record,diff,bundle,self.mask))['verified'])
    def test_empty_reference_domain_returns_null_for_all_metrics(self):
        bundle=self.create(valid_mask=png(Image.new('L',(8,6))),valid_source='Empty fixture')
        r,_=evaluate_reference(bundle,self.mask,source='Reference fixture',target='building',independent=False,created_at='2026-10-05')
        self.assertEqual(sum(r['counts'].values()),0)
        self.assertTrue(all(v is None for v in r['metrics'].values()))
    def test_comparison_uses_common_validity_and_explains_exclusions(self):
        a=self.scoped();b=self.create()
        r=compare_bundles(a,b)
        self.assertEqual(r['common_scope_pixels'],12)
        self.assertEqual(r['changed_pixels'],0)
        self.assertEqual(r['mask_agreement_iou'],1)
        self.assertFalse(r['valid_masks_equal']);self.assertTrue(r['full_prediction_pixels_equal'])
        self.assertEqual(r['b_domain_excluded_from_comparison_pixels'],36)
    def test_disjoint_validity_blocks_pixel_diff(self):
        other=Image.new('L',(8,6));other.paste(255,(4,0,8,6))
        r=compare_bundles(self.scoped(),self.create(valid_mask=png(other),valid_source='Right-half fixture'))
        self.assertEqual(r['status'],'No_Common_Valid_Domain')
        self.assertFalse(r['pixel_diff_available']);self.assertIsNone(r['difference_png_base64'])
        self.assertIsNone(r['mask_agreement_iou']);self.assertIsNone(r['mask_agreement_dice'])
    def test_polygon_domain_uses_validity_and_replays(self):
        geometry=json.dumps({'type':'Polygon','coordinates':[[[1,1],[7,1],[7,5],[1,5],[1,1]]]}).encode()
        r=verify_zonal_packet(zonal_packet(self.scoped(),geometry))['zones'][0]
        self.assertEqual((r['foreground_pixels'],r['geometric_region_pixels'],r['valid_region_pixels']),(6,24,12))
        self.assertEqual(r['coverage_of_region'],.5)
    def test_seeded_masks_match_independent_python_set_arithmetic(self):
        rng=random.Random(731)
        for invert in (False,True):
            for size in ((7,5),(8,6),(1,5)):
                w,h=size;m=[rng.choice((0,255)) for _ in range(w*h)];v=[rng.choice((0,255)) for _ in m]
                mask=Image.new('L',size);mask.putdata(m);valid=Image.new('L',size);valid.putdata(v)
                payload=create_evidence(png(Image.new('RGB',size)),png(mask),target='building',source='Randomized deterministic fixture',aligned=True,
                    scope='right',invert=invert,valid_mask=png(valid),valid_source='Seeded inclusion fixture')
                _,_,r=self.read(payload);domain={i for i in range(w*h) if i%w>=w//2 and v[i]}
                foreground={i for i in domain if bool(m[i])!=invert}
                measured=r['metrics']['validity_measurements']
                self.assertEqual(measured['foreground_pixels'],len(foreground))
                self.assertEqual(measured['valid_region_pixels'],len(domain))
    @unittest.skipUnless(importlib.util.find_spec('jsonschema'),'Optional schema extra not installed')
    def test_versioned_metadata_schemas(self):
        for payload in (self.create(),self.scoped(),recalculate_evidence(self.scoped(),valid_mask=None)):
            _,files,_=self.read(payload)
            with zipfile.ZipFile(io.BytesIO(payload)) as z:manifest=json.loads(z.read('manifest.json'))
            validate_metadata(files,manifest)
    def test_report_and_cli_use_both_explicit_denominators(self):
        self.assertIn('Valid selected-region denominator',build_report(self.scoped()))
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            for name,raw in [('image.png',self.image),('mask.png',self.mask),('valid.png',self.valid)]: (folder/name).write_bytes(raw)
            with patch('sys.stdout',new=io.StringIO()):
                self.assertEqual(main(['create','--image',str(folder/'image.png'),'--mask',str(folder/'mask.png'),'--target','building','--source','CLI fixture',
                    '--valid-mask',str(folder/'valid.png'),'--valid-source','Left-half fixture','--aligned','--output',str(folder/'bundle.zip')]),0)
                self.assertEqual(main(['recalc',str(folder/'bundle.zip'),'--all-valid','--output',str(folder/'reset.zip')]),0)
            self.assertEqual(self.read((folder/'reset.zip').read_bytes())[2]['metrics']['pixel_area'],12)
    @unittest.skipUnless(importlib.util.find_spec('rasterio') and importlib.util.find_spec('pyproj'),'Optional geo extra not installed')
    def test_geospatial_nominal_valid_area_internal_mask_and_schema(self):
        import numpy as np
        import rasterio
        from rasterio.transform import Affine
        from geomasklab.geospatial import geospatial_packet,verify_geospatial_packet
        with rasterio.io.MemoryFile() as memory:
            with memory.open(driver='GTiff',width=8,height=6,count=3,dtype='uint8',crs='EPSG:32613',transform=Affine(2,0,500000,0,-3,4400000)) as ds:
                ds.write(np.zeros((3,6,8),dtype=np.uint8))
            raster=memory.read()
        packet=geospatial_packet(self.scoped(),raster)
        measured=verify_geospatial_packet(packet)['measurements']
        self.assertEqual(measured['foreground_area_m2'],36)
        self.assertEqual(measured['valid_image_area_m2'],144)
        self.assertEqual(measured['valid_region_area_m2'],72)
        self.assertEqual(measured['selected_region_area_m2'],144)
        self.assertEqual(measured['coverage_of_valid_region_area'],.5)
        with zipfile.ZipFile(io.BytesIO(packet)) as z:
            with rasterio.io.MemoryFile(z.read('mask.tif')) as memory,memory.open() as ds:
                self.assertEqual(ds.dataset_mask().tobytes(),Image.open(io.BytesIO(self.valid)).tobytes())
            if importlib.util.find_spec('jsonschema'):
                from jsonschema import Draft202012Validator
                from importlib.resources import files
                schema=json.loads(files('geomasklab').joinpath('schemas/geospatial-1.0.schema.json').read_text())
                Draft202012Validator(schema).validate(json.loads(z.read('geospatial.json')))
    @unittest.skipUnless(importlib.util.find_spec('rasterio') and importlib.util.find_spec('pyproj'),'Optional geo extra not installed')
    def test_geodesic_valid_denominators_follow_row_area(self):
        import numpy as np
        import rasterio
        from rasterio.transform import Affine
        from pyproj import Geod
        from geomasklab.geospatial import geospatial_packet,verify_geospatial_packet
        with rasterio.io.MemoryFile() as memory:
            with memory.open(driver='GTiff',width=8,height=6,count=3,dtype='uint8',crs='EPSG:4326',transform=Affine(.01,0,-105,0,-.01,40)) as ds:
                ds.write(np.zeros((3,6,8),dtype=np.uint8))
            raster=memory.read()
        m=verify_geospatial_packet(geospatial_packet(self.scoped(),raster,method='geodesic'))['measurements']
        geod=Geod(ellps='WGS84');expected=[]
        for y in range(1,5):
            for x in range(1,4):
                lon=[-105+.01*x,-105+.01*(x+1),-105+.01*(x+1),-105+.01*x]
                lat=[40-.01*y,40-.01*y,40-.01*(y+1),40-.01*(y+1)]
                expected.append(abs(geod.polygon_area_perimeter(lon,lat)[0]))
        self.assertAlmostEqual(m['valid_region_area_m2'],sum(expected),delta=sum(expected)*1e-9)
        self.assertEqual(m['valid_region_pixels'],12)


class ValidityWorkbench(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.data=patch.object(server,'DATA',Path(self.temp.name));self.data.start()
        self.sessions=patch.object(server,'SESSIONS',{});self.sessions.start()
        self.s=server.SESSIONS[server.new_session('urban')['id']]
    def tearDown(self):
        self.sessions.stop();self.data.stop();self.temp.cleanup()
    def bundle(self,r,s=None):
        s=s or self.s
        return build_bundle(server.DATA/s['id']/'original.png',server.DATA/s['id']/r['id'])
    def test_import_derive_restore_and_review_use_same_core(self):
        full=png(server.demo_mask('urban'));valid=Image.new('L',(800,600));valid.paste(255,(0,0,400,600))
        r=server.import_mask(self.s,{'mask':base64.b64encode(full).decode(),'target':'building','source':'Procedural source fixture','aligned':True,
            'valid_mask':base64.b64encode(png(valid)).decode(),'valid_source':'Left-half fixture'})
        self.assertEqual(r['metrics']['pixel_area'],38000)
        payload=self.bundle(r);_,files=load_verified_bundle(payload)
        restored=server.import_evidence({'bundle':base64.b64encode(payload).decode()});s=server.SESSIONS[restored['id']]
        self.assertEqual(load_verified_bundle(self.bundle(s['runs'][0],s))[1]['source_valid_mask.png'],files['source_valid_mask.png'])
        server.review_result(s,{'run_id':r['id'],'decision':'accepted','reviewer':'AUTOMATED FIXTURE','note':'Persistence test; not human review.'})
        derived=server.recalculate_region(s,{'run_id':r['id'],'scope':'right'})
        self.assertEqual(derived['metrics']['pixel_area'],0)
        self.assertEqual(derived['semantic_review']['state'],'pending')
        self.assertIsNone(derived['metrics']['validity_measurements']['coverage_of_valid_region'])
        reset=server.recalculate_region(s,{'run_id':derived['id'],'validity_action':'all_valid'})
        self.assertEqual(reset['metrics']['pixel_area'],75350)
        self.assertTrue(load_verified_bundle(self.bundle(reset,s))[0]['verified'])
    def test_model_task_complement_retains_saved_validity(self):
        original=server.run_task(self.s,{'query':'Segment buildings','mode':'demo'})
        valid=Image.new('L',(800,600));valid.paste(255,(0,0,400,600))
        r=server.recalculate_region(self.s,{'run_id':original['id'],'validity_action':'replace','valid_mask':base64.b64encode(png(valid)).decode(),'valid_source':'Left-half fixture'})
        inverse=server.run_task(self.s,{'query':'Segment non-buildings','mode':'demo','parent_run_id':r['id']})
        self.assertEqual(inverse['metrics']['pixel_area'],240000-38000)
        self.assertTrue(load_verified_bundle(self.bundle(inverse))[0]['verified'])
    def test_invalid_replacement_preserves_existing_result(self):
        r=server.run_task(self.s,{'query':'Segment buildings','mode':'demo'});before=self.bundle(r)
        with self.assertRaises(ValueError):server.recalculate_region(self.s,{'run_id':r['id'],'validity_action':'replace','valid_mask':base64.b64encode(png(Image.new('L',(2,2),255))).decode(),'valid_source':'Wrong grid'})
        self.assertEqual(len(self.s['runs']),1)
        self.assertEqual(load_verified_bundle(before)[1],load_verified_bundle(self.bundle(r))[1])
    def test_ledger_preserves_valid_denominators_and_failure_blanks(self):
        import csv
        from workbench.experiment_management import ledger_csv
        r=server.run_task(self.s,{'query':'Segment buildings','mode':'demo'})
        valid=Image.new('L',(800,600));valid.paste(255,(0,0,400,600))
        server.recalculate_region(self.s,{'run_id':r['id'],'validity_action':'replace','valid_mask':base64.b64encode(png(valid)).decode(),'valid_source':'Left-half fixture'})
        server.run_task(self.s,{'query':'Segment buildings','mode':'demo','simulate_failure':True})
        rows=list(csv.DictReader(io.StringIO(ledger_csv(self.s).lstrip('\ufeff'))))
        self.assertEqual(rows[1]['valid_region_pixels'],'240000')
        self.assertEqual(rows[1]['excluded_region_pixels'],'240000')
        self.assertEqual(float(rows[1]['coverage_of_valid_region']),38000/240000)
        self.assertEqual(rows[2]['valid_region_pixels'],'')
        self.assertEqual(rows[2]['coverage_of_valid_region'],'')


if __name__=='__main__':unittest.main()
