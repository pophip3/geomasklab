"""Cross-session handoff must preserve pixel identities and reject inconsistent intent."""
import base64
import hashlib
import io
import json
import tempfile
import threading
import unittest
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
import server
from export_bundle import build_bundle, verify_bundle


def rewrite_bundle(bundle, mutate):
    """Re-sign files to test domain consistency, beyond a simple checksum failure."""
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        files={n:archive.read(n) for n in archive.namelist()}
    mutate(files)
    manifest=json.loads(files['manifest.json'])
    manifest['checksums']={n:{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
                           for n,raw in files.items() if n!='manifest.json'}
    files['manifest.json']=json.dumps(manifest).encode()
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,raw in files.items(): archive.writestr(name,raw)
    return out.getvalue()


class EvidenceHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.data=patch.object(server,'DATA',Path(self.temp.name));self.data.start()
        self.sessions=patch.object(server,'SESSIONS',{});self.sessions.start()
        self.s=server.SESSIONS[server.new_session('urban')['id']]
        self.r=server.run_task(self.s,{'query':'提取右侧建筑','mode':'demo'})
        self.folder=server.DATA/self.s['id']/self.r['id']
        self.bundle=build_bundle(server.DATA/self.s['id']/'original.png',self.folder)
    def tearDown(self):
        self.sessions.stop();self.data.stop();self.temp.cleanup()
    def restore(self,bundle=None):
        return server.import_evidence({'bundle':base64.b64encode(bundle or self.bundle).decode(),'name':'fixture.zip'})
    def test_cross_session_reload_review_and_export_without_models(self):
        source_result=(self.folder/'result.json').read_bytes()
        with patch.object(server,'post_json',side_effect=AssertionError('Must not run models')):
            restored=self.restore()
        self.assertNotEqual(restored['id'],self.s['id'])
        self.assertIsNone(restored['sample'])
        r=restored['runs'][0];folder=server.DATA/restored['id']/r['id']
        self.assertNotIn('mask_cache_key',r)
        self.assertIsNone(r['parent_run_id'])
        for name in ('mask.png','full_mask.png','statistics.json'):
            self.assertEqual((folder/name).read_bytes(),(self.folder/name).read_bytes())
        self.assertEqual((server.DATA/restored['id']/'original.png').read_bytes(),(server.DATA/self.s['id']/'original.png').read_bytes())
        self.assertEqual((server.DATA/restored['id']/'source-evidence.zip').read_bytes(),self.bundle)
        server.SESSIONS.clear();s=server.get_session(restored['id'])
        server.review_result(s,{'run_id':r['id'],'decision':'rejected','reviewer':'AUTOMATED HANDOFF TEST',
                               'note':'Testing persistence only, not a semantic judgement.'})
        self.assertEqual(verify_bundle(build_bundle(server.DATA/s['id']/'original.png',folder))['semantic_review_state'],'rejected')
        self.assertEqual((self.folder/'result.json').read_bytes(),source_result)
        self.assertIn('本次导入未运行模型',(folder/'report.md').read_text(encoding='utf-8'))
    def test_inconsistent_resigned_metadata_does_not_create_session(self):
        def bad_roi(files):
            r=json.loads(files['result.json']);r['task']['roi']={'xyxy':[0,0,10,10]}
            files['result.json']=json.dumps(r).encode()
        def bad_candidates(files):
            r=json.loads(files['result.json']);r['metrics']['candidate_stats']['candidate_count']+=1
            files['statistics.json']=json.dumps(r['metrics']).encode();files['result.json']=json.dumps(r).encode()
        def bad_invert(files):
            r=json.loads(files['result.json']);r['task']['invert']='false';files['result.json']=json.dumps(r).encode()
        for mutate in (bad_roi,bad_candidates,bad_invert):
            before=set(server.DATA.iterdir())
            with self.subTest(mutate=mutate.__name__),self.assertRaises(ValueError):self.restore(rewrite_bundle(self.bundle,mutate))
            self.assertEqual(set(server.DATA.iterdir()),before)
    def test_local_urls_replace_untrusted_locations_and_cache_is_revoked(self):
        def mutate(files):
            r=json.loads(files['result.json']);r.update(mask_url='https://invalid.test/mask',
                export_url='https://invalid.test/export',mask_cache_key='foreign-cache')
            files['result.json']=json.dumps(r).encode()
        r=self.restore(rewrite_bundle(self.bundle,mutate))['runs'][0]
        self.assertTrue(r['mask_url'].startswith('/experiments/'))
        self.assertTrue(r['export_url'].startswith('/api/export/'))
        self.assertNotIn('mask_cache_key',r)
    def test_bad_zip_and_paths_are_rejected(self):
        for raw in (b'not a zip',rewrite_bundle(self.bundle,lambda f:f.update({'../outside':b'no'}))):
            with self.assertRaises(ValueError):self.restore(raw)
        with self.assertRaises(ValueError):server.import_evidence({'bundle':'not valid base64!'})

    def test_http_import_restores_downloads_and_rejects_bad_request(self):
        class Quiet(server.Handler):
            def log_message(self,*args):pass
        httpd=ThreadingHTTPServer(('127.0.0.1',0),Quiet)
        worker=threading.Thread(target=httpd.serve_forever,daemon=True);worker.start()
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        url=f'http://127.0.0.1:{httpd.server_port}'
        def request(raw):
            return urllib.request.Request(url+'/api/import',data=json.dumps({'bundle':base64.b64encode(raw).decode()}).encode(),headers={'Content-Type':'application/json'})
        try:
            with patch.object(server,'post_json',side_effect=AssertionError('No inference')):
                with opener.open(request(self.bundle)) as response:s=json.load(response)
            with opener.open(url+s['runs'][0]['export_url']) as response:
                self.assertEqual(verify_bundle(response.read())['pixel_area'],37350)
            with self.assertRaises(urllib.error.HTTPError) as error:opener.open(request(b'invalid'))
            self.assertEqual(error.exception.code,400)
        finally:
            httpd.shutdown();httpd.server_close();worker.join()


if __name__=='__main__':unittest.main()
