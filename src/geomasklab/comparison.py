"""Fair mask comparison and replayable, source-bound comparison packets."""
import base64
import hashlib
import html
import io
import json
import re
import zipfile
from PIL import Image, ImageChops
from .evidence import load_verified_bundle
from .domain import selected_region, analysis_domain, valid_image
from ._version import VERSION

SCHEMA = 'geomasklab-result-comparison/2.0'
PACKET_SCHEMA = 'geomasklab-comparison-packet/1.0'
POLICIES = ('intersection', 'identical')
LIMIT = 512 * 1024 * 1024


def _image(files, name):
    with Image.open(io.BytesIO(files[name])) as image:
        return image.copy()


def _png(image):
    output = io.BytesIO()
    image.save(output, 'PNG')
    return output.getvalue()


def _count(mask):
    return mask.histogram()[255]


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def compare_bundles(payload_a, payload_b, *, domain_policy='intersection'):
    """Compare aligned saved masks; explicitly account for excluded domains.

    ``intersection`` restricts the pixel comparison to S_A & V_A & S_B & V_B.
    ``identical`` requires the two realized valid domains to match exactly.
    Neither policy resamples an image, reruns inference, or estimates accuracy.
    Saved foreground change is decomposed into shared-domain change plus the
    difference in foreground excluded from that shared domain.
    """
    if domain_policy not in POLICIES:
        raise ValueError('Comparison domain policy must be intersection or identical.')
    facts_a, files_a = load_verified_bundle(payload_a)
    facts_b, files_b = load_verified_bundle(payload_b)
    image_hash = hashlib.sha256(files_a['original.png']).hexdigest()
    if image_hash != hashlib.sha256(files_b['original.png']).hexdigest():
        raise ValueError('Compare results from the same exact input image; no registration or resampling is performed.')
    a, b = (json.loads(files['result.json']) for files in (files_a, files_b))
    for field in ('target', 'invert'):
        if a['task'].get(field, False) != b['task'].get(field, False):
            raise ValueError('Comparison requires the same semantic target and complement setting.')
    ma, mb = (_image(files, 'mask.png').convert('L') for files in (files_a, files_b))
    domain_a = analysis_domain(files_a, ma.size, a['task'])
    domain_b = analysis_domain(files_b, mb.size, b['task'])
    domains_equal = domain_a.tobytes() == domain_b.tobytes()
    if domain_policy == 'identical' and not domains_equal:
        raise ValueError('Incompatible_Analysis_Domains: identical policy requires equal realized selected valid pixels. Choose intersection to restrict comparison explicitly.')
    sa, sb = (selected_region(ma.size, task) for task in (a['task'], b['task']))
    va, vb = (valid_image(files, ma.size) for files in (files_a, files_b))
    scope_equal, validity_equal = sa.tobytes() == sb.tobytes(), va.tobytes() == vb.tobytes()
    common = ImageChops.multiply(domain_a, domain_b)
    ca, cb = ImageChops.multiply(ma, common), ImageChops.multiply(mb, common)
    shared = ImageChops.multiply(ca, cb)
    only_a, only_b = ImageChops.subtract(ca, shared), ImageChops.subtract(cb, shared)
    counts = {key: _count(value) for key, value in
              [('common', common), ('a', ca), ('b', cb), ('shared', shared), ('only_a', only_a), ('only_b', only_b)]}
    union = counts['shared'] + counts['only_a'] + counts['only_b']
    predictions_equal = _image(files_a, 'full_mask.png').convert('L').tobytes() == _image(files_b, 'full_mask.png').convert('L').tobytes()
    conditions_equal = scope_equal and validity_equal
    if predictions_equal:
        change_kind = 'Identical_Realized_Analysis' if conditions_equal else 'Analysis_Conditions_Only'
    else:
        change_kind = 'Prediction_Only' if conditions_equal else 'Prediction_And_Analysis_Conditions'
    excluded_a = facts_a['pixel_area'] - counts['a']
    excluded_b = facts_b['pixel_area'] - counts['b']
    common_delta = counts['only_b'] - counts['only_a']
    excluded_delta = excluded_b - excluded_a
    total_delta = facts_b['pixel_area'] - facts_a['pixel_area']
    # An identity over disjoint pixel sets, not a causal allocation of changes.
    if total_delta != common_delta + excluded_delta:
        raise ValueError('Foreground accounting identity failed.')
    explanation = ('The saved full-image prediction pixels are identical; changes in totals come from analysis conditions.'
                   if predictions_equal and not conditions_equal else
                   'Both prediction pixels and analysis conditions changed; inspect the shared domain and excluded-domain counts separately.'
                   if not predictions_equal and not conditions_equal else
                   'Analysis conditions match; differences reflect saved prediction pixels.'
                   if not predictions_equal else 'Saved prediction pixels and realized analysis conditions match.')
    if domains_equal and not conditions_equal:
        explanation += ' The realized selected valid domains still match; condition differences lie outside that effective domain or cancel there.'
    if not counts['common']:
        explanation += ' There is no common valid domain; pixel differences and agreement are unavailable.'
    elif not union:
        explanation += ' Both masks have no foreground in the common domain; IoU and Dice are undefined.'
    elif not predictions_equal and not (counts['only_a']+counts['only_b']):
        explanation += ' Prediction differences occur outside the common valid domain.'
    visual = _image(files_a, 'original.png').convert('RGB')
    original = visual.copy()
    # Categorical difference: 0 excluded, 1 common background, 2 common
    # foreground, 3 removed foreground (A only), 4 added foreground (B only).
    classes = Image.new('L', ma.size)
    classes.paste(1, mask=common)
    for mask, value, color in ((shared, 2, '#45c5a1'), (only_a, 3, '#4c83ff'), (only_b, 4, '#f0ad4e')):
        classes.paste(value, mask=mask)
        visual = Image.composite(Image.blend(original, Image.new('RGB', ma.size, color), .75), visual, mask)
    def source_summary(record, facts, scope, valid, domain, excluded):
        denominator = _count(domain)
        return {'run_id': record['id'], 'version': record['version'], 'scope': record['task']['side'],
                'roi': record['task'].get('roi'), 'foreground_pixels': facts['pixel_area'],
                'whole_image_coverage': facts['area_ratio'], 'geometric_region_pixels': _count(scope),
                'valid_image_pixels': _count(valid), 'valid_region_pixels': denominator,
                'coverage_of_valid_region': facts['pixel_area']/denominator if denominator else None,
                'foreground_excluded_from_comparison_pixels': excluded,
                'validity_policy': record.get('analysis_config', {}).get('validity', {}).get('policy', 'all_pixels_declared_valid')}
    summary_a = source_summary(a, facts_a, sa, va, domain_a, excluded_a)
    summary_b = source_summary(b, facts_b, sb, vb, domain_b, excluded_b)
    for summary, source in ((summary_a, a), (summary_b, b)):
        summary['software_version'] = source.get('software_version') or source.get('software', {}).get('version', 'unrecorded')
    return {'schema': SCHEMA, 'operation_software_version': VERSION,
            'status': 'Compared' if counts['common'] else 'No_Common_Valid_Domain',
            'domain_policy': domain_policy, 'pixel_diff_available': bool(counts['common']),
            'inference_performed': False, 'semantic_accuracy_measured': False,
            'image_sha256': image_hash, 'source_a_sha256': hashlib.sha256(payload_a).hexdigest(),
            'source_b_sha256': hashlib.sha256(payload_b).hexdigest(), 'image_size': list(ma.size),
            'target': a['task']['target'], 'invert': a['task'].get('invert', False),
            'change_kind': change_kind, 'selected_regions_equal': scope_equal,
            'selected_valid_domains_equal': domains_equal, 'valid_masks_equal': validity_equal,
            'common_scope_pixels': counts['common'], 'a_foreground_in_common_scope': counts['a'],
            'b_foreground_in_common_scope': counts['b'], 'shared_foreground_pixels': counts['shared'],
            'analysis_domain_policy': 'Intersection of both selected regions and both declared valid masks.' if domain_policy == 'intersection' else 'Identical realized selected valid domains required.',
            'a_domain_pixels': _count(domain_a), 'b_domain_pixels': _count(domain_b),
            'a_domain_excluded_from_comparison_pixels': _count(domain_a)-counts['common'],
            'b_domain_excluded_from_comparison_pixels': _count(domain_b)-counts['common'],
            'a_only_pixels': counts['only_a'], 'b_only_pixels': counts['only_b'],
            'changed_pixels': counts['only_a'] + counts['only_b'],
            'mask_agreement_iou': counts['shared']/union if union else None,
            'mask_agreement_dice': 2*counts['shared']/(counts['a']+counts['b']) if union else None,
            'full_prediction_pixels_equal': predictions_equal,
            'foreground_change_accounting': {'saved_total_delta_pixels': total_delta,
                'common_domain_delta_pixels': common_delta, 'excluded_domain_delta_pixels': excluded_delta,
                'identity': 'saved_total_delta = common_domain_delta + excluded_domain_delta', 'causal_attribution': False},
            'a': summary_a, 'b': summary_b,
            'difference_png_base64': base64.b64encode(_png(visual)).decode('ascii') if counts['common'] else None,
            'difference_classes_png_base64': base64.b64encode(_png(classes)).decode('ascii') if counts['common'] else None,
            'difference_classes': {'0': 'Outside common valid domain', '1': 'Common background',
                '2': 'Common foreground', '3': 'Removed foreground (A only)', '4': 'Added foreground (B only)'},
            'legend': {'a_only': '#4c83ff', 'b_only': '#f0ad4e', 'shared': '#45c5a1'},
            'explanation': explanation,
            'interpretation': 'Mask agreement uses the explicitly chosen common valid domain. Agreement is not ground-truth accuracy. Excluded-domain accounting is not a causal decomposition of model and configuration effects.'}


def comparison_report(record, overlay=None):
    """Render a compact English report with explicit domains and accounting."""
    esc = lambda value: html.escape(str(value))
    rows = ''.join('<tr><th>'+label+'</th><td>'+esc(record['a'][key])+'</td><td>'+esc(record['b'][key])+'</td></tr>'
                   for label, key in [('Saved foreground (px)', 'foreground_pixels'),
                       ('Geometric region (px)', 'geometric_region_pixels'), ('Valid region (px)', 'valid_region_pixels'),
                       ('Valid-region coverage', 'coverage_of_valid_region'),
                       ('Foreground outside comparison (px)', 'foreground_excluded_from_comparison_pixels')])
    delta = record['foreground_change_accounting']
    visual = '<img alt="Removed, added and common foreground in the common valid domain" src="data:image/png;base64,'+base64.b64encode(overlay).decode()+'">' if overlay else '<p>Pixel difference unavailable: no common valid domain.</p>'
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>GeoMaskLab comparison</title><style>body{font:16px/1.6 system-ui,sans-serif;color:#183b37;background:#f3f6f3;max-width:960px;margin:40px auto;padding:24px}h1{font-size:36px}table{border-collapse:collapse;width:100%;background:white}th,td{padding:10px;border-bottom:1px solid #dbe5df;text-align:left}img{max-width:100%;margin:24px 0}code{overflow-wrap:anywhere}</style>'
        '<h1>Fair comparison, explicit domains</h1><p>'+esc(record['explanation'])+'</p><p>Domain policy: <strong>'+esc(record['domain_policy'])+'</strong>. Common valid domain: '+esc(record['common_scope_pixels'])+' px.</p>'
        '<table><tr><th>Measurement</th><th>A</th><th>B</th></tr>'+rows+'</table>'+visual+
        '<p>Blue: removed foreground (A only). Amber: added foreground (B only). Mint: common foreground.</p>'
        '<p>Saved foreground change: '+esc(delta['saved_total_delta_pixels'])+' = '+esc(delta['common_domain_delta_pixels'])+' (shared domain) + '+esc(delta['excluded_domain_delta_pixels'])+' (excluded domains) px.</p>'
        '<p>'+esc(record['interpretation'])+'</p><p>Offline replay: <code>geomasklab verify-comparison comparison.zip</code></p>'
        '<p>Internal replay checks consistency. Origin authenticity requires a separately trusted signature or external digest.</p></html>')


def comparison_packet(payload_a, payload_b, *, domain_policy='intersection'):
    """Preserve both exact evidence sources, conditions, counts and diff pixels."""
    record = compare_bundles(payload_a, payload_b, domain_policy=domain_policy)
    overlay = record.pop('difference_png_base64')
    classes = record.pop('difference_classes_png_base64')
    content = {'source-a.zip': payload_a, 'source-b.zip': payload_b,
               'comparison.json': (json.dumps(record, indent=2, allow_nan=False)+'\n').encode()}
    if overlay:
        content['difference.png'] = base64.b64decode(overlay)
        content['difference-classes.png'] = base64.b64decode(classes)
    content['report.html'] = comparison_report(record, content.get('difference.png')).encode()
    manifest = {'schema': PACKET_SCHEMA, 'checksums': {name: {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)} for name, raw in content.items()}}
    if sum(map(len, content.values())) > LIMIT:
        raise ValueError('Comparison packet exceeds the expanded size limit.')
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, raw in content.items():
            z.writestr(name, raw)
        z.writestr('manifest.json', json.dumps(manifest, indent=2))
    packet=output.getvalue()
    if len(packet)>LIMIT:raise ValueError('Comparison packet exceeds the size limit.')
    return packet


def verify_comparison_packet(payload):
    """Verify flat membership/digests and replay both sources and every record."""
    if len(payload) > LIMIT:
        raise ValueError('Comparison packet exceeds the size limit.')
    base = {'source-a.zip', 'source-b.zip', 'comparison.json', 'report.html'}
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        info = z.infolist()
        names = [item.filename for item in info]
        if len(names) != len(set(names)) or sum(item.file_size for item in info) > LIMIT or set(names) not in (base | {'manifest.json'}, base | {'manifest.json', 'difference.png', 'difference-classes.png'}):
            raise ValueError('Invalid comparison packet membership or expanded size.')
        manifest = json.loads(z.read('manifest.json'))
        expected_names = set(names) - {'manifest.json'}
        if not isinstance(manifest,dict) or set(manifest) != {'schema', 'checksums'} or manifest['schema'] != PACKET_SCHEMA or not isinstance(manifest['checksums'],dict) or set(manifest['checksums']) != expected_names:
            raise ValueError('Invalid comparison manifest.')
        content = {name: z.read(name) for name in expected_names}
    for name, raw in content.items():
        if _canonical(manifest['checksums'][name]) != _canonical({'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}):
            raise ValueError('Comparison checksum mismatch: '+name)
    record = json.loads(content['comparison.json'])
    if not isinstance(record,dict):raise ValueError('Comparison record must be a JSON object.')
    replay = compare_bundles(content['source-a.zip'], content['source-b.zip'], domain_policy=record['domain_policy'])
    overlay = replay.pop('difference_png_base64')
    classes = replay.pop('difference_classes_png_base64')
    recorded_version = record.get('operation_software_version')
    if not isinstance(recorded_version, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._+-]{0,63}', recorded_version):
        raise ValueError('Invalid comparison operation software version.')
    replay['operation_software_version'] = recorded_version
    if _canonical(record) != _canonical(replay):
        raise ValueError('Comparison record disagrees with replayed source pixels or analysis conditions.')
    expected_images = {'difference.png': overlay, 'difference-classes.png': classes} if overlay else {}
    if (set(content) - base) != set(expected_images):
        raise ValueError('Comparison difference availability disagrees with its domain.')
    for name, encoded in expected_images.items():
        with Image.open(io.BytesIO(content[name])) as actual, Image.open(io.BytesIO(base64.b64decode(encoded))) as expected:
            if actual.mode != expected.mode or actual.size != expected.size or actual.tobytes() != expected.tobytes():
                raise ValueError('Comparison image disagrees with replayed pixels: '+name)
    if content['report.html'] != comparison_report(replay, content.get('difference.png')).encode():
        raise ValueError('Comparison report disagrees with replayed measurements.')
    return {'verified': True, 'schema': PACKET_SCHEMA, 'files_checked': len(content),
            'comparison': replay, 'origin_authenticated': False, 'semantic_accuracy_measured': False}
