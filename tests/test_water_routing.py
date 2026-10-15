"""Model routing and cache regression tests; model quality is tested separately."""
import tempfile
import os
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from model_services.sam_service import SAMService
from model_services.water_backend import is_water_request, window_starts
from workbench import server


class WaterFixture:
    metadata={'model_name':'TEST-WATER-ONLY','checkpoint_sha256':'test-water-v1'}
    def __init__(self):self.calls=[]
    def predict(self,image,quality):
        self.calls.append((image.size,quality))
        return Image.new('L',image.size,0),{'tile_count':1,'resolved_mode':quality}


class LegacyFixture:
    metadata={'model_name':'TEST-LEGACY-ONLY'}
    def predict_mask(self,image,prompt):
        raise AssertionError('Water must never call the old referring model')


class WaterRoutingTests(unittest.TestCase):
    def test_both_api_routes_and_all_quality_modes_use_the_water_model(self):
        water=WaterFixture();service=SAMService(LegacyFixture(),water_backend=water)
        raw=server.image_b64(Image.new('RGB',(13,7)))
        for quality in ('fast','auto','accurate'):
            for fields in ({'task':'semantic_seg','classes':['water']},
                           {'task':'referring_seg','text':'water bodies'}):
                result=service.predict({**fields,'image':raw,'quality_mode':quality})
                self.assertEqual(result['model']['model_name'],'TEST-WATER-ONLY')
                self.assertEqual(result['quality']['foreground_pixels'],0)
                self.assertEqual(result['quality_mode'],'accurate' if quality=='accurate' else 'fast')
                self.assertEqual(result['warnings'],[])
                self.assertEqual(result['output_size'],[13,7])
        self.assertEqual(len(water.calls),6)

    def test_water_words_in_a_ship_prompt_do_not_switch_the_target(self):
        self.assertFalse(is_water_request(None,'the ship on the water'))
        self.assertTrue(is_water_request(None,'all water bodies in the image'))
        self.assertTrue(is_water_request('water','ignored'))

    def test_overlap_tiles_cover_odd_and_small_images_without_gaps(self):
        for length in (1,311,512,513,1024,1149):
            coverage=[0]*length
            for start in window_starts(length):
                for pixel in range(start,min(length,start+512)):coverage[pixel]+=1
            self.assertGreater(min(coverage),0)

    def test_boundary_refinement_cannot_create_water_from_an_empty_prediction(self):
        try:
            import numpy as np
            import cv2
        except ImportError:
            self.skipTest('Model-runtime numeric dependencies are optional')
        from model_services.water_refinement import WaterBoundaryRefiner
        refiner=WaterBoundaryRefiner.__new__(WaterBoundaryRefiner)
        mask=np.zeros((7,13),dtype=bool)
        self.assertIs(refiner.refine(Image.new('RGB',(13,7)),mask),mask)

    def test_boundary_refiner_preserves_a_thin_nonwater_walkway(self):
        try:
            import numpy as np
            import cv2
        except ImportError:
            self.skipTest('Model-runtime numeric dependencies are optional')
        from model_services.water_refinement import merge_boundaries
        coarse=np.ones((41,41),dtype=bool)
        coarse[:25,18:23]=False
        # Even an overfilled edge-model mask must keep the walkway interior.
        result=merge_boundaries(coarse,np.ones_like(coarse))
        self.assertFalse(result[:25,18:23].any())
        self.assertTrue(result[30:,30:].all())

    def test_workbench_water_skips_agent_and_does_not_reuse_the_old_mask(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(server,'DATA',Path(tmp)), \
             patch.dict(os.environ,{'GEO_REMOTESAM_URL':'http://test.invalid/predict',
                                    'GEO_REMOTESAM_REVISION':'old-remote-model','GEO_WATER_MODEL_REVISION':''}), \
             patch('workbench.server.AgentTurn',side_effect=AssertionError('No planner needed')), \
             patch.object(server,'post_json') as predict:
            session_id=server.new_session(uploaded=server.image_b64(Image.new('RGB',(13,7))))['id']
            session=server.SESSIONS[session_id]
            mask=server.image_b64(Image.new('L',(13,7),0))
            predict.return_value={'status':'success','mask':mask,'masks':{'water':mask},
                                  'quality_mode':'fast','model':WaterFixture.metadata}
            result=server.run_task(session,{'mode':'live','query':'Extract water in the whole image.'})
            self.assertEqual(result['status'],'completed',result.get('message'))
            self.assertEqual(result['metrics']['pixel_area'],0)
            self.assertEqual(result['message'],'No water detected. Water coverage: 0.00%.')
            self.assertEqual(predict.call_args.args[1]['classes'],['water'])
            self.assertIsNone(server.mask_cache_key(session,'live','water',{'task':'semantic_seg','classes':['water']}))
            followup=server.run_task(session,{'mode':'live','query':'Extract water in the left half.',
                                              'parent_run_id':result['id']})
            self.assertEqual(followup['status'],'completed')
            self.assertEqual(predict.call_count,2)
            server.SESSIONS.pop(session_id,None)


if __name__=='__main__':unittest.main()
