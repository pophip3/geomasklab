"""Independent research adapter tested against explicitly fake HTTP services."""
import base64
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from PIL import Image
from workbench import server
class FakeAgentAndSAM(BaseHTTPRequestHandler):
    decision = 'T_call(referring_expression_segmentation, "/not-the-current-image.png", "all buildings")'
    final = '<answer>完成。</answer>'
    requests = []
    fail_sam = False
    fail_feedback = False

    def log_message(self, *args): pass

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        type(self).requests.append((self.path, data, self.headers.get('Authorization')))
        if self.path == '/v1/chat/completions':
            is_feedback = isinstance(data['messages'][-1]['content'], str)
            if is_feedback and self.fail_feedback:
                return self.send_error(503)
            result = {'choices':[{'message':{'content': self.final if is_feedback else self.decision}}]}
        elif self.path == '/predict':
            if self.fail_sam:
                return self.send_error(503)
            image = Image.open(io.BytesIO(base64.b64decode(data['image'])))
            mask = server.image_b64(Image.new('L', image.size, 255))
            result = {'status':'success','mask':mask,'model':{'checkpoint_sha256':'FAKE-TEST-SHA'}}
            if data['task']=='semantic_seg':
                result['masks'] = {data['classes'][0]:mask}
        else:
            return self.send_error(404)
        raw = json.dumps(result).encode()
        self.send_response(200); self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)


class ProtocolIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(('127.0.0.1',0), FakeAgentAndSAM)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever,daemon=True); cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.httpd.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown(); cls.httpd.server_close(); cls.thread.join()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = patch.object(server,'DATA',Path(self.temp.name)); self.data.start()
        self.env = patch.dict(os.environ,{'GEO_AGENT_BASE_URL':self.base+'/v1',
            'GEO_AGENT_MODEL':'EXPLICIT-FAKE-MODEL','GEO_AGENT_API_KEY':'test-key-not-a-secret',
            'GEO_REMOTESAM_URL':self.base+'/predict','GEO_REMOTESAM_REVISION':'fake-v1',
            'GEO_SERVICE_PROXY_MODE':'direct'}); self.env.start()
        FakeAgentAndSAM.decision = 'T_call(referring_expression_segmentation, "/wrong.png", "all buildings")'
        FakeAgentAndSAM.final = '<answer>已收到执行结果。</answer>'
        FakeAgentAndSAM.requests = []; FakeAgentAndSAM.fail_sam = False; FakeAgentAndSAM.fail_feedback = False
        server.SESSIONS.clear()
        sid = server.new_session(uploaded=server.image_b64(Image.new('RGB',(11,7),'white')))['id']
        self.session = server.SESSIONS[sid]

    def tearDown(self):
        server.SESSIONS.clear(); self.env.stop(); self.data.stop(); self.temp.cleanup()

    def run_task(self,query='提取右侧建筑',**kwargs):
        return server.run_task(self.session,{'query':query,'mode':'live',**kwargs})

    def test_official_plan_tool_feedback_contains_real_asset_and_exact_statistics(self):
        result = self.run_task()
        self.assertEqual(result['status'],'completed')
        self.assertEqual([r[0] for r in FakeAgentAndSAM.requests],['/v1/chat/completions','/predict','/v1/chat/completions'])
        first, sam, final = FakeAgentAndSAM.requests
        self.assertEqual(first[2],'Bearer test-key-not-a-secret')
        self.assertEqual(first[1]['model'],'EXPLICIT-FAKE-MODEL')
        content = first[1]['messages'][-1]['content']
        self.assertTrue(content[1]['image_url']['url'].startswith('data:image/png;base64,'))
        self.assertEqual(result['agent_decision']['tool_call']['arguments']['image_path'],str((server.DATA/self.session['id']/'original.png').resolve()))
        self.assertEqual(sam[1]['text'],'all buildings')
        self.assertEqual(result['tool_feedback']['metrics']['pixel_area'],42)
        self.assertEqual(result['agent_feedback']['status'],'completed')
        feedback_text = final[1]['messages'][-1]['content']
        self.assertIn('"pixel_area": 42',feedback_text)
        self.assertNotIn('base64',feedback_text)
        self.assertEqual(result['task']['scope_source'],'harness_pixel_scope_rule')

    def test_direct_answer_does_not_segment(self):
        FakeAgentAndSAM.decision = '<answer>图中有建筑。</answer>'
        result = self.run_task('描述影像')
        self.assertEqual(result['status'],'answered'); self.assertEqual(len(FakeAgentAndSAM.requests),1)
        self.assertNotIn('metrics',result)
        request = FakeAgentAndSAM.requests[0][1]
        self.assertIn('INTERNAL VISUAL UNDERSTANDING ONLY', request['messages'][0]['content'])
        self.assertIn('only these deployed tools are available: none', request['messages'][0]['content'])
        self.assertEqual(json.loads(request['messages'][-1]['content'][0]['text'])['context']['task_route'], 'internal')

    def test_dense_prompt_exposes_only_deployed_tools_and_whole_image_airplanes(self):
        FakeAgentAndSAM.decision = 'T_call(referring_expression_segmentation, "wrong.png", "all airplanes")'
        result = self.run_task('提取右侧的飞机')
        self.assertEqual(result['status'], 'completed')
        first, sam, _ = FakeAgentAndSAM.requests
        prompt = first[1]['messages'][0]['content']
        self.assertIn('exactly ONE plain T_call', prompt)
        self.assertIn('"all planes"', prompt)
        self.assertIn('["aircraft"]', prompt)
        self.assertIn('"Extract only the buildings in the left half"', prompt)
        self.assertIn('"contours of all objects"', prompt)
        self.assertNotIn('object_detection(', prompt)
        self.assertNotIn('crossearth_semantic_segmentation', prompt)
        self.assertEqual(sam[1]['text'], 'all planes')
        self.assertEqual(result['task']['side'], 'right')

    def test_semantic_aircraft_keeps_canonical_service_class(self):
        FakeAgentAndSAM.decision = 'T_call(semantic_segmentation, "wrong.png", ["aircraft"])'
        result = self.run_task('Extract all aircraft in this image.')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(FakeAgentAndSAM.requests[1][1]['classes'], ['aircraft'])

    def test_visual_question_cannot_accidentally_run_segmentation(self):
        FakeAgentAndSAM.decision = 'T_call(semantic_segmentation, "wrong.png", ["building", "road"])'
        result = self.run_task('这张影像主要是什么场景？')
        self.assertEqual(result['status'], 'failed')
        self.assertNotIn('metrics', result)
        self.assertEqual([r[0] for r in FakeAgentAndSAM.requests], ['/v1/chat/completions'])

    def test_annotation_and_complement_route_to_mask_then_invert(self):
        FakeAgentAndSAM.decision = 'T_call(semantic_segmentation, "wrong.png", ["aircraft"])'
        result = self.run_task('把非飞机的部分标注出来')
        self.assertEqual(result['task']['action'], 'segment')
        self.assertTrue(result['task']['invert'])
        self.assertEqual(result['metrics']['pixel_area'], 0)
        self.assertEqual([r[0] for r in FakeAgentAndSAM.requests],
                         ['/v1/chat/completions', '/predict', '/v1/chat/completions'])
        self.assertEqual(FakeAgentAndSAM.requests[1][1]['classes'], ['aircraft'])

    def test_direct_answer_cannot_pretend_dense_task_completed(self):
        FakeAgentAndSAM.decision = '<answer>已经提取完成。</answer>'
        result = self.run_task()
        self.assertEqual(result['status'],'failed')
        self.assertIn('returned only text',result['message'])
        self.assertNotIn('metrics',result)
        # No tool was pending, so RemoteSAM and tool-result feedback are both skipped.
        self.assertEqual([r[0] for r in FakeAgentAndSAM.requests],['/v1/chat/completions'])

    def test_reasoning_text_is_redacted_but_response_hash_is_kept(self):
        FakeAgentAndSAM.decision = '<think>private model reasoning</think>\n<answer>图中有建筑。</answer>'
        result = self.run_task('描述影像')
        record = result['agent_decision']
        self.assertNotIn('private model reasoning',json.dumps(record))
        self.assertIn('Reasoning omitted from the experiment record',record['raw_response'])
        self.assertEqual(len(record['raw_response_sha256']),64)

    def test_rejected_or_unparsed_decisions_cannot_call_sam(self):
        for response in ['T_call(object_detection, "wrong.png", ["building"])','{"action":"segment"}','invalid']:
            FakeAgentAndSAM.decision = response; FakeAgentAndSAM.requests = []
            result = self.run_task()
            self.assertEqual(result['status'],'failed'); self.assertNotIn('mask_url',result)
            self.assertEqual(len(FakeAgentAndSAM.requests),1)

    def test_single_class_semantic_tool_keeps_actual_service_task(self):
        FakeAgentAndSAM.decision = 'T_call(semantic_segmentation, "wrong.png", ["building"])'
        result = self.run_task()
        self.assertEqual(result['status'],'completed')
        self.assertEqual(FakeAgentAndSAM.requests[1][1]['task'],'semantic_seg')
        self.assertEqual(FakeAgentAndSAM.requests[1][1]['classes'],['building'])

    def test_aircraft_referring_prompt_matches_improved_fast_configuration(self):
        FakeAgentAndSAM.decision = (
            'T_call(referring_expression_segmentation, "wrong.png", "all aircraft")'
        )
        result = self.run_task('提取全图飞机')
        self.assertEqual(result['status'], 'completed')
        request = FakeAgentAndSAM.requests[1][1]
        self.assertEqual(request['task'], 'referring_seg')
        self.assertEqual(request['text'], 'all planes')

    def test_unsupported_model_constraints_and_multi_class_require_clarification(self):
        for response in ['T_call(referring_expression_segmentation, "x.png", "buildings near roads")',
                         'T_call(semantic_segmentation, "x.png", ["building", "road"])',
                         'T_call(referring_expression_segmentation, "x.png", "buildings on the left")']:
            FakeAgentAndSAM.decision = response; FakeAgentAndSAM.requests = []
            result = self.run_task()
            self.assertEqual(result['status'],'needs_clarification')
            self.assertEqual(len(FakeAgentAndSAM.requests),1)

    def test_complex_or_conflicting_pixel_scope_stops_before_model(self):
        for query in ['提取靠近道路的建筑','提取左右两侧建筑','提取右下角建筑','提取右侧建筑，但不要右侧的']:
            self.assertEqual(self.run_task(query)['status'],'needs_clarification')
        self.assertEqual(self.run_task(scope='left')['status'],'needs_clarification')
        self.assertEqual(FakeAgentAndSAM.requests,[])

    def test_failure_is_fed_back_without_new_metrics_or_overwriting_old_result(self):
        first = self.run_task(); FakeAgentAndSAM.fail_sam = True
        old = (server.DATA/self.session['id']/first['id']/'mask.png').read_bytes()
        result = self.run_task('改成左侧',parent_run_id=first['id'],force_perception=True)
        self.assertEqual(result['status'],'failed'); self.assertNotIn('metrics',result)
        self.assertEqual(result['tool_feedback']['status'],'error')
        self.assertEqual(self.session['context']['side'],'right')
        self.assertEqual(old,(server.DATA/self.session['id']/first['id']/'mask.png').read_bytes())

    def test_feedback_outage_preserves_successful_artifacts(self):
        FakeAgentAndSAM.fail_feedback = True
        result = self.run_task()
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['metrics']['pixel_area'],42)
        self.assertEqual(result['agent_feedback']['status'],'transport_failed')
        self.assertIn('feedback failed',result['message'])

    def test_feedback_cannot_overwrite_statistics_or_start_another_tool(self):
        FakeAgentAndSAM.final = '<answer>面积是999999像素，占99%。</answer>'
        result = self.run_task()
        self.assertEqual(result['metrics']['pixel_area'],42)
        self.assertNotIn('999999',result['message'])
        self.assertIn('999999',result['agent_feedback']['raw_response'])
        FakeAgentAndSAM.final = 'T_call(referring_expression_segmentation, "x.png", "all roads")'
        result = self.run_task(force_perception=True)
        self.assertIn('feedback_warning',result)
        self.assertEqual(len(FakeAgentAndSAM.requests),6)

    def test_cache_reuse_still_reports_execution_to_model_and_selected_context(self):
        first = self.run_task()
        second = self.run_task('改成左侧的',parent_run_id=first['id'])
        self.assertEqual(second['metrics']['pixel_area'],35)
        self.assertEqual(second['tool_feedback']['reused_from_run_id'],first['id'])
        self.assertEqual(len([r for r in FakeAgentAndSAM.requests if r[0]=='/predict']),1)
        self.assertIn('"target": "building"',FakeAgentAndSAM.requests[3][1]['messages'][-1]['content'][0]['text'])

    def test_switching_tool_task_does_not_reuse_other_task_mask(self):
        first = self.run_task()
        FakeAgentAndSAM.decision = 'T_call(semantic_segmentation, "x.png", ["building"])'
        second = self.run_task('改成左侧',parent_run_id=first['id'])
        self.assertNotIn('reused_from_run_id',second)
        self.assertEqual(len([r for r in FakeAgentAndSAM.requests if r[0]=='/predict']),2)

    def test_export_is_local_and_preserves_decision_evidence(self):
        first = self.run_task()
        result = self.run_task('导出刚才的结果',parent_run_id=first['id'])
        self.assertEqual(result['export_url'],first['export_url'])
        self.assertEqual(len(FakeAgentAndSAM.requests),3)
        saved = json.loads((server.DATA/self.session['id']/first['id']/'result.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['agent_decision']['status'],'tool_call')
        self.assertEqual(saved['agent_feedback']['status'],'completed')
        self.assertNotIn('test-key-not-a-secret',json.dumps(saved))


if __name__=='__main__': unittest.main()
