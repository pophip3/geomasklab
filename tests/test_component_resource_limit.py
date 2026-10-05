"""Fragmented inputs must fail before materializing an unbounded component list."""
import io
import unittest
from unittest.mock import patch
from PIL import Image
from _source_package import use_local_core
use_local_core()
from geomasklab.geometry import candidate_statistics
from geomasklab.api import create_evidence
from geomasklab.evidence import verify_bundle


def png(image):
    output=io.BytesIO();image.save(output,'PNG');return output.getvalue()


class ComponentResourceLimitTests(unittest.TestCase):
    def setUp(self):
        # Three isolated components under eight-connectivity, two pixels apart.
        self.mask=Image.new('L',(7,3))
        for point in ((0,1),(3,1),(6,1)):self.mask.putpixel(point,255)
        self.image=png(Image.new('RGB',self.mask.size,'white'))

    def test_limit_rejects_instead_of_truncating_even_filtered_components(self):
        with patch('geomasklab.geometry.MAX_COMPONENTS',2):
            with self.assertRaisesRegex(ValueError,'component limit'):
                candidate_statistics(self.mask,min_area_pixels=4)

    def test_create_and_replay_apply_the_same_admission_guard(self):
        source=create_evidence(self.image,png(self.mask),target='tree',source='Three isolated fixture pixels',aligned=True)
        self.assertEqual(verify_bundle(source)['pixel_area'],3)
        with patch('geomasklab.geometry.MAX_COMPONENTS',2):
            with self.assertRaisesRegex(ValueError,'component limit'):
                create_evidence(self.image,png(self.mask),target='tree',source='Fixture',aligned=True)
            with self.assertRaisesRegex(ValueError,'component limit'):
                verify_bundle(source)
