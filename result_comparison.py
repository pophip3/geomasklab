"""Compare verified results in their common pixel scope, without model inference."""
import base64
import hashlib
import io
import json
from PIL import Image, ImageChops
from export_bundle import load_verified_bundle


def selected_region(size, task):
    """Build the declared pixel domain after bundle verification."""
    w, h = size
    boxes = {'all': (0, 0, w, h), 'left': (0, 0, w//2, h),
             'right': (w//2, 0, w, h), 'top': (0, 0, w, h//2),
             'bottom': (0, h//2, w, h)}
    region = Image.new('L', size)
    box = boxes[task['side']]
    region.paste(255, box)
    if task.get('roi'):
        rectangle = Image.new('L', size)
        rectangle.paste(255, tuple(task['roi']['xyxy']))
        region = ImageChops.multiply(region, rectangle)
    return region


def compare_bundles(payload_a, payload_b):
    """Measure mask agreement only inside the intersection of selected regions.

    This is agreement between predictions, never accuracy against ground truth.
    Empty unions and disjoint domains have undefined IoU/Dice rather than 100%.
    """
    facts_a, files_a = load_verified_bundle(payload_a)
    facts_b, files_b = load_verified_bundle(payload_b)
    if hashlib.sha256(files_a['original.png']).digest() != hashlib.sha256(files_b['original.png']).digest():
        raise ValueError('Compare results from the same exact input image.')
    a = json.loads(files_a['result.json'])
    b = json.loads(files_b['result.json'])
    for field in ('target', 'invert'):
        if a['task'].get(field) != b['task'].get(field):
            raise ValueError('Comparison requires the same semantic target and complement setting.')
    def image(files, name):
        with Image.open(io.BytesIO(files[name])) as im:
            return im.copy()
    ma, mb = image(files_a, 'mask.png').convert('L'), image(files_b, 'mask.png').convert('L')
    common = ImageChops.multiply(selected_region(ma.size, a['task']), selected_region(mb.size, b['task']))
    ca, cb = ImageChops.multiply(ma, common), ImageChops.multiply(mb, common)
    shared = ImageChops.multiply(ca, cb)
    only_a, only_b = ImageChops.subtract(ca, shared), ImageChops.subtract(cb, shared)
    counts = {key: value.histogram()[255] for key, value in
              [('common', common), ('a', ca), ('b', cb), ('shared', shared), ('only_a', only_a), ('only_b', only_b)]}
    union = counts['shared'] + counts['only_a'] + counts['only_b']
    original = image(files_a, 'original.png').convert('RGB')
    visual = original.copy()
    for mask, color in ((only_a, '#4c83ff'), (only_b, '#f0ad4e'), (shared, '#45c5a1')):
        visual = Image.composite(Image.blend(original, Image.new('RGB', ma.size, color), .75), visual, mask)
    buffer = io.BytesIO()
    visual.save(buffer, 'PNG')
    return {'schema': 'geomasklab-result-comparison/1.0',
            'inference_performed': False, 'semantic_accuracy_measured': False,
            'target': a['task']['target'], 'invert': a['task'].get('invert', False),
            'common_scope_pixels': counts['common'], 'a_foreground_in_common_scope': counts['a'],
            'b_foreground_in_common_scope': counts['b'], 'shared_foreground_pixels': counts['shared'],
            'a_only_pixels': counts['only_a'], 'b_only_pixels': counts['only_b'],
            'changed_pixels': counts['only_a'] + counts['only_b'],
            'mask_agreement_iou': counts['shared']/union if union else None,
            'mask_agreement_dice': 2*counts['shared']/(counts['a']+counts['b']) if union else None,
            'full_prediction_pixels_equal': image(files_a, 'full_mask.png').convert('L').tobytes() == image(files_b, 'full_mask.png').convert('L').tobytes(),
            'a': {'run_id': a['id'], 'version': a['version'], 'scope': a['task']['side'],
                  'roi': a['task'].get('roi'), 'foreground_pixels': facts_a['pixel_area'],
                  'whole_image_coverage': facts_a['area_ratio']},
            'b': {'run_id': b['id'], 'version': b['version'], 'scope': b['task']['side'],
                  'roi': b['task'].get('roi'), 'foreground_pixels': facts_b['pixel_area'],
                  'whole_image_coverage': facts_b['area_ratio']},
            'difference_png_base64': base64.b64encode(buffer.getvalue()).decode('ascii'),
            'legend': {'a_only': '#4c83ff', 'b_only': '#f0ad4e', 'shared': '#45c5a1'},
            'interpretation': 'Mask agreement within the common selected region. This is not ground-truth accuracy; different scopes can change totals without changing prediction pixels.'}
