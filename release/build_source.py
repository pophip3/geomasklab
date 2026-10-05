"""Build a deterministic source ZIP from a fixed Git commit, without local secrets.

Only committed regular files are included. The manifest records the commit and
each file hash; untracked experiments, credentials and model weights cannot enter.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ('README.md', 'LICENSE', 'Licence.txt', 'THIRD_PARTY_NOTICES.md',
            'requirements.txt', 'requirements-reviewer.txt', '.env.example',
            'quickstart.py', 'reviewer_demo.py', 'workbench/fixtures.py', 'workbench/web/index.html',
            'docs/reviewer_quickstart.md', 'docs/model_services.md', 'workbench/web/help.html',
            'bin/geomasklab.cmd', 'bin/geomasklab.sh', 'workbench/mask_inputs.py',
            'workbench/reference_evaluation.py', 'examples/reference_workflow.py',
            'workbench/web/mask-tools.js', 'workbench/web/mask-tools.css', 'pyproject.toml',
            'src/geomasklab/api.py', 'src/geomasklab/cli.py', 'src/geomasklab/_version.py',
            'src/geomasklab/schemas/manifest-1.0.schema.json',
            'src/geomasklab/schemas/result-1.0.schema.json',
            'src/geomasklab/schemas/statistics-1.0.schema.json',
            'examples/real_image_handoff.py', 'examples/data/san-francisco-bay/provenance.json',
            'src/geomasklab/provenance.py', 'src/geomasklab/geospatial.py',
            'src/geomasklab/schemas/geospatial-1.0.schema.json', 'examples/geospatial_workflow.py',
            'docs/provenance_mapping.md', 'docs/geospatial_assessment.md',
            'src/geomasklab/zonal.py', 'src/geomasklab/signing.py',
            'src/geomasklab/raster_input.py', 'docs/zonal_statistics.md', 'docs/signatures.md',
            'docs/raster_inputs.md', 'examples/naip_zonal_workflow.py',
            'examples/data/naip-denver/source.tif', 'examples/data/naip-denver/provenance.json',
            'examples/prepare_handoff_study.py', 'evaluation/analyze_handoff_study.py')
FORBIDDEN_PARTS = {'.git', '.venv', 'venv', 'experiments', '__pycache__',
                   'node_modules', 'weights', 'checkpoints', 'pretrained_weights', 'build', 'dist'}
FORBIDDEN_SUFFIXES = {'.pth', '.pt', '.ckpt', '.safetensors', '.onnx', '.log', '.zip', '.whl'}


def git(*args):
    """Read Git data with explicit arguments and no shell evaluation."""
    return subprocess.check_output(['git', '-c', f'safe.directory={ROOT.as_posix()}',
                                    *args], cwd=ROOT)


def build(output, revision):
    """Return the archive identity after validating its committed source list."""
    commit = git('rev-parse', '--verify', f'{revision}^{{commit}}').decode().strip()
    records = git('ls-tree', '-rz', '--full-tree', commit).split(b'\0')
    files = {}
    for entry in filter(None, records):
        meta, name = entry.split(b'\t', 1)
        mode, kind, oid = meta.split()
        path = name.decode('utf-8')
        parts = Path(path).parts
        if mode not in (b'100644', b'100755') or kind != b'blob':
            raise ValueError(f'Unsupported source entry: {path}')
        if (set(parts) & FORBIDDEN_PARTS or Path(path).suffix.lower() in FORBIDDEN_SUFFIXES
                or (Path(path).name.startswith('.env') and path != '.env.example')
                or path.startswith('evaluation/images/')):
            raise ValueError(f'Excluded local/private artifact is committed: {path}')
        files[path] = git('cat-file', 'blob', oid.decode())
    for path in REQUIRED:
        if path not in files:
            raise ValueError(f'Required source file missing: {path}')
    if files['LICENSE'] != files['Licence.txt'] or b'MIT License' not in files['LICENSE']:
        raise ValueError('The standard MIT license copies must match')
    tree = ast.parse(files['src/geomasklab/_version.py'].decode('utf-8'))
    version = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == 'VERSION' for t in n.targets))
    manifest = {'schema': 'geomasklab-source-release/1.0', 'version': version,
                'source_commit': commit, 'files': {n: hashlib.sha256(b).hexdigest()
                                                 for n, b in sorted(files.items())},
                'excluded': 'All untracked/ignored files; local data, credentials and model weights',
                'archive_doi': None}
    prefix = f'GeoMaskLab-{version}/'
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(prefix + name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, data)
        info = zipfile.ZipInfo(prefix + 'SOURCE-MANIFEST.json', date_time=(2026, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        z.writestr(info, json.dumps(manifest, indent=2) + '\n')
    return {'version': version, 'source_commit': commit, 'file_count': len(files),
            'archive_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
            'archive': str(output), 'archive_doi': None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', default='HEAD')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output, args.revision), indent=2))


if __name__ == '__main__':
    main()
