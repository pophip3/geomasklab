"""Run the fixed five-stage offline workflow on credited, frozen NAIP imagery.

The packaged excess-green mask, demonstration exclusion and controlled pixel
perturbations are protocol fixtures. They are not independent semantic labels,
cloud detections, model improvements or observed land-cover change.
"""
import argparse
import hashlib
import html
import io
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from PIL import Image
from geomasklab._version import VERSION
from geomasklab.api import create_evidence, recalculate_evidence, timestamp
from geomasklab.batch import run_batch, verify_batch, batch_packet, verify_batch_packet, MANIFEST_SCHEMA
from geomasklab.comparison import compare_bundles, comparison_packet, verify_comparison_packet
from geomasklab.components import inspect_components, component_packet, verify_component_packet
from geomasklab.domain import png
from geomasklab.evidence import load_verified_bundle
from geomasklab.reference import evaluate_reference, evaluation_packet, verify_reference_packet
from geomasklab.report import build_report


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def _foreground(raw):
    """Read binary source pixels as an explicit set, independently of domain APIs."""
    with Image.open(io.BytesIO(raw)) as image:
        return image.size, {index for index, value in enumerate(image.convert('L').tobytes()) if value == 255}


def _encoded(size, pixels):
    image = Image.new('L', size)
    image.putdata([255 if index in pixels else 0 for index in range(size[0] * size[1])])
    return png(image)


def _rectangle(size, box):
    width = size[0]
    x1, y1, x2, y2 = box
    return {y * width + x for y in range(y1, y2) for x in range(x1, x2)}


def _index_report(summary):
    escape = lambda value: html.escape(str(value))
    counts = summary['independent_comparison']
    aggregate = summary['batch']['aggregate']
    rows = ''.join('<tr><th>' + escape(label) + '</th><td>' + escape(value) + '</td></tr>'
        for label, value in [('Baseline foreground in valid domain (px)', summary['measurement']['foreground_pixels']),
            ('Valid domain (px)', summary['measurement']['valid_region_pixels']),
            ('Common comparison domain (px)', counts['common_pixels']),
            ('Removed foreground (px)', counts['removed_pixels']),
            ('Added foreground (px)', counts['added_pixels']),
            ('Shared foreground (px)', counts['shared_foreground_pixels']),
            ('Batch samples completed', summary['batch']['completed_count']),
            ('Deliberate sample failures', summary['batch']['failed_count']),
            ('Undefined successful coverage samples', aggregate['undefined_coverage_samples']),
            ('Macro mean coverage', aggregate['macro_mean_coverage']),
            ('Micro weighted coverage', aggregate['micro_weighted_coverage'])])
    links = ''.join('<a href="' + filename + '">' + label + '</a>' for filename, label in [
        ('baseline.html', 'Baseline evidence report'), ('region.html', 'Region evidence report'),
        ('comparison/report.html', 'Fair comparison report'), ('comparison.zip', 'Comparison packet'),
        ('components.zip', 'Component inspection packet'), ('assessment.zip', 'Protocol reference assessment'),
        ('batch.zip', 'Offline batch packet'), ('summary.json', 'Machine-readable acceptance results')])
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>GeoMaskLab five-stage workflow</title><style>body{font:16px/1.7 system-ui,sans-serif;background:#f4f7f5;color:#173d38;max-width:1020px;margin:40px auto;padding:24px}header,section{background:#fff;border:1px solid #dce7df;border-radius:12px;padding:28px;margin:20px 0}h1{font-size:38px;line-height:1.2}h2{font-size:23px}small{color:#55766a}table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:11px;border-bottom:1px solid #e1eae4}th{font-weight:500}a{display:inline-block;color:#1c775c;margin:8px 18px 8px 0}code{overflow-wrap:anywhere}img{width:100%;border-radius:8px}.notice{padding:16px;background:#f2f7f1;border-left:4px solid #53976d}@media(max-width:600px){body{padding:12px}header,section{padding:18px}h1{font-size:29px}}</style></head><body>'
        '<header><small>GEOMASKLAB / OFFLINE ACCEPTANCE EXAMPLE</small><h1>One image. Explicit conditions. Replayable results.</h1>'
        '<p>Import an external mask → declare validity and region → compare fairly → inspect candidates → batch and replay.</p>'
        '<p>Software version: <code>' + escape(summary['software_version']) + '</code>. Image credit: ' + escape(summary['dataset_credit']) + '.</p></header>'
        '<section><h2>Independent arithmetic checks</h2><table>' + rows + '</table>'
        '<p>The comparison uses a shared valid domain. Saved total change is checked against shared-domain change plus excluded-domain foreground accounting.</p>'
        '<p class="notice">The alternative mask has declared, deterministic pixel perturbations. The baseline reference is not independent ground truth. These results verify workflow arithmetic and replay, not segmentation accuracy or real temporal change.</p></section>'
        '<section><h2>Inspect the real image</h2><img src="inputs/image.png" alt="Credited 2019 NAIP aerial image of Denver City Park">'
        '<p>The left quarter is explicitly excluded as a demonstration condition. It has not been classified as cloud or invalid sensor data.</p></section>'
        '<section><h2>Exported artifacts</h2>' + links + '<p>Verify the downloaded packets with the installed CLI: '
        '<code>geomasklab verify-comparison comparison.zip</code>, <code>geomasklab verify-components components.zip</code> '
        'and <code>geomasklab verify-batch batch.zip</code>.</p><p>Independent human handoff testing remains pending; this example involves zero human participants.</p></section></body></html>')


def run_workflow(output, *, geo=False):
    """Create a new output directory and return independently checked results."""
    output = Path(output).resolve()
    if output.exists():
        _require(output.is_dir() and not any(output.iterdir()), 'Choose a new or empty example output directory; existing artifacts are preserved.')
    data = ROOT / 'examples' / 'data' / 'naip-denver'
    provenance = json.loads((data / 'provenance.json').read_text(encoding='utf-8'))
    for name, identity in provenance['files'].items():
        raw = (data / name).read_bytes()
        _require(len(raw) == identity['bytes'] and hashlib.sha256(raw).hexdigest() == identity['sha256'],
                 'Frozen NAIP example asset changed: ' + name)
    image = (data / 'image.png').read_bytes()
    source = (data / 'mask.png').read_bytes()
    size, original_foreground = _foreground(source)
    _require(size == (512, 512), 'This explicit example is defined for the frozen 512 by 512 NAIP image.')
    width, height = size
    all_pixels = set(range(width * height))
    valid_pixels = {index for index in all_pixels if index % width >= width // 4}
    valid = _encoded(size, valid_pixels)
    empty_valid = _encoded(size, set())
    roi_box = [192, 160, 352, 320]
    roi = {'xyxy': roi_box, 'source': 'imported', 'image_size': list(size)}
    region_pixels = _rectangle(size, roi_box)
    # One patch lies inside the comparison ROI, the other outside it.
    patch_boxes = [[224, 192, 256, 224], [400, 64, 416, 80]]
    toggled = set().union(*[_rectangle(size, box) for box in patch_boxes])
    altered_foreground = original_foreground ^ toggled
    altered = _encoded(size, altered_foreground)
    validity_source = 'Explicit demonstration exclusion of the left quarter; not cloud detection or quality labels.'
    options = dict(target='tree', aligned=True, image_source=provenance['credit'],
        valid_mask=valid, valid_source=validity_source)
    baseline = create_evidence(image, source, source='Packaged excess-green color baseline; semantic accuracy unvalidated.', **options)
    alternate = create_evidence(image, altered, source='Controlled protocol fixture: XOR pixel perturbations in two declared rectangles; not a model prediction.', **options)
    region = recalculate_evidence(alternate, roi=roi)
    baseline_facts, baseline_files = load_verified_bundle(baseline)
    region_facts, region_files = load_verified_bundle(region)
    expected_a = original_foreground & valid_pixels
    expected_b = altered_foreground & region_pixels & valid_pixels
    common = valid_pixels & region_pixels
    common_a, common_b = original_foreground & common, altered_foreground & common
    shared, removed, added = common_a & common_b, common_a - common_b, common_b - common_a
    _require(len(expected_a) == 105232 and len(valid_pixels) == 196608, 'Frozen real-image counts differ from the documented baseline.')
    _require(baseline_facts['pixel_area'] == len(expected_a), 'Baseline foreground disagrees with independent pixel indices.')
    _require(region_facts['pixel_area'] == len(expected_b), 'Region foreground disagrees with independent pixel indices.')
    _require(baseline_files['source_valid_mask.png'] == region_files['source_valid_mask.png'] == valid,
             'Derived evidence failed to preserve the exact declared validity source.')
    _require(region_files['source_mask.png'] == altered, 'Region derivation changed the external source mask.')
    comparison = compare_bundles(baseline, region)
    expected_comparison = {'common_pixels': len(common), 'shared_foreground_pixels': len(shared),
        'removed_pixels': len(removed), 'added_pixels': len(added), 'changed_pixels': len(removed) + len(added),
        'saved_total_delta_pixels': len(expected_b) - len(expected_a),
        'common_domain_delta_pixels': len(added) - len(removed),
        'excluded_domain_delta_pixels': len(expected_b - common) - len(expected_a - common)}
    for field, key in [('common_scope_pixels', 'common_pixels'), ('shared_foreground_pixels', 'shared_foreground_pixels'),
                       ('a_only_pixels', 'removed_pixels'), ('b_only_pixels', 'added_pixels'), ('changed_pixels', 'changed_pixels')]:
        _require(comparison[field] == expected_comparison[key], 'Independent comparison count mismatch: ' + field)
    for key in ('saved_total_delta_pixels', 'common_domain_delta_pixels', 'excluded_domain_delta_pixels'):
        _require(comparison['foreground_change_accounting'][key] == expected_comparison[key], 'Independent foreground accounting mismatch: ' + key)
    _require(expected_comparison['saved_total_delta_pixels'] == expected_comparison['common_domain_delta_pixels'] + expected_comparison['excluded_domain_delta_pixels'],
             'Independent foreground set identity failed.')
    comparison_zip = comparison_packet(baseline, region)
    verify_comparison_packet(comparison_zip)
    assessment, difference = evaluate_reference(region, source, target='tree',
        source='The same packaged excess-green baseline; deliberately not independent semantic ground truth.',
        independent=False, created_at=timestamp())
    expected_reference = {'tp': len(shared), 'fp': len(added), 'fn': len(removed),
                          'tn': len(common) - len(shared | added | removed)}
    _require(assessment['counts'] == expected_reference and assessment['evaluated_pixels'] == len(common),
             'Reference assessment did not use the independently defined common valid region.')
    assessment_zip = evaluation_packet(assessment, difference, region, source)
    verify_reference_packet(assessment_zip)
    inspection = inspect_components(region, min_area_pixels=16, boundary_filter='touching')
    _require(sum(item['area_pixels'] for item in inspection['components']) == len(expected_b),
             'Candidate component areas do not sum to independently counted foreground.')
    selected = [item for item in inspection['components'] if item['selected']]
    _require(all(item['area_pixels'] >= 16 and any(item[name] for name in
        ('touches_image_boundary', 'touches_roi_boundary', 'touches_invalid_boundary')) for item in selected),
        'Candidate selection violates declared area and boundary criteria.')
    component_zip = component_packet(region, min_area_pixels=16, boundary_filter='touching')
    verify_component_packet(component_zip)
    output.mkdir(parents=True, exist_ok=True)
    inputs = output / 'inputs'
    inputs.mkdir()
    for name, raw in [('image.png', image), ('baseline.png', source), ('perturbed.png', altered),
                      ('valid.png', valid), ('empty-valid.png', empty_valid)]:
        (inputs / name).write_bytes(raw)
    sample = dict(image='image.png', target='tree', source='Declared NAIP protocol fixture; semantic accuracy unvalidated.',
        image_source=provenance['credit'], aligned=True)
    manifest = {'schema': MANIFEST_SCHEMA, 'samples': [
        {**sample, 'id': 'baseline-valid', 'mask': 'baseline.png', 'valid_mask': 'valid.png', 'valid_source': validity_source},
        {**sample, 'id': 'perturbed-right', 'mask': 'perturbed.png', 'scope': 'right', 'valid_mask': 'valid.png',
         'valid_source': validity_source, 'reference': {'path': 'baseline.png', 'source': 'Packaged color baseline; not independent ground truth.', 'independent': False}},
        {**sample, 'id': 'empty-valid', 'mask': 'baseline.png', 'valid_mask': 'empty-valid.png',
         'valid_source': 'Explicit empty valid domain fixture; coverage must be undefined.'},
        {**sample, 'id': 'deliberate-missing-input', 'mask': 'missing-mask.png'}]}
    _json(output / 'batch-manifest.json', manifest)
    batch_output = output / 'batch-results'
    batch = run_batch(manifest, base_dir=inputs, output_dir=batch_output)
    by_id = {row['id']: row for row in batch['samples']}
    right_domain = {index for index in valid_pixels if index % width >= width // 2}
    right_foreground = altered_foreground & right_domain
    _require(batch['status'] == 'completed_with_errors' and batch['completed_count'] == 3 and batch['failed_count'] == 1,
             'The deliberate missing sample was not isolated from successful samples.')
    _require(by_id['empty-valid']['foreground_pixels'] == 0 and by_id['empty-valid']['coverage_of_valid_region'] is None,
             'Empty valid-domain coverage was converted to a numerical zero.')
    _require(by_id['deliberate-missing-input']['foreground_pixels'] is None,
             'Failed sample foreground was converted to a numerical zero.')
    _require(by_id['baseline-valid']['foreground_pixels'] == len(expected_a) and
             by_id['baseline-valid']['valid_region_pixels'] == len(valid_pixels) and
             by_id['perturbed-right']['foreground_pixels'] == len(right_foreground) and
             by_id['perturbed-right']['valid_region_pixels'] == len(right_domain),
             'Explicit batch sample pairing or selected-domain counts differ from independent pixel sets.')
    expected_macro = (len(expected_a) / len(valid_pixels) + len(right_foreground) / len(right_domain)) / 2
    expected_micro = (len(expected_a) + len(right_foreground)) / (len(valid_pixels) + len(right_domain))
    _require(math.isclose(batch['aggregate']['macro_mean_coverage'], expected_macro, rel_tol=1e-14) and
             math.isclose(batch['aggregate']['micro_weighted_coverage'], expected_micro, rel_tol=1e-14),
             'Macro or micro coverage differs from independently counted sample domains.')
    _require(batch['aggregate']['defined_coverage_samples'] == 2 and batch['aggregate']['undefined_coverage_samples'] == 1,
             'Batch coverage aggregation included a failed or undefined-domain sample.')
    verify_batch(batch_output)
    before_resume = {(row['id'], filename): hashlib.sha256((batch_output / row['id'] / filename).read_bytes()).hexdigest()
        for row in batch['samples'] if row['status'] == 'completed' for filename in ('evidence.zip', 'receipt.json')}
    resumed = run_batch(manifest, base_dir=inputs, output_dir=batch_output, resume=True)
    _require(resumed['status'] == 'completed_with_errors', 'Verified resume lost the explicit failure state.')
    _require(all(hashlib.sha256((batch_output / sid / name).read_bytes()).hexdigest() == digest
                 for (sid, name), digest in before_resume.items()), 'Resume rewrote already verified completed samples.')
    batch_zip = batch_packet(batch_output)
    replayed_batch = verify_batch_packet(batch_zip)
    _require(replayed_batch['aggregate'] == batch['aggregate'], 'Offline batch packet aggregation differs.')
    for name, raw in [('baseline.zip', baseline), ('alternate.zip', alternate), ('region.zip', region),
                      ('comparison.zip', comparison_zip), ('components.zip', component_zip),
                      ('assessment.zip', assessment_zip), ('batch.zip', batch_zip)]:
        (output / name).write_bytes(raw)
    (output / 'baseline.html').write_text(build_report(baseline), encoding='utf-8')
    (output / 'region.html').write_text(build_report(region), encoding='utf-8')
    report_dir = output / 'comparison'
    report_dir.mkdir()
    import zipfile
    with zipfile.ZipFile(io.BytesIO(comparison_zip)) as archive:
        (report_dir / 'report.html').write_bytes(archive.read('report.html'))
    summary = {'schema': 'geomasklab-five-step-acceptance/1.0', 'passed': True, 'software_version': VERSION,
        'dataset_credit': provenance['credit'], 'source_tile': provenance['acquisition']['catalog_item']['Name'],
        'image_size': list(size), 'measurement': baseline_facts['validity_measurements'],
        'perturbation': {'kind': 'deterministic XOR protocol fixture', 'rectangles_xyxy': patch_boxes,
            'toggled_pixels': len(toggled), 'semantic_improvement_claimed': False, 'temporal_change_claimed': False},
        'independent_comparison': expected_comparison, 'comparison_change_kind': comparison['change_kind'],
        'reference': {'independent': False, 'semantic_accuracy_claimed': False, 'counts': expected_reference},
        'component_inspection': {'component_count': inspection['component_count'],
            'selected_component_count': inspection['selected_component_count'],
            'selected_foreground_pixels': inspection['selected_foreground_pixels'], 'source_mask_modified': False},
        'batch': {'status': batch['status'], 'completed_count': batch['completed_count'], 'failed_count': batch['failed_count'],
            'aggregate': batch['aggregate'], 'verified_resume_preserved_completed_artifacts': True,
            'offline_packet_replay': replayed_batch['verified']},
        'independent_checks': ['explicit pixel-domain count', 'common-domain removed/added/shared sets',
            'saved-total foreground accounting', 'reference contingency table on the same valid region',
            'component-area conservation', 'sample failure and undefined coverage isolation', 'macro and micro aggregation'],
        'inference_performed': False, 'semantic_accuracy_measured': False, 'human_participants': 0,
        'human_handoff_validation': 'pending', 'outputs': {name: name for name in
            ('baseline.zip', 'alternate.zip', 'region.zip', 'comparison.zip', 'components.zip', 'assessment.zip', 'batch.zip', 'index.html')}}
    if geo:
        from geomasklab.geospatial import geospatial_packet, verify_geospatial_packet
        area_zip = geospatial_packet(region, (data / 'source.tif').read_bytes())
        area_record = verify_geospatial_packet(area_zip)['measurements']
        transform = provenance['georeference']['transform']
        nominal_pixel_area = abs(transform[0] * transform[4] - transform[1] * transform[3])
        expected_area = len(expected_b) * nominal_pixel_area
        _require(math.isclose(area_record['foreground_area_m2'], expected_area, rel_tol=1e-12, abs_tol=1e-8),
                 'Nominal area differs from independent affine-determinant arithmetic.')
        _require(math.isclose(area_record['valid_region_area_m2'], len(common) * nominal_pixel_area, rel_tol=1e-12, abs_tol=1e-8),
                 'Valid-region nominal area differs from independent affine-determinant arithmetic.')
        (output / 'geospatial.zip').write_bytes(area_zip)
        summary['optional_geospatial'] = {'foreground_area_m2': expected_area,
            'valid_region_area_m2': len(common) * nominal_pixel_area,
            'interpretation': 'Nominal projected exported-grid area; projection distortion and terrain omitted.'}
    _json(output / 'summary.json', summary)
    (output / 'index.html').write_text(_index_report(summary), encoding='utf-8')
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('five-step-output'))
    parser.add_argument('--geo', action='store_true', help='Also check optional nominal GeoTIFF area.')
    args = parser.parse_args(argv)
    summary = run_workflow(args.output, geo=args.geo)
    print(json.dumps(summary, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
