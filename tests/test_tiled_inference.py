"""Arithmetic fixtures only. Actual model validation is performed separately."""
import unittest
from PIL import Image
from model_services.tiled_inference import predict_tiled


class PixelBackend:
    def __init__(self):self.calls=[]
    def predict_mask(self, image, prompt):
        self.calls.append((image.size, prompt))
        return image.getchannel('R').point(lambda value: 255 if value >= 128 else 0)


class TiledInferenceTests(unittest.TestCase):
    def test_non_divisible_image_cores_cover_every_pixel_exactly_once(self):
        image=Image.new('RGB',(1031,519));red=Image.new('L',image.size)
        red.putdata([255 if (x*17+y*13)%23<11 else 0 for y in range(image.height) for x in range(image.width)])
        image.putalpha(255);image=image.convert('RGB');image.paste(Image.merge('RGB',(red,red,red)))
        backend=PixelBackend();result,metadata=predict_tiled(backend,image,'controlled fixture')
        self.assertEqual(result.tobytes(),red.tobytes());self.assertEqual(metadata['tile_count'],6)
        coverage=bytearray(image.width*image.height)
        for window in metadata['tile_windows']:
            x0,y0,x1,y1=window['core_xyxy']
            for y in range(y0,y1):
                for x in range(x0,x1):coverage[y*image.width+x]+=1
            rx0,ry0,rx1,ry1=window['read_xyxy'];self.assertTrue(0<=rx0<x1<=rx1<=image.width);self.assertTrue(0<=ry0<y1<=ry1<=image.height)
        self.assertEqual(set(coverage),{1})

    def test_single_tile_matches_original_backend(self):
        image=Image.new('RGB',(311,197),(200,0,0));backend=PixelBackend();result,metadata=predict_tiled(backend,image,'fixture')
        self.assertEqual(result.tobytes(),PixelBackend().predict_mask(image,'fixture').tobytes());self.assertEqual(metadata['tile_count'],1)

    def test_invalid_later_tile_never_returns_a_partial_mask(self):
        class Broken(PixelBackend):
            def predict_mask(self,image,prompt):
                if self.calls:return Image.new('L',image.size,128)
                return super().predict_mask(image,prompt)
        with self.assertRaisesRegex(ValueError,'No partial mask'):
            predict_tiled(Broken(),Image.new('RGB',(1024,512)),'fixture')

    def test_tile_budget_rejected_before_any_inference(self):
        backend=PixelBackend()
        with self.assertRaisesRegex(ValueError,'256 tiles'):
            predict_tiled(backend,Image.new('RGB',(512*257,1)),'fixture')
        self.assertEqual(backend.calls,[])
