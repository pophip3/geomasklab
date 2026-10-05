"""Source-bound, deterministic inspection of clipped binary-mask components.

Inspection never changes prediction evidence. Components describe eight-connected
foreground pixels in the saved analysis result; they are not semantic objects.
"""
from collections import deque
import csv
import hashlib
import io
import json
import re
import zipfile

from PIL import Image

from .contract import VERSION
from .domain import png, selected_region, valid_image
from .evidence import load_verified_bundle

SCHEMA = 'geomasklab-component-inspection/1.0'
PACKET_SCHEMA = 'geomasklab-component-packet/1.0'
MAX_PACKET_BYTES = 384 * 1024 * 1024
MAX_COMPONENTS = 100_000
BOUNDARY_FILTERS = ('all', 'touching', 'interior')

BOUNDARY_RULES = {
    'neighborhood': 'Eight neighboring pixel positions; diagonal adjacency is included.',
    'image': 'At least one component pixel lies on an outer image row or column.',
    'roi': 'At least one component pixel has an in-image neighbor outside the selected geometric region.',
    'invalid': 'At least one component pixel has an in-image neighbor whose declared validity is zero.',
    'overlap': 'Boundary flags are independent and may overlap. An out-of-image neighbor only affects the image flag.',
}


def _canonical(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


def _options(min_area_pixels, boundary_filter):
    if type(min_area_pixels) is not int or min_area_pixels < 1:
        raise ValueError('Minimum component area must be a positive integer.')
    if boundary_filter not in BOUNDARY_FILTERS:
        raise ValueError('Boundary filter must be all, touching or interior.')
    return {'min_area_pixels': min_area_pixels, 'boundary_filter': boundary_filter}


def _inspect(bundle, *, min_area_pixels=1, boundary_filter='all'):
    options = _options(min_area_pixels, boundary_filter)
    facts, files = load_verified_bundle(bundle)
    result = json.loads(files['result.json'])
    task = result['task']
    with Image.open(io.BytesIO(files['mask.png'])) as saved:
        mask = saved.copy()
    width, height = mask.size
    pixels = mask.tobytes()
    geometric = selected_region(mask.size, task).tobytes()
    valid = valid_image(files, mask.size).tobytes()
    seen = bytearray(len(pixels))
    selection = bytearray(len(pixels))
    records = []
    for seed, value in enumerate(pixels):
        if not value or seen[seed]:
            continue
        if len(records) >= MAX_COMPONENTS:
            raise ValueError('Component inspection exceeds the 100,000-component limit; choose a smaller analysis region.')
        component_id = len(records) + 1
        queue = deque([seed])
        seen[seed] = 1
        area = sx = sy = 0
        left, top, right, bottom = width, height, 0, 0
        image_boundary = roi_boundary = invalid_boundary = False
        # Selection is written while visiting, then removed for a rejected component.
        # A second bounded flood-fill avoids retaining every component pixel as a list.
        while queue:
            index = queue.popleft()
            y, x = divmod(index, width)
            selection[index] = 255
            area += 1
            sx += x
            sy += y
            left, top = min(left, x), min(top, y)
            right, bottom = max(right, x + 1), max(bottom, y + 1)
            image_boundary |= x == 0 or y == 0 or x == width - 1 or y == height - 1
            for ny in range(max(0, y - 1), min(height, y + 2)):
                row = ny * width
                for nx in range(max(0, x - 1), min(width, x + 2)):
                    neighbor = row + nx
                    roi_boundary |= not geometric[neighbor]
                    invalid_boundary |= not valid[neighbor]
                    if pixels[neighbor] and not seen[neighbor]:
                        seen[neighbor] = 1
                        queue.append(neighbor)
        touching = image_boundary or roi_boundary or invalid_boundary
        reasons = []
        if area < min_area_pixels:
            reasons.append('below_minimum_area')
        if boundary_filter == 'touching' and not touching:
            reasons.append('no_boundary_contact')
        if boundary_filter == 'interior' and touching:
            reasons.append('boundary_contact')
        selected = not reasons
        if not selected:
            selection[seed] = 0
            queue = deque([seed])
            while queue:
                index = queue.popleft()
                y, x = divmod(index, width)
                for ny in range(max(0, y - 1), min(height, y + 2)):
                    row = ny * width
                    for nx in range(max(0, x - 1), min(width, x + 2)):
                        neighbor = row + nx
                        if selection[neighbor] and pixels[neighbor]:
                            selection[neighbor] = 0
                            queue.append(neighbor)
        records.append({
            'component_id': component_id, 'area_pixels': area,
            'bbox': [left, top, right, bottom],
            'centroid': {'x': round(sx / area + .5, 6), 'y': round(sy / area + .5, 6)},
            'touches_image_boundary': bool(image_boundary),
            'touches_roi_boundary': bool(roi_boundary),
            'touches_invalid_boundary': bool(invalid_boundary),
            'selected': selected, 'exclusion_reasons': reasons,
        })
    selected_records = [item for item in records if item['selected']]
    record = {
        'schema': SCHEMA, 'software_version': VERSION,
        'source_bundle_sha256': hashlib.sha256(bundle).hexdigest(),
        'source_image_sha256': hashlib.sha256(files['original.png']).hexdigest(),
        'source_result_mask_sha256': hashlib.sha256(files['mask.png']).hexdigest(),
        'source_run_id': result['id'], 'source_version': result['version'],
        'image_size': [width, height], 'source_task': task,
        'analysis_config': result.get('analysis_config'),
        'connectivity': 8,
        'component_id_order': 'First foreground pixel encountered in row-major order; filters do not renumber IDs.',
        'bbox_convention': 'Zero-based [x1, y1, x2, y2] with exclusive upper bounds.',
        'centroid_convention': 'Arithmetic mean of pixel centers (column + 0.5, row + 0.5), rounded to six decimal places.',
        'boundary_rules': BOUNDARY_RULES.copy(), 'options': options,
        'component_count': len(records), 'foreground_pixels': facts['pixel_area'],
        'selected_component_count': len(selected_records),
        'selected_foreground_pixels': sum(item['area_pixels'] for item in selected_records),
        'excluded_component_count': len(records) - len(selected_records),
        'components': records, 'source_mask_modified': False, 'inference_performed': False,
        'semantic_objects_verified': False,
        'interpretation': 'Candidate components are measured after geometric-region and validity clipping. '
            'Clipping can split one source component into several candidates. Boundary contact is a review hint, '
            'not proof of truncation or an instruction to alter the source mask. Selection filters only create a separate inspection layer.',
    }
    return record, png(Image.frombytes('L', mask.size, bytes(selection)))


def inspect_components(bundle, *, min_area_pixels=1, boundary_filter='all'):
    """Return every component and source-bound selection hints, preserving evidence."""
    return _inspect(bundle, min_area_pixels=min_area_pixels, boundary_filter=boundary_filter)[0]


def components_csv(record):
    """Serialize all candidates, including unselected candidates and boundary flags."""
    table = io.StringIO(newline='')
    writer = csv.writer(table)
    writer.writerow(['component_id', 'area_pixels', 'bbox_x1', 'bbox_y1', 'bbox_x2', 'bbox_y2',
                     'centroid_x', 'centroid_y', 'touches_image_boundary', 'touches_roi_boundary',
                     'touches_invalid_boundary', 'selected', 'exclusion_reasons'])
    for item in record['components']:
        writer.writerow([item['component_id'], item['area_pixels'], *item['bbox'],
                         item['centroid']['x'], item['centroid']['y'],
                         *[str(item[name]).lower() for name in ('touches_image_boundary', 'touches_roi_boundary',
                                                              'touches_invalid_boundary', 'selected')],
                         ';'.join(item['exclusion_reasons'])])
    return table.getvalue().encode('utf-8')


def _report(record):
    options = record['options']
    return '\n'.join([
        '# GeoMaskLab candidate inspection', '', record['interpretation'], '',
        f"- Source run: {record['source_run_id']}; version: {record['source_version']}",
        f"- Foreground: {record['foreground_pixels']} pixels in {record['component_count']} components",
        f"- Selected: {record['selected_foreground_pixels']} pixels in {record['selected_component_count']} components",
        f"- Minimum area: {options['min_area_pixels']} pixels; boundary filter: {options['boundary_filter']}",
        '- Source evidence and its mask are unchanged; selection.png is a separate candidate-review layer.',
        '', '## Boundary rules', '', *[f'- {name}: {text}' for name, text in record['boundary_rules'].items()],
        '', '## Offline replay', '',
        'Use geomasklab inspect evidence.zip --min-area-pixels '+str(options['min_area_pixels'])+
        ' --boundary-filter '+options['boundary_filter']+' --output recomputed.zip',
        'Use geomasklab verify-components inspection.zip to validate saved records and the selection layer.', '',
    ]).encode('utf-8')


def component_packet(bundle, *, min_area_pixels=1, boundary_filter='all'):
    """Export immutable source evidence, all inspection records and a selection layer."""
    record, selection = _inspect(bundle, min_area_pixels=min_area_pixels, boundary_filter=boundary_filter)
    files = {'evidence.zip': bundle, 'inspection.json': json.dumps(record, indent=2, allow_nan=False).encode('utf-8'),
             'components.csv': components_csv(record), 'selection.png': selection, 'report.md': _report(record)}
    if sum(len(raw) for raw in files.values()) > MAX_PACKET_BYTES:
        raise ValueError('Component packet exceeds the expanded size limit.')
    manifest = {'schema': PACKET_SCHEMA, 'checksums': {
        name: {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()} for name, raw in files.items()}}
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, raw in files.items():
            archive.writestr(name, raw)
        archive.writestr('manifest.json', json.dumps(manifest, indent=2).encode('utf-8'))
    if len(output.getvalue()) > MAX_PACKET_BYTES:
        raise ValueError('Component packet exceeds the size limit.')
    return output.getvalue()


def verify_component_packet(payload):
    """Replay all flags, counts, stable IDs and selection pixels, without extraction."""
    required = {'evidence.zip', 'inspection.json', 'components.csv', 'selection.png', 'report.md'}
    if len(payload) > MAX_PACKET_BYTES:
        raise ValueError('Component packet exceeds the size limit.')
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        if (len(names) != 6 or set(names) != required | {'manifest.json'} or
                sum(item.file_size for item in infos) > MAX_PACKET_BYTES):
            raise ValueError('Component packet requires unique, bounded flat files.')
        manifest = json.loads(archive.read('manifest.json'))
        if (not isinstance(manifest, dict) or set(manifest) != {'schema', 'checksums'} or manifest.get('schema') != PACKET_SCHEMA or
                not isinstance(manifest.get('checksums'), dict) or set(manifest['checksums']) != required):
            raise ValueError('Invalid component packet manifest.')
        files = {name: archive.read(name) for name in required}
    for name, raw in files.items():
        if _canonical(manifest['checksums'][name]) != _canonical({'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}):
            raise ValueError('Component packet checksum mismatch: ' + name)
    saved = json.loads(files['inspection.json'])
    if not isinstance(saved, dict) or not isinstance(saved.get('software_version'), str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._+-]{0,63}', saved['software_version']):
        raise ValueError('Component inspection must record its software version.')
    options = saved.get('options')
    if not isinstance(options, dict) or set(options) != {'min_area_pixels', 'boundary_filter'}:
        raise ValueError('Invalid component inspection options.')
    expected, selection = _inspect(files['evidence.zip'], **options)
    expected['software_version'] = saved['software_version']
    if _canonical(saved) != _canonical(expected):
        raise ValueError('Component measurements, selection or boundary flags do not replay.')
    if files['components.csv'] != components_csv(expected) or files['report.md'] != _report(expected):
        raise ValueError('Component table or report does not replay.')
    with Image.open(io.BytesIO(files['selection.png'])) as actual, Image.open(io.BytesIO(selection)) as replay:
        if actual.mode != 'L' or actual.size != replay.size or actual.tobytes() != replay.tobytes():
            raise ValueError('Component selection layer does not replay.')
    return {'verified': True, 'schema': PACKET_SCHEMA, 'component_count': expected['component_count'],
            'foreground_pixels': expected['foreground_pixels'],
            'selected_component_count': expected['selected_component_count'],
            'selected_foreground_pixels': expected['selected_foreground_pixels'],
            'source_mask_modified': False, 'inference_performed': False, 'origin_authenticated': False,
            'semantic_objects_verified': False}
