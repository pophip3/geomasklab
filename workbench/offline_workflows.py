"""HTTP adapters for installed-core comparison, inspection and explicit batches."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import uuid
import zipfile

from geomasklab.api import timestamp
from geomasklab.comparison import compare_bundles, comparison_packet
from geomasklab.components import inspect_components, component_packet
from geomasklab.batch import validate_manifest, run_batch, verify_batch, batch_packet

JOBS = {}
JOBS_LOCK = threading.RLock()
_ID = re.compile(r'[a-f0-9]{12}')
_FILE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}')
_RESERVED = {'con','prn','aux','nul',*(f'com{i}' for i in range(1,10)),*(f'lpt{i}' for i in range(1,10))}
MAX_UPLOAD_BYTES = 32 * 1024 * 1024


def _write_json(path, value):
    _write_bytes(path,json.dumps(value, indent=2, allow_nan=False).encode('utf-8'))


def _write_bytes(path, raw):
    temporary = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_bytes(raw)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _folder(data, job_id):
    if not isinstance(job_id, str) or not _ID.fullmatch(job_id):
        raise ValueError('Invalid offline batch ID.')
    return Path(data)/'offline-batches'/job_id


def save_comparison(data, bundles, *, domain_policy='intersection'):
    """Store a packet from the same installed-core operation shown in the UI."""
    record = compare_bundles(*bundles, domain_policy=domain_policy)
    packet = comparison_packet(*bundles, domain_policy=domain_policy)
    identifier = hashlib.sha256(packet).hexdigest()[:24]
    folder = Path(data)/'comparisons'
    folder.mkdir(exist_ok=True)
    _write_bytes(folder/(identifier+'.zip'),packet)
    return {**record, 'packet_url': '/api/comparison-export/'+identifier}


def save_inspection(data, bundle, *, min_area_pixels=1, boundary_filter='all'):
    record = inspect_components(bundle, min_area_pixels=min_area_pixels, boundary_filter=boundary_filter)
    packet = component_packet(bundle, min_area_pixels=min_area_pixels, boundary_filter=boundary_filter)
    identifier = hashlib.sha256(packet).hexdigest()[:24]
    folder = Path(data)/'inspections'
    folder.mkdir(exist_ok=True)
    _write_bytes(folder/(identifier+'.zip'),packet)
    with zipfile.ZipFile(io.BytesIO(packet)) as archive:
        selection = base64.b64encode(archive.read('selection.png')).decode('ascii')
    return {**record, 'selection_png_base64': selection, 'packet_url': '/api/component-export/'+identifier}


def verify_uploaded_packet(encoded):
    """Dispatch supported saved operations to their mandatory core replayers."""
    if not isinstance(encoded, str) or len(encoded)>18*1024*1024:
        raise ValueError('Review packets must be 12 MB or smaller in this browser.')
    try:
        raw = base64.b64decode(encoded.split(',', 1)[-1], validate=True)
        if len(raw)>12*1024*1024:raise ValueError('Review packets must be 12 MB or smaller in this browser.')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if sum(item.file_size for item in archive.infolist())>256*1024*1024:
                raise ValueError('Packet exceeds the browser expanded-size limit.')
            if 'manifest.json' in archive.namelist():
                if archive.getinfo('manifest.json').file_size>1024*1024:
                    raise ValueError('Packet manifest exceeds the size limit.')
                manifest=json.loads(archive.read('manifest.json'))
                if not isinstance(manifest,dict):raise ValueError('Packet manifest must be a JSON object.')
                schema = manifest.get('schema')
            else:
                schema = None
    except (zipfile.BadZipFile, OSError) as error:
        raise ValueError('Provide a supported ZIP review packet.') from error
    if schema=='geomasklab-comparison-packet/1.0':
        from geomasklab.comparison import verify_comparison_packet
        return {'kind': 'comparison', **verify_comparison_packet(raw)}
    if schema=='geomasklab-component-packet/1.0':
        from geomasklab.components import verify_component_packet
        return {'kind': 'components', **verify_component_packet(raw)}
    if schema=='geomasklab-reference-packet/1.0':
        from geomasklab.reference import verify_reference_packet
        return {'kind': 'reference', **verify_reference_packet(raw)}
    # Batch export has its own bounded nested-membership verifier.
    from geomasklab.batch import verify_batch_packet
    return {'kind': 'batch', **verify_batch_packet(raw)}


def get_offline_batch(data, job_id):
    folder = _folder(data, job_id)
    key = str(folder.resolve())
    with JOBS_LOCK:
        if key in JOBS:
            return json.loads(json.dumps(JOBS[key]['public']))
    if not (folder/'job.json').is_file():
        raise ValueError('Offline batch not found.')
    public = json.loads((folder/'job.json').read_text(encoding='utf-8'))
    if public['status'] in ('running', 'cancelling'):
        public['status'] = 'interrupted'
        public['notice'] = 'The service restarted. Resume verifies pinned identities and completed artifacts; damaged initial metadata or foreign files are rejected.'
    summary = folder/'output'/'batch_summary.json'
    if summary.is_file():
        public['summary'] = json.loads(summary.read_text(encoding='utf-8'))
        if public['status'] not in ('running','cancelling','interrupted'):
            public['packet_url']='/api/offline-batch-export/'+job_id
    return public


def _launch(data, job_id, *, resume):
    folder = _folder(data, job_id)
    key = str(folder.resolve())
    with JOBS_LOCK:
        if key in JOBS and JOBS[key]['public']['status'] in ('running', 'cancelling'):
            raise ValueError('This offline batch is still running.')
        event = threading.Event()
        public = {'id': job_id, 'status': 'running', 'started_at': timestamp(), 'resume': resume,
                  'notice': 'Cancellation takes effect at a sample boundary or before publishing a sample.'}
        JOBS[key] = {'public': public, 'cancel': event}
        _write_json(folder/'job.json', public)
    def progress(value):
        with JOBS_LOCK:
            public['progress'] = value
            _write_json(folder/'job.json', public)
    def worker():
        try:
            manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
            summary = run_batch(manifest, base_dir=folder/'inputs', output_dir=folder/'output',
                                resume=resume, cancel=event.is_set, progress=progress)
            with JOBS_LOCK:
                public.update(status=summary['status'], summary=summary, finished_at=timestamp(),
                    packet_url='/api/offline-batch-export/'+job_id)
        except (ValueError, OSError, KeyError) as error:
            with JOBS_LOCK:
                public.update(status='failed', error=str(error), finished_at=timestamp())
        except Exception:
            with JOBS_LOCK:
                public.update(status='failed', error='Offline processing failed. Local debug records are retained for diagnosis.', finished_at=timestamp())
        finally:
            with JOBS_LOCK:
                # A newer resume may start after this worker exposes its terminal state.
                if JOBS.get(key, {}).get('public') is public:
                    _write_json(folder/'job.json', public)
    threading.Thread(target=worker, daemon=True, name='geomasklab-offline-'+job_id).start()
    return get_offline_batch(data, job_id)


def start_offline_batch(data, payload):
    """Stage explicitly named browser uploads in an owned private input folder."""
    manifest = validate_manifest(payload.get('manifest'))
    files = payload.get('files')
    if not isinstance(files, list) or not 1<=len(files)<=128:
        raise ValueError('Upload 1 to 128 explicitly named input files.')
    root = Path(data)/'offline-batches'
    root.mkdir(exist_ok=True)
    identifier = uuid.uuid4().hex[:12]
    total, seen = 0, set()
    with tempfile.TemporaryDirectory(prefix='.upload-', dir=root) as temporary:
        stage = Path(temporary)
        inputs = stage/'inputs'
        inputs.mkdir()
        for item in files:
            if not isinstance(item, dict) or set(item)!={'name', 'data'}:
                raise ValueError('Each input upload requires name and data.')
            name = item['name']
            if (not isinstance(name, str) or not _FILE.fullmatch(name) or '..' in name or name.endswith('.') or
                    name.split('.')[0].casefold() in _RESERVED or name.casefold() in seen):
                raise ValueError('Uploaded filenames must be unique portable ASCII basenames without traversal.')
            seen.add(name.casefold())
            value = item['data']
            if not isinstance(value, str) or len(value)>MAX_UPLOAD_BYTES*4//3+1024:
                raise ValueError('Offline browser inputs exceed the 32 MB aggregate limit.')
            raw = base64.b64decode(value.split(',', 1)[-1], validate=True)
            total += len(raw)
            if total>MAX_UPLOAD_BYTES:
                raise ValueError('Offline browser inputs exceed the 32 MB aggregate limit; use the installed CLI for larger batches.')
            (inputs/name).write_bytes(raw)
        _write_json(stage/'manifest.json', manifest)
        # Publish inputs as one directory only after all uploads have validated.
        stage.rename(root/identifier)
    return _launch(data, identifier, resume=False)


def cancel_offline_batch(data, job_id):
    key = str(_folder(data, job_id).resolve())
    with JOBS_LOCK:
        job = JOBS.get(key)
        if not job or job['public']['status'] not in ('running', 'cancelling'):
            raise ValueError('This offline batch is not running.')
        job['cancel'].set()
        job['public']['status'] = 'cancelling'
    return get_offline_batch(data, job_id)


def resume_offline_batch(data, job_id):
    get_offline_batch(data, job_id)
    return _launch(data, job_id, resume=True)


def export_offline_batch(data, job_id):
    public = get_offline_batch(data, job_id)
    if public['status'] in ('running', 'cancelling'):
        raise ValueError('Wait for completion or cancellation before exporting.')
    return batch_packet(_folder(data, job_id)/'output')


def offline_batch_evidence(data, job_id, sample_id):
    """Open only a completed, source-replayed sample in the regular workbench."""
    public=get_offline_batch(data,job_id)
    if public['status'] in ('running','cancelling'):
        raise ValueError('Wait for completion or cancellation before opening results.')
    output=_folder(data,job_id)/'output'
    facts=verify_batch(output)
    selected=next((row for row in facts['samples'] if row['id']==sample_id and row['status']=='completed'),None)
    if not selected:raise ValueError('Choose a completed sample from the verified batch.')
    return (output/selected['id']/'evidence.zip').read_bytes()
