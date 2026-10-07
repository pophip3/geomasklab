"""Execute both documented reviewer commands against the bundled real image."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReviewerQuickstartTests(unittest.TestCase):
    def run_script(self, name, directory):
        return subprocess.run([sys.executable, str(ROOT / 'examples' / name)], cwd=directory,
            capture_output=True, text=True, encoding='utf-8', check=True, timeout=60).stdout

    def test_published_figures_and_mutation_rejection_execute_without_models(self):
        with tempfile.TemporaryDirectory() as directory:
            table = self.run_script('reproduce_table.py', directory)
            for expected in ('54.41%', '48.09%', '53.52%', 'spread = 6.32 pp'):
                self.assertIn(expected, table)
            replay = self.run_script('run_replay_demo.py', directory)
            self.assertIn('Replay result: PASS', replay)
            self.assertIn('manifest.checksums.valid_mask.png.sha256; expected rejection', replay)
            output = Path(directory) / 'reviewer-output/replay-demo'
            self.assertTrue((output / 'original.zip').is_file())
            self.assertTrue((output / 'tampered.zip').is_file())


if __name__ == '__main__':
    unittest.main()
