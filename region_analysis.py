"""Explicit offline analysis of a verified full-image prediction.

This operation changes only the spatial scope. It does not call a model,
interpret a new semantic request, or turn an imported prediction into truth.
"""
from copy import deepcopy
import hashlib
import io
import json
import time

from PIL import Image, ImageOps
from export_bundle import load_verified_bundle
from product_contract import VERSION
from semantic_review import initial_review

SCOPE_NAMES = {'all': 'Whole image', 'left': 'Left half', 'right': 'Right half',
               'top': 'Top half', 'bottom': 'Bottom half'}


def validate_region(side, roi, width, height):
    """Validate one scope: an image/half-image, or a full-coordinate rectangle."""
    if not isinstance(side, str) or side not in SCOPE_NAMES:
        raise ValueError('Choose a valid analysis scope.')
    if roi is None:
        return None
    if side != 'all':
        raise ValueError('Choose either a half-image or a rectangle, not both.')
    if not isinstance(roi, dict) or set(roi) != {'xyxy', 'source', 'image_size'}:
        raise ValueError('ROI must contain xyxy, source, and image_size.')
    xyxy = roi['xyxy']
    if (not isinstance(xyxy, list) or len(xyxy) != 4 or
        any(type(v) is not int for v in xyxy) or
        not isinstance(roi['image_size'], list) or
        any(type(v) is not int for v in roi['image_size']) or
        roi['image_size'] != [width, height] or
        roi['source'] not in ('drawn', 'imported')):
        raise ValueError('ROI coordinates, source, or image dimensions are invalid.')
    x1, y1, x2, y2 = xyxy
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        raise ValueError('ROI must be nonempty and inside the image.')
    return deepcopy(roi)


def prepare_analysis(payload, side, roi, *, run_id, created_at, version,
                     statistics, constrain):
    """Verify first, then return a derived record and an explicit file allowlist."""
    start = time.perf_counter()
    facts, source_files = load_verified_bundle(payload)
    source = json.loads(source_files['result.json'])
    if source.get('status') not in ('completed', 'needs_review'):
        raise ValueError('The source must be a completed mask result.')
    roi = validate_region(side, roi, facts['width'], facts['height'])
    if not isinstance(source['metrics'].get('candidate_stats'), dict):
        raise ValueError('The source does not contain supported candidate measurements.')
    with Image.open(io.BytesIO(source_files['original.png'])) as raw:
        image = raw.convert('RGB')
    with Image.open(io.BytesIO(source_files['full_mask.png'])) as raw:
        full = raw.copy()
    task = deepcopy(source['task'])
    task.update(side=side, roi=roi, scope_rule='deterministic_pixel_scope')
    positive = ImageOps.invert(full) if task.get('invert') else full
    mask = constrain(positive, side, roi)
    metrics = statistics(mask, side, roi, positive)
    metrics['scope_label'] = SCOPE_NAMES[side]
    metrics['spatial_rule'] = 'Deterministic pixel crop; area_ratio uses the whole image as its denominator.'
    overlay = image.copy()
    overlay.paste(Image.blend(image, Image.new('RGB', image.size, (69, 213, 152)), .48), (0, 0), mask)
    files = {'full_mask.png': source_files['full_mask.png']}
    if 'source_mask.png' in source_files:
        files['source_mask.png'] = source_files['source_mask.png']
    for name, value in (('mask.png', mask), ('overlay.png', overlay)):
        encoded = io.BytesIO()
        value.save(encoded, format='PNG')
        files[name] = encoded.getvalue()
    origin = deepcopy(source.get('source_prediction')) or {
        'run_id': source['id'], 'software_version': source.get('software_version'),
        'mode': source['mode'], 'query': source['query'], 'task': deepcopy(source['task']),
        'provenance': deepcopy(source['provenance']),
        'service_metadata': deepcopy(source.get('service_metadata', {})),
        'duration_ms': source.get('duration_ms')}
    provenance = deepcopy(source['provenance'])
    provenance['planner'] = 'deterministic_saved_mask_analysis'
    label = 'Rectangle ROI' if roi else SCOPE_NAMES[side]
    scope_text = 'rectangle ROI' if roi else SCOPE_NAMES[side].lower()
    result = {
        'id': run_id, 'session_id': source['session_id'], 'parent_run_id': source['id'],
        'version': version, 'software_version': VERSION, 'created_at': created_at,
        'query': f'Recalculate the {scope_text} from the saved {task["target"]} mask.',
        'mode': source['mode'], 'execution_kind': 'saved_mask_region_analysis',
        'inference_performed': False, 'task': task,
        'task_options': {'roi': roi, 'roi_source': 'explicit_offline_selection',
                         'quality_mode': task.get('quality_mode'),
                         'effective_quality_mode': task.get('effective_quality_mode')},
        'provenance': provenance, 'source_prediction': origin,
        'derived_from': {'run_id': source['id'], 'bundle_sha256': hashlib.sha256(payload).hexdigest(),
                         'mask_sha256': hashlib.sha256(source_files['mask.png']).hexdigest(),
                         'full_mask_sha256': source['full_mask_sha256'],
                         'execution_kind': source.get('execution_kind', 'segmentation')},
        'full_mask_sha256': source['full_mask_sha256'], 'metrics': metrics,
        'semantic_review': {**initial_review(), 'notice':
            'Self-reported review; not authenticated truth, an accuracy assessment, or a boundary correction.'},
        'status': 'completed' if metrics['pixel_area'] else 'needs_review',
        'message': f'{label}: {metrics["pixel_area"]:,} foreground pixels; '
                   f'{metrics["area_ratio"] * 100:.2f}% of the whole image. '
                   'Recalculated from a verified saved mask without model inference. '
                   'Review this derived result separately; pixel consistency does not establish accuracy.',
        'trace': [
            {'step': 1, 'name': 'Verify source evidence', 'state': 'completed',
             'detail': 'Verified file identities, mask replay, measurements, and review bindings.'},
            {'step': 2, 'name': 'Recalculate selected region', 'state': 'completed',
             'detail': 'Used the original full-image mask; no agent or segmentation service was called.'},
            {'step': 3, 'name': 'Create a separate result version', 'state': 'completed',
             'detail': 'Retained prediction provenance and reset semantic review to pending.'}]}
    result['duration_ms'] = round((time.perf_counter() - start) * 1000, 2)
    if source.get('external_mask'):
        result['external_mask'] = deepcopy(source['external_mask'])
    return result, files


def region_report(session, result):
    """Report local arithmetic separately from the upstream prediction execution."""
    m = result['metrics']
    origin = result['source_prediction']
    within = 'undefined (empty scope)' if m['scope_area_ratio'] is None else f'{m["scope_area_ratio"] * 100:.4f}%'
    lines = ['# GeoMaskLab saved-mask region analysis', '',
             f'- Run: {result["id"]}', f'- Parent run: {result["parent_run_id"]}',
             '- Execution: deterministic offline analysis; no model inference.',
             f'- Target: {result["task"]["target"]}; complement: {result["task"].get("invert", False)}',
             f'- Scope: {result["task"]["side"]}; ROI: {json.dumps(result["task"].get("roi"))}',
             f'- Foreground: {m["pixel_area"]:,} pixels',
             f'- Whole-image denominator: {m["total_pixels"]:,} pixels',
             f'- Whole-image coverage: {m["area_ratio"] * 100:.4f}%',
             f'- Selected-region denominator: {m["scope_area_pixels"]:,} pixels',
             f'- Within-region coverage: {within}',
             f'- Candidate connected components: {m["candidate_stats"]["candidate_count"]}; not validated object counts.',
             f'- Local verification and recalculation: {result["duration_ms"]} ms', '',
             '## Prediction provenance', '',
             f'- Upstream mode: {origin["mode"]}; procedural fixtures are not model predictions.',
             f'- External mask provenance (user supplied): {json.dumps(result.get("external_mask"), ensure_ascii=False, sort_keys=True)}',
             f'- Upstream run: {origin["run_id"]}',
             f'- Upstream software version: {origin.get("software_version")}',
             f'- Original prediction task: {json.dumps(origin["task"], ensure_ascii=False, sort_keys=True)}',
             f'- Original service metadata (historical): {json.dumps(origin["service_metadata"], ensure_ascii=False, sort_keys=True)}',
             f'- Original execution duration (historical): {origin.get("duration_ms")} ms',
             f'- Immediate source bundle SHA-256: {result["derived_from"]["bundle_sha256"]}',
             f'- Image SHA-256: {result["provenance"]["image_sha256"]}',
             f'- Full-mask SHA-256: {result["full_mask_sha256"]}', '',
             '## Review and limitations', '',
             f'- Semantic review: {result["semantic_review"]["state"]}',
             f'- Review events: {json.dumps(result["semantic_review"]["events"], ensure_ascii=False, sort_keys=True)}',
             '- Review of the parent prediction is not transferred to this derived result.',
             '- Integrity checks do not authenticate the source or establish semantic accuracy.',
             '- Coverage is measured in image pixels, not square meters or hectares.',
             '- Recalculating a region cannot correct a missed target or an inaccurate boundary.',
             '- Replay: python export_bundle.py <bundle.zip>', '']
    if result.get('imported_evidence'):
        lines.extend(['## Evidence handoff', '', '- Import did not run models.',
                      '- Single-run imports do not restore the complete branch history.', ''])
    return '\n'.join(lines)
