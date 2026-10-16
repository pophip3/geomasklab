import base64
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from workbench import server
from PIL import Image

class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patcher=patch.object(server,'DATA',Path(self.temp.name));self.patcher.start()
        self.s=server.SESSIONS[server.new_session()['id']]
    def tearDown(self):
        server.SESSIONS.clear();self.patcher.stop();self.temp.cleanup()
    def run_task(self,q,**kw):
        return server.run_task(self.s,{'query':q,'mode':'demo',**kw})
    def test_half_masks_partition_full_image(self):
        mask=server.demo_mask('urban')
        total=server.statistics(mask,'all')['pixel_area']
        left=server.statistics(server.constrain(mask,'left'),'left')
        right=server.statistics(server.constrain(mask,'right'),'right')
        self.assertEqual(total,left['pixel_area']+right['pixel_area'])
        self.assertTrue(left['spatial_check']);self.assertTrue(right['spatial_check'])
        self.assertEqual(right['total_pixels'],480000)
    def test_odd_image_partition(self):
        mask=Image.new('L',(5,3),255)
        self.assertEqual(server.statistics(server.constrain(mask,'left'),'left')['pixel_area'],6)
        self.assertEqual(server.statistics(server.constrain(mask,'right'),'right')['pixel_area'],9)
    def test_followup_preserves_target_and_versions(self):
        first=self.run_task('\u63d0\u53d6\u53f3\u4fa7\u5efa\u7b51\u5e76\u8ba1\u7b97\u9762\u79ef\u5360\u6bd4')
        old=(server.DATA/self.s['id']/first['id']/'mask.png').read_bytes()
        second=self.run_task('\u6539\u6210\u5de6\u4fa7\u7684',parent_run_id=first['id'])
        self.assertEqual(second['task']['target'],'building')
        self.assertEqual(second['task']['side'],'left')
        self.assertTrue(second['task']['inherited_target'])
        self.assertEqual(old,(server.DATA/self.s['id']/first['id']/'mask.png').read_bytes())
        self.assertNotEqual(old,(server.DATA/self.s['id']/second['id']/'mask.png').read_bytes())
    def test_non_target_annotation_inverts_the_base_mask(self):
        positive=self.run_task('\u63d0\u53d6\u5168\u56fe\u5efa\u7b51')
        inverse=self.run_task('\u628a\u975e\u5efa\u7b51\u7684\u90e8\u5206\u6807\u6ce8\u51fa\u6765')
        self.assertTrue(inverse['task']['invert'])
        self.assertEqual(positive['metrics']['pixel_area']+inverse['metrics']['pixel_area'],480000)
        self.assertIn('non-buildings',inverse['message'])
    def test_branch_from_old_result(self):
        r=self.run_task('\u63d0\u53d6\u53f3\u4fa7\u5efa\u7b51')
        self.run_task('\u6539\u6210\u5de6\u4fa7\u7684',parent_run_id=r['id'])
        branch=self.run_task('\u8ba1\u7b97\u9762\u79ef\u5360\u6bd4',parent_run_id=r['id'])
        self.assertEqual(branch['task']['side'],'right')
        self.assertEqual(branch['metrics'],r['metrics'])
        self.assertTrue(any('Reuse' in t['name'] for t in branch['trace']))
    def test_no_pretend_live_result(self):
        with patch.dict(server.os.environ,{},clear=True): r=self.run_task('\u63d0\u53d6\u53f3\u4fa7\u5efa\u7b51',mode='live')
        self.assertEqual(r['status'],'failed');self.assertNotIn('mask_url',r)
    def test_ambiguity_preserves_context(self):
        first=self.run_task('\u63d0\u53d6\u53f3\u4fa7\u5efa\u7b51')
        r=self.run_task('\u628a\u90a3\u4e2a\u533a\u57df\u63d0\u51fa\u6765')
        self.assertEqual(r['status'],'needs_clarification')
        self.assertNotIn('mask_url',r);self.assertEqual(self.s['context']['side'],'right')
    def test_failure_never_generates_fake_statistics(self):
        r=self.run_task('\u63d0\u53d6\u53f3\u4fa7\u5efa\u7b51',simulate_failure=True)
        self.assertEqual(r['status'],'failed');self.assertNotIn('metrics',r)
        self.assertFalse((server.DATA/self.s['id']/r['id']/'mask.png').exists())
    def test_unsupported_class_not_empty_truth(self):
        r=self.run_task('\u63d0\u53d6\u8239\u8236')
        self.assertEqual(r['status'],'failed');self.assertIn('cannot establish',r['message'])
    def test_complex_spatial_constraint_clarifies(self):
        r=self.run_task('\u63d0\u53d6\u9760\u8fd1\u9053\u8def\u7684\u5efa\u7b51')
        self.assertEqual(r['status'],'needs_clarification')
    def test_custom_image_requires_model(self):
        b=io.BytesIO();Image.new('RGB',(80,50),'white').save(b,format='PNG')
        self.s=server.SESSIONS[server.new_session(uploaded=base64.b64encode(b.getvalue()).decode(),name='custom.png')['id']]
        r=self.run_task('\u63d0\u53d6\u53f3\u4fa7\u5efa\u7b51');self.assertEqual(r['status'],'failed')
        self.assertNotIn('mask_url',r)
    def test_export_refuses_missing_result(self):
        r=self.run_task('\u5bfc\u51fa\u521a\u624d\u7684\u7ed3\u679c');self.assertEqual(r['status'],'failed')
        first=self.run_task('\u63d0\u53d6\u5efa\u7b51');r=self.run_task('\u5bfc\u51fa\u521a\u624d\u7684\u7ed3\u679c',parent_run_id=first['id'])
        self.assertEqual(r['export_url'],first['export_url'])
    def test_real_mask_size_error_is_not_resized(self):
        wrong=Image.new('L',(2,2),255)
        with patch('workbench.agent_bridge.WorkbenchAgent._run_llm',return_value='T_call(referring_expression_segmentation, "ignored.png", "all buildings")'), patch.object(server,'post_json',return_value={'status':'success','mask':server.image_b64(wrong)}), patch.dict(server.os.environ,{'GEO_AGENT_BASE_URL':'http://example.invalid/v1','GEO_AGENT_MODEL':'FAKE','GEO_REMOTESAM_URL':'http://example.invalid/predict'}):
            r=self.run_task('\u63d0\u53d6\u53f3\u4fa7\u5efa\u7b51',mode='live')
        self.assertEqual(r['status'],'failed');self.assertIn('dimensions',r['message'])
    def test_real_adapter_accepts_aligned_mask(self):
        mask=Image.new('L',(800,600),255)
        with patch('workbench.agent_bridge.WorkbenchAgent._run_llm',return_value='T_call(referring_expression_segmentation, "ignored.png", "all buildings")'), patch.object(server,'post_json',return_value={'status':'success','mask':server.image_b64(mask)}), patch.dict(server.os.environ,{'GEO_AGENT_BASE_URL':'http://example.invalid/v1','GEO_AGENT_MODEL':'FAKE','GEO_REMOTESAM_URL':'http://example.invalid/predict'}):
            r=self.run_task('\u63d0\u53d6\u53f3\u4fa7\u5efa\u7b51',mode='live')
        self.assertEqual(r['metrics']['area_ratio'],.5)
        self.assertEqual(r['mode'],'live')

if __name__=='__main__':unittest.main()
