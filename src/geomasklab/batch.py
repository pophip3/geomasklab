"""Explicit, resumable offline batches with per-sample isolation.

A batch pairs files through a manifest, never through filename guessing. Its
identity binds the declared settings, input bytes and software version. Completed
samples contain independently replayable evidence; the summary reports failed
samples separately and never assigns them zero coverage. Internal replay does
not authenticate the supplied images, masks or reference labels.
"""
from copy import deepcopy
from contextlib import contextmanager
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import stat
import tempfile
import traceback
import zipfile

from PIL import Image, ImageOps

from ._version import VERSION
from .api import create_evidence, timestamp
from .evidence import load_verified_bundle, MAX_BUNDLE_BYTES, MAX_IMAGE_PIXELS
from .masks import MAX_IMAGE_BYTES, MAX_MASK_BYTES
from .reference import evaluate_reference, evaluation_packet, verify_reference_packet

MANIFEST_SCHEMA = 'geomasklab-batch-manifest/1.0'
SUMMARY_SCHEMA = 'geomasklab-batch-summary/1.0'
MAX_SAMPLES = 128
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_PACKET_BYTES = 256 * 1024 * 1024
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}')
_RESERVED = {'con', 'prn', 'aux', 'nul', *(f'com{i}' for i in range(1, 10)),
             *(f'lpt{i}' for i in range(1, 10))}
_SAMPLE_FIELDS = {'id', 'image', 'mask', 'target', 'source', 'aligned', 'scope',
                  'roi', 'invert', 'image_source', 'valid_mask', 'valid_source', 'reference'}
_INPUT_LIMITS = {'image': MAX_IMAGE_BYTES, 'mask': MAX_MASK_BYTES,
                 'valid_mask': MAX_MASK_BYTES, 'reference': MAX_MASK_BYTES}
_PUBLIC_ERROR = 'Sample processing failed. Check its explicit inputs and settings; a local debug log records details.'


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _json_bytes(value):
    return json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False).encode('utf-8')


def _atomic(path, raw, *, owner):
    """Replace one receipt atomically; staging always stays in its directory."""
    path = Path(path)
    targets = {'batch_manifest.json', 'batch_identity.json', 'batch_summary.json', 'batch_summary.csv'}
    if path.name not in targets or not isinstance(owner, str) or not re.fullmatch(r'[0-9a-f]{64}', owner):
        raise ValueError('Atomic metadata staging requires a permitted target and pinned batch owner.')
    prefix = '.write-' + owner + '--' + path.name + '-'
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=prefix, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _output_lock(output):
    """Hold a nonblocking OS advisory lock, released even after process death."""
    path = output / '.batch.lock'
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError('Batch lock must be a regular file in the owned output directory.')
    flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0)
    descriptor = os.open(path, flags, 0o600)
    stream = os.fdopen(descriptor, 'r+b', buffering=0)
    locked = False
    try:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('Batch lock must be a regular file.')
        if os.fstat(stream.fileno()).st_size == 0:
            stream.write(b'1')
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError as error:
            raise ValueError('Batch output is already locked by an active writer.') from error
        yield
    finally:
        if locked:
            stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()


def _recover_staging(output, identity):
    """Remove only validated staging directories owned by this pinned batch."""
    sample_ids = {item['id'] for item in identity['samples']}
    for candidate in output.iterdir():
        if not candidate.name.startswith('.sample-'):
            continue
        if (not re.fullmatch(r'\.sample-[a-z0-9_]{8}', candidate.name) or candidate.is_symlink() or
                not candidate.is_dir() or candidate.resolve().parent != output):
            raise ValueError('Unrecognized or unsafe temporary sample directory prevents resume.')
        children = list(candidate.iterdir())
        if not children:
            # TemporaryDirectory may have been created immediately before death.
            candidate.rmdir()
            continue
        marker = candidate / '.owner.json'
        if marker.is_symlink() or not marker.is_file() or marker.stat().st_size > 4096:
            raise ValueError('Temporary sample ownership is missing or unsafe.')
        owner = json.loads(marker.read_bytes())
        if (set(owner) != {'schema', 'batch_fingerprint', 'sample_id'} or
                owner['schema'] != 'geomasklab-batch-staging/1.0' or
                owner['batch_fingerprint'] != identity['fingerprint'] or owner['sample_id'] not in sample_ids):
            raise ValueError('Temporary sample belongs to a different batch.')
        stage = candidate / owner['sample_id']
        if ({child.name for child in children} - {'.owner.json', owner['sample_id']} or stage.is_symlink() or
                (stage.exists() and not stage.is_dir())):
            raise ValueError('Temporary sample contains unexpected paths.')
        if stage.exists():
            allowed = {'evidence.zip', 'image-input.bin', 'receipt.json', 'reference.zip'}
            for child in stage.iterdir():
                if child.name not in allowed or child.is_symlink() or not child.is_file():
                    raise ValueError('Temporary sample contains unsafe or unexpected artifacts.')
        resolved = candidate.resolve()
        if not resolved.is_relative_to(output) or resolved.parent != output:
            raise ValueError('Temporary sample escapes the owned batch output directory.')
        shutil.rmtree(resolved)


def _recover_atomic(output, identity):
    """Discard only fingerprint-bound metadata staging under the held OS lock."""
    pattern = re.compile(r'\.write-([0-9a-f]{64})--(batch_manifest\.json|batch_identity\.json|batch_summary\.json|batch_summary\.csv)-[a-z0-9_]{8}')
    for candidate in output.iterdir():
        if not candidate.name.startswith('.write-'):
            continue
        matched = pattern.fullmatch(candidate.name)
        if (not matched or matched.group(1) != identity['fingerprint'] or candidate.is_symlink() or
                not candidate.is_file() or candidate.resolve().parent != output or
                candidate.stat().st_size > MAX_MANIFEST_BYTES * 2 or candidate.stat().st_nlink != 1):
            raise ValueError('Unrecognized or unsafe atomic metadata staging prevents resume.')
        candidate.unlink()


def _relative(value):
    if (not isinstance(value, str) or not value or len(value) > 1024 or '\\' in value or
            '\x00' in value or PureWindowsPath(value).drive or PurePosixPath(value).is_absolute() or
            any(part in {'', '.', '..'} for part in value.split('/'))):
        raise ValueError('Input paths must be explicit relative paths using forward slashes without traversal.')
    return value


def _input_path(base, name):
    path = (base / _relative(name)).resolve()
    if not path.is_relative_to(base):
        raise ValueError('Input paths must remain inside the declared base directory.')
    return path


def validate_manifest(manifest):
    """Validate structure without opening input files or calling a model."""
    if not isinstance(manifest, dict) or set(manifest) != {'schema', 'samples'}:
        raise ValueError('A batch manifest must contain exactly schema and samples.')
    if manifest['schema'] != MANIFEST_SCHEMA:
        raise ValueError('Unsupported batch manifest schema.')
    if len(_canonical(manifest)) > MAX_MANIFEST_BYTES:
        raise ValueError('Batch manifest exceeds the 1 MB limit.')
    samples = manifest['samples']
    if not isinstance(samples, list) or not 1 <= len(samples) <= MAX_SAMPLES:
        raise ValueError('Provide 1 to 128 explicitly paired samples.')
    normalized, seen = [], set()
    for entry in samples:
        required = {'id', 'image', 'mask', 'target', 'source', 'aligned'}
        if not isinstance(entry, dict) or not required <= set(entry) or set(entry) - _SAMPLE_FIELDS:
            raise ValueError('Every sample requires id, image, mask, target, source and aligned; unknown fields are rejected.')
        sid = entry['id']
        if not isinstance(sid, str) or not _ID.fullmatch(sid) or sid.casefold() in _RESERVED:
            raise ValueError('Sample IDs must be portable ASCII names of 1 to 64 letters, digits, underscores or hyphens.')
        if sid.casefold() in seen:
            raise ValueError('Sample IDs must be unique, including on case-insensitive filesystems.')
        seen.add(sid.casefold())
        if entry['aligned'] is not True or type(entry.get('invert', False)) is not bool:
            raise ValueError('Explicitly confirm alignment and provide a boolean complement setting.')
        if not isinstance(entry['target'], str) or not isinstance(entry['source'], str):
            raise ValueError('Sample target and source must be strings.')
        if 'image_source' in entry and not isinstance(entry['image_source'], str):
            raise ValueError('Image source must be a string.')
        if ('valid_mask' in entry) != ('valid_source' in entry):
            raise ValueError('An explicit valid mask and its source description must be provided together.')
        if 'valid_source' in entry and not isinstance(entry['valid_source'], str):
            raise ValueError('Validity source must be a string.')
        item = deepcopy(entry)
        for field in ('image', 'mask', 'valid_mask'):
            if field in item:
                item[field] = _relative(item[field])
        reference = item.get('reference')
        if reference is not None:
            if (not isinstance(reference, dict) or not {'path', 'source', 'independent'} <= set(reference) or
                    set(reference) - {'path', 'source', 'independent', 'target'} or
                    not isinstance(reference['source'], str) or type(reference['independent']) is not bool):
                raise ValueError('References require path, source and an explicit boolean independence assertion.')
            reference['path'] = _relative(reference['path'])
            reference.setdefault('target', item['target'])
        elif 'reference' in item:
            raise ValueError('Omit reference when no reference mask is supplied.')
        item.setdefault('scope', 'all')
        item.setdefault('roi', None)
        item.setdefault('invert', False)
        item.setdefault('image_source', 'Explicit batch image supplied by the user')
        normalized.append(item)
    return {'schema': MANIFEST_SCHEMA, 'samples': normalized}


def _settings(sample):
    return {key: deepcopy(value) for key, value in sample.items()
            if key not in {'id', 'image', 'mask', 'valid_mask', 'reference'}}


def _descriptors(sample, base):
    """Hash inputs in bounded chunks; missing/corrupt samples can fail locally."""
    paths = {name: sample[name] for name in ('image', 'mask', 'valid_mask') if name in sample}
    if 'reference' in sample:
        paths['reference'] = sample['reference']['path']
    descriptors = {}
    for role, relative in paths.items():
        path = _input_path(base, relative)
        descriptor = {'path': relative, 'state': 'unavailable', 'sha256': None, 'bytes': None}
        try:
            if not path.is_file():
                raise OSError('The declared input is not a regular file.')
            size = path.stat().st_size
            if not 0 < size <= _INPUT_LIMITS[role]:
                descriptor.update(state='outside_size_limit', bytes=size)
            else:
                digest = hashlib.sha256()
                consumed = 0
                with path.open('rb') as stream:
                    while chunk := stream.read(1024 * 1024):
                        consumed += len(chunk)
                        if consumed > _INPUT_LIMITS[role]:
                            raise OSError('Input grew beyond its size limit.')
                        digest.update(chunk)
                if consumed != size:
                    raise OSError('Input changed while its identity was being captured.')
                descriptor.update(state='available', bytes=size, sha256=digest.hexdigest())
        except OSError:
            pass
        descriptors[role] = descriptor
    return descriptors


def _identity(manifest, base):
    items = []
    for sample in manifest['samples']:
        inputs = _descriptors(sample, base)
        fingerprint = _digest(_canonical({'software_version': VERSION, 'sample': sample, 'inputs': inputs}))
        items.append({'id': sample['id'], 'fingerprint': fingerprint, 'inputs': inputs})
    body = {'schema': 'geomasklab-batch-identity/1.0', 'software_version': VERSION,
            'manifest_sha256': _digest(_canonical(manifest)), 'samples': items}
    return {**body, 'fingerprint': _digest(_canonical(body))}


def _read_input(base, descriptor, role):
    if descriptor['state'] != 'available':
        raise ValueError('A declared input is missing, unreadable or outside its size limit.')
    path = _input_path(base, descriptor['path'])
    with path.open('rb') as stream:
        raw = stream.read(_INPUT_LIMITS[role] + 1)
    if len(raw) != descriptor['bytes'] or _digest(raw) != descriptor['sha256']:
        raise ValueError('Input bytes changed after the batch identity was captured.')
    return raw


def _measurements(bundle):
    _, files = load_verified_bundle(bundle)
    result = json.loads(files['result.json'])
    metrics = result['metrics']
    validity = metrics.get('validity_measurements')
    region = validity['valid_region_pixels'] if validity else metrics['scope_area_pixels']
    return {'foreground_pixels': metrics['pixel_area'], 'valid_region_pixels': region,
            'coverage_of_valid_region': metrics['pixel_area'] / region if region else None,
            'geometric_region_pixels': metrics['scope_area_pixels'],
            'excluded_region_pixels': validity['excluded_region_pixels'] if validity else 0,
            'semantic_review_state': result['semantic_review']['state']}


def _row(sid, status, **fields):
    return {'id': sid, 'status': status, 'foreground_pixels': None, 'valid_region_pixels': None,
            'coverage_of_valid_region': None, 'geometric_region_pixels': None,
            'excluded_region_pixels': None, 'semantic_review_state': None,
            'evidence': None, 'reference': None, 'error': None, **fields}


def _summary(identity, rows, status):
    complete = [row for row in rows if row['status'] == 'completed']
    defined = [row for row in complete if row['valid_region_pixels'] > 0]
    foreground = sum(row['foreground_pixels'] for row in defined)
    denominator = sum(row['valid_region_pixels'] for row in defined)
    return {'schema': SUMMARY_SCHEMA, 'software_version': identity['software_version'],
            'batch_id': identity['fingerprint'][:12],
            'batch_fingerprint': identity['fingerprint'], 'status': status,
            'sample_count': len(rows), 'completed_count': len(complete),
            'failed_count': sum(row['status'] == 'failed' for row in rows),
            'cancelled_count': sum(row['status'] == 'cancelled' for row in rows),
            'pending_count': sum(row['status'] == 'pending' for row in rows),
            'aggregate': {'coverage_basis': 'foreground / selected valid region',
                'defined_coverage_samples': len(defined),
                'undefined_coverage_samples': len(complete) - len(defined),
                'macro_mean_coverage': math.fsum(row['coverage_of_valid_region'] for row in defined) / len(defined) if defined else None,
                'micro_weighted_coverage': foreground / denominator if denominator else None,
                'summed_foreground_pixels': foreground, 'summed_valid_region_pixels': denominator,
                'failed_samples_included': False},
            'samples': rows, 'inference_performed': False, 'origin_authenticated': False,
            'verification_scope': 'Replay completed samples and aggregate arithmetic; failure causes and supplied provenance are not authenticated.'}


def summary_csv(summary):
    """Export successful zero measurements as zero and unavailable values blank."""
    stream = io.StringIO(newline='')
    columns = ['id', 'status', 'foreground_pixels', 'valid_region_pixels',
               'coverage_of_valid_region', 'geometric_region_pixels', 'excluded_region_pixels',
               'semantic_review_state', 'evidence', 'reference', 'error_code']
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    for sample in summary['samples']:
        row = {key: sample.get(key) for key in columns}
        row['error_code'] = sample['error']['code'] if sample.get('error') else None
        writer.writerow(row)
    return stream.getvalue().encode('utf-8')


def _save_summary(output, identity, rows, status, progress=None):
    summary = _summary(identity, deepcopy(rows), status)
    _atomic(output / 'batch_summary.json', _json_bytes(summary), owner=identity['fingerprint'])
    _atomic(output / 'batch_summary.csv', summary_csv(summary), owner=identity['fingerprint'])
    if progress:
        progress(deepcopy(summary))
    return summary


def _verify_sample(folder, sample, expected):
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError('Completed sample output is not a regular directory.')
    receipt_path = folder / 'receipt.json'
    if receipt_path.is_symlink() or not receipt_path.is_file() or receipt_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError('Sample receipt exceeds its resource or path limits.')
    receipt = json.loads(receipt_path.read_bytes())
    required = {'evidence.zip', 'image-input.bin', 'receipt.json'}
    if 'reference' in sample:
        required.add('reference.zip')
    if {path.name for path in folder.iterdir()} != required:
        raise ValueError('Unexpected or missing completed sample files.')
    artifacts = {}
    for name in required - {'receipt.json'}:
        path = folder / name
        limit = MAX_IMAGE_BYTES if name == 'image-input.bin' else MAX_BUNDLE_BYTES
        if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
            raise ValueError('Completed sample artifact exceeds its resource or path limits.')
        raw = path.read_bytes()
        artifacts[name] = {'sha256': _digest(raw), 'bytes': len(raw)}
    expected_receipt = {'schema': 'geomasklab-batch-sample/1.0',
        'software_version': expected['software_version'], 'sample_id': sample['id'],
        'sample_fingerprint': expected['fingerprint'], 'inputs': expected['inputs'],
        'settings': _settings(sample), 'reference_settings': sample.get('reference'),
        'artifacts': artifacts}
    if _canonical(receipt) != _canonical(expected_receipt):
        raise ValueError('Completed sample receipt or artifact identity disagrees.')
    payload = (folder / 'evidence.zip').read_bytes()
    _, files = load_verified_bundle(payload)
    result = json.loads(files['result.json'])
    task = result['task']
    if (task['target'] != sample['target'] or task['side'] != sample['scope'] or
            task.get('roi') != sample['roi'] or task.get('invert', False) != sample['invert'] or
            result.get('software_version') != expected['software_version'] or
            result['external_mask']['source'] != sample['source'] or
            result['provenance']['source'] != sample['image_source']):
        raise ValueError('Completed evidence disagrees with declared batch settings.')
    bound = {'image': (folder / 'image-input.bin').read_bytes(), 'mask': files['source_mask.png']}
    if 'valid_mask' in sample:
        bound['valid_mask'] = files['source_valid_mask.png']
        if result['analysis_config']['validity']['source'] != sample['valid_source']:
            raise ValueError('Saved validity provenance disagrees with the manifest.')
    elif 'analysis_config' in result:
        raise ValueError('Unexpected validity declaration in a batch sample.')
    with Image.open(io.BytesIO(bound['image'])) as raw, Image.open(io.BytesIO(files['original.png'])) as saved:
        if raw.width * raw.height > MAX_IMAGE_PIXELS or getattr(raw, 'n_frames', 1) != 1:
            raise ValueError('Retained image upload exceeds the single-frame pixel limit.')
        normalized = ImageOps.exif_transpose(raw).convert('RGB')
        if normalized.size != saved.size or normalized.tobytes() != saved.tobytes():
            raise ValueError('Saved image pixels disagree with the original upload.')
    reference_name = None
    if 'reference' in sample:
        packet = (folder / 'reference.zip').read_bytes()
        verify_reference_packet(packet)
        import zipfile
        with zipfile.ZipFile(io.BytesIO(packet)) as archive:
            bound['reference'] = archive.read('reference.png')
            record = json.loads(archive.read('evaluation.json'))
            if archive.read('prediction.zip') != payload:
                raise ValueError('Reference packet uses different prediction evidence.')
        ref = sample['reference']
        if (record['reference']['source'] != ref['source'] or record['target'] != ref['target'] or
                record['reference']['independent_user_assertion'] != ref['independent']):
            raise ValueError('Reference packet disagrees with the manifest assertions.')
        reference_name = sample['id'] + '/reference.zip'
    for role, raw in bound.items():
        descriptor = expected['inputs'][role]
        if descriptor['state'] != 'available' or descriptor['bytes'] != len(raw) or descriptor['sha256'] != _digest(raw):
            raise ValueError('Retained input bytes disagree with the pinned sample identity.')
    return _row(sample['id'], 'completed', **_measurements(payload),
                evidence=sample['id'] + '/evidence.zip', reference=reference_name)


def _validate_saved(output, allow_missing_csv=False):
    for child in output.iterdir():
        if child.is_symlink() or (child.name in {'debug.log', '.batch.lock'} and not child.is_file()):
            raise ValueError('Batch output cannot contain symbolic links or non-file log/lock paths.')
    for name in ('batch_manifest.json', 'batch_identity.json', 'batch_summary.json', 'batch_summary.csv'):
        path = output / name
        if name == 'batch_summary.csv' and allow_missing_csv and not path.exists():
            continue
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_MANIFEST_BYTES * 2:
            raise ValueError('Batch metadata exceeds its resource or path limits.')
    manifest = validate_manifest(json.loads((output / 'batch_manifest.json').read_bytes()))
    identity = json.loads((output / 'batch_identity.json').read_bytes())
    if (set(identity) != {'schema', 'software_version', 'manifest_sha256', 'samples', 'fingerprint'} or
            identity['schema'] != 'geomasklab-batch-identity/1.0' or
            not isinstance(identity['software_version'], str) or not 1 <= len(identity['software_version']) <= 64 or
            identity['manifest_sha256'] != _digest(_canonical(manifest)) or
            identity['fingerprint'] != _digest(_canonical({key: value for key, value in identity.items() if key != 'fingerprint'})) or
            len(identity['samples']) != len(manifest['samples'])):
        raise ValueError('Batch identity or manifest binding disagrees.')
    for sample, pinned in zip(manifest['samples'], identity['samples']):
        roles = {'image', 'mask'} | ({'valid_mask'} if 'valid_mask' in sample else set()) | ({'reference'} if 'reference' in sample else set())
        if not isinstance(pinned.get('inputs'), dict) or set(pinned['inputs']) != roles:
            raise ValueError('Pinned input roles disagree with the manifest.')
        for role, descriptor in pinned['inputs'].items():
            relative = sample['reference']['path'] if role == 'reference' else sample[role]
            if (not isinstance(descriptor, dict) or set(descriptor) != {'path', 'state', 'sha256', 'bytes'} or
                    descriptor['path'] != relative or descriptor['state'] not in {'available', 'unavailable', 'outside_size_limit'}):
                raise ValueError('Pinned input descriptor disagrees with the manifest.')
            if descriptor['state'] == 'available' and (type(descriptor['bytes']) is not int or
                    not 0 < descriptor['bytes'] <= _INPUT_LIMITS[role] or
                    not isinstance(descriptor['sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', descriptor['sha256'])):
                raise ValueError('Invalid pinned input byte identity.')
            if (descriptor['state'] == 'unavailable' and (descriptor['bytes'] is not None or descriptor['sha256'] is not None) or
                    descriptor['state'] == 'outside_size_limit' and
                    (type(descriptor['bytes']) is not int or descriptor['bytes'] < 0 or descriptor['sha256'] is not None)):
                raise ValueError('Invalid unavailable input descriptor.')
        if (set(pinned) != {'id', 'fingerprint', 'inputs'} or pinned['id'] != sample['id'] or
                pinned['fingerprint'] != _digest(_canonical({'software_version': identity['software_version'],
                                                            'sample': sample, 'inputs': pinned['inputs']}))):
            raise ValueError('Pinned sample settings disagree with the manifest.')
    return manifest, identity


def _verify_batch(output_dir, recover=False):
    output = Path(output_dir).resolve()
    manifest, identity = _validate_saved(output, allow_missing_csv=recover)
    saved = json.loads((output / 'batch_summary.json').read_bytes())
    if len(saved['samples']) != len(manifest['samples']):
        raise ValueError('Batch summary sample count disagrees.')
    rows = []
    original_rows = []
    allowed = {'batch_manifest.json', 'batch_identity.json', 'batch_summary.json', 'batch_summary.csv',
               'debug.log', '.batch.lock'}
    for sample, pinned, row in zip(manifest['samples'], identity['samples'], saved['samples']):
        sid = sample['id']
        if row['id'] != sid or row['status'] not in {'completed', 'failed', 'cancelled', 'pending'}:
            raise ValueError('Batch summary sample identity or state disagrees.')
        if row['status'] == 'completed':
            recomputed = _verify_sample(output / sid, sample, {**pinned, 'software_version': identity['software_version']})
            if _canonical(row) != _canonical(recomputed):
                raise ValueError('Completed sample summary disagrees with verified pixels.')
            allowed.add(sid)
            rows.append(recomputed)
            original_rows.append(recomputed)
        else:
            expected = _row(sid, row['status'], error=row.get('error'))
            if _canonical(row) != _canonical(expected) or (row['status'] != 'failed' and row.get('error') is not None):
                raise ValueError('Incomplete samples must have unavailable measurements.')
            if row['status'] == 'failed' and (not isinstance(row.get('error'), dict) or
                    row['error'] not in [{'code': code, 'message': _PUBLIC_ERROR} for code in ('InvalidInput', 'ProcessingError')]):
                raise ValueError('Public failure records must use the concise error contract.')
            original_rows.append(expected)
            if recover and (output / sid).exists():
                rows.append(_verify_sample(output / sid, sample, {**pinned, 'software_version': identity['software_version']}))
                allowed.add(sid)
            else:
                rows.append(expected)
    if {path.name for path in output.iterdir()} - allowed:
        raise ValueError('Unexpected batch output files or incomplete sample directories.')
    status = saved['status']
    valid_status = _status(original_rows)
    if status != valid_status:
        raise ValueError('Batch status disagrees with its sample states.')
    original = _summary(identity, original_rows, status)
    csv_path = output / 'batch_summary.csv'
    csv_matches = csv_path.is_file() and csv_path.read_bytes() == summary_csv(original)
    if _canonical(saved) != _canonical(original) or (not csv_matches and not recover):
        raise ValueError('Batch summary or CSV disagrees with recomputed aggregate arithmetic.')
    return {**_summary(identity, rows, _status(rows)), 'verified': True}


def _status(rows):
    return ('running' if any(row['status'] == 'pending' for row in rows) else
            'cancelled' if any(row['status'] == 'cancelled' for row in rows) else
            'completed_with_errors' if any(row['status'] == 'failed' for row in rows) else 'completed')


def verify_batch(output_dir):
    """Replay completed artifacts and summary without the original input folder."""
    return _verify_batch(output_dir)


def run_batch(manifest, *, base_dir, output_dir, resume=False, cancel=None, progress=None):
    """Execute an explicit manifest, isolating failures and checking safe resume.

    ``cancel`` is a cooperative zero-argument predicate checked before each sample
    and before publishing its artifacts. ``progress`` receives independent summary
    snapshots. A cancelled sample has no successful output. Resume requires exactly
    the same input bytes, settings and software version, and replays every already
    completed artifact. Conflicting output is rejected rather than overwritten.
    """
    if type(resume) is not bool:
        raise ValueError('Resume must be boolean.')
    manifest = validate_manifest(manifest)
    base = Path(base_dir).resolve()
    output = Path(output_dir).resolve()
    if not base.is_dir() or output == base:
        raise ValueError('Use an existing input base directory and a distinct batch output directory.')
    if Path(output_dir).is_symlink():
        raise ValueError('Batch output cannot be a symbolic link.')
    for sample in manifest['samples']:
        names = [sample[role] for role in ('image', 'mask', 'valid_mask') if role in sample]
        if 'reference' in sample:
            names.append(sample['reference']['path'])
        for name in names:
            if _input_path(base, name).is_relative_to(output):
                raise ValueError('Batch output must not contain any declared input files.')
    identity = _identity(manifest, base)
    output.mkdir(parents=True, exist_ok=True)
    with _output_lock(output):
        return _run_locked(manifest, base, output, identity, resume, cancel, progress)


def _run_locked(manifest, base, output, identity, resume, cancel, progress):
    existing = {path.name for path in output.iterdir()} - {'.batch.lock'}
    if existing and not resume:
        raise ValueError('Output already exists; explicitly request verified resume or choose a new directory.')
    if resume and existing:
        _, saved_identity = _validate_saved(output, allow_missing_csv=True)
        if _canonical(saved_identity) != _canonical(identity):
            raise ValueError('Resume rejected: input bytes, settings or software version differ from the pinned batch.')
        _recover_atomic(output, identity)
        _recover_staging(output, identity)
        saved = _verify_batch(output, recover=True)
        rows = deepcopy(saved['samples'])
    else:
        rows = [_row(sample['id'], 'pending') for sample in manifest['samples']]
    if not (output / 'batch_identity.json').exists():
        _atomic(output / 'batch_manifest.json', _json_bytes(manifest), owner=identity['fingerprint'])
        _atomic(output / 'batch_identity.json', _json_bytes(identity), owner=identity['fingerprint'])
    for index, row in enumerate(rows):
        if row['status'] != 'completed':
            rows[index] = _row(row['id'], 'pending')
    _save_summary(output, identity, rows, _status(rows), progress)
    for index, (sample, pinned) in enumerate(zip(manifest['samples'], identity['samples'])):
        if rows[index]['status'] == 'completed':
            continue
        if cancel and cancel():
            for pending in range(index, len(rows)):
                if rows[pending]['status'] != 'completed':
                    rows[pending] = _row(rows[pending]['id'], 'cancelled')
            return _save_summary(output, identity, rows, 'cancelled', progress)
        sid = sample['id']
        try:
            with tempfile.TemporaryDirectory(dir=output, prefix='.sample-') as temporary:
                parent = Path(temporary)
                (parent / '.owner.json').write_bytes(_json_bytes({
                    'schema': 'geomasklab-batch-staging/1.0',
                    'batch_fingerprint': identity['fingerprint'], 'sample_id': sid}))
                stage = parent / sid
                stage.mkdir()
                raw = {role: _read_input(base, value, role) for role, value in pinned['inputs'].items()}
                payload = create_evidence(raw['image'], raw['mask'],
                    target=sample['target'], source=sample['source'], aligned=sample['aligned'],
                    scope=sample['scope'], roi=sample['roi'], invert=sample['invert'],
                    image_source=sample['image_source'], valid_mask=raw.get('valid_mask'),
                    valid_source=sample.get('valid_source'))
                (stage / 'evidence.zip').write_bytes(payload)
                (stage / 'image-input.bin').write_bytes(raw['image'])
                if 'reference' in sample:
                    ref = sample['reference']
                    record, difference = evaluate_reference(payload, raw['reference'], source=ref['source'],
                        target=ref['target'], independent=ref['independent'], created_at=timestamp())
                    (stage / 'reference.zip').write_bytes(evaluation_packet(record, difference, payload, raw['reference']))
                artifacts = {path.name: {'sha256': _digest(path.read_bytes()), 'bytes': path.stat().st_size}
                             for path in stage.iterdir()}
                receipt = {'schema': 'geomasklab-batch-sample/1.0', 'software_version': VERSION,
                    'sample_id': sid, 'sample_fingerprint': pinned['fingerprint'], 'inputs': pinned['inputs'],
                    'settings': _settings(sample), 'reference_settings': sample.get('reference'), 'artifacts': artifacts}
                (stage / 'receipt.json').write_bytes(_json_bytes(receipt))
                completed = _verify_sample(stage, sample, {**pinned, 'software_version': VERSION})
                if cancel and cancel():
                    for pending in range(index, len(rows)):
                        if rows[pending]['status'] != 'completed':
                            rows[pending] = _row(rows[pending]['id'], 'cancelled')
                    return _save_summary(output, identity, rows, 'cancelled', progress)
                if (output / sid).exists():
                    raise ValueError('Conflicting sample output cannot be overwritten.')
                os.replace(stage, output / sid)
                rows[index] = completed
        except Exception as error:
            with (output / 'debug.log').open('a', encoding='utf-8') as log:
                log.write('\nSample ' + sid + '\n')
                traceback.print_exc(file=log)
            code = 'InvalidInput' if isinstance(error, (ValueError, OSError, KeyError)) else 'ProcessingError'
            rows[index] = _row(sid, 'failed', error={'code': code, 'message': _PUBLIC_ERROR})
        _save_summary(output, identity, rows, _status(rows), progress)
    status = 'completed_with_errors' if any(row['status'] == 'failed' for row in rows) else 'completed'
    return _save_summary(output, identity, rows, status, progress)


def batch_packet(output_dir):
    """Export only verified public artifacts; local logs and locks stay outside."""
    output = Path(output_dir).resolve()
    with _output_lock(output):
        payload = _batch_packet_locked(output)
        verify_batch_packet(payload)
        return payload


def _batch_packet_locked(output):
    facts = verify_batch(output)
    if facts['status'] == 'running':
        raise ValueError('Wait for completion or cancellation before exporting a batch packet.')
    names = ['batch_manifest.json', 'batch_identity.json', 'batch_summary.json', 'batch_summary.csv']
    for row in facts['samples']:
        if row['status'] == 'completed':
            names.extend(row['id'] + '/' + name for name in ('receipt.json', 'image-input.bin', 'evidence.zip'))
            if row['reference']:
                names.append(row['reference'])
    if sum((output / name).stat().st_size for name in names) > MAX_PACKET_BYTES:
        raise ValueError('Batch packet expanded size exceeds 256 MB; export a smaller manifest.')
    files = {name: (output / name).read_bytes() for name in names}
    manifest = {'schema': 'geomasklab-batch-packet/1.0',
        'batch_fingerprint': facts['batch_fingerprint'],
        'checksums': {name: {'sha256': _digest(raw), 'bytes': len(raw)} for name, raw in files.items()},
        'verification_scope': facts['verification_scope']}
    raw_manifest = _json_bytes(manifest)
    if sum(map(len, files.values())) + len(raw_manifest) > MAX_PACKET_BYTES:
        raise ValueError('Batch packet expanded size exceeds 256 MB; export a smaller manifest.')
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, raw in files.items():
            archive.writestr(name, raw)
        archive.writestr('manifest.json', raw_manifest)
    payload = stream.getvalue()
    if len(payload) > MAX_PACKET_BYTES:
        raise ValueError('Batch packet compressed size exceeds 256 MB; export a smaller manifest.')
    return payload


def verify_batch_packet(payload):
    """Validate flat/two-level packet membership, hashes and offline replay."""
    if len(payload) > MAX_PACKET_BYTES:
        raise ValueError('Batch packet exceeds the 256 MB size limit.')
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        if (len(names) != len(set(names)) or len(names) > MAX_SAMPLES * 4 + 5 or
                sum(item.file_size for item in infos) > MAX_PACKET_BYTES or
                'manifest.json' not in names):
            raise ValueError('Invalid batch packet membership or expanded size.')
        top = {'batch_manifest.json', 'batch_identity.json', 'batch_summary.json', 'batch_summary.csv', 'manifest.json'}
        if not top <= set(names):
            raise ValueError('Required batch packet metadata is missing.')
        for item in infos:
            parts = item.filename.split('/')
            valid = item.filename in top or (len(parts) == 2 and _ID.fullmatch(parts[0]) and
                parts[0].casefold() not in _RESERVED and parts[1] in {'receipt.json', 'image-input.bin', 'evidence.zip', 'reference.zip'})
            if not valid or item.is_dir() or ((item.external_attr >> 16) & 0o170000) == 0o120000:
                raise ValueError('Unsafe or unexpected batch packet member.')
            limit = (MAX_IMAGE_BYTES if parts[-1] == 'image-input.bin' else
                     MAX_BUNDLE_BYTES if parts[-1] in {'evidence.zip', 'reference.zip'} else
                     MAX_MANIFEST_BYTES * 2)
            if item.file_size > limit:
                raise ValueError('Batch packet member exceeds its declared resource limit.')
        manifest = json.loads(archive.read('manifest.json'))
        if (set(manifest) != {'schema', 'batch_fingerprint', 'checksums', 'verification_scope'} or
                manifest['schema'] != 'geomasklab-batch-packet/1.0' or
                set(manifest['checksums']) != set(names) - {'manifest.json'}):
            raise ValueError('Batch packet checksum membership disagrees.')
        with tempfile.TemporaryDirectory(prefix='geomasklab-batch-verify-') as temporary:
            root = Path(temporary).resolve()
            for name in names:
                if name == 'manifest.json':
                    continue
                raw = archive.read(name)
                if manifest['checksums'][name] != {'sha256': _digest(raw), 'bytes': len(raw)}:
                    raise ValueError('Batch packet checksum mismatch.')
                path = (root / name).resolve()
                if not path.is_relative_to(root):
                    raise ValueError('Batch packet path escapes the verification directory.')
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            facts = verify_batch(root)
            if (facts['status'] == 'running' or manifest['batch_fingerprint'] != facts['batch_fingerprint'] or
                    manifest['verification_scope'] != facts['verification_scope']):
                raise ValueError('Batch packet identity or verification scope disagrees.')
            return facts
