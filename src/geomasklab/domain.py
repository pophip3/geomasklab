"""Explicit pixel validity shared by measurement, comparison and assessment.

Validity is a declared analysis condition, not a cloud detector or a semantic
quality claim. Positive source masks remain immutable when domains change.
"""
import hashlib
import io
from PIL import Image, ImageChops
from .masks import binary_png, source_text
from .measurements import constrain

EVIDENCE_SCHEMA = 'geomasklab-evidence/2.0'
CONFIG_SCHEMA = 'geomasklab-analysis-config/1.0'
METRICS_SCHEMA = 'geomasklab-validity-measurements/1.0'
KEEP_VALIDITY = object()
DOMAIN_FILES = {'analysis.json', 'valid_mask.png', 'source_valid_mask.png'}


def png(image):
    output = io.BytesIO()
    image.save(output, 'PNG')
    return output.getvalue()


def selected_region(size, task):
    """Geometric region in normalized image pixels; upper bounds exclusive."""
    return constrain(Image.new('L', size, 255), task['side'], task.get('roi'))


def validity_input(raw, size, source=None):
    """Normalize an explicitly aligned binary PNG, retaining original bytes."""
    if raw is None:
        if source is not None:
            raise ValueError('A validity source requires an explicit valid mask.')
        valid = Image.new('L', size, 255)
        declaration = {'policy': 'all_pixels_declared_valid', 'source': None,
                       'upload_sha256': None, 'alignment_user_assertion': True,
                       'origin_authenticated': False}
        files = {}
    else:
        source = source_text(source)
        valid = binary_png(raw, size)
        declaration = {'policy': 'explicit_binary_mask', 'source': source,
                       'upload_sha256': hashlib.sha256(raw).hexdigest(),
                       'alignment_user_assertion': True, 'origin_authenticated': False}
        files = {'source_valid_mask.png': raw}
    files['valid_mask.png'] = png(valid)
    return valid, declaration, files


def configuration(task, image_sha256, size, declaration):
    """Record realized coordinates and conditions, bound to one exact image."""
    return {'schema': CONFIG_SCHEMA, 'image_sha256': image_sha256,
            'image_size': list(size), 'coordinate_system': 'normalized_image_pixels',
            'scope': task['side'], 'roi': task.get('roi'), 'target': task['target'],
            'invert': task.get('invert', False), 'connectivity': 8,
            'validity': declaration}


def valid_image(files, size):
    """Use the saved declared validity; legacy evidence declares all pixels valid."""
    if 'valid_mask.png' not in files:
        return Image.new('L', size, 255)
    with Image.open(io.BytesIO(files['valid_mask.png'])) as image:
        return image.copy()


def analysis_domain(files, size, task):
    """D = selected geometric region intersected with declared valid pixels."""
    return ImageChops.multiply(selected_region(size, task), valid_image(files, size))


def validity_measurements(positive, task, valid):
    """Return foreground, effective domain and separately named denominators."""
    geometric = selected_region(positive.size, task)
    domain = ImageChops.multiply(geometric, valid)
    foreground = ImageChops.multiply(positive, domain)
    area = foreground.histogram()[255]
    region = geometric.histogram()[255]
    effective = domain.histogram()[255]
    whole = valid.histogram()[255]
    geometric_foreground = ImageChops.multiply(positive, geometric).histogram()[255]
    record = {'schema': METRICS_SCHEMA, 'foreground_pixels': area,
              'geometric_image_pixels': positive.width * positive.height,
              'geometric_region_pixels': region, 'valid_image_pixels': whole,
              'valid_region_pixels': effective,
              'excluded_image_pixels': positive.width * positive.height - whole,
              'excluded_region_pixels': region - effective,
              'excluded_foreground_pixels': geometric_foreground - area,
              'coverage_of_valid_image': area / whole if whole else None,
              'coverage_of_valid_region': area / effective if effective else None}
    return foreground, domain, record


def add_validity_statistics(metrics, positive, task, valid):
    """Extend legacy geometric denominators without changing their definitions."""
    _, _, record = validity_measurements(positive, task, valid)
    metrics['validity_measurements'] = record
    metrics['distribution']['basis'] = 'full_mask_before_scope_and_validity'
    if task.get('roi'):
        raw_area = record['foreground_pixels'] + record['excluded_foreground_pixels']
        distribution = metrics['distribution']
        distribution.update(roi_inside_pixels=raw_area,
                            roi_outside_pixels=distribution['left_pixels'] + distribution['right_pixels'] - raw_area,
                            roi_valid_foreground_pixels=record['foreground_pixels'],
                            roi_excluded_foreground_pixels=record['excluded_foreground_pixels'])
