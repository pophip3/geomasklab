import unittest
from PIL import Image
from model_services.landcover_backend import landcover_target,TARGET_CLASSES
from model_services.sam_service import SAMService
from workbench.server import image_b64
from workbench.v07_contract import target_intent

class LandcoverFixture:
    metadata={'model_name':'fixture-landcover'}
    def __init__(self):self.calls=[]
    def predict(self,image,target,quality):
        self.calls.append((target,quality))
        return Image.new('L',image.size,255),{'class_ids':list(TARGET_CLASSES[target])}
class Legacy:
    metadata={}
    def predict_mask(self,*args):raise AssertionError('Explicit land-cover task called legacy model')
class LandcoverTests(unittest.TestCase):
    def test_trees_and_vegetation_have_distinct_semantics(self):
        self.assertEqual(target_intent('Extract all vegetation'),'vegetation')
        self.assertEqual(target_intent('\u63d0\u53d6\u6811\u6728'),'tree')
        self.assertEqual(TARGET_CLASSES['tree'],(5,))
        self.assertEqual(TARGET_CLASSES['vegetation'],(2,5,7))
        self.assertIsNone(landcover_target(None,'buildings near roads'))
    def test_exact_target_routes_and_original_grid(self):
        fixture=LandcoverFixture();service=SAMService(Legacy(),landcover_backends={'building':fixture,'road':fixture,'vegetation':fixture})
        try:
            for target in ('building','road','tree','vegetation'):
                for quality in ('fast','accurate'):
                    result=service.predict({'task':'semantic_seg','classes':[target],'quality_mode':quality,'image':image_b64(Image.new('RGB',(17,11)))})
                    self.assertEqual(result['output_size'],[17,11]);self.assertEqual(result['quality']['foreground_pixels'],187)
                    self.assertEqual(result['mode_parameters']['class_ids'],list(TARGET_CLASSES[target]))
                    self.assertIn(target,result['masks'])
            self.assertEqual(len(fixture.calls),8)
        finally:service.close()
