"""Test acceptance helpers with explicit fake workbench model boundaries only."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from examples import live_model_acceptance as acceptance
from workbench import server
from workbench.planner_protocol import Decision, ToolCall


def png(image):
    output = io.BytesIO()
    image.save(output, 'PNG')
    return output.getvalue()


class ExplicitFakeAgentTurn:
    calls = []
    scene_failed = False
    feedback_failed = False

    def __init__(self, query, image_path, context, side, scope_source, task_route='dense', **kwargs):
        self.calls.append((query, task_route))
        if task_route == 'internal':
            self.decision = (Decision('unparsed', '<answer>Explicit fake truncated response') if self.scene_failed else
                Decision('completed', '<answer>Explicit fake scene fixture.</answer>', text='Explicit fake scene fixture.'))
        else:
            self.decision = Decision('tool_call', 'Explicit fake fixture, not inference evidence.',
                tool_call=ToolCall('referring_expression_segmentation',
                                  {'image_path': str(Path(image_path).resolve()), 'prompt': 'all buildings'}))

    def feedback(self, payload):
        if self.feedback_failed:
            raise ValueError('Explicit fake feedback failure.')
        return Decision('completed', '<answer>Explicit fake completed feedback.</answer>',
                        text='Explicit fake completed feedback.')


class LiveAcceptanceHelperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / 'sessions'
        self.data.mkdir()
        self.output = self.root / 'report'
        self.image = self.root / 'fixture-image.png'
        self.image.write_bytes(png(Image.new('RGB', (13, 7), (40, 90, 120))))
        self.mask = Image.new('L', (13, 7), 0)
        for x in (0, 6, 12):
            for y in (0, 3, 6):
                self.mask.putpixel((x, y), 255)
        for patcher in (patch.object(server, 'DATA', self.data), patch.object(server, 'SESSIONS', {}),
                        patch.object(server, 'AgentTurn', ExplicitFakeAgentTurn),
                        patch.dict(os.environ, {'GEO_AGENT_MODEL': 'EXPLICIT-FAKE-ONLY',
                            'GEO_REMOTESAM_URL': 'http://example.invalid/predict',
                            'GEO_REMOTESAM_REVISION': 'explicit-fake-test-only'}, clear=True)):
            patcher.start()
            self.addCleanup(patcher.stop)
        ExplicitFakeAgentTurn.calls = []
        ExplicitFakeAgentTurn.scene_failed = False
        ExplicitFakeAgentTurn.feedback_failed = False
        self.sam = patch.object(server, 'post_json', side_effect=self.fake_sam)
        self.fake_request = self.sam.start()
        self.addCleanup(self.sam.stop)

    def fake_sam(self, url, payload, timeout=120, headers=None):
        self.assertEqual(payload['task'], 'referring_seg')
        self.assertEqual(payload['text'], 'all buildings')
        self.assertEqual(payload['quality_mode'], 'fast')
        return {'status': 'success', 'mask': server.image_b64(self.mask), 'quality_mode': 'fast',
                'model': {'identity': 'EXPLICIT-FAKE-TEST-ONLY', 'model_evidence': False}}

    def execute(self, **kwargs):
        return acceptance.run_acceptance(server, self.image, 'building', self.output,
            metadata_reader=lambda: {'available': True, 'metadata': {
                'backend': 'EXPLICIT-FAKE-TEST-ONLY', 'model_evidence': False}}, **kwargs)

    def test_live_driver_and_four_verified_exports_are_consistent_with_explicit_fake_pixels(self):
        report = self.execute()
        self.assertTrue(report['passed'], report['failures'])
        self.assertFalse(report['semantic_accuracy_verified'])
        self.assertEqual(report['human_participants'], 0)
        self.assertEqual(report['scene']['status'], 'answered')
        self.assertEqual(report['segmentation']['agent_feedback_status'], 'completed')
        self.assertEqual([(c['case'], c['foreground_pixels']) for c in report['cases']],
                         [('whole-image-live', 9), ('left-saved-mask', 3),
                          ('right-saved-mask', 6), ('rectangle-saved-mask', 1)])
        self.assertEqual([c['version'] for c in report['cases']], [2, 3, 4, 5])
        self.assertEqual([c['selected_region_pixels'] for c in report['cases']], [91, 42, 49, 24])
        self.assertTrue(all(c['bundle_verified'] and c['full_mask_bytes_preserved'] for c in report['cases']))
        self.assertTrue(all(c['inference_performed'] is False for c in report['cases'][1:]))
        self.assertEqual(len(ExplicitFakeAgentTurn.calls), 2)
        self.fake_request.assert_called_once()
        self.assertEqual(len(list(self.output.glob('*.zip'))), 4)
        saved = json.loads((self.output / 'summary.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['agent_metadata_probe']['metadata']['backend'], 'EXPLICIT-FAKE-TEST-ONLY')
        self.assertFalse(saved['agent_metadata_probe']['metadata']['model_evidence'])

    def test_failed_scene_is_recorded_while_independent_segmentation_and_replay_continue(self):
        ExplicitFakeAgentTurn.scene_failed = True
        report = self.execute()
        self.assertFalse(report['passed'])
        self.assertEqual(report['failures'][0]['stage'], 'scene')
        self.assertEqual(len(report['cases']), 4)
        self.fake_request.assert_called_once()

    def test_feedback_failure_preserves_verified_masks_but_does_not_pass_full_chain(self):
        ExplicitFakeAgentTurn.feedback_failed = True
        report = self.execute()
        self.assertFalse(report['passed'])
        self.assertEqual([f['stage'] for f in report['failures']], ['tool_feedback'])
        self.assertEqual(len(report['cases']), 4)
        self.assertTrue(all(c['bundle_verified'] for c in report['cases']))

    def test_missing_or_invalid_fresh_prediction_never_substitutes_a_demo_mask(self):
        self.fake_request.side_effect = lambda *args, **kwargs: {'status': 'success',
            'mask': server.image_b64(Image.new('L', (2, 2), 255)), 'quality_mode': 'fast'}
        report = self.execute()
        self.assertFalse(report['passed'])
        self.assertEqual(report['cases'], [])
        self.assertFalse(list(self.output.glob('*.zip')))
        self.assertEqual(report['failures'][-1]['stage'], 'segmentation_or_whole_export')

    def test_missing_input_writes_a_failure_report_and_performs_no_model_request(self):
        self.image.unlink()
        report = self.execute()
        self.assertFalse(report['passed'])
        self.assertEqual(report['failures'][0]['stage'], 'input')
        self.assertEqual(ExplicitFakeAgentTurn.calls, [])
        self.fake_request.assert_not_called()
        self.assertTrue((self.output / 'summary.json').is_file())

    def test_independent_pixel_checks_detect_count_ratio_and_selected_pixel_tampering(self):
        report = self.execute()
        whole = report['cases'][0]
        source = server.SESSIONS[report['session_id']]['runs'][1]
        folder = self.data / report['session_id'] / source['id']
        full = (folder / 'full_mask.png').read_bytes()
        mask = (folder / 'mask.png').read_bytes()
        for key, value in (('pixel_area', 8), ('total_pixels', 90), ('scope_area_pixels', 90),
                           ('area_ratio', 0.5), ('scope_area_ratio', 0.5)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                acceptance.independent_pixel_check(full, mask, (0, 0, 13, 7), {**source['metrics'], key: value})
        altered = self.mask.copy()
        altered.putpixel((0, 0), 0)
        altered.putpixel((1, 0), 255)
        with self.assertRaisesRegex(ValueError, 'pixel set'):
            acceptance.independent_pixel_check(full, png(altered), (0, 0, 13, 7), source['metrics'])
        self.assertEqual(whole['foreground_pixels'], 9)

    def test_public_summary_redacts_local_paths_service_urls_and_bearer_credentials(self):
        cleaned = acceptance.public_summary_value({'checkpoint_path': r'C:\private\weights.pth',
            'metadata': {'note': 'http://127.0.0.1:8000 private 192.168.0.7 Bearer fixture-secret',
                         'checkpoint_sha256': 'public-checksum', 'max_context_tokens': 4096},
            'note': r'Loading C:\private\model files'})
        text = json.dumps(cleaned)
        for secret in ('C:\\private', '127.0.0.1', '192.168.0.7', 'fixture-secret'):
            self.assertNotIn(secret, text)
        self.assertEqual(cleaned['metadata']['checkpoint_sha256'], 'public-checksum')
        self.assertEqual(cleaned['metadata']['max_context_tokens'], 4096)

    def test_input_normalization_applies_exif_orientation_before_workbench_upload(self):
        image = Image.new('RGB', (3, 2), 'white')
        image.putpixel((0, 0), (255, 0, 0))
        exif = image.getexif()
        exif[274] = 6
        path = self.root / 'rotated.jpg'
        image.save(path, 'JPEG', exif=exif)
        _, data, normalized = acceptance.normalize_input(path)
        self.assertEqual(normalized.size, (2, 3))
        with Image.open(io.BytesIO(data)) as saved:
            self.assertEqual(saved.size, (2, 3))
            self.assertNotIn(274, saved.getexif())


class LiveAcceptanceCLITests(unittest.TestCase):
    def test_help_imports_no_heavy_dependencies_and_does_not_contact_services(self):
        root = Path(__file__).resolve().parents[1]
        code = """
import builtins, runpy, sys
original = builtins.__import__
def guard(name, *args, **kwargs):
    if name.split('.')[0] in {'torch', 'transformers', 'accelerate', 'vllm', 'openai'} or name == 'workbench':
        raise AssertionError('Help must not import services or model runtime: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guard
sys.argv = ['live_model_acceptance', '--help']
runpy.run_module('examples.live_model_acceptance', run_name='__main__')
"""
        result = subprocess.run([sys.executable, '-B', '-c', code], cwd=root,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--target', result.stdout)
        self.assertIn('--timeout', result.stdout)

    def test_invalid_timeout_cli_exits_before_any_model_request(self):
        root = Path(__file__).resolve().parents[1]
        for value in ('4', '3601', 'nan', 'inf'):
            with self.subTest(value=value):
                result = subprocess.run([sys.executable, '-B', 'examples/live_model_acceptance.py', '--timeout', value],
                                        cwd=root, capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn('--timeout must be finite', result.stderr)


if __name__ == '__main__':
    unittest.main()
