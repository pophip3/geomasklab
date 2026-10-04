import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image
import server
from export_bundle import build_bundle, verify_bundle
from planner_protocol import parse_decision


class ResearchEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = Path(self.temp.name)
        self.patcher = patch.object(server,'DATA',self.data)
        self.patcher.start()
        session = server.new_session('urban')
        self.session = server.SESSIONS[session['id']]

    def tearDown(self):
        server.SESSIONS.clear()
        self.patcher.stop()
        self.temp.cleanup()

    def bundle(self, query='提取右侧建筑', **options):
        result = server.run_task(self.session,{'query':query,'mode':'demo',**options})
        self.assertIn(result['status'],('completed','needs_review'))
        folder = self.data / self.session['id'] / result['id']
        return build_bundle(self.data / self.session['id'] / 'original.png',folder)

    def rewrite(self, payload, mutate, rehash=False):
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            contents = {name:archive.read(name) for name in archive.namelist()}
        mutate(contents)
        if rehash:
            manifest = json.loads(contents['manifest.json'])
            for name, raw in contents.items():
                if name != 'manifest.json':
                    manifest['checksums'][name] = {'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
            contents['manifest.json'] = json.dumps(manifest).encode()
        result = io.BytesIO()
        with zipfile.ZipFile(result,'w',zipfile.ZIP_DEFLATED) as archive:
            for name,raw in contents.items():
                archive.writestr(name,raw)
        return result.getvalue()

    def test_scope_and_complement_replay(self):
        for query in ['提取右侧建筑','提取左侧建筑','把非建筑的部分标注出来']:
            with self.subTest(query=query):
                report = verify_bundle(self.bundle(query))
                self.assertTrue(report['verified'])
                self.assertFalse(report['semantic_accuracy_verified'])

    def test_roi_replay(self):
        roi={'xyxy':[80,50,280,250],'source':'drawn','image_size':[800,600]}
        report=verify_bundle(self.bundle('提取框选区域内的建筑',roi=roi,scope='all'))
        self.assertEqual(report['pixel_area'],12850)

    def test_changed_file_is_detected(self):
        payload = self.rewrite(self.bundle(), lambda c:c.update({'run_log.json':b'[]'}))
        with self.assertRaisesRegex(ValueError,'Checksum'):
            verify_bundle(payload)

    def test_rehashed_false_metrics_are_detected(self):
        def mutate(contents):
            stats = json.loads(contents['statistics.json'])
            stats['pixel_area'] += 1
            contents['statistics.json'] = json.dumps(stats).encode()
            result=json.loads(contents['result.json'])
            result['metrics']=stats
            contents['result.json']=json.dumps(result).encode()
        with self.assertRaisesRegex(ValueError,'Pixel statistics'):
            verify_bundle(self.rewrite(self.bundle(),mutate,True))

    def test_wrong_denominator_even_after_rehash_is_detected(self):
        def mutate(contents):
            stats=json.loads(contents['statistics.json'])
            stats['area_ratio'] *= 2
            contents['statistics.json']=json.dumps(stats).encode()
            result=json.loads(contents['result.json'])
            result['metrics']=stats
            contents['result.json']=json.dumps(result).encode()
        with self.assertRaisesRegex(ValueError,'denominator'):
            verify_bundle(self.rewrite(self.bundle(),mutate,True))

    def test_non_flat_member_is_rejected_without_extraction(self):
        payload=self.rewrite(self.bundle(),lambda c:c.update({'../outside.txt':b'unsafe'}))
        with self.assertRaisesRegex(ValueError,'archive paths'):
            verify_bundle(payload)

    def test_duplicate_member_is_rejected(self):
        output=io.BytesIO(self.bundle())
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',UserWarning)
            with zipfile.ZipFile(output,'a') as archive:
                archive.writestr('mask.png',b'wrong')
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            verify_bundle(output.getvalue())

    def test_planner_code_and_call_chains_fail_closed(self):
        allowed={'referring_expression_segmentation','semantic_segmentation'}
        for raw in ['T_call(semantic_segmentation,"x",__import__("os").system("echo bad"))',
                    'T_call(semantic_segmentation,"x",["building"]); T_call(semantic_segmentation,"y",["road"])',
                    'T_call(semantic_segmentation,"x",[["building"]])',
                    '<answer>T_call(semantic_segmentation,"x",["building"])</answer><answer>done</answer>']:
            self.assertEqual(parse_decision(raw,'bound.png',allowed).status,'unparsed')

    def test_planner_path_is_bound_and_feedback_cannot_execute(self):
        raw='T_call(semantic_segmentation,"/private/other-image.png",["aircraft"])'
        result=parse_decision(raw,'bound.png',{'semantic_segmentation'})
        self.assertEqual(result.tool_call.arguments['image_path'],str(Path('bound.png').resolve()))
        self.assertEqual(parse_decision(raw,'bound.png',set()).status,'rejected_tool')

    def test_roi_cannot_silently_intersect_inherited_half(self):
        first=server.run_task(self.session,{'query':'提取右侧建筑','mode':'demo'})
        roi={'xyxy':[80,50,280,250],'source':'drawn','image_size':[800,600]}
        rejected=server.run_task(self.session,{'query':'提取框选区域内的建筑','mode':'demo',
                                             'parent_run_id':first['id'],'roi':roi})
        self.assertEqual(rejected['status'],'failed')
        self.assertNotIn('mask_url',rejected)
        accepted=server.run_task(self.session,{'query':'提取框选区域内的建筑','mode':'demo',
                                             'parent_run_id':first['id'],'roi':roi,'scope':'all'})
        self.assertEqual(accepted['metrics']['pixel_area'],12850)


if __name__=='__main__':
    unittest.main()
