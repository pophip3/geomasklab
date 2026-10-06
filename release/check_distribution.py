"""Verify and run an extracted source archive outside the development checkout."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    environment = dict(os.environ)
    environment.pop('PYTHONPATH', None)
    environment['PYTHONUTF8'] = '1'
    with tempfile.TemporaryDirectory(prefix='geomasklab-distribution-') as directory:
        destination = Path(directory).resolve()
        with zipfile.ZipFile(args.archive) as z:
            for item in z.infolist():
                candidate = (destination / item.filename).resolve()
                if not candidate.is_relative_to(destination):
                    raise ValueError('Archive path escapes extraction directory')
            z.extractall(destination)
        roots = list(destination.iterdir())
        if len(roots) != 1 or not roots[0].is_dir():
            raise ValueError('Expected one source root')
        root = roots[0]
        manifest = json.loads((root/'SOURCE-MANIFEST.json').read_text(encoding='utf-8'))
        for name, expected in manifest['files'].items():
            if hashlib.sha256((root/name).read_bytes()).hexdigest() != expected:
                raise ValueError(f'Source hash mismatch: {name}')
        for name in ('.git', '.env', 'experiments', 'reviewer-output'):
            if (root/name).exists():
                raise ValueError(f'Unexpected local artifact: {name}')
        commands = [['reviewer_demo.py'], ['examples/recalculate_region.py', 'reviewer-output/right.zip'],
                    ['examples/reference_workflow.py'], ['examples/real_image_handoff.py'],
                    ['examples/five_step_workflow.py']]
        for command in commands:
            result = subprocess.run([args.python, *command], cwd=root, env=environment,
                                    text=True, encoding='utf-8', capture_output=True, check=True)
            if re.search(r'[\u3400-\u9fff]', result.stdout + result.stderr):
                raise ValueError('New example output must be English')
        reviewer = json.loads((root/'reviewer-output/summary.json').read_text(encoding='utf-8'))
        if not reviewer['passed'] or len(reviewer['results']) != 5:
            raise ValueError('Reviewer workflow did not complete five cases')
        five=json.loads((root/'five-step-output/summary.json').read_text(encoding='utf-8'))
        if not five['passed'] or five['software_version']!=manifest['version'] or not five['batch']['offline_packet_replay']:
            raise ValueError('Connected five-step example did not replay for the candidate version')
        for archive in (root/'reviewer-output').glob('*.zip'):
            with zipfile.ZipFile(archive) as z:
                for name in z.namelist():
                    if name.endswith(('.json', '.md', '.csv', '.txt')):
                        if re.search(r'[\u3400-\u9fff]', z.read(name).decode('utf-8')):
                            raise ValueError(f'New evidence text must be English: {name}')
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            port = s.getsockname()[1]
        process = subprocess.Popen([args.python, '-u', 'quickstart.py', '--port', str(port)],
                                   cwd=root, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            for attempt in range(100):
                if process.poll() is not None:
                    raise RuntimeError('Extracted workbench exited before readiness')
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/status', timeout=1) as response:
                        status = json.load(response)
                    break
                except (OSError, TimeoutError):
                    time.sleep(.1)
            else:
                raise RuntimeError('Extracted workbench did not become ready')
            if status.get('version') != manifest['version']:
                raise ValueError('Running version differs from archive identity')
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=2) as response:
                page = response.read().decode('utf-8')
            if 'GeoMaskLab' not in page or '<html lang="en">' not in page:
                raise ValueError('English browser interface missing')
            if not all(identifier in page for identifier in ('inspectComponentsBtn','offlineBatchBtn','verifyPacketBtn')):
                raise ValueError('Connected browser workflow controls are missing')
            for asset in ('offline-tools.js','offline-tools.css','presentation.js','presentation.css',
                          'assets/naip-preview.png','assets/naip-preview-mask.png','assets/naip-preview-provenance.json'):
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/'+asset,timeout=2) as response:
                    if not response.read():raise ValueError('New workflow asset is missing: '+asset)
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/help.html', timeout=2) as response:
                help_page = response.read().decode('utf-8')
            if '<html lang="en">' not in help_page or 'Compare result versions' not in help_page:
                raise ValueError('Offline English user guide missing')
            ids = set(re.findall(r'id="([^"]+)"', help_page))
            if not set(re.findall(r'href="#([^"]+)"', help_page)).issubset(ids):
                raise ValueError('Offline guide has broken section links')
            launcher = ([os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c', str(root/'bin/geomasklab.cmd')]
                        if os.name == 'nt' else ['sh', str(root/'bin/geomasklab.sh')])
            launch_environment = {**environment, 'PATH': str(Path(args.python).resolve().parent)
                                  + os.pathsep + environment.get('PATH', '')}
            result = subprocess.run(launcher+['--help'], cwd=destination, env=launch_environment,
                                    capture_output=True, text=True, encoding='utf-8', check=True, timeout=15)
            if '--port' not in result.stdout:
                raise ValueError('Distributed platform launcher failed argument forwarding')
        finally:
            process.terminate()
            process.communicate(timeout=10)
    report = {'passed': True, 'version': manifest['version'], 'source_commit': manifest['source_commit'],
              'source_hashes_checked': len(manifest['files']), 'reviewer_cases': 5,
              'saved_mask_region_example': 'passed', 'external_mask_reference_example': 'passed',
              'real_image_color_baseline_handoff': 'passed', 'new_generated_text': 'English',
              'real_naip_connected_five_step_example': 'passed',
              'isolated_server_startup_and_interface': 'passed',
              'offline_user_guide': 'passed', 'platform_launcher': 'passed',
              'python': args.python, 'duration_seconds': round(time.perf_counter()-started, 3),
              'limits': 'Existing interpreter/dependencies; no clean OS or live model installation claimed.'}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
