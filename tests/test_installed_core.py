"""Headless core, provider contracts and safe standalone report boundaries."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

import _source_package
_source_package.use_local_core()
from PIL import Image
from geomasklab.api import create_evidence,recalculate_evidence
from geomasklab.evidence import load_verified_bundle,bundle_contents
from geomasklab.providers import ExcessGreenProvider,CommandProvider
from geomasklab.report import build_report
from geomasklab.schema import validate_metadata


def png(image):
    out=io.BytesIO();image.save(out,'PNG');return out.getvalue()


class HeadlessCore(unittest.TestCase):
    def setUp(self):
        self.image=png(Image.new('RGB',(7,5),(40,180,40)))
        mask=Image.new('L',(7,5));mask.paste(255,(1,1,5,4))
        self.mask=png(mask)
        self.bundle=create_evidence(self.image,self.mask,target='tree',source='Explicit test mask',aligned=True)

    def test_recalculation_preserves_source_and_denominators(self):
        child=recalculate_evidence(self.bundle,scope='right')
        facts,files=load_verified_bundle(child)
        self.assertEqual(facts['pixel_area'],6)
        metrics=json.loads(files['statistics.json'])
        self.assertEqual(metrics['total_pixels'],35)
        self.assertEqual(metrics['scope_area_pixels'],20)
        self.assertAlmostEqual(metrics['area_ratio'],6/35)
        self.assertAlmostEqual(metrics['scope_area_ratio'],6/20)
        self.assertEqual(files['original.png'],self.image)
        self.assertEqual(files['source_mask.png'],self.mask)
        result=json.loads(files['result.json'])
        self.assertFalse(result['inference_performed'])

    def test_packaged_schemas_validate_new_and_derived_metadata(self):
        import zipfile
        for bundle in (self.bundle,recalculate_evidence(self.bundle,scope='bottom')):
            _,files=load_verified_bundle(bundle)
            with zipfile.ZipFile(io.BytesIO(bundle)) as z:manifest=json.loads(z.read('manifest.json'))
            validate_metadata(files,manifest)

    def test_report_escapes_source_text_and_requires_valid_evidence(self):
        raw=create_evidence(self.image,self.mask,target='tree',source='<script>alert(1)</script>',aligned=True)
        report=build_report(raw)
        self.assertIn('&lt;script&gt;',report)
        self.assertNotIn('<script>',report)
        self.assertIn('Whole-image denominator',report)
        self.assertIn('Selected-region denominator',report)
        _,files=load_verified_bundle(raw)
        metrics=json.loads(files['statistics.json']);metrics['pixel_area']+=1
        files['statistics.json']=json.dumps(metrics).encode()
        result=json.loads(files['result.json']);result['metrics']=metrics
        files['result.json']=json.dumps(result).encode()
        with self.assertRaises(ValueError):build_report(bundle_contents(files))

    def test_schema_catches_invalid_metadata_type(self):
        import zipfile
        _,files=load_verified_bundle(self.bundle)
        with zipfile.ZipFile(io.BytesIO(self.bundle)) as z:manifest=json.loads(z.read('manifest.json'))
        result=json.loads(files['result.json']);result['version']='one'
        files['result.json']=json.dumps(result).encode()
        with self.assertRaisesRegex(ValueError,'schema validation'):validate_metadata(files,manifest)

    def test_provider_identity_is_bound_and_retained_after_recalculation(self):
        product=ExcessGreenProvider().produce(self.image)
        bundle=create_evidence(self.image,product.mask,target='tree',source='Green-color candidate baseline',aligned=True,
                               provider_info=product.metadata)
        _,files=load_verified_bundle(recalculate_evidence(bundle,scope='right'))
        self.assertEqual(json.loads(files['result.json'])['external_mask']['provider'],product.metadata)
        with self.assertRaisesRegex(ValueError,'identity'):
            create_evidence(self.image,self.mask,target='tree',source='Mismatch',aligned=True,provider_info=product.metadata)


class Providers(unittest.TestCase):
    def setUp(self):
        image=Image.new('RGB',(7,5),(120,110,100));image.paste((40,180,40),(0,0,3,5))
        self.image=png(image)

    def test_color_baseline_is_reproducible_and_explicit(self):
        first=ExcessGreenProvider().produce(self.image)
        self.assertEqual(first,ExcessGreenProvider().produce(self.image))
        with Image.open(io.BytesIO(first.mask)) as mask:
            self.assertEqual(mask.tobytes().count(255),15)
        self.assertFalse(first.metadata['neural_model'])
        self.assertIn('accuracy has not been established',first.metadata['semantic_status'])

    def test_uniform_color_and_invalid_threshold(self):
        product=ExcessGreenProvider().produce(png(Image.new('RGB',(7,5),(120,120,120))))
        with Image.open(io.BytesIO(product.mask)) as mask:self.assertEqual(mask.getbbox(),None)
        for value in (float('nan'),float('inf'),True,511):
            with self.assertRaises(ValueError):ExcessGreenProvider(value).produce(self.image)

    def test_command_with_spaces_and_valid_binary_output(self):
        with tempfile.TemporaryDirectory(prefix='provider tool with spaces ') as root:
            path=Path(root)/'external tool.py'
            path.write_text('from PIL import Image\nimport sys\nImage.new("L",Image.open(sys.argv[1]).size,255).save(sys.argv[2])\n')
            product=CommandProvider([sys.executable,str(path),'{image}','{output}']).produce(self.image)
        with Image.open(io.BytesIO(product.mask)) as mask:self.assertEqual(mask.tobytes().count(255),35)
        self.assertFalse(product.metadata['shell'])
        self.assertNotIn('command',product.metadata)

    def test_noop_failure_timeout_and_wrong_grid_are_rejected(self):
        commands=[['pass','fresh binary PNG'],['raise SystemExit(2)','code 2'],
                  ['from PIL import Image; import sys; Image.new("L",(1,1),255).save(sys.argv[2])','dimensions']]
        for code,error in commands:
            with self.assertRaisesRegex(ValueError,error):
                CommandProvider([sys.executable,'-c',code,'{image}','{output}']).produce(self.image)
        with self.assertRaisesRegex(ValueError,'timed out'):
            CommandProvider([sys.executable,'-c','import time; time.sleep(5)','{image}','{output}'],.1).produce(self.image)


if __name__=='__main__':unittest.main()
