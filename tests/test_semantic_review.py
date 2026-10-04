"""Review records must persist, bind to exact artifacts, and never change inference."""
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
from semantic_review import verify_review


class SemanticReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.data=patch.object(server,'DATA',Path(self.temp.name));self.data.start()
        self.sessions=patch.object(server,'SESSIONS',{});self.sessions.start()
        self.s=server.SESSIONS[server.new_session('urban')['id']]
        self.r=server.run_task(self.s,{'query':'提取右侧建筑','mode':'demo'})
        self.folder=server.DATA/self.s['id']/self.r['id']
    def tearDown(self):
        self.sessions.stop();self.data.stop();self.temp.cleanup()
    def review(self,decision='accepted',**extra):
        return server.review_result(self.s,{'run_id':self.r['id'],'decision':decision,
                                         'reviewer':'EXPLICIT TEST FIXTURE','note':'Only testing software persistence.',**extra})
    def test_reload_export_and_branch_never_inherit_acceptance(self):
        before={name:(self.folder/name).read_bytes() for name in ('mask.png','full_mask.png','statistics.json')}
        self.review()
        sid=self.s['id'];server.SESSIONS.clear();self.s=server.get_session(sid)
        self.assertEqual(self.s['runs'][0]['semantic_review']['state'],'accepted')
        bundle=build_bundle(server.DATA/sid/'original.png',self.folder)
        verified=verify_bundle(bundle)
        self.assertEqual(verified['semantic_review_state'],'accepted')
        self.assertFalse(verified['semantic_accuracy_verified'])
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            self.assertIn('EXPLICIT TEST FIXTURE',archive.read('report.md').decode())
        for name,raw in before.items():self.assertEqual((self.folder/name).read_bytes(),raw)
        new=server.run_task(self.s,{'query':'改成左侧建筑','mode':'demo','parent_run_id':self.r['id']})
        self.assertEqual(new['semantic_review'],server.initial_review())
        self.assertEqual(new['metrics']['pixel_area'],38000)
    def test_reject_and_reset_preserve_complete_history(self):
        self.review();self.review('rejected');updated=self.review('pending')
        self.assertEqual([e['decision'] for e in updated['semantic_review']['events']],['accepted','rejected','pending'])
        self.assertEqual(updated['status'],'completed')
        self.assertEqual(updated['metrics']['pixel_area'],37350)
    def test_invalid_review_cannot_mutate_saved_result(self):
        before=(self.folder/'result.json').read_bytes()
        for extra in ({'decision':'good'},{'decision':[]},{'reviewer':''},{'reviewer':5},{'note':''},
                      {'note':'x'*2001},{'run_id':'../../anything'},{'run_id':'a'*12}):
            with self.subTest(extra=str(extra)[:80]),self.assertRaises(ValueError):self.review(**extra)
            self.assertEqual((self.folder/'result.json').read_bytes(),before)
        with self.s['lock'],self.assertRaises(ValueError):self.review()
        for record in ([],{'schema':'geoscope-semantic-review/1.0','state':'pending','events':[None]}):
            with self.assertRaises(ValueError):verify_review(record,run_id=self.r['id'],image_sha256='',mask_sha256='')
    def test_review_cannot_be_transferred_even_with_new_file_checksums(self):
        self.review()
        bundle=build_bundle(server.DATA/self.s['id']/'original.png',self.folder)
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:files={n:archive.read(n) for n in archive.namelist()}
        result=json.loads(files['result.json'])
        result['semantic_review']['events'][0]['mask_sha256']='0'*64
        files['result.json']=json.dumps(result).encode()
        manifest=json.loads(files['manifest.json'])
        manifest['checksums']['result.json']={'bytes':len(files['result.json']),
            'sha256':hashlib.sha256(files['result.json']).hexdigest()}
        files['manifest.json']=json.dumps(manifest).encode()
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w') as archive:
            for name,raw in files.items():archive.writestr(name,raw)
        with self.assertRaisesRegex(ValueError,'review result identity'):verify_bundle(output.getvalue())
    def test_review_over_http_updates_downloaded_report_and_export(self):
        class QuietHandler(server.Handler):
            def log_message(self,*args):pass
        httpd=ThreadingHTTPServer(('127.0.0.1',0),QuietHandler)
        thread=threading.Thread(target=httpd.serve_forever,daemon=True);thread.start()
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        base=f'http://127.0.0.1:{httpd.server_port}'
        try:
            payload={'session_id':self.s['id'],'run_id':self.r['id'],'decision':'rejected',
                     'reviewer':'HTTP TEST FIXTURE','note':'Testing rejection recording; not a semantic judgement.'}
            request=urllib.request.Request(base+'/api/review',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
            with opener.open(request) as response:self.assertEqual(json.load(response)['semantic_review']['state'],'rejected')
            with opener.open(base+self.r['export_url']) as response:
                self.assertEqual(verify_bundle(response.read())['semantic_review_state'],'rejected')
            with opener.open(base+self.r['report_url']) as response:self.assertIn('HTTP TEST FIXTURE',response.read().decode())
        finally:httpd.shutdown();httpd.server_close();thread.join()


if __name__=='__main__':unittest.main()
