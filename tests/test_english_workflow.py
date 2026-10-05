"""English acceptance scenarios using the public executor and exported artifacts."""
import json
import re
import tempfile
import unittest
import zipfile
import io
from pathlib import Path
from unittest.mock import patch
import server
from export_bundle import build_bundle, verify_bundle
from task_grammar import requires_dense_result, resolve_invert, is_export_command


class EnglishWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(server, 'DATA', Path(self.temp.name)), patch.object(server, 'SESSIONS', {}),
                        patch.object(server, 'post_json', side_effect=AssertionError('Offline acceptance must not call models'))]
        for item in self.patches: item.start()
        self.session = server.SESSIONS[server.new_session('urban')['id']]

    def tearDown(self):
        for item in reversed(self.patches): item.stop()
        self.temp.cleanup()

    def run_task(self, query, **options):
        return server.run_task(self.session, {'query': query, 'mode': 'demo', **options})

    def assert_english(self, value):
        self.assertIsNone(re.search(r'[\u3400-\u9fff]', value), value)

    def test_whole_halves_and_followup_branch(self):
        whole = self.run_task('Extract buildings in the whole image.')
        right = self.run_task('Switch to the right half.', parent_run_id=whole['id'])
        left = self.run_task('Switch to the left half.', parent_run_id=whole['id'])
        self.assertEqual([r['metrics']['pixel_area'] for r in (whole, right, left)], [75350, 37350, 38000])
        self.assertEqual(right['parent_run_id'], whole['id'])
        self.assertEqual(left['parent_run_id'], whole['id'])
        self.assertTrue(right['task']['inherited_target'])

    def test_roi_review_and_new_generated_bundle_are_english(self):
        result = self.run_task('Extract buildings in the selected region.', roi={
            'xyxy': [80, 50, 280, 250], 'source': 'drawn', 'image_size': [800, 600]})
        self.assertEqual(result['metrics']['pixel_area'], 12850)
        self.assertEqual(result['metrics']['scope_area_pixels'], 40000)
        self.assertAlmostEqual(result['metrics']['scope_area_ratio'], .32125)
        server.review_result(self.session, {'run_id': result['id'], 'decision': 'pending',
            'reviewer': 'AUTOMATED LANGUAGE ACCEPTANCE',
            'note': 'Language and artifact checks only; not a human semantic assessment.'})
        bundle = build_bundle(server.DATA/self.session['id']/'original.png', server.DATA/self.session['id']/result['id'])
        self.assertTrue(verify_bundle(bundle)['verified'])
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            for name in archive.namelist():
                if name.endswith(('.json', '.md')):
                    self.assert_english(archive.read(name).decode('utf-8'))

    def test_english_complement_and_positive_override(self):
        complement = self.run_task('Extract non-buildings in the right half.')
        self.assertTrue(complement['task']['invert'])
        self.assertEqual(complement['metrics']['pixel_area'], 202650)
        positive = self.run_task('Extract only buildings in the right half.', parent_run_id=complement['id'])
        self.assertFalse(positive['task']['invert'])
        self.assertEqual(positive['metrics']['pixel_area'], 37350)

    def test_scene_clarification_and_failure_are_english(self):
        for query, expected in [('Describe the scene in this image.', 'answered'),
                                ('Extract that region.', 'needs_clarification'),
                                ('Extract buildings near the road.', 'needs_clarification'),
                                ('Extract ships.', 'failed')]:
            result = self.run_task(query)
            self.assertEqual(result['status'], expected, result)
            self.assert_english(json.dumps(result, ensure_ascii=False))
            self.assertNotIn('mask_url', result)

    def test_export_command_does_not_call_models_or_create_a_mask(self):
        result = self.run_task('Extract buildings.')
        exported = self.run_task('Export the selected result.', parent_run_id=result['id'])
        self.assertEqual(exported['status'], 'export_ready')
        self.assertEqual(exported['export_url'], result['export_url'])
        self.assertNotIn('mask_url', exported)
        self.assertTrue(is_export_command('Download the evidence bundle.'))
        self.assertFalse(is_export_command('Extract buildings and export a result.'))

    def test_dense_routes_for_english_scopes_and_coverage(self):
        for query in ['Extract aircraft.', 'Calculate coverage.', 'Annotate the mask.']:
            self.assertTrue(requires_dense_result(query))
        self.assertTrue(requires_dense_result('Switch to the bottom half.', {'target': 'building'}))
        self.assertFalse(requires_dense_result('Describe the scene.'))
        self.assertTrue(resolve_invert('Extract non-aircraft.'))
        self.assertFalse(resolve_invert('Extract only aircraft.', {'invert': True}))


if __name__ == '__main__':
    unittest.main()
