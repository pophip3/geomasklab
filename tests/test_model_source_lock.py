"""The original adapter must not silently import a modified architecture."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from model_services.sam_backend import validate_source_files


class SourceLockTests(unittest.TestCase):
    def test_exact_snapshot_passes_and_same_size_change_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / 'architecture.py'
            path.write_bytes(b'original')
            lock = {'sam_source_revision': 'fixed-revision',
                    'sam_source_files': {'architecture.py': hashlib.sha256(b'original').hexdigest()}}
            self.assertTrue(validate_source_files(root, lock)['architecture_file_lock_verified'])
            path.write_bytes(b'modified')
            with self.assertRaisesRegex(ValueError, 'differs'):
                validate_source_files(root, lock)

    def test_missing_and_outside_source_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'source'
            root.mkdir()
            outside = root.parent / 'external.py'
            outside.write_bytes(b'outside')
            digest = hashlib.sha256(b'outside').hexdigest()
            for name in ('absent.py', '../external.py'):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    validate_source_files(root, {'sam_source_revision': 'fixed',
                        'sam_source_files': {name: digest}})


if __name__ == '__main__':
    unittest.main()
