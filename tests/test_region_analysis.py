"""Saved-mask investigation must work offline and keep its statistical frame explicit."""
import base64
import hashlib
import json
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from workbench import server
from workbench.export_bundle import build_bundle, verify_bundle
from workbench.pixel_geometry import scope_area_pixels
from test_evidence_handoff import rewrite_bundle


class RegionAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.data=patch.object(server,'DATA',Path(self.temp.name));self.data.start()
        self.sessions=patch.object(server,'SESSIONS',{});self.sessions.start()
        self.s=server.SESSIONS[server.new_session('urban')['id']]
        self.source=server.run_task(self.s,{'query':'Segment buildings in the right half','mode':'demo'})
        self.folder=server.DATA/self.s['id']/self.source['id']
        self.bundle=build_bundle(server.DATA/self.s['id']/'original.png',self.folder)
    def tearDown(self):
        self.sessions.stop();self.data.stop();self.temp.cleanup()
    def analyze(self,s=None,**selection):
        s=s or self.s
        with (patch.object(server,'post_json',side_effect=AssertionError('No model calls')),
              patch.object(server,'AgentTurn',side_effect=AssertionError('No agent calls'))):
            return server.recalculate_region(s,{'run_id':s['runs'][0]['id'],**selection})
    def test_imported_result_supports_all_scopes_and_rectangle_without_models(self):
        imported=server.import_evidence({'bundle':base64.b64encode(self.bundle).decode()})
        s=server.SESSIONS[imported['id']]
        roi={'xyxy':[80,50,280,250],'source':'drawn','image_size':[800,600]}
        selections=[('all',None,75350,480000),('left',None,38000,240000),
                    ('right',None,37350,240000),('top',None,37000,240000),
                    ('bottom',None,38350,240000),('all',roi,12850,40000)]
        for side,rectangle,area,denominator in selections:
            with self.subTest(scope=side,roi=rectangle):
                r=self.analyze(s,scope=side,roi=rectangle)
                self.assertEqual(r['metrics']['pixel_area'],area)
                self.assertEqual(r['metrics']['scope_area_pixels'],denominator)
                self.assertAlmostEqual(r['metrics']['scope_area_ratio'],area/denominator)
                self.assertAlmostEqual(r['metrics']['area_ratio'],area/480000)
                folder=server.DATA/s['id']/r['id']
                self.assertEqual((folder/'full_mask.png').read_bytes(),(self.folder/'full_mask.png').read_bytes())
                self.assertTrue(verify_bundle(build_bundle(server.DATA/s['id']/'original.png',folder))['verified'])
                self.assertFalse(r['inference_performed'])
                self.assertNotIn('mask_cache_key',r)
    def test_new_version_resets_review_and_preserves_source_and_prediction_metadata(self):
        server.review_result(self.s,{'run_id':self.source['id'],'decision':'accepted',
            'reviewer':'AUTOMATED SOFTWARE CHECK','note':'Fixture-only persistence test, not an image accuracy assessment.'})
        original={p.name:p.read_bytes() for p in self.folder.iterdir()}
        r=self.analyze(scope='left')
        self.assertEqual(r['parent_run_id'],self.source['id'])
        self.assertEqual(r['version'],2)
        self.assertEqual(r['semantic_review']['state'],'pending')
        self.assertEqual(r['semantic_review']['events'],[])
        self.assertEqual({p.name:p.read_bytes() for p in self.folder.iterdir()},original)
        self.assertEqual(r['source_prediction']['task'],self.source['task'])
        self.assertEqual(r['derived_from']['full_mask_sha256'],self.source['full_mask_sha256'])
        server.SESSIONS.clear();s=server.get_session(self.s['id'])
        self.assertEqual(s['runs'][-1]['execution_kind'],'saved_mask_region_analysis')
    def test_derived_result_can_be_exported_imported_reviewed_and_recalculated(self):
        first=self.analyze(scope='left')
        bundle=build_bundle(server.DATA/self.s['id']/'original.png',server.DATA/self.s['id']/first['id'])
        restored=server.import_evidence({'bundle':base64.b64encode(bundle).decode()})
        s=server.SESSIONS[restored['id']]
        r=self.analyze(s,scope='right')
        self.assertEqual(r['source_prediction']['run_id'],self.source['id'])
        server.review_result(s,{'run_id':r['id'],'decision':'rejected','reviewer':'AUTOMATED TEST',
                               'note':'Testing saved-mask review persistence only.'})
        report=(server.DATA/s['id']/r['id']/'report.md').read_text(encoding='utf-8')
        self.assertIn('no model inference',report)
        self.assertIn('Semantic review: rejected',report)
    def test_invalid_selection_and_tampered_source_leave_session_unchanged(self):
        selections=[{'scope':'unknown'},{'scope':[]},{'scope':'all','roi':{}},
            {'scope':'left','roi':{'xyxy':[1,1,10,10],'source':'drawn','image_size':[800,600]}},
            {'scope':'all','roi':{'xyxy':[1,1,801,10],'source':'drawn','image_size':[800,600]}}]
        for selection in selections:
            before=set((server.DATA/self.s['id']).iterdir())
            with self.subTest(selection=selection),self.assertRaises(ValueError):self.analyze(**selection)
            self.assertEqual(set((server.DATA/self.s['id']).iterdir()),before)
            self.assertEqual(len(self.s['runs']),1)
        mask=self.folder/'mask.png';mask.write_bytes(b'invalid')
        before=set((server.DATA/self.s['id']).iterdir())
        with self.assertRaises((ValueError,OSError)):self.analyze(scope='all')
        self.assertEqual(set((server.DATA/self.s['id']).iterdir()),before)
    def test_busy_session_rejects_recalculation(self):
        self.s['lock'].acquire()
        try:
            with self.assertRaisesRegex(ValueError,'busy'):self.analyze(scope='all')
        finally:self.s['lock'].release()
    def test_complement_is_retained_without_a_new_semantic_request(self):
        source=server.run_task(self.s,{'query':'Segment non-buildings in the right half','mode':'demo'})
        with patch.object(server,'post_json',side_effect=AssertionError('No inference')):
            r=server.recalculate_region(self.s,{'run_id':source['id'],'scope':'left'})
        self.assertTrue(r['task']['invert'])
        self.assertEqual(r['metrics']['pixel_area'],202000)
        verify_bundle(build_bundle(server.DATA/self.s['id']/'original.png',server.DATA/self.s['id']/r['id']))
        with self.assertRaisesRegex(ValueError,'semantic target'):
            server.recalculate_region(self.s,{'run_id':source['id'],'scope':'left','target':'aircraft'})
    def test_half_image_denominators_handle_odd_and_empty_scopes(self):
        self.assertEqual(scope_area_pixels(5,3,'left'),6)
        self.assertEqual(scope_area_pixels(5,3,'right'),9)
        empty=Image.new('L',(1,3),0)
        m=server.statistics(empty,'left',full_mask=empty)
        self.assertEqual(m['scope_area_pixels'],0)
        self.assertIsNone(m['scope_area_ratio'])
    def test_verifier_rejects_resigned_region_ratios_and_accepts_legacy_metrics(self):
        def edit(files,legacy=False):
            r=json.loads(files['result.json'])
            if legacy:
                for key in ('scope_area_pixels','scope_area_ratio'):r['metrics'].pop(key)
            else:r['metrics']['scope_area_ratio']=r['metrics']['area_ratio']
            files['statistics.json']=json.dumps(r['metrics']).encode()
            files['result.json']=json.dumps(r).encode()
        with self.assertRaisesRegex(ValueError,'Within-region'):verify_bundle(rewrite_bundle(self.bundle,edit))
        self.assertTrue(verify_bundle(rewrite_bundle(self.bundle,lambda f:edit(f,True)))['verified'])
    def test_http_recalculate_export_and_invalid_request(self):
        class Quiet(server.Handler):
            def log_message(self,*args):pass
        httpd=ThreadingHTTPServer(('127.0.0.1',0),Quiet)
        worker=threading.Thread(target=httpd.serve_forever,daemon=True);worker.start()
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        root=f'http://127.0.0.1:{httpd.server_port}'
        def request(scope):
            return urllib.request.Request(root+'/api/recalculate-region',data=json.dumps({
                'session_id':self.s['id'],'run_id':self.source['id'],'scope':scope}).encode(),
                headers={'Content-Type':'application/json'})
        try:
            with patch.object(server,'post_json',side_effect=AssertionError('No model calls')):
                with opener.open(request('all')) as response:r=json.load(response)
            with opener.open(root+r['export_url']) as response:self.assertEqual(verify_bundle(response.read())['pixel_area'],75350)
            with self.assertRaises(urllib.error.HTTPError) as error:opener.open(request('invalid'))
            self.assertEqual(error.exception.code,400)
        finally:httpd.shutdown();httpd.server_close();worker.join()


if __name__=='__main__':unittest.main()
