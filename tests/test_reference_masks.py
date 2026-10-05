"""External-mask round trips and independently counted reference assessment."""
import base64
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from PIL import Image
import server
from export_bundle import build_bundle, load_verified_bundle
from mask_inputs import binary_png
from reference_evaluation import evaluate_reference, evaluation_packet, verify_reference_packet


def png(image):
    out=io.BytesIO();image.save(out,'PNG');return out.getvalue()


class ReferenceMaskTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patches=[patch.object(server,'DATA',Path(self.temp.name)),patch.object(server,'SESSIONS',{}),
                      patch.object(server,'post_json',side_effect=AssertionError('No model inference permitted'))]
        for p in self.patches:p.start()
        # The 5x3 grid tests odd midpoint geometry and hand-countable confusion.
        image=base64.b64encode(png(Image.new('RGB',(5,3),'#345267'))).decode()
        self.s=server.SESSIONS[server.new_session(uploaded=image)['id']]
        pred=Image.new('L',(5,3));pred.putdata([255,255,0,255,0, 0,255,0,0,0, 0,0,0,0,0])
        ref=Image.new('L',(5,3));ref.putdata([255,0,255,255,0, 0,255,0,0,0, 0,0,0,0,0])
        self.pred,self.ref=png(pred),png(ref)
        self.run=self.imported(self.pred)

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def imported(self,raw,**fields):
        return server.import_mask(self.s,{'mask':base64.b64encode(raw).decode(),'target':'building',
                                         'source':'Hand-counted procedural test prediction.','aligned':True,**fields})

    def bundle(self,run=None):
        return build_bundle(server.DATA/self.s['id']/'original.png',server.DATA/self.s['id']/(run or self.run)['id'])

    def evaluate(self,run=None,ref=None):
        return evaluate_reference(self.bundle(run),ref or self.ref,source='Hand-counted procedural labels.',
                                  target='building',independent=False,created_at='2026-10-05T00:00:00Z')

    def test_import_roundtrip_review_and_offline_region_retain_origin(self):
        facts,files=load_verified_bundle(self.bundle())
        self.assertEqual(facts['pixel_area'],4);self.assertEqual(self.run['mode'],'external')
        self.assertFalse(self.run['inference_performed']);self.assertEqual(self.run['semantic_review']['state'],'pending')
        self.assertEqual(files['source_mask.png'],self.pred)
        restored=server.import_evidence({'bundle':base64.b64encode(self.bundle()).decode(),'name':'external.zip'})
        self.assertEqual(restored['runs'][0]['external_mask'],self.run['external_mask'])
        region=server.recalculate_region(self.s,{'run_id':self.run['id'],'scope':'right'})
        _,derived=load_verified_bundle(self.bundle(region))
        self.assertEqual(derived['source_mask.png'],self.pred)
        self.assertEqual(region['source_prediction']['mode'],'external')
        report=(server.DATA/self.s['id']/self.run['id']/'report.md').read_text(encoding='utf-8')
        self.assertIn('imported without model inference',report)

    def test_confusion_is_manually_counted_not_prediction_agreement(self):
        result,_=self.evaluate()
        self.assertEqual(result['counts'],{'tp':3,'fp':1,'fn':1,'tn':10})
        self.assertEqual(result['evaluated_pixels'],15)
        self.assertEqual(result['metrics']['iou'],3/5);self.assertEqual(result['metrics']['dice'],6/8)
        self.assertEqual(result['metrics']['precision'],3/4);self.assertEqual(result['metrics']['recall'],3/4)
        self.assertEqual(result['metrics']['pixel_accuracy'],13/15)
        self.assertFalse(result['reference']['independent_user_assertion'])

    def test_odd_half_roi_and_complement_use_only_saved_domain(self):
        right=server.recalculate_region(self.s,{'run_id':self.run['id'],'scope':'right'})
        result,_=self.evaluate(right)
        self.assertEqual(result['counts'],{'tp':1,'fp':0,'fn':1,'tn':7})
        self.assertEqual(result['evaluated_pixels'],9)
        roi={'xyxy':[0,0,2,2],'source':'drawn','image_size':[5,3]}
        cut=server.recalculate_region(self.s,{'run_id':self.run['id'],'scope':'all','roi':roi})
        result,_=self.evaluate(cut)
        self.assertEqual(result['counts'],{'tp':2,'fp':1,'fn':0,'tn':1})
        # Create a valid complement record through the existing executor's
        # demo fixture path, without changing the supplied positive-target ref.
        demo=server.SESSIONS[server.new_session('urban')['id']]
        negative=server.run_task(demo,{'query':'Extract non-buildings in the right half.','mode':'demo'})
        raw=build_bundle(server.DATA/demo['id']/'original.png',server.DATA/demo['id']/negative['id'])
        reference=png(server.demo_mask('urban'))
        result,_=evaluate_reference(raw,reference,source='Procedural fixture, not independent.',target='building',independent=False,created_at='test')
        self.assertEqual(result['counts'],{'tp':202650,'fp':0,'fn':0,'tn':37350})

    def test_empty_union_and_zero_prediction_are_undefined_not_perfect(self):
        zero=png(Image.new('L',(5,3)))
        empty=self.imported(zero)
        result,_=self.evaluate(empty,zero)
        for key in ('iou','dice','precision','recall'):self.assertIsNone(result['metrics'][key])
        self.assertEqual(result['metrics']['pixel_accuracy'],1)
        result,_=self.evaluate(empty)
        self.assertEqual(result['metrics']['iou'],0);self.assertEqual(result['metrics']['recall'],0)
        self.assertIsNone(result['metrics']['precision'])

    def test_strict_binary_validation_rejects_silent_conversion(self):
        for im in (Image.new('L',(4,3)),Image.new('L',(5,3),127),Image.new('RGB',(5,3),'red'),
                   Image.new('P',(5,3)),Image.new('RGBA',(5,3),(255,255,255,0))):
            with self.assertRaises(ValueError):binary_png(png(im),(5,3))
        one=Image.new('L',(5,3),1)
        self.assertEqual(binary_png(png(one),(5,3)).histogram()[255],15)
        self.assertEqual(binary_png(png(Image.new('RGB',(5,3),'white')),(5,3)).histogram()[255],15)
        mixed=Image.new('L',(5,3));mixed.putdata([0,1,255]*5)
        with self.assertRaises(ValueError):binary_png(png(mixed),(5,3))

    def test_invalid_inputs_leave_previous_runs_and_pixels_unchanged(self):
        before=self.bundle();count=len(self.s['runs'])
        with self.assertRaises(ValueError):self.imported(png(Image.new('L',(2,2))))
        with self.assertRaises(ValueError):self.imported(self.pred,parent_run_id='ffffffffffff')
        with self.assertRaises(ValueError):evaluate_reference(before,self.ref,source='test',target='aircraft',independent=True,created_at='test')
        with self.assertRaises(ValueError):evaluate_reference(before,self.ref,source='',target='building',independent=True,created_at='test')
        with self.assertRaises(ValueError):server.assess_reference(self.s,{'run_id':self.run['id'],'aligned':False,'reference':base64.b64encode(self.ref).decode()})
        self.assertEqual(len(self.s['runs']),count);self.assertEqual(load_verified_bundle(self.bundle())[1],load_verified_bundle(before)[1])

    def test_packet_inputs_hashes_and_recomputation_without_mutation(self):
        before=self.bundle();result,difference=self.evaluate()
        packet=evaluation_packet(result,difference,before,self.ref)
        self.assertTrue(verify_reference_packet(packet)['verified'])
        with zipfile.ZipFile(io.BytesIO(packet)) as z:
            manifest=json.loads(z.read('manifest.json'))
            for name,identity in manifest['checksums'].items():
                self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(),identity['sha256'])
                self.assertEqual(len(z.read(name)),identity['bytes'])
            again,_=evaluate_reference(z.read('prediction.zip'),z.read('reference.png'),source=result['reference']['source'],
                target='building',independent=False,created_at=result['created_at'])
            self.assertEqual(again,result)
        self.assertEqual(load_verified_bundle(self.bundle())[1],load_verified_bundle(before)[1]);self.assertEqual(len(self.s['runs']),1)

    def test_empty_half_has_no_evaluated_pixels_or_defined_scores(self):
        image=base64.b64encode(png(Image.new('RGB',(1,2)))).decode()
        session=server.SESSIONS[server.new_session(uploaded=image)['id']]
        raw=png(Image.new('L',(1,2)))
        run=server.import_mask(session,{'mask':base64.b64encode(raw).decode(),'target':'building',
            'source':'Empty procedural grid.','aligned':True})
        left=server.recalculate_region(session,{'run_id':run['id'],'scope':'left'})
        bundle=build_bundle(server.DATA/session['id']/'original.png',server.DATA/session['id']/left['id'])
        record,_=evaluate_reference(bundle,raw,source='Procedural empty reference.',target='building',independent=False,created_at='test')
        self.assertEqual(record['evaluated_pixels'],0)
        self.assertEqual(record['counts'],dict.fromkeys(('tp','fp','fn','tn'),0))
        self.assertTrue(all(v is None for v in record['metrics'].values()))

    def test_resigned_forged_scores_are_rejected_by_pixel_replay(self):
        result,difference=self.evaluate()
        result['metrics']['iou']=1
        forged=evaluation_packet(result,difference,self.bundle(),self.ref)
        with self.assertRaisesRegex(ValueError,'recomputed pixels'):
            verify_reference_packet(forged)

    def test_http_upload_assessment_download_survive_session_reload(self):
        httpd=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        thread=threading.Thread(target=httpd.serve_forever,daemon=True);thread.start()
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def request(path,payload=None):
            req=urllib.request.Request(f'http://127.0.0.1:{httpd.server_port}'+path,
                data=json.dumps(payload).encode() if payload else None,headers={'Content-Type':'application/json'})
            with opener.open(req) as response:return response.read(),response.headers
        try:
            raw,_=request('/api/import-mask',{'session_id':self.s['id'],'mask':base64.b64encode(self.pred).decode(),
                'source':'Procedural HTTP acceptance.','target':'building','aligned':True})
            imported=json.loads(raw);before=len(self.s['runs'])
            raw,_=request('/api/evaluate-reference',{'session_id':self.s['id'],'run_id':imported['id'],
                'reference':base64.b64encode(self.ref).decode(),'source':'Procedural labels.',
                'target':'building','aligned':True,'independent':False})
            result=json.loads(raw)
            server.SESSIONS.clear()
            packet,headers=request(result['packet_url'])
            self.assertIn('attachment',headers['Content-Disposition'])
            self.assertEqual(verify_reference_packet(packet)['counts'],{'tp':3,'fp':1,'fn':1,'tn':10})
            self.assertEqual(len(server.get_session(self.s['id'])['runs']),before)
        finally:httpd.shutdown();httpd.server_close();thread.join()


if __name__=='__main__':unittest.main()
