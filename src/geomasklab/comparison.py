"""Compare verified results in their common pixel scope, without model inference."""
import base64
import hashlib
import io
import json
from PIL import Image, ImageChops
from .evidence import load_verified_bundle
from .domain import selected_region,analysis_domain,valid_image


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
    domain_a=analysis_domain(files_a,ma.size,a['task'])
    domain_b=analysis_domain(files_b,mb.size,b['task'])
    common = ImageChops.multiply(domain_a,domain_b)
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
            'status':'Compared' if counts['common'] else 'No_Common_Valid_Domain',
            'pixel_diff_available':bool(counts['common']),
            'inference_performed': False, 'semantic_accuracy_measured': False,
            'target': a['task']['target'], 'invert': a['task'].get('invert', False),
            'common_scope_pixels': counts['common'], 'a_foreground_in_common_scope': counts['a'],
            'analysis_domain_policy':'Intersection of both selected regions and both declared valid masks.',
            'selected_valid_domains_equal':domain_a.tobytes()==domain_b.tobytes(),
            'valid_masks_equal':valid_image(files_a,ma.size).tobytes()==valid_image(files_b,mb.size).tobytes(),
            'a_domain_pixels':domain_a.histogram()[255], 'b_domain_pixels':domain_b.histogram()[255],
            'a_domain_excluded_from_comparison_pixels':domain_a.histogram()[255]-counts['common'],
            'b_domain_excluded_from_comparison_pixels':domain_b.histogram()[255]-counts['common'],
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
            'difference_png_base64': base64.b64encode(buffer.getvalue()).decode('ascii') if counts['common'] else None,
            'legend': {'a_only': '#4c83ff', 'b_only': '#f0ad4e', 'shared': '#45c5a1'},
            'interpretation': 'Mask agreement within the intersection of selected valid domains. This is not ground-truth accuracy; scope or validity changes can change totals without changing prediction pixels.'}
