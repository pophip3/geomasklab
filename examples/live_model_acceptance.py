"""Run fresh live scene/segmentation requests, then replay saved pixel scopes.

Requires independently started and configured RemoteAgent and RemoteSAM services.
No responses, masks, demo fixtures, model weights, or GPU code are substituted by
this script. Passing checks establish software execution and pixel consistency,
not semantic accuracy, authenticated model origin, or a user study.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sys
import time
import uuid
import zipfile

from PIL import Image, ImageOps, __version__ as PILLOW_VERSION

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from _source_package import use_local_core
use_local_core()

TARGET_QUERIES = {
    'building': 'Extract all buildings in the whole image.',
    'aircraft': 'Extract all aircraft in the whole image.',
    'road': 'Extract all roads in the whole image.',
    'water': 'Extract all water in the whole image.',
    'tree': 'Extract all trees in the whole image.',
    'ship': 'Extract all ships in the whole image.',
}
SCENE_QUERY = 'Describe the scene in this image concisely.'
LIMITS = [
    'This is a single-image software acceptance run, not a semantic accuracy evaluation or user study.',
    'The scene and whole-image extraction use configured live endpoints; the script provides no substitute outputs.',
    'Left, right and rectangle cases replay the saved mask using deterministic pixel operations; they perform no new inference.',
    'Bundle verification proves file integrity and deterministic pixel arithmetic; it does not authenticate model origin.',
    'Pixel coverage uses image-grid denominators and is not geographic ground area.',
    'Target identity and mask boundaries remain subject to separate semantic review.',
]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def public_summary_value(value):
    """Keep the shareable summary free of credentials and machine locations."""
    if isinstance(value, dict):
        clean = {}
        for key, child in value.items():
            lowered = str(key).lower()
            if (lowered in {'api_key', 'authorization', 'password', 'token', 'endpoint', 'url',
                            'image_path', 'model_dir', 'checkpoint_path', 'tokenizer_path'} or
                    lowered.endswith(('_path', '_dir'))):
                clean[key] = '[local setting omitted]'
            else:
                clean[key] = public_summary_value(child)
        return clean
    if isinstance(value, (list, tuple)):
        return [public_summary_value(child) for child in value]
    if isinstance(value, str):
        value = re.sub(r'(?i)\bBearer\s+[^\s<>]+', 'Bearer [omitted]', value)
        value = re.sub(r'(?i)https?://[^\s\"\'<>]+', '[URL omitted]', value)
        value = re.sub(r'\b(?:127\.(?:\d{1,3}\.){2}\d{1,3}|10\.(?:\d{1,3}\.){2}\d{1,3}|'
                       r'192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})'
                       r'(?::\d+)?\b', '[private address omitted]', value)
        value = re.sub(r'(?i)\b[A-Z]:[\\/][^\r\n\"\'<>]+', '[local path omitted]', value)
        value = re.sub(r'(?<!\w)/(?:home|Users|tmp|mnt|var|opt)/[^\s\"\'<>]+', '[local path omitted]', value)
        return value
    return value


def normalize_input(path):
    raw = Path(path).read_bytes()
    if len(raw) > 12 * 1024 * 1024:
        raise ValueError('The input exceeds the workbench 12 MB upload limit.')
    with Image.open(io.BytesIO(raw)) as source:
        if source.width * source.height > 16_000_000:
            raise ValueError('The input exceeds the workbench 16 MP image limit.')
        normalized = ImageOps.exif_transpose(source).convert('RGB')
        normalized.info.clear()
    if min(normalized.size) < 2:
        raise ValueError('The left/right/rectangle acceptance needs at least a 2 by 2 image.')
    encoded = io.BytesIO()
    normalized.save(encoded, 'PNG')
    png = encoded.getvalue()
    if len(png) > 12 * 1024 * 1024:
        raise ValueError('The normalized PNG exceeds the workbench 12 MB upload limit.')
    return raw, png, normalized


def independent_pixel_check(full_bytes, mask_bytes, box, metrics):
    """Check clipping with direct Pillow operations and independent byte counts."""
    with Image.open(io.BytesIO(full_bytes)) as image:
        full = image.copy()
    with Image.open(io.BytesIO(mask_bytes)) as image:
        measured = image.copy()
    if full.mode != 'L' or measured.mode != 'L' or full.size != measured.size:
        raise ValueError('The saved masks must be aligned binary L-mode images.')
    if not set(full.tobytes()).issubset({0, 255}) or not set(measured.tobytes()).issubset({0, 255}):
        raise ValueError('Non-binary mask values cannot pass pixel acceptance.')
    w, h = full.size
    x1, y1, x2, y2 = box
    if not (0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h):
        raise ValueError('Invalid independent check rectangle.')
    reference = Image.new('L', (w, h), 0)
    cropped = full.crop(box)
    reference.paste(cropped, (x1, y1))
    area = cropped.tobytes().count(255)
    total = w * h
    selected = (x2 - x1) * (y2 - y1)
    expected_integers = {'pixel_area': area, 'total_pixels': total,
                         'scope_area_pixels': selected, 'width': w, 'height': h}
    for key, expected in expected_integers.items():
        if type(metrics.get(key)) is not int or metrics[key] != expected:
            raise ValueError('Independent pixel count disagrees with ' + key + '.')
    for key, expected in (('area_ratio', area / total), ('scope_area_ratio', area / selected)):
        actual = metrics.get(key)
        if type(actual) not in (int, float) or not math.isfinite(actual) or not math.isclose(actual, expected, rel_tol=0, abs_tol=1e-12):
            raise ValueError('Independent pixel denominator disagrees with ' + key + '.')
    if measured.tobytes() != reference.tobytes() or measured.tobytes().count(255) != area:
        raise ValueError('The saved mask does not match the independently selected pixel set.')
    return {'foreground_pixels': area, 'whole_image_pixels': total,
            'selected_region_pixels': selected, 'whole_image_coverage': area / total,
            'within_region_coverage': area / selected,
            'reference_pillow_pixel_set_exact': True}


def inspect_agent_metadata():
    """Optional read-only metadata probe; no image or inference request is sent."""
    from workbench.service_transport import request_json
    base = os.environ.get('GEO_AGENT_BASE_URL', '').rstrip('/')
    if not base:
        return {'available': False, 'reason': 'Agent URL is not configured.'}
    root = base[:-3] if base.endswith('/v1') else base
    try:
        result = request_json(root + '/model-info', timeout=5,
            headers={'Authorization': 'Bearer ' + os.environ.get('GEO_AGENT_API_KEY', 'EMPTY')})
        return {'available': True, 'ready_declaration': result.get('ready'),
                'metadata': result.get('metadata'), 'identity_authenticated': False}
    except Exception as exc:
        return {'available': False, 'reason': str(exc),
                'note': 'Some external model servers do not implement /model-info.'}


def checked_export(server, session, result, label, output, original_bytes,
                   full_bytes, box, build_bundle, verify_bundle):
    folder = server.DATA / session['id'] / result['id']
    payload = build_bundle(server.DATA / session['id'] / 'original.png', folder)
    facts = verify_bundle(payload)
    if facts.get('verified') is not True:
        raise ValueError('The core verifier did not confirm the exported ZIP.')
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        exported_original = archive.read('original.png')
        exported_full = archive.read('full_mask.png')
        exported_mask = archive.read('mask.png')
    if exported_original != original_bytes or exported_full != full_bytes:
        raise ValueError('Saved-mask replay changed the original image or full mask bytes.')
    counts = independent_pixel_check(exported_full, exported_mask, box, result['metrics'])
    if facts.get('pixel_area') != counts['foreground_pixels']:
        raise ValueError('The ZIP verifier and independent foreground counts disagree.')
    destination = output / (label + '.zip')
    destination.write_bytes(payload)
    return {'case': label, 'run_id': result['id'], 'version': result['version'],
            'status': result['status'], 'scope_box_xyxy': list(box), **counts,
            'zip_file': destination.name, 'zip_sha256': digest(payload),
            'mask_sha256': digest(exported_mask), 'full_mask_sha256': digest(exported_full),
            'original_image_bytes_preserved': True, 'full_mask_bytes_preserved': True,
            'bundle_verified': True, 'semantic_accuracy_verified': False,
            'semantic_review_state': facts.get('semantic_review_state'),
            'workbench_duration_ms': result.get('duration_ms')}


def run_acceptance(server, image, target, output, *, metadata_reader=inspect_agent_metadata,
                   build_bundle=None, verify_bundle=None):
    """Execute an explicit live workbench and return a shareable check report.

    Unit tests may supply an explicitly fake workbench boundary. The command-line
    entry point always supplies the actual workbench and configured endpoints.
    """
    if target not in TARGET_QUERIES:
        raise ValueError('Unsupported target.')
    if build_bundle is None or verify_bundle is None:
        from geomasklab.evidence import build_bundle as core_build, verify_bundle as core_verify
        build_bundle = build_bundle or core_build
        verify_bundle = verify_bundle or core_verify
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    report = {'schema': 'geomasklab-live-model-acceptance/1.0',
              'started_at_utc': datetime.now(timezone.utc).isoformat(),
              'software_version': server.VERSION, 'python_version': sys.version.split()[0],
              'pillow_version': PILLOW_VERSION,
              'acceptance_script_sha256': digest(Path(__file__).read_bytes()),
              'target': target, 'passed': False, 'failures': [], 'warnings': [], 'cases': [],
              'limits': list(LIMITS), 'semantic_accuracy_verified': False,
              'human_participants': 0,
              'client_settings': {'max_tokens_override': os.environ.get('GEO_AGENT_MAX_TOKENS'),
                                  'chat_timeout_seconds': os.environ.get('GEO_AGENT_TIMEOUT_SECONDS', '120')},
              'agent_metadata_probe': public_summary_value(metadata_reader())}

    def failure(stage, error):
        report['failures'].append({'stage': stage, 'error_type': type(error).__name__,
                                   'message': public_summary_value(str(error))})

    try:
        source, normalized_png, normalized = normalize_input(image)
        report['input'] = {'uploaded_file_sha256': digest(source),
                           'normalized_upload_sha256': digest(normalized_png),
                           'width': normalized.width, 'height': normalized.height,
                           'normalization': 'EXIF transpose, RGB conversion, PNG; image metadata removed.'}
        public = server.new_session(uploaded=base64.b64encode(normalized_png).decode('ascii'),
                                    name='Live model software acceptance')
        session = server.SESSIONS[public['id']]
        original_file = server.DATA / session['id'] / 'original.png'
        original_bytes = original_file.read_bytes()
        with Image.open(io.BytesIO(original_bytes)) as uploaded:
            if uploaded.size != normalized.size or uploaded.convert('RGB').tobytes() != normalized.tobytes():
                raise ValueError('Workbench upload normalization changed the expected image pixels.')
        report['input']['saved_original_sha256'] = digest(original_bytes)
        report['session_id'] = session['id']
    except Exception as exc:
        failure('input', exc)
        report['elapsed_ms'] = round((time.perf_counter() - started) * 1000, 2)
        write_report(output, report)
        return report

    try:
        step_started = time.perf_counter()
        scene = server.run_task(session, {'query': SCENE_QUERY, 'mode': 'live'})
        report['scene'] = {'run_id': scene['id'], 'version': scene['version'], 'status': scene['status'],
                           'agent_decision_status': scene.get('agent_decision', {}).get('status'),
                           'answer': public_summary_value(scene.get('message', '')),
                           'workbench_duration_ms': scene.get('duration_ms'),
                           'elapsed_ms': round((time.perf_counter() - step_started) * 1000, 2)}
        if (scene.get('mode') != 'live' or scene.get('status') != 'answered' or
                scene.get('agent_decision', {}).get('status') != 'completed' or
                not scene.get('message', '').strip() or scene.get('mask_url')):
            raise ValueError('Scene request did not produce a complete parsed live answer without segmentation.')
    except Exception as exc:
        failure('scene', exc)

    source_run = None
    try:
        step_started = time.perf_counter()
        source_run = server.run_task(session, {'query': TARGET_QUERIES[target], 'mode': 'live',
            'scope': 'all', 'roi': {}, 'quality_mode': 'fast', 'force_perception': True})
        report['segmentation'] = {'run_id': source_run['id'], 'version': source_run['version'],
            'status': source_run['status'],
            'agent_decision_status': source_run.get('agent_decision', {}).get('status'),
            'agent_feedback_status': source_run.get('agent_feedback', {}).get('status'),
            'workbench_duration_ms': source_run.get('duration_ms'),
            'elapsed_ms': round((time.perf_counter() - step_started) * 1000, 2),
            'fresh_perception_requested': True, 'cache_reuse_observed': bool(source_run.get('reused_from_run_id')),
            'model_metadata': public_summary_value(source_run.get('service_metadata', {})),
            'planner_decision_sha256': source_run.get('agent_decision', {}).get('raw_response_sha256'),
            'feedback_response_sha256': source_run.get('agent_feedback', {}).get('raw_response_sha256'),
            'failure_or_review_message': public_summary_value(source_run.get('message', ''))}
        task = source_run.get('task', {})
        if (source_run.get('mode') != 'live' or source_run.get('status') not in {'completed', 'needs_review'} or
                not source_run.get('mask_url') or source_run.get('reused_from_run_id') or
                source_run.get('agent_decision', {}).get('status') != 'tool_call' or
                task.get('target') != target or task.get('side') != 'all' or
                task.get('roi') is not None or task.get('invert')):
            raise ValueError('The fresh live request did not produce the requested whole-image target mask.')
        full_bytes = (server.DATA / session['id'] / source_run['id'] / 'full_mask.png').read_bytes()
        w, h = normalized.size
        whole = checked_export(server, session, source_run, 'whole-image-live', output,
            original_bytes, full_bytes, (0, 0, w, h), build_bundle, verify_bundle)
        whole.update(execution_kind='fresh_live_segmentation', saved_mask_replay=False)
        report['cases'].append(whole)
        if source_run.get('agent_feedback', {}).get('status') != 'completed':
            failure('tool_feedback', ValueError('The mask was preserved, but the Agent did not finish a parsed feedback answer.'))
    except Exception as exc:
        failure('segmentation_or_whole_export', exc)
        source_run = None

    if source_run is not None:
        roi_box = (w // 4, h // 4, max(w // 4 + 1, 3 * w // 4), max(h // 4 + 1, 3 * h // 4))
        scopes = [('left', 'left', None, (0, 0, w // 2, h)),
                  ('right', 'right', None, (w // 2, 0, w, h)),
                  ('rectangle', 'all', {'xyxy': list(roi_box), 'source': 'imported', 'image_size': [w, h]}, roi_box)]
        for label, side, roi, box in scopes:
            try:
                step_started = time.perf_counter()
                derived = server.recalculate_region(session, {'run_id': source_run['id'], 'scope': side, 'roi': roi})
                if (derived.get('inference_performed') is not False or
                        derived.get('execution_kind') != 'saved_mask_region_analysis' or
                        derived.get('parent_run_id') != source_run['id']):
                    raise ValueError('A scope replay did not declare saved-mask analysis without new inference.')
                case = checked_export(server, session, derived, label + '-saved-mask', output,
                    original_bytes, full_bytes, box, build_bundle, verify_bundle)
                case.update(execution_kind='saved_mask_region_analysis', saved_mask_replay=True,
                            inference_performed=False,
                            elapsed_ms=round((time.perf_counter() - step_started) * 1000, 2))
                report['cases'].append(case)
            except Exception as exc:
                failure(label + '_saved_mask_replay', exc)
        try:
            if (original_file.read_bytes() != original_bytes or
                    (server.DATA / session['id'] / source_run['id'] / 'full_mask.png').read_bytes() != full_bytes):
                raise ValueError('A replay changed the original saved image or full-mask bytes.')
        except Exception as exc:
            failure('source_preservation', exc)

    report['passed'] = not report['failures'] and len(report['cases']) == 4
    report['elapsed_ms'] = round((time.perf_counter() - started) * 1000, 2)
    write_report(output, report)
    return report


def write_report(output, report):
    (Path(output) / 'summary.json').write_text(
        json.dumps(public_summary_value(report), ensure_ascii=False, indent=2, allow_nan=False) + '\n',
        encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, default=ROOT / 'examples/data/naip-denver/image.png')
    parser.add_argument('--target', choices=tuple(TARGET_QUERIES), default='building')
    parser.add_argument('--output', type=Path, default=Path('outputs/model-acceptance'))
    parser.add_argument('--timeout', type=float, default=3600,
                        help='Agent chat timeout in seconds (5 to 3600); health probes remain 5 seconds.')
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or not 5 <= args.timeout <= 3600:
        parser.error('--timeout must be finite and between 5 and 3600 seconds.')
    # Every attempt has an isolated folder, so failed attempts cannot display a
    # previous successful run's ZIPs as their own results.
    run_name = datetime.now(timezone.utc).strftime('run-%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:8]
    output = args.output.resolve() / run_name
    output.mkdir(parents=True)
    os.environ['GEO_DATA_DIR'] = str(output / 'sessions')
    os.environ['GEO_AGENT_TIMEOUT_SECONDS'] = str(args.timeout)
    from workbench import server
    report = run_acceptance(server, args.image, args.target, output)
    print(json.dumps({'passed': report['passed'], 'cases_checked': len(report['cases']),
                      'failures': report['failures'], 'summary': str(output / 'summary.json')}, ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
