"""Hand-counted batch arithmetic and source-bound failure/recovery checks."""
from copy import deepcopy
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import _source_package
_source_package.use_local_core()
from PIL import Image
from geomasklab.batch import (run_batch, verify_batch, batch_packet, verify_batch_packet,
                             validate_manifest, summary_csv, MANIFEST_SCHEMA)
from geomasklab.domain import png


class ManifestBatch(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.inputs = self.root / 'inputs'
        self.inputs.mkdir()
        self.output = self.root / 'output'
        (self.inputs / 'image.png').write_bytes(png(Image.new('RGB', (4, 4), '#507c68')))
        a = Image.new('L', (4, 4)); a.paste(255, (0, 0, 4, 1))
        b = Image.new('L', (4, 4)); b.paste(255, (0, 0, 2, 1))
        v = Image.new('L', (4, 4)); v.paste(255, (0, 0, 2, 4))
        for name, image in [('a.png', a), ('b.png', b), ('valid.png', v),
                            ('empty.png', Image.new('L', (4, 4))),
                            ('wrong.png', Image.new('L', (2, 2), 255))]:
            (self.inputs / name).write_bytes(png(image))
        self.sample = {'id': 'first', 'image': 'image.png', 'mask': 'a.png', 'target': 'building',
                       'source': 'Hand-counted positive-label fixture', 'aligned': True}
        self.manifest = {'schema': MANIFEST_SCHEMA, 'samples': [self.sample]}

    def tearDown(self):
        self.temporary.cleanup()

    def execute(self, manifest=None, **kwargs):
        return run_batch(manifest or self.manifest, base_dir=self.inputs, output_dir=self.output, **kwargs)

    def test_explicit_pairing_and_independent_macro_micro_arithmetic(self):
        second = {**self.sample, 'id': 'second', 'mask': 'b.png', 'scope': 'left'}
        # first=4/16; second=2/8; both count exactly the declared mask and domain.
        summary = self.execute({'schema': MANIFEST_SCHEMA, 'samples': [self.sample, second]})
        self.assertEqual(summary['status'], 'completed')
        self.assertEqual(summary['aggregate']['macro_mean_coverage'], (4/16 + 2/8)/2)
        self.assertEqual(summary['aggregate']['micro_weighted_coverage'], 6/24)
        self.assertEqual([row['foreground_pixels'] for row in summary['samples']], [4, 2])
        self.assertTrue(verify_batch(self.output)['verified'])

    def test_weighted_coverage_is_distinct_from_macro(self):
        second = {**self.sample, 'id': 'second', 'mask': 'b.png', 'roi': {
            'xyxy': [0, 0, 2, 1], 'source': 'imported', 'image_size': [4, 4]}}
        summary = self.execute({'schema': MANIFEST_SCHEMA, 'samples': [self.sample, second]})
        self.assertEqual(summary['aggregate']['macro_mean_coverage'], (4/16 + 2/2)/2)
        self.assertEqual(summary['aggregate']['micro_weighted_coverage'], 6/18)

    def test_validity_zero_success_and_empty_domain_aggregation(self):
        entries = [
            {**self.sample, 'id': 'valid', 'valid_mask': 'valid.png', 'valid_source': 'Left-half validity fixture'},
            {**self.sample, 'id': 'zero', 'mask': 'empty.png'},
            {**self.sample, 'id': 'undefined', 'valid_mask': 'empty.png', 'valid_source': 'Empty validity fixture'}]
        summary = self.execute({'schema': MANIFEST_SCHEMA, 'samples': entries})
        a = summary['aggregate']
        self.assertEqual((a['defined_coverage_samples'], a['undefined_coverage_samples']), (2, 1))
        self.assertEqual((a['macro_mean_coverage'], a['micro_weighted_coverage']), ((2/8 + 0/16)/2, 2/24))
        self.assertIsNone(summary['samples'][2]['coverage_of_valid_region'])
        self.assertEqual(summary['samples'][1]['coverage_of_valid_region'], 0)
        rows = list(csv.DictReader(io.StringIO((self.output / 'batch_summary.csv').read_text())))
        self.assertEqual(rows[1]['coverage_of_valid_region'], '0.0')
        self.assertEqual(rows[2]['coverage_of_valid_region'], '')
        self.assertTrue(verify_batch_packet(batch_packet(self.output))['verified'])

    def test_one_bad_sample_does_not_damage_others(self):
        bad = {**self.sample, 'id': 'bad', 'mask': 'wrong.png'}
        missing = {**self.sample, 'id': 'missing', 'mask': 'missing.png'}
        summary = self.execute({'schema': MANIFEST_SCHEMA, 'samples': [bad, self.sample, missing]})
        self.assertEqual((summary['completed_count'], summary['failed_count']), (1, 2))
        self.assertEqual(summary['aggregate']['macro_mean_coverage'], 4/16)
        self.assertIsNone(summary['samples'][0]['foreground_pixels'])
        self.assertNotIn(str(self.root), json.dumps(summary))
        self.assertFalse((self.output / 'bad').exists())
        self.assertFalse(any(p.name.startswith('.sample-') for p in self.output.iterdir()))
        self.assertIn('Traceback', (self.output / 'debug.log').read_text())
        packet = batch_packet(self.output)
        with zipfile.ZipFile(io.BytesIO(packet)) as archive:
            self.assertNotIn('debug.log', archive.namelist())
        self.assertEqual(verify_batch_packet(packet)['failed_count'], 2)

    def test_reference_failure_aborts_sample_before_publication(self):
        item = {**self.sample, 'reference': {'path': 'wrong.png', 'source': 'Deliberately wrong-size fixture', 'independent': True}}
        summary = self.execute({'schema': MANIFEST_SCHEMA, 'samples': [item]})
        self.assertEqual(summary['failed_count'], 1)
        self.assertFalse((self.output / item['id']).exists())
        self.assertIsNone(summary['aggregate']['macro_mean_coverage'])
        self.assertTrue(verify_batch(self.output)['verified'])

    def test_reference_roundtrip_source_bound(self):
        item = {**self.sample, 'reference': {'path': 'a.png', 'source': 'Same pixels for arithmetic test only', 'independent': False}}
        summary = self.execute({'schema': MANIFEST_SCHEMA, 'samples': [item]})
        self.assertEqual(summary['samples'][0]['reference'], 'first/reference.zip')
        self.assertEqual(verify_batch_packet(batch_packet(self.output))['completed_count'], 1)

    def test_cancel_at_boundary_then_resume_keeps_completed_bytes(self):
        entries = [self.sample, {**self.sample, 'id': 'second'}, {**self.sample, 'id': 'third'}]
        done = False
        def progress(summary):
            nonlocal done
            done = summary['completed_count'] >= 1
        summary = self.execute({'schema': MANIFEST_SCHEMA, 'samples': entries}, cancel=lambda: done, progress=progress)
        self.assertEqual(summary['status'], 'cancelled')
        self.assertEqual((summary['completed_count'], summary['cancelled_count']), (1, 2))
        original = (self.output / 'first' / 'evidence.zip').read_bytes()
        self.assertTrue(verify_batch_packet(batch_packet(self.output))['verified'])
        resumed = self.execute({'schema': MANIFEST_SCHEMA, 'samples': entries}, resume=True)
        self.assertEqual(resumed['completed_count'], 3)
        self.assertEqual((self.output / 'first' / 'evidence.zip').read_bytes(), original)
        self.assertTrue(verify_batch(self.output)['verified'])

    def test_cancel_before_commit_leaves_no_successful_artifacts(self):
        calls = 0
        def cancel():
            nonlocal calls
            calls += 1
            return calls > 1
        summary = self.execute(cancel=cancel)
        self.assertEqual(summary['cancelled_count'], 1)
        self.assertFalse((self.output / 'first').exists())
        self.assertFalse(any(p.name.startswith('.sample-') for p in self.output.iterdir()))
        self.assertTrue(verify_batch(self.output)['verified'])

    def test_resume_rejects_changed_input_settings_or_runtime(self):
        self.execute()
        before = (self.output / 'first' / 'evidence.zip').read_bytes()
        changed = {**self.sample, 'scope': 'right'}
        with self.assertRaisesRegex(ValueError, 'Resume rejected'):
            self.execute({'schema': MANIFEST_SCHEMA, 'samples': [changed]}, resume=True)
        with patch('geomasklab.batch.VERSION', '999.0.0'):
            with self.assertRaisesRegex(ValueError, 'Resume rejected'):
                self.execute(resume=True)
        (self.inputs / 'a.png').write_bytes((self.inputs / 'b.png').read_bytes())
        with self.assertRaisesRegex(ValueError, 'Resume rejected'):
            self.execute(resume=True)
        self.assertEqual((self.output / 'first' / 'evidence.zip').read_bytes(), before)

    def test_resuming_all_completed_is_noop_and_conflicting_output_rejected(self):
        self.execute()
        before = (self.output / 'first' / 'evidence.zip').read_bytes()
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.execute()
        self.assertEqual(self.execute(resume=True)['status'], 'completed')
        self.assertEqual((self.output / 'first' / 'evidence.zip').read_bytes(), before)

    def test_duplicate_ids_reserved_names_and_unsafe_paths_rejected(self):
        for sid in ['CON', '../oops', 'x.y', 'LPT1']:
            with self.subTest(sid=sid), self.assertRaises(ValueError):
                validate_manifest({'schema': MANIFEST_SCHEMA, 'samples': [{**self.sample, 'id': sid}]})
        with self.assertRaisesRegex(ValueError, 'unique'):
            validate_manifest({'schema': MANIFEST_SCHEMA, 'samples': [self.sample, {**self.sample, 'id': 'FIRST'}]})
        for path in ['../a.png', '/a.png', 'C:/a.png', 'a\\b.png', './a.png', 'a//b.png']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.execute({'schema': MANIFEST_SCHEMA, 'samples': [{**self.sample, 'mask': path}]})

    def test_symlink_escape_rejected_when_supported(self):
        outside = self.root / 'outside.png'
        outside.write_bytes((self.inputs / 'a.png').read_bytes())
        link = self.inputs / 'link.png'
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest('File symlinks unavailable for this account.')
        with self.assertRaisesRegex(ValueError, 'inside'):
            self.execute({'schema': MANIFEST_SCHEMA, 'samples': [{**self.sample, 'mask': 'link.png'}]})

    def test_changed_input_between_capture_and_processing_fails_locally(self):
        def progress(summary):
            if summary['status'] == 'running':
                (self.inputs / 'a.png').write_bytes((self.inputs / 'b.png').read_bytes())
        summary = self.execute(progress=progress)
        self.assertEqual(summary['failed_count'], 1)
        self.assertFalse((self.output / 'first').exists())

    def test_corrupt_completed_artifact_blocks_resume(self):
        self.execute()
        path = self.output / 'first' / 'image-input.bin'
        path.write_bytes(path.read_bytes() + b'corrupt')
        with self.assertRaises(ValueError):
            self.execute(resume=True)

    def test_empty_validity_only_keeps_both_aggregates_undefined(self):
        item = {**self.sample, 'valid_mask': 'empty.png', 'valid_source': 'Empty domain fixture'}
        summary = self.execute({'schema': MANIFEST_SCHEMA, 'samples': [item]})
        self.assertEqual(summary['completed_count'], 1)
        self.assertEqual(summary['aggregate']['undefined_coverage_samples'], 1)
        self.assertIsNone(summary['aggregate']['macro_mean_coverage'])
        self.assertIsNone(summary['aggregate']['micro_weighted_coverage'])
        self.assertTrue(verify_batch_packet(batch_packet(self.output))['verified'])

    def test_active_lock_is_not_removed_or_overwritten(self):
        import geomasklab.batch as module
        self.execute()
        locked = self.output / '.batch.lock'
        marker = locked.read_bytes()
        evidence = (self.output / 'first' / 'evidence.zip').read_bytes()
        with module._output_lock(self.output):
            with self.assertRaisesRegex(ValueError, 'already locked'):
                self.execute(resume=True)
        self.assertEqual(locked.read_bytes(), marker)
        self.assertEqual((self.output / 'first' / 'evidence.zip').read_bytes(), evidence)

    def test_actual_process_death_releases_lock_and_recovers_owned_staging(self):
        manifest = {'schema': MANIFEST_SCHEMA, 'samples': [self.sample, {**self.sample, 'id': 'second'}]}
        path = self.root / 'manifest.json'
        path.write_text(json.dumps(manifest), encoding='utf-8')
        script = '''import json, os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import geomasklab.batch as batch
original = batch.create_evidence
calls = 0
def crash(*args, **kwargs):
    global calls
    calls += 1
    if calls == 2:
        os._exit(77)
    return original(*args, **kwargs)
batch.create_evidence = crash
batch.run_batch(json.loads(Path(sys.argv[2]).read_text()), base_dir=sys.argv[3], output_dir=sys.argv[4])
'''
        core = Path(__file__).resolve().parents[1] / 'src'
        completed = subprocess.run([sys.executable, '-c', script, str(core), str(path),
                                    str(self.inputs), str(self.output)], cwd=self.root,
                                   capture_output=True, timeout=30)
        self.assertEqual(completed.returncode, 77, completed.stderr.decode(errors='replace'))
        original = (self.output / 'first' / 'evidence.zip').read_bytes()
        self.assertTrue((self.output / '.batch.lock').is_file())
        self.assertTrue(any(p.name.startswith('.sample-') for p in self.output.iterdir()))
        resumed = self.execute(manifest, resume=True)
        self.assertEqual(resumed['completed_count'], 2)
        self.assertEqual((self.output / 'first' / 'evidence.zip').read_bytes(), original)
        self.assertFalse(any(p.name.startswith('.sample-') for p in self.output.iterdir()))
        self.assertTrue(verify_batch(self.output)['verified'])

    def test_actual_crash_during_atomic_write_recovers_only_owned_temporary(self):
        manifest = {'schema': MANIFEST_SCHEMA, 'samples': [self.sample, {**self.sample, 'id': 'second'}]}
        path = self.root / 'manifest.json'
        path.write_text(json.dumps(manifest), encoding='utf-8')
        script = '''import json, os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import geomasklab.batch as batch
output = Path(sys.argv[4])
original = batch.os.replace
def crash(source, destination):
    if (Path(source).name.startswith('.write-') and Path(destination).name == 'batch_summary.json'
            and (output / 'first' / 'evidence.zip').exists()):
        os._exit(78)
    return original(source, destination)
batch.os.replace = crash
batch.run_batch(json.loads(Path(sys.argv[2]).read_text()), base_dir=sys.argv[3], output_dir=output)
'''
        core = Path(__file__).resolve().parents[1] / 'src'
        completed = subprocess.run([sys.executable, '-c', script, str(core), str(path),
                                    str(self.inputs), str(self.output)], cwd=self.root,
                                   capture_output=True, timeout=30)
        self.assertEqual(completed.returncode, 78, completed.stderr.decode(errors='replace'))
        original = (self.output / 'first' / 'evidence.zip').read_bytes()
        orphan = [p for p in self.output.iterdir() if p.name.startswith('.write-')]
        self.assertEqual(len(orphan), 1)
        pinned = json.loads((self.output / 'batch_identity.json').read_bytes())
        self.assertIn(pinned['fingerprint'], orphan[0].name)
        resumed = self.execute(manifest, resume=True)
        self.assertEqual(resumed['completed_count'], 2)
        self.assertEqual((self.output / 'first' / 'evidence.zip').read_bytes(), original)
        self.assertFalse(any(p.name.startswith('.write-') for p in self.output.iterdir()))
        self.assertTrue(verify_batch(self.output)['verified'])

    def test_foreign_atomic_temp_is_preserved_and_blocks_resume(self):
        self.execute()
        foreign = self.output / '.write-unrelated-important-file'
        foreign.write_bytes(b'Preserve these unrelated bytes')
        with self.assertRaisesRegex(ValueError, 'atomic metadata'):
            self.execute(resume=True)
        self.assertEqual(foreign.read_bytes(), b'Preserve these unrelated bytes')

    def test_snapshot_is_replayed_before_export_returns_a_packet(self):
        import geomasklab.batch as module
        self.execute()
        original = module.verify_batch
        def mutate_after_verification(output):
            facts = original(output)
            saved = json.loads((self.output / 'batch_summary.json').read_bytes())
            saved['samples'][0]['foreground_pixels'] = 99
            (self.output / 'batch_summary.json').write_text(json.dumps(saved))
            (self.output / 'batch_summary.csv').write_bytes(summary_csv(saved))
            return facts
        with patch('geomasklab.batch.verify_batch', side_effect=mutate_after_verification):
            with self.assertRaisesRegex(ValueError, 'verified pixels'):
                batch_packet(self.output)

    def test_export_holds_advisory_lock_against_concurrent_resume(self):
        import geomasklab.batch as module
        self.execute()
        original = module.verify_batch
        def attempt_resume(output):
            with self.assertRaisesRegex(ValueError, 'already locked'):
                self.execute(resume=True)
            return original(output)
        with patch('geomasklab.batch.verify_batch', side_effect=attempt_resume):
            packet = batch_packet(self.output)
        self.assertTrue(verify_batch_packet(packet)['verified'])

    def test_recovery_rejects_foreign_or_unexpected_staging_contents(self):
        self.execute()
        candidate = self.output / '.sample-abcdefgh'
        candidate.mkdir()
        (candidate / 'unrelated-important-file.txt').write_text('Preserve this file')
        with self.assertRaisesRegex(ValueError, 'ownership'):
            self.execute(resume=True)
        self.assertEqual((candidate / 'unrelated-important-file.txt').read_text(), 'Preserve this file')

    def test_packet_resource_limit_is_checked_before_reading_artifacts(self):
        self.execute()
        with patch('geomasklab.batch.MAX_PACKET_BYTES', 32):
            with self.assertRaisesRegex(ValueError, 'expanded size'):
                batch_packet(self.output)

    def test_rehashed_wrong_summary_is_rejected_by_pixels(self):
        self.execute()
        saved = json.loads((self.output / 'batch_summary.json').read_bytes())
        saved['samples'][0]['foreground_pixels'] = 99
        (self.output / 'batch_summary.json').write_text(json.dumps(saved))
        (self.output / 'batch_summary.csv').write_bytes(summary_csv(saved))
        with self.assertRaisesRegex(ValueError, 'verified pixels'):
            verify_batch(self.output)

    def test_packet_tampering_and_unsafe_members_are_rejected(self):
        self.execute()
        packet = batch_packet(self.output)
        with zipfile.ZipFile(io.BytesIO(packet)) as archive:
            files = {name: archive.read(name) for name in archive.namelist()}
        def encoded(items):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
                for name, raw in items.items():
                    archive.writestr(name, raw)
            return stream.getvalue()
        with self.assertRaises(ValueError):
            verify_batch_packet(encoded({**files, '../escape': b'x'}))
        bad = dict(files); bad['batch_summary.csv'] += b'x'
        with self.assertRaisesRegex(ValueError, 'checksum'):
            verify_batch_packet(encoded(bad))
        manifest = json.loads(files['manifest.json'])
        bad['manifest.json'] = json.dumps({**manifest, 'checksums': {
            **manifest['checksums'], 'batch_summary.csv': {'sha256': hashlib.sha256(bad['batch_summary.csv']).hexdigest(), 'bytes': len(bad['batch_summary.csv'])}}}).encode()
        with self.assertRaisesRegex(ValueError, 'CSV'):
            verify_batch_packet(encoded(bad))

    def test_resume_recovers_published_sample_after_interrupted_summary_write(self):
        # Force the exact interval after sample directory publication and before
        # the new summary is written; its earlier pending summary remains valid.
        import geomasklab.batch as module
        original = module._save_summary
        def interrupt(output, identity, rows, status, progress=None):
            if any(row['status'] == 'completed' for row in rows):
                raise KeyboardInterrupt('Simulated interruption after atomic sample publication')
            return original(output, identity, rows, status, progress)
        with patch('geomasklab.batch._save_summary', side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.execute()
        before = (self.output / 'first' / 'evidence.zip').read_bytes()
        with self.assertRaises(ValueError):
            verify_batch(self.output)
        resumed = self.execute(resume=True)
        self.assertEqual(resumed['status'], 'completed')
        self.assertEqual((self.output / 'first' / 'evidence.zip').read_bytes(), before)
        self.assertTrue(verify_batch(self.output)['verified'])

    def test_resume_rebuilds_derived_csv_after_json_csv_crash_window(self):
        import geomasklab.batch as module
        original = module._atomic
        def interrupt(path, raw, **kwargs):
            if path.name == 'batch_summary.csv':
                raise KeyboardInterrupt('Simulated interruption between JSON and CSV publication')
            return original(path, raw, **kwargs)
        with patch('geomasklab.batch._atomic', side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.execute()
        self.assertTrue((self.output / 'batch_summary.json').is_file())
        self.assertFalse((self.output / 'batch_summary.csv').exists())
        resumed = self.execute(resume=True)
        self.assertEqual(resumed['completed_count'], 1)
        self.assertTrue(verify_batch(self.output)['verified'])
        (self.output / 'batch_summary.csv').write_bytes(b'Stale derived CSV')
        with self.assertRaisesRegex(ValueError, 'CSV'):
            verify_batch(self.output)
        evidence = (self.output / 'first' / 'evidence.zip').read_bytes()
        self.assertEqual(self.execute(resume=True)['completed_count'], 1)
        self.assertEqual((self.output / 'first' / 'evidence.zip').read_bytes(), evidence)
        self.assertTrue(verify_batch(self.output)['verified'])

    @unittest.skipUnless(importlib.util.find_spec('jsonschema'), 'Optional jsonschema extra unavailable.')
    def test_published_manifest_schema_accepts_explicit_fixture(self):
        from jsonschema import Draft202012Validator
        schema = json.loads((Path(__file__).resolve().parents[1] / 'src' / 'geomasklab' / 'schemas' / 'batch-manifest-1.0.schema.json').read_text())
        Draft202012Validator(schema).validate(self.manifest)


if __name__ == '__main__':
    unittest.main()
