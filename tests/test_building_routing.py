"""Ensure generic imported building requests use the supervised model and revision."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from model_services.landcover_backend import landcover_target, TARGET_CLASSES
from model_services.sam_service import SAMService
from model_services.launcher import workbench_settings
from workbench import server


class BuildingFixture:
    metadata = {'model_name':'test-supervised-building','checkpoint_sha256':'building-v2'}
    def predict(self, image, target, quality):
        return Image.new('L', image.size, 255), {'class_ids':[8], 'resolved_mode':quality}


class Legacy:
    metadata = {}
    def predict_mask(self, *args):
        raise AssertionError('Whole-building extraction must not fall back to RemoteSAM')


class BuildingTests(unittest.TestCase):
    def test_whole_building_routes_cover_both_protocols_and_modes(self):
        service = SAMService(Legacy(), landcover_backends={'building':BuildingFixture()})
        try:
            for quality in ('auto','fast','accurate'):
                for fields in ({'task':'semantic_seg','classes':['building']},
                               {'task':'referring_seg','text':'all buildings'}):
                    result = service.predict({**fields,'quality_mode':quality,
                                              'image':server.image_b64(Image.new('RGB',(17,11)))})
                    self.assertEqual(result['model']['model_name'],'test-supervised-building')
                    self.assertEqual(result['quality']['foreground_pixels'],187)
                    self.assertEqual(result['mode_parameters']['class_ids'],[8])
                    self.assertEqual(result['output_size'],[17,11])
        finally:
            service.close()
        self.assertEqual(TARGET_CLASSES['building'],(8,))
        self.assertIsNone(landcover_target(None,'buildings near roads'))
        self.assertIsNone(landcover_target(None,'the building on the left'))

    def test_building_cache_requires_its_own_model_revision(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(server,'DATA',Path(tmp)), \
             patch.dict(os.environ, {'GEO_REMOTESAM_REVISION':'old-remotesam',
                                     'GEO_BUILDING_MODEL_REVISION':''}):
            session = server.new_session(uploaded=server.image_b64(Image.new('RGB',(17,11))))
            try:
                self.assertIsNone(server.mask_cache_key(session,'live','building'))
                os.environ['GEO_BUILDING_MODEL_REVISION']='building-v1'
                first = server.mask_cache_key(session,'live','building')
                os.environ['GEO_BUILDING_MODEL_REVISION']='building-v2'
                self.assertNotEqual(first,server.mask_cache_key(session,'live','building'))
            finally:
                server.SESSIONS.pop(session['id'],None)

    def test_portable_launcher_generates_verified_building_revision(self):
        config={'sam':{'port':6657}}
        metadata={'landcover_models':{'building':BuildingFixture.metadata}}
        settings=workbench_settings(config,'sam',{'services':{'sam':{'ready_declaration':metadata}}})
        self.assertIn('GEO_BUILDING_MODEL_REVISION=supervised-building:',settings)
        metadata['landcover_models']['building']={**BuildingFixture.metadata,'checkpoint_sha256':'building-v3'}
        self.assertNotEqual(settings,workbench_settings(config,'sam',{'services':{'sam':{'ready_declaration':metadata}}}))
