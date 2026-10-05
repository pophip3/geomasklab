"""Check real platform launcher argument forwarding outside the software root."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DistributionEntrypointTests(unittest.TestCase):
    def test_platform_launcher_help_and_invalid_port(self):
        launcher = ([os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c',
                     str(ROOT/'bin'/'geomasklab.cmd')] if os.name == 'nt'
                    else ['sh', str(ROOT/'bin'/'geomasklab.sh')])
        with tempfile.TemporaryDirectory(prefix='geomasklab-launch-') as outside:
            help_result = subprocess.run(launcher+['--help'], cwd=outside,
                                         capture_output=True, text=True, timeout=15)
            self.assertEqual(help_result.returncode, 0, help_result.stderr)
            self.assertIn('--port', help_result.stdout)
            invalid = subprocess.run(launcher+['--port', '0'], cwd=outside,
                                     capture_output=True, text=True, timeout=15)
            self.assertNotEqual(invalid.returncode, 0)
            self.assertIn('port must be between', invalid.stderr)


if __name__ == '__main__':
    unittest.main()
