"""Real HTTP/PNG/ZIP integration with EXPLICITLY FAKE model endpoints; no GPU."""
import base64
import io
import json
import os
import tempfile
import threading
import unittest
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from PIL import Image
import server
from runtime_config import load_settings
from service_transport import inspect_services, request_json


class FakeModels(BaseHTTPRequestHandler):
    calls = 0
    ready = True
    def log_message(self, *args): pass
    def reply(self, data):
        raw = json.dumps(data).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        if self.path == '/v1/models': return self.reply({'data': [{'id': 'TEST-FAKE-ONLY'}]})
        if self.path == '/ready': return self.reply({'ready': self.ready})
        self.send_error(404)
    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.path == '/v1/chat/completions':
            content = data['messages'][-1]['content']
            if isinstance(content,list):
                image = content[1]['image_url']['url']; assert image.startswith('data:image/png;base64,')
                answer = 'T_call(referring_expression_segmentation, "ignored.png", "all buildings")'
            else:
                assert '[Execution Result]' in content
                answer = '<answer>已收到工作台的分割结果和确定性统计。</answer>'
            return self.reply({'choices': [{'message': {'content': answer}}]})
        if self.path == '/predict':
            type(self).calls += 1
            image = Image.open(io.BytesIO(base64.b64decode(data['image'])))
            return self.reply({'status': 'success', 'mask': server.image_b64(Image.new('L', image.size, 1))})
        self.send_error(404)


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.models = ThreadingHTTPServer(('127.0.0.1', 0), FakeModels)
        cls.thread = threading.Thread(target=cls.models.serve_forever, daemon=True); cls.thread.start()
        cls.endpoint = f'http://127.0.0.1:{cls.models.server_port}'
    @classmethod
    def tearDownClass(cls):
        cls.models.shutdown(); cls.models.server_close(); cls.thread.join()
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data_patch = patch.object(server, 'DATA', Path(self.temp.name)); self.data_patch.start()
        self.env_patch = patch.dict(os.environ, {
            'GEO_AGENT_BASE_URL': self.endpoint + '/v1', 'GEO_AGENT_MODEL': 'TEST-FAKE-ONLY',
            'GEO_REMOTESAM_URL': self.endpoint + '/predict', 'GEO_REMOTESAM_REVISION': 'fake-fixture-v1',
            'GEO_SERVICE_PROXY_MODE': 'direct', 'http_proxy': 'http://127.0.0.1:1',
            'https_proxy': 'http://127.0.0.1:1', 'no_proxy': '', 'NO_PROXY': '',
        }); self.env_patch.start()
        server.SESSIONS.clear(); FakeModels.calls = 0; FakeModels.ready = True
        self.session = server.SESSIONS[server.new_session(uploaded=server.image_b64(Image.new('RGB', (11, 7), 'white')), name='FAKE TEST.png')['id']]
    def tearDown(self):
        server.SESSIONS.clear(); self.env_patch.stop(); self.data_patch.stop(); self.temp.cleanup()
    def run_task(self, query, **extra):
        return server.run_task(self.session, {'query': query, 'mode': 'live', **extra})
    def test_actual_http_binary_one_masks_cache_and_restart(self):
        right = self.run_task('提取右半幅建筑')
        self.assertEqual(right['metrics']['pixel_area'], 42)
        server.SESSIONS.clear()
        self.session = server.get_session(self.session['id'])
        left = self.run_task('改成左半幅', parent_run_id=right['id'])
        self.assertEqual(left['metrics']['pixel_area'], 35)
        self.assertEqual(FakeModels.calls, 1)
        self.assertEqual(left['reused_from_run_id'], right['id'])
        self.assertEqual(len(server.session_index()), 1)
        self.assertEqual(server.session_index()[0]['run_count'], 2)
    def test_revision_change_invalidates_cached_segmentation(self):
        first = self.run_task('提取右侧建筑')
        os.environ['GEO_REMOTESAM_REVISION'] = 'fake-fixture-v2'
        second = self.run_task('改成左侧', parent_run_id=first['id'])
        self.assertEqual(FakeModels.calls, 2); self.assertNotIn('reused_from_run_id', second)
    def test_unknown_revision_and_force_do_not_reuse(self):
        first = self.run_task('提取右侧建筑')
        self.run_task('改成左侧', parent_run_id=first['id'], force_perception=True)
        os.environ['GEO_REMOTESAM_REVISION'] = ''
        self.run_task('改成左侧', parent_run_id=first['id'])
        self.assertEqual(FakeModels.calls, 3)
    def test_corrupt_cached_mask_triggers_new_inference(self):
        first = self.run_task('提取右侧建筑')
        (server.DATA/self.session['id']/first['id']/'full_mask.png').write_bytes(b'corrupt')
        second = self.run_task('改成左侧', parent_run_id=first['id'])
        self.assertEqual(second['status'], 'completed'); self.assertEqual(FakeModels.calls, 2)
    def test_probability_maps_are_rejected(self):
        with patch.object(server, 'post_json', return_value={'status': 'success', 'mask': server.image_b64(Image.new('L', (11, 7), 128))}):
            result = self.run_task('提取右侧建筑')
        self.assertEqual(result['status'], 'failed'); self.assertNotIn('metrics', result)
        self.assertFalse((server.DATA/self.session['id']/result['id']/'mask.png').exists())
    def test_service_probe_does_not_infer_and_requires_true_readiness(self):
        report = inspect_services()
        self.assertTrue(report['services_ready']); self.assertFalse(report['inference_verified'])
        self.assertEqual(FakeModels.calls, 0)
        FakeModels.ready = False
        self.assertFalse(inspect_services()['services_ready'])
        os.environ['GEO_AGENT_MODEL'] = 'NOT-A-SERVED-MODEL'
        self.assertEqual(inspect_services()['agent']['status'], 'model_missing')
    def test_export_over_http_and_missing_session(self):
        result = self.run_task('提取右侧建筑')
        class QuietHandler(server.Handler):
            def log_message(self, *args): pass
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True); thread.start()
        try:
            endpoint = f'http://127.0.0.1:{httpd.server_port}'
            server.SESSIONS.clear()
            saved = request_json(endpoint+'/api/session/'+self.session['id'])
            self.assertEqual(saved['runs'][0]['id'], result['id'])
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(endpoint+result['export_url']) as response: payload = response.read()
            with zipfile.ZipFile(io.BytesIO(payload)) as z:
                self.assertEqual(set(z.namelist()), {'original.png','mask.png','overlay.png','result.json','statistics.json','run_log.json','report.md','full_mask.png','manifest.json'})
                mask = Image.open(io.BytesIO(z.read('mask.png')))
                metrics = json.loads(z.read('statistics.json'))
                self.assertEqual(sum(mask.histogram()[1:]), metrics['pixel_area'])
                report = z.read('report.md').decode('utf-8')
                self.assertIn(f'{metrics["pixel_area"]:,} 像素', report)
                self.assertIn('候选连通区域', report)
            with opener.open(endpoint+result['report_url']) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(server.capabilities()['name'], response.read().decode('utf-8'))
            self.assertIsNone(server.get_session('../../anything'))
        finally:
            httpd.shutdown(); httpd.server_close(); thread.join()
    def test_roi_candidate_statistics_use_final_mask(self):
        roi={'xyxy':[0,0,5,7],'source':'drawn','image_size':[11,7]}
        result=self.run_task('提取框选区域内的建筑',roi=roi,scope='all')
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['metrics']['pixel_area'],35)
        stats=result['metrics']['candidate_stats']
        self.assertEqual(stats['candidate_count'],1)
        self.assertEqual(stats['total_area_pixels'],35)
        self.assertEqual(stats['candidates'][0]['bbox'],{'x':0,'y':0,'width':5,'height':7})
        self.assertEqual(result['metrics']['distribution'],{
            'basis':'full_mask_before_scope','left_pixels':35,'right_pixels':42,
            'roi_inside_pixels':35,'roi_outside_pixels':42})
    def test_corrupt_persisted_session_is_not_loaded(self):
        sid = self.session['id']; server.SESSIONS.clear()
        (server.DATA/sid/'session.json').write_text('{invalid', encoding='utf-8')
        self.assertIsNone(server.get_session(sid))
    def test_semantic_report_preserves_actual_request_and_nested_model_identity(self):
        response={'status':'success','masks':{'building':server.image_b64(Image.new('L',(11,7),255))},
                  'quality_mode':'fast','model':{'service_version':'fixture-1.2','checkpoint_sha256':'fixture-checkpoint'}}
        with patch('agent_bridge.WorkbenchAgent._run_llm',return_value='T_call(semantic_segmentation, "ignored.png", ["building"])'), \
             patch.object(server,'post_json',return_value=response):
            result=self.run_task('提取建筑',quality_mode='fast')
        self.assertEqual(result['status'],'completed',result['message'])
        report=(server.DATA/self.session['id']/result['id']/'report.md').read_text(encoding='utf-8')
        self.assertIn('"task": "semantic_seg"',report)
        self.assertIn('"classes": ["building"]',report)
        self.assertNotIn('all buildings',report)
        self.assertIn('fixture-1.2',report)
        self.assertIn('fixture-checkpoint',report)
        self.assertTrue(result['capability']['semantic_review_required'])

    def test_experimental_category_stays_available_and_explicitly_labelled(self):
        response={'status':'success','mask':server.image_b64(Image.new('L',(11,7),255)),'quality_mode':'fast'}
        with patch('agent_bridge.WorkbenchAgent._run_llm',return_value='T_call(referring_expression_segmentation, "ignored.png", "all roads")'), \
             patch.object(server,'post_json',return_value=response):
            result=self.run_task('提取道路',quality_mode='fast')
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['capability']['level'],'experimental')
        self.assertIn('实验阶段',result['message'])
        report=(server.DATA/self.session['id']/result['id']/'report.md').read_text(encoding='utf-8')
        self.assertIn('"text": "all roads"',report)
        self.assertIn('实验类别',report)

    def test_demo_report_never_invents_a_model_prompt(self):
        s=server.SESSIONS[server.new_session('urban')['id']]
        result=server.run_task(s,{'query':'提取建筑','mode':'demo'})
        report=(server.DATA/s['id']/result['id']/'report.md').read_text(encoding='utf-8')
        self.assertIn('合成演示未调用模型',report)
        self.assertNotIn('all buildings',report)

    def test_new_quality_label_maps_to_existing_accurate_mode(self):
        from v07_contract import resolve_quality
        for label in ('改成分块细化模式','use accurate mode','改成高精度模式'):
            self.assertEqual(resolve_quality(label,{},None)[:2],('accurate','accurate'))

    def test_dotenv_is_literal_and_shell_wins(self):
        path = Path(self.temp.name)/'.env'
        path.write_text('GEO_AGENT_MODEL=from-file\nGEO_TEST_LITERAL="$(do-not-execute)"\n', encoding='utf-8')
        load_settings(path)
        self.assertEqual(os.environ['GEO_AGENT_MODEL'], 'TEST-FAKE-ONLY')
        self.assertEqual(os.environ['GEO_TEST_LITERAL'], '$(do-not-execute)')


if __name__ == '__main__': unittest.main()
