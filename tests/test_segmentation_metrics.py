import sys, unittest
from pathlib import Path
try:
    import numpy as np
except ImportError:
    np=None
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'evaluation'))
if np is not None:
    from segmentation_metrics import score

@unittest.skipIf(np is None,'Install evaluation/requirements-evaluation.txt for metric tests.')
class MetricsTests(unittest.TestCase):
    def test_known_confusion_and_ignored_pixel(self):
        p=np.array([[1,1],[0,1]]);g=np.array([[1,0],[1,0]]);v=np.array([[1,1],[1,0]])
        r=score(p,g,v)
        self.assertEqual((r['tp'],r['fp'],r['fn'],r['tn']),(1,1,1,0))
        self.assertAlmostEqual(r['iou'],1/3);self.assertEqual(r['dice'],.5)
    def test_empty_target_is_separate(self):
        z=np.zeros((2,2),bool);r=score(z,z,~z)
        self.assertIsNone(r['iou']);self.assertIsNone(r['dice']);self.assertFalse(r['false_positive_image'])
        r=score(~z,z,~z);self.assertEqual(r['fp'],4);self.assertTrue(r['false_positive_image'])
    def test_scoped_iou_does_not_count_outside(self):
        g=np.zeros((4,4),bool);g[0,0]=1;g[1,3]=1;p=np.zeros((4,4),bool);p[1,3]=1
        self.assertEqual(score(p,g,np.ones_like(g),'right')['iou'],1)
        self.assertEqual(score(p,g,np.ones_like(g),'whole')['iou'],.5)
    def test_size_mismatch_is_rejected(self):
        with self.assertRaises(ValueError):score(np.zeros((2,3)),np.zeros((2,2)),np.ones((2,2)))
