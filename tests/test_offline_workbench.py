"""HTTP-to-core replay, explicit batch isolation and portable upload safety."""
import base64
from copy import deepcopy
import io
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer

import _source_package
_source_package.use_local_core()
from PIL import Image
from geomasklab.batch import verify_batch_packet
from geomasklab.comparison import verify_comparison_packet
from geomasklab.components import verify_component_packet
from geomasklab.domain import png
from geomasklab.evidence import load_verified_bundle
from geomasklab.reference import verify_reference_packet
from workbench import offline_workflows, server


class QuietHandler(server.Handler):
    def log_message(self, format, *args):
        pass


class OfflineWorkbench(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.patches = [patch.object(server, 'DATA', self.root), patch.object(server, 'SESSIONS', {}),
                        patch.object(offline_workflows, 'JOBS', {}),
                        patch.object(server, 'post_json', side_effect=AssertionError('Offline workflows must not call model services.'))]
        for item in self.patches:
            item.start()
        self.httpd = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        self.thread = threading.Thread(target=lambda: self.httpd.serve_forever(poll_interval=.01), daemon=True)
        self.thread.start()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.release_events = []
        self.image = png(Image.new('RGB', (8, 6), '#356259'))
        mask = Image.new('L', (8, 6)); mask.paste(255, (2, 1, 6, 4))
        self.mask = png(mask)
        valid = Image.new('L', (8, 6)); valid.paste(255, (0, 0, 4, 6))
        self.valid = png(valid)
        self.session = self.json_request('/api/session', {'image': self.encode(self.image), 'name': 'Hand-counted HTTP workflow'})

    def tearDown(self):
        for event in self.release_events:
            event.set()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with offline_workflows.JOBS_LOCK:
                active = any(job['public']['status'] in ('running', 'cancelling') for job in offline_workflows.JOBS.values())
            if not active:
                break
            time.sleep(.01)
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)
        for item in reversed(self.patches):
            item.stop()
        self.temporary.cleanup()

    @staticmethod
    def encode(raw):
        return base64.b64encode(raw).decode('ascii')

    def request(self, path, payload=None, *, status=200):
        request = urllib.request.Request('http://127.0.0.1:'+str(self.httpd.server_port)+path,
            data=json.dumps(payload).encode('utf-8') if payload is not None else None,
            headers={'Content-Type': 'application/json'})
        try:
            response = self.opener.open(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read()
            self.assertEqual(response.status, status, raw.decode('utf-8', errors='replace')[:500])
            return raw

    def json_request(self, path, payload=None, *, status=200):
        return json.loads(self.request(path, payload, status=status))

    def import_mask(self, *, valid=False, raw=None):
        payload = {'session_id': self.session['id'], 'mask': self.encode(raw or self.mask),
                   'target': 'building', 'source': 'Hand-counted HTTP mask fixture', 'aligned': True}
        if valid:
            payload.update(valid_mask=self.encode(self.valid), valid_source='Explicit left-half HTTP validity fixture')
        return self.json_request('/api/import-mask', payload)

    def compare(self, a, b, **options):
        return self.json_request('/api/compare-results', {'session_id': self.session['id'],
            'run_a': a['id'], 'run_b': b['id'], **options})

    def fixture_batch(self, *, failure=False):
        sample = {'id': 'first', 'image': 'image.png', 'mask': 'mask.png', 'target': 'building',
                  'source': 'Explicit HTTP batch fixture', 'aligned': True,
                  'valid_mask': 'valid.png', 'valid_source': 'Left-half HTTP batch validity'}
        second = {**sample, 'id': 'second', 'mask': 'missing.png' if failure else 'mask.png'}
        return {'manifest': {'schema': 'geomasklab-batch-manifest/1.0', 'samples': [sample, second]},
                'files': [{'name': name, 'data': self.encode(raw)} for name, raw in
                          [('image.png', self.image), ('mask.png', self.mask), ('valid.png', self.valid)]]}

    def wait_batch(self, identifier):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            result = self.json_request('/api/offline-batch/'+identifier)
            if result['status'] not in ('running', 'cancelling'):
                return result
            time.sleep(.01)
        self.fail('Offline batch did not finish within the small-fixture timeout.')

    def test_comparison_condition_accounting_and_prediction_difference_replay(self):
        whole = self.import_mask()
        restricted = self.import_mask(valid=True)
        result = self.compare(whole, restricted, domain_policy='intersection')
        self.assertEqual(result['change_kind'], 'Analysis_Conditions_Only')
        self.assertEqual(result['common_scope_pixels'], 24)
        self.assertEqual(result['changed_pixels'], 0)
        self.assertEqual(result['foreground_change_accounting']['saved_total_delta_pixels'], -6)
        self.assertEqual(result['foreground_change_accounting']['common_domain_delta_pixels'], 0)
        self.assertEqual(result['foreground_change_accounting']['excluded_domain_delta_pixels'], -6)
        packet = self.request(result['packet_url'])
        self.assertTrue(verify_comparison_packet(packet)['verified'])
        dispatched = self.json_request('/api/verify-review-packet', {'packet': self.encode(packet)})
        self.assertEqual(dispatched['kind'], 'comparison')
        self.assertEqual(dispatched['comparison']['change_kind'], 'Analysis_Conditions_Only')
        with Image.open(io.BytesIO(self.mask)) as original:
            changed = original.copy()
        changed.putpixel((2, 1), 0)
        changed.putpixel((1, 4), 255)
        third = self.import_mask(valid=True, raw=png(changed))
        compared = self.compare(restricted, third, domain_policy='identical')
        self.assertEqual(compared['change_kind'], 'Prediction_Only')
        self.assertEqual((compared['a_only_pixels'], compared['b_only_pixels']), (1, 1))
        self.assertEqual(compared['mask_agreement_iou'], 5/7)
        self.assertTrue(verify_comparison_packet(self.request(compared['packet_url']))['verified'])
        self.assertEqual(len(server.SESSIONS[self.session['id']]['runs']), 3)

    def test_identical_policy_rejection_and_disjoint_domain_export(self):
        whole = self.import_mask()
        restricted = self.import_mask(valid=True)
        error = self.json_request('/api/compare-results', {'session_id': self.session['id'],
            'run_a': whole['id'], 'run_b': restricted['id'], 'domain_policy': 'identical'}, status=400)
        self.assertIn('Incompatible_Analysis_Domains', error['error'])
        right = self.json_request('/api/recalculate-region', {'session_id': self.session['id'],
            'run_id': whole['id'], 'scope': 'right'})
        result = self.compare(restricted, right)
        self.assertEqual(result['status'], 'No_Common_Valid_Domain')
        self.assertFalse(result['pixel_diff_available'])
        self.assertIsNone(result['difference_png_base64'])
        self.assertIsNone(result['mask_agreement_iou'])
        packet = self.request(result['packet_url'])
        with zipfile.ZipFile(io.BytesIO(packet)) as archive:
            self.assertNotIn('difference.png', archive.namelist())
            self.assertNotIn('difference-classes.png', archive.namelist())
        self.assertTrue(verify_comparison_packet(packet)['verified'])

    def test_inspection_boundary_selection_and_packet_dispatch_preserve_source(self):
        restricted = self.import_mask(valid=True)
        before = self.request(restricted['export_url'])
        result = self.json_request('/api/inspect-components', {'session_id': self.session['id'],
            'run_id': restricted['id'], 'min_area_pixels': 10, 'boundary_filter': 'all'})
        self.assertEqual(result['foreground_pixels'], 6)
        self.assertEqual(result['component_count'], 1)
        self.assertEqual(result['selected_component_count'], 0)
        component = result['components'][0]
        self.assertEqual(component['bbox'], [2, 1, 4, 4])
        self.assertTrue(component['touches_invalid_boundary'])
        self.assertFalse(component['touches_image_boundary'])
        packet = self.request(result['packet_url'])
        self.assertTrue(verify_component_packet(packet)['verified'])
        dispatched = self.json_request('/api/verify-review-packet', {'packet': self.encode(packet)})
        self.assertEqual(dispatched['kind'], 'components')
        self.assertEqual(dispatched['selected_foreground_pixels'], 0)
        self.assertEqual(load_verified_bundle(before)[1], load_verified_bundle(self.request(restricted['export_url']))[1])
        self.assertEqual(len(server.SESSIONS[self.session['id']]['runs']), 1)

    def test_explicit_batch_failure_isolated_and_public_packet_replays(self):
        result = self.json_request('/api/offline-batch/start', self.fixture_batch(failure=True))
        final = self.wait_batch(result['id'])
        self.assertEqual(final['status'], 'completed_with_errors')
        summary = final['summary']
        self.assertEqual((summary['completed_count'], summary['failed_count']), (1, 1))
        self.assertEqual(summary['aggregate']['macro_mean_coverage'], 6/24)
        self.assertEqual(summary['aggregate']['micro_weighted_coverage'], 6/24)
        self.assertIsNone(summary['samples'][1]['foreground_pixels'])
        self.assertNotIn(str(self.root), json.dumps(summary))
        packet = self.request(final['packet_url'])
        facts = verify_batch_packet(packet)
        self.assertEqual((facts['completed_count'], facts['failed_count']), (1, 1))
        with zipfile.ZipFile(io.BytesIO(packet)) as archive:
            self.assertNotIn('debug.log', archive.namelist())
            self.assertNotIn('second/evidence.zip', archive.namelist())
        dispatched = self.json_request('/api/verify-review-packet', {'packet': self.encode(packet)})
        self.assertEqual(dispatched['kind'], 'batch')
        self.assertEqual(dispatched['failed_count'], 1)

    def test_completed_batch_result_opens_source_preserving_session_and_continues_workflow(self):
        result = self.json_request('/api/offline-batch/start', self.fixture_batch(failure=True))
        final = self.wait_batch(result['id'])
        folder = self.root / 'offline-batches' / result['id'] / 'output' / 'first'
        original_evidence = (folder / 'evidence.zip').read_bytes()
        opened = self.json_request('/api/offline-batch/open-result', {'id': result['id'], 'sample_id': 'first'})
        self.assertNotEqual(opened['id'], self.session['id'])
        self.assertEqual(len(opened['runs']), 1)
        run = opened['runs'][0]
        self.assertEqual(run['metrics']['pixel_area'], 6)
        self.assertEqual(run['metrics']['validity_measurements']['valid_region_pixels'], 24)
        restored_packet = self.request(run['export_url'])
        _, files = load_verified_bundle(restored_packet)
        self.assertEqual(files['source_mask.png'], self.mask)
        self.assertEqual(files['source_valid_mask.png'], self.valid)
        self.assertEqual((self.root / opened['id'] / 'source-evidence.zip').read_bytes(), original_evidence)
        roi = {'xyxy': [2, 1, 4, 4], 'source': 'imported', 'image_size': [8, 6]}
        derived = self.json_request('/api/recalculate-region', {'session_id': opened['id'],
            'run_id': run['id'], 'scope': 'all', 'roi': roi})
        self.assertEqual(derived['metrics']['pixel_area'], 6)
        self.assertEqual(derived['metrics']['validity_measurements']['valid_region_pixels'], 6)
        self.assertEqual(derived['metrics']['validity_measurements']['coverage_of_valid_region'], 1)
        self.assertFalse(derived['inference_performed'])
        self.assertEqual(derived['semantic_review']['state'], 'pending')
        self.assertTrue(load_verified_bundle(self.request(derived['export_url']))[0]['verified'])
        assessment = self.json_request('/api/evaluate-reference', {'session_id': opened['id'],
            'run_id': derived['id'], 'reference': self.encode(self.mask), 'target': 'building', 'aligned': True,
            'source': 'Same hand-counted pixels for a workflow test; no independent accuracy claim', 'independent': False})
        self.assertEqual(assessment['counts'], {'tp': 6, 'fp': 0, 'fn': 0, 'tn': 0})
        self.assertEqual(assessment['evaluated_pixels'], 6)
        assessment_packet = self.request(assessment['packet_url'])
        self.assertTrue(verify_reference_packet(assessment_packet)['verified'])
        dispatched = self.json_request('/api/verify-review-packet', {'packet': self.encode(assessment_packet)})
        self.assertEqual(dispatched['kind'], 'reference')
        self.assertFalse(dispatched['independent_reference_verified'])
        self.assertEqual((folder / 'evidence.zip').read_bytes(), original_evidence)
        self.assertTrue(verify_batch_packet(self.request(final['packet_url']))['verified'])

    def test_open_batch_result_rejects_failed_missing_and_traversal_samples(self):
        result = self.json_request('/api/offline-batch/start', self.fixture_batch(failure=True))
        self.wait_batch(result['id'])
        before_sessions = set(server.SESSIONS)
        for sample_id in ('second', 'missing', '../first', '/first', None, ['first']):
            with self.subTest(sample_id=sample_id):
                self.json_request('/api/offline-batch/open-result', {'id': result['id'], 'sample_id': sample_id}, status=400)
                self.assertEqual(set(server.SESSIONS), before_sessions)
        for job_id in ('../escape', '0' * 12, None):
            with self.subTest(job_id=job_id):
                self.json_request('/api/offline-batch/open-result', {'id': job_id, 'sample_id': 'first'}, status=400)
                self.assertEqual(set(server.SESSIONS), before_sessions)

    def test_open_batch_result_rejects_corrupt_saved_evidence_without_creating_session(self):
        result = self.json_request('/api/offline-batch/start', self.fixture_batch())
        self.wait_batch(result['id'])
        before_sessions = set(server.SESSIONS)
        folder = self.root / 'offline-batches' / result['id'] / 'output' / 'first'
        (folder / 'evidence.zip').write_bytes(b'Invalid replacement evidence')
        self.json_request('/api/offline-batch/open-result', {'id': result['id'], 'sample_id': 'first'}, status=400)
        self.assertEqual(set(server.SESSIONS), before_sessions)

    def test_cancel_then_verified_resume_preserves_already_completed_bytes(self):
        entered = threading.Event()
        release = threading.Event()
        self.release_events.append(release)
        original_run = offline_workflows.run_batch
        def paused(*args, **kwargs):
            original_progress = kwargs['progress']
            def progress(summary):
                original_progress(summary)
                if summary['completed_count'] == 1 and summary['pending_count'] == 1:
                    entered.set()
                    if not release.wait(timeout=5):
                        raise ValueError('Test fixture release timed out.')
            kwargs['progress'] = progress
            return original_run(*args, **kwargs)
        with patch.object(offline_workflows, 'run_batch', side_effect=paused):
            result = self.json_request('/api/offline-batch/start', self.fixture_batch())
            self.assertTrue(entered.wait(timeout=3))
            busy = self.json_request('/api/offline-batch/resume', {'id': result['id']}, status=400)
            self.assertIn('still running', busy['error'])
            cancelled = self.json_request('/api/offline-batch/cancel', {'id': result['id']})
            self.assertEqual(cancelled['status'], 'cancelling')
            release.set()
            final = self.wait_batch(result['id'])
        self.assertEqual(final['status'], 'cancelled')
        self.assertEqual((final['summary']['completed_count'], final['summary']['cancelled_count']), (1, 1))
        first = self.root / 'offline-batches' / result['id'] / 'output' / 'first' / 'evidence.zip'
        original_bytes = first.read_bytes()
        self.assertTrue(verify_batch_packet(self.request(final['packet_url']))['verified'])
        self.json_request('/api/offline-batch/resume', {'id': result['id']})
        resumed = self.wait_batch(result['id'])
        self.assertEqual(resumed['status'], 'completed')
        self.assertEqual(resumed['summary']['completed_count'], 2)
        self.assertEqual(first.read_bytes(), original_bytes)
        self.assertTrue(verify_batch_packet(self.request(resumed['packet_url']))['verified'])

    def test_restored_interrupted_status_and_resume_revalidate_existing_artifacts(self):
        result = self.json_request('/api/offline-batch/start', self.fixture_batch())
        final = self.wait_batch(result['id'])
        self.assertEqual(final['status'], 'completed')
        folder = self.root / 'offline-batches' / result['id']
        before = (folder / 'output' / 'first' / 'evidence.zip').read_bytes()
        saved = json.loads((folder / 'job.json').read_text(encoding='utf-8'))
        saved['status'] = 'running'
        (folder / 'job.json').write_text(json.dumps(saved), encoding='utf-8')
        offline_workflows.JOBS.clear()
        restored = self.json_request('/api/offline-batch/'+result['id'])
        self.assertEqual(restored['status'], 'interrupted')
        self.json_request('/api/offline-batch/resume', {'id': result['id']})
        resumed = self.wait_batch(result['id'])
        self.assertEqual(resumed['status'], 'completed')
        self.assertEqual((folder / 'output' / 'first' / 'evidence.zip').read_bytes(), before)
        self.assertTrue(verify_batch_packet(self.request(resumed['packet_url']))['verified'])

    def test_previous_worker_cannot_overwrite_resumed_generation_job_receipt(self):
        # Pause the previous worker after it publishes terminal in-memory state
        # but before its finally block reacquires the job lock. A legitimate
        # resume is accepted in exactly this interval and owns the new receipt.
        previous_terminal = threading.Event()
        release_previous = threading.Event()
        resume_entered = threading.Event()
        release_resume = threading.Event()
        self.release_events.extend([release_previous, release_resume])
        previous_threads = []
        original_lock = offline_workflows.JOBS_LOCK
        original_run = offline_workflows.run_batch
        class PauseAfterTerminalPublication:
            def __enter__(self):
                original_lock.acquire()
                return self
            def __exit__(self, *args):
                current = threading.current_thread()
                should_pause = (current.name.startswith('geomasklab-offline-') and
                    not previous_terminal.is_set() and any(
                        job['public']['status'] == 'completed' and job['public']['resume'] is False
                        for job in offline_workflows.JOBS.values()))
                if should_pause:
                    previous_threads.append(current)
                original_lock.release()
                if should_pause:
                    previous_terminal.set()
                    if not release_previous.wait(timeout=5):
                        raise ValueError('Previous-worker barrier timed out.')
        def controlled_run(*args, **kwargs):
            if kwargs['resume']:
                resume_entered.set()
                if not release_resume.wait(timeout=5):
                    raise ValueError('Resume-worker barrier timed out.')
            return original_run(*args, **kwargs)
        with patch.object(offline_workflows, 'JOBS_LOCK', PauseAfterTerminalPublication()), \
                patch.object(offline_workflows, 'run_batch', side_effect=controlled_run):
            result = self.json_request('/api/offline-batch/start', self.fixture_batch())
            try:
                self.assertTrue(previous_terminal.wait(timeout=3))
                resumed = self.json_request('/api/offline-batch/resume', {'id': result['id']})
                self.assertTrue(resume_entered.wait(timeout=3))
                self.assertEqual(resumed['status'], 'running')
                self.assertTrue(resumed['resume'])
                release_previous.set()
                previous_threads[0].join(timeout=3)
                self.assertFalse(previous_threads[0].is_alive())
                path = self.root / 'offline-batches' / result['id'] / 'job.json'
                saved = json.loads(path.read_text(encoding='utf-8'))
                self.assertEqual(saved['status'], 'running')
                self.assertTrue(saved['resume'])
                self.assertEqual(saved['started_at'], resumed['started_at'])
                self.assertEqual(self.json_request('/api/offline-batch/'+result['id'])['status'], 'running')
            finally:
                release_previous.set()
                release_resume.set()
                final = self.wait_batch(result['id'])
        self.assertEqual(final['status'], 'completed')
        self.assertTrue(final['resume'])
        self.assertTrue(verify_batch_packet(self.request(final['packet_url']))['verified'])

    def test_changed_uploaded_input_rejects_resume_without_replacing_prior_evidence(self):
        result = self.json_request('/api/offline-batch/start', self.fixture_batch())
        final = self.wait_batch(result['id'])
        self.assertEqual(final['status'], 'completed')
        folder = self.root / 'offline-batches' / result['id']
        before = (folder / 'output' / 'first' / 'evidence.zip').read_bytes()
        (folder / 'inputs' / 'mask.png').write_bytes(png(Image.new('L', (8, 6))))
        self.json_request('/api/offline-batch/resume', {'id': result['id']})
        resumed = self.wait_batch(result['id'])
        self.assertEqual(resumed['status'], 'failed')
        self.assertIn('Resume rejected', resumed['error'])
        self.assertEqual((folder / 'output' / 'first' / 'evidence.zip').read_bytes(), before)

    def test_invalid_uploads_leave_no_job_or_partially_published_input_directory(self):
        fixture = self.fixture_batch()
        invalid = []
        for name in ('../escape.png', 'CON.png', 'NUL', 'COM1.txt', 'mask.png.'):
            value = deepcopy(fixture)
            value['files'][1]['name'] = name
            invalid.append(value)
        duplicate = deepcopy(fixture)
        duplicate['files'].append({'name': 'IMAGE.PNG', 'data': self.encode(self.image)})
        invalid.append(duplicate)
        corrupt = deepcopy(fixture)
        corrupt['files'][1]['data'] = 'Invalid base64!'
        invalid.append(corrupt)
        for payload in invalid:
            with self.subTest(filename=payload['files'][1]['name']):
                self.json_request('/api/offline-batch/start', payload, status=400)
                root = self.root / 'offline-batches'
                self.assertEqual(list(root.iterdir()) if root.exists() else [], [])
                self.assertEqual(offline_workflows.JOBS, {})

    def test_invalid_review_packet_formats_are_client_errors(self):
        self.json_request('/api/verify-review-packet', {'packet': self.encode(b'Not a ZIP archive')}, status=400)
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            archive.writestr('manifest.json', '[]')
        self.json_request('/api/verify-review-packet', {'packet': self.encode(output.getvalue())}, status=400)

    def test_rehashed_nonobject_comparison_record_and_invalid_manifest_shapes_are_client_errors(self):
        whole = self.import_mask()
        restricted = self.import_mask(valid=True)
        result = self.compare(whole, restricted)
        packet = self.request(result['packet_url'])
        with zipfile.ZipFile(io.BytesIO(packet)) as archive:
            original = {name: archive.read(name) for name in archive.namelist()}
        for malformed in ([], None, 'Invalid record', 12):
            files = dict(original)
            files['comparison.json'] = json.dumps(malformed).encode('utf-8')
            manifest = json.loads(files['manifest.json'])
            manifest['checksums']['comparison.json'] = {'bytes': len(files['comparison.json']),
                'sha256': hashlib.sha256(files['comparison.json']).hexdigest()}
            files['manifest.json'] = json.dumps(manifest).encode('utf-8')
            output = io.BytesIO()
            with zipfile.ZipFile(output, 'w') as archive:
                for name, raw in files.items():
                    archive.writestr(name, raw)
            with self.subTest(record_type=type(malformed).__name__):
                self.json_request('/api/verify-review-packet', {'packet': self.encode(output.getvalue())}, status=400)
        files = dict(original)
        manifest = json.loads(files['manifest.json'])
        manifest['checksums'] = []
        files['manifest.json'] = json.dumps(manifest).encode('utf-8')
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            for name, raw in files.items():
                archive.writestr(name, raw)
        self.json_request('/api/verify-review-packet', {'packet': self.encode(output.getvalue())}, status=400)


if __name__ == '__main__':
    unittest.main()
