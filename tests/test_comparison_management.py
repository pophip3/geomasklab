"""Version comparison, editable metadata and ledger must preserve scientific context."""
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from PIL import Image
import server
from export_bundle import build_bundle
from experiment_management import ledger_csv, metadata_changes
from result_comparison import compare_bundles


class ComparisonManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(server,'DATA',Path(self.temp.name)), patch.object(server,'SESSIONS',{}),
                        patch.object(server,'post_json',side_effect=AssertionError('Offline comparison must not infer'))]
        for p in self.patches: p.start()
        self.s = server.SESSIONS[server.new_session('urban')['id']]
        self.whole = self.run_mask('Extract buildings in the whole image.')
        self.right = self.run_mask('Extract buildings in the right half.')

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.temp.cleanup()

    def run_mask(self,query,**options):
        return server.run_task(self.s,{'query':query,'mode':'demo',**options})

    def bundle(self,run):
        return build_bundle(server.DATA/self.s['id']/'original.png', server.DATA/self.s['id']/run['id'])

    def test_common_scope_avoids_treating_cropping_as_model_change(self):
        result=compare_bundles(self.bundle(self.whole),self.bundle(self.right))
        self.assertEqual(result['common_scope_pixels'],240000)
        self.assertEqual(result['shared_foreground_pixels'],37350)
        self.assertEqual(result['changed_pixels'],0)
        self.assertEqual(result['mask_agreement_iou'],1)
        self.assertTrue(result['full_prediction_pixels_equal'])
        self.assertEqual(result['a']['foreground_pixels'],75350)
        self.assertFalse(result['semantic_accuracy_measured'])

    def test_disjoint_domains_have_undefined_agreement(self):
        left=self.run_mask('Extract buildings in the left half.')
        result=compare_bundles(self.bundle(left),self.bundle(self.right))
        self.assertEqual(result['common_scope_pixels'],0)
        self.assertIsNone(result['mask_agreement_iou'])
        self.assertIsNone(result['mask_agreement_dice'])

    def test_different_predictions_and_empty_masks_are_not_perfect(self):
        with patch.object(server,'demo_mask',return_value=Image.new('L',(800,600))):
            empty=self.run_mask('Extract buildings in the whole image.',force_perception=True)
            empty2=self.run_mask('Extract buildings in the whole image.',force_perception=True)
        result=compare_bundles(self.bundle(self.whole),self.bundle(empty))
        self.assertEqual(result['changed_pixels'],75350)
        self.assertEqual(result['mask_agreement_iou'],0)
        self.assertFalse(result['full_prediction_pixels_equal'])
        result=compare_bundles(self.bundle(empty),self.bundle(empty2))
        self.assertIsNone(result['mask_agreement_iou'])

    def test_semantic_mismatch_and_corrupt_metadata_are_rejected(self):
        negative=self.run_mask('Extract non-buildings in the whole image.')
        with self.assertRaisesRegex(ValueError,'same semantic target'):
            compare_bundles(self.bundle(self.whole),self.bundle(negative))
        folder=server.DATA/self.s['id']/self.right['id']
        path=folder/'statistics.json'
        stats=json.loads(path.read_text(encoding='utf-8'));stats['pixel_area']+=1
        path.write_text(json.dumps(stats),encoding='utf-8')
        with self.assertRaises(ValueError):compare_bundles(self.bundle(self.whole),self.bundle(self.right))

    def test_ledger_keeps_failures_blank_and_user_text_literal(self):
        self.s['name']='=HYPERLINK("example")'
        self.run_mask('Extract ships.')
        rows=list(csv.DictReader(io.StringIO(ledger_csv(self.s).lstrip('\ufeff'))))
        self.assertEqual(len(rows),3)
        self.assertTrue(rows[0]['experiment_name'].startswith("'="))
        self.assertEqual(rows[1]['foreground_pixels'],'37350')
        self.assertEqual(rows[1]['selected_region_pixels'],'240000')
        self.assertEqual(rows[-1]['status'],'failed')
        self.assertEqual(rows[-1]['foreground_pixels'],'')
        with self.assertRaises(ValueError):metadata_changes({'name':'','pinned':False})
        with self.assertRaises(ValueError):metadata_changes({'name':'valid','source':'forged'})
        with self.assertRaises(ValueError):metadata_changes({'pinned':'true'})

    def test_http_metadata_reload_and_comparison_preserve_artifacts(self):
        httpd=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        thread=threading.Thread(target=httpd.serve_forever,daemon=True);thread.start()
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def request(path,payload=None):
            req=urllib.request.Request(f'http://127.0.0.1:{httpd.server_port}'+path,
                data=json.dumps(payload).encode() if payload else None,
                headers={'Content-Type':'application/json'})
            with opener.open(req) as response:return response.read()
        original=server.DATA/self.s['id']/'original.png'
        before=hashlib.sha256(original.read_bytes()).hexdigest()
        try:
            request('/api/session/update',{'session_id':self.s['id'],'name':'Building inspection',
                'notes':'Compare the two measurement domains.','pinned':True})
            server.SESSIONS.clear();loaded=server.get_session(self.s['id'])
            self.assertEqual(loaded['name'],'Building inspection')
            self.assertTrue(loaded['pinned']);self.assertEqual(len(loaded['runs']),2)
            result=json.loads(request('/api/compare-results',{'session_id':self.s['id'],
                'run_a':self.whole['id'],'run_b':self.right['id']}))
            self.assertEqual(result['changed_pixels'],0)
            self.assertEqual(len(loaded['runs']),2)
            self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(),before)
            ledger=request('/api/ledger/'+self.s['id']).decode('utf-8-sig')
            self.assertIn('Building inspection',ledger)
            self.assertIn('within_region_coverage',ledger)
        finally:httpd.shutdown();httpd.server_close();thread.join()


if __name__=='__main__':unittest.main()
