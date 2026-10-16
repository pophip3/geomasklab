"""Reproduce Figure 4 measurements and optionally recalculate archived metrics.

Uses the bundled NAIP pixels. --records reads the published experiment-record
ZIP to recalculate Table 4 and section 3.4 from recorded counts.
"""
import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from PIL import Image, ImageDraw
from geomasklab.api import create_evidence
from geomasklab.comparison import compare_bundles, comparison_packet, verify_comparison_packet
from geomasklab.domain import png
from geomasklab.evidence import load_verified_bundle


def require(value, message):
    if not value:
        raise ValueError(message)


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def recalculate_records(archive, output):
    with zipfile.ZipFile(archive) as source:
        rows = list(csv.DictReader(io.StringIO(source.read('six_image_metrics.csv').decode('utf-8-sig'))))
        water = json.loads(source.read('water_65_scene_results.json'))
    expected_ids = ['WHU_9_2', 'WHU_42_0', 'WHU_4_1', 'ISAID_P1137', 'ISAID_P2239', 'ISAID_P2215']
    expected_percent = [('38.71', '42.94', '39.06', '56.17'), ('24.42', '12.15', '42.64', '59.79'),
                        ('48.81', '49.83', '39.81', '56.94'), ('4.90', '5.94', '52.19', '68.58'),
                        ('1.21', '0.00', '42.88', '60.02'), ('5.63', '3.03', '26.79', '42.25')]
    require([row['id'] for row in rows] == expected_ids, 'Unexpected six-image sample identifiers.')
    table = []
    for row, expected in zip(rows, expected_percent):
        tp, fp, fn = (int(row[key]) for key in ('tp', 'fp', 'fn'))
        values = [int(row['foreground']) / int(row['image_pixels']),
                  int(row['right_foreground']) / int(row['right_pixels']),
                  tp / (tp + fp + fn), 2 * tp / (2 * tp + fp + fn)]
        for key, value in zip(('whole_coverage', 'right_coverage', 'iou', 'dice'), values):
            require(math.isclose(value, float(row[key]), rel_tol=1e-12), 'Recorded metric mismatch: ' + row['id'] + '/' + key)
        formatted = tuple(f'{value * 100:.2f}' for value in values)
        require(formatted == expected, 'Table 4 mismatch: ' + row['id'])
        table.append(dict(zip(('sample', 'whole_percent', 'right_percent', 'iou_percent', 'dice_percent'), [row['id'], *formatted])))
    with (output / 'table4_metrics.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(table[0]))
        writer.writeheader()
        writer.writerows(table)
    require(len(water['scenes']) == 65, 'Expected 65 water scenes.')
    counts = {key: sum(scene[key] for scene in water['scenes']) for key in ('tp', 'fp', 'fn')}
    require(counts == {key: water[key] for key in counts}, 'Water per-scene counts do not sum to the recorded totals.')
    require(counts == {'tp': 1356978, 'fp': 35782, 'fn': 256701}, 'Water counts differ from section 3.4.')
    tp, fp, fn = (counts[key] for key in ('tp', 'fp', 'fn'))
    metrics = {'iou': tp / (tp + fp + fn), 'dice': 2 * tp / (2 * tp + fp + fn),
               'precision': tp / (tp + fp), 'recall': tp / (tp + fn)}
    for key, value in metrics.items():
        require(math.isclose(value, water[key], rel_tol=1e-12), 'Water metric mismatch: ' + key)
    require([f'{metrics[key]*100:.2f}' for key in ('iou', 'dice', 'precision', 'recall')] ==
            ['82.27', '90.27', '97.43', '84.09'], 'Water metrics differ from section 3.4.')
    negative = [scene for scene in water['scenes'] if scene['water_pixels'] == 0]
    require(len(negative) == 28 and sum(scene['fp'] > 0 for scene in negative) == 5, 'Water negative-scene counts differ.')
    result = {'source': 'Published numerical records; no new model inference', 'counts': counts,
              'metrics': metrics, 'scene_count': 65, 'negative_scenes': 28, 'negative_scenes_with_fp': 5}
    save_json(output / 'water_metrics.json', result)
    return {'table4_samples': len(table), 'water': result, 'records_sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}


def run(output, records=None):
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())), 'Choose a new or empty output directory.')
    data = ROOT / 'examples/data/naip-denver'
    provenance = json.loads((data / 'provenance.json').read_text(encoding='utf-8'))
    for name in ('image.png', 'mask.png'):
        require(hashlib.sha256((data / name).read_bytes()).hexdigest() == provenance['files'][name]['sha256'], 'Bundled input hash mismatch: ' + name)
    image, mask = (data / 'image.png').read_bytes(), (data / 'mask.png').read_bytes()
    with Image.open(io.BytesIO(image)) as source:
        size = source.size
    valid = Image.new('L', size, 255)
    valid.paste(0, (0, 0, size[0] // 4, size[1]))
    cases = [('whole', {}, 142629, 262144), ('right', {'scope': 'right'}, 63028, 131072),
             ('valid', {'valid_mask': png(valid), 'valid_source': 'Declared left-quarter exclusion'}, 105232, 196608),
             ('empty', {'valid_mask': png(Image.new('L', size)), 'valid_source': 'Declared empty valid domain'}, 0, 0)]
    output.mkdir(parents=True, exist_ok=True)
    rows, bundles = [], []
    preview = Image.new('RGB', (1024, 1144), 'white')
    draw = ImageDraw.Draw(preview)
    for index, (name, options, foreground, denominator) in enumerate(cases):
        options = {'valid_mask': png(Image.new('L', size, 255)), 'valid_source': 'All pixels declared valid', **options}
        bundle = create_evidence(image, mask, target='tree', source='Bundled excess-green mask', aligned=True, **options)
        facts, files = load_verified_bundle(bundle)
        measurement = facts['validity_measurements']
        require(facts['pixel_area'] == foreground and measurement['valid_region_pixels'] == denominator, 'Figure 4 pixel count mismatch: ' + name)
        coverage = foreground / denominator if denominator else None
        require(measurement['coverage_of_valid_region'] == coverage, 'Figure 4 coverage mismatch: ' + name)
        row = {'case': name, 'foreground_pixels': foreground, 'valid_region_pixels': denominator, 'coverage': coverage}
        rows.append(row)
        bundles.append(bundle)
        (output / (name + '.zip')).write_bytes(bundle)
        x, y = (index % 2) * 512, (index // 2) * 572
        with Image.open(io.BytesIO(files['overlay.png'])) as overlay:
            preview.paste(overlay.convert('RGB'), (x, y))
        value = f'{coverage*100:.2f}%' if coverage is not None else 'Undefined'
        draw.text((x + 12, y + 522), f'{name}: {foreground:,} / {denominator:,} pixels', fill='black')
        draw.text((x + 12, y + 545), value, fill='black')
        print(f'{name}: {foreground} / {denominator}; coverage {value}; verified')
    preview.save(output / 'figure4_measurements.png')
    with (output / 'figure4_metrics.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    comparison = compare_bundles(bundles[0], bundles[1])
    require(comparison['changed_pixels'] == 0, 'Expected zero common-domain changed pixels.')
    accounting = comparison['foreground_change_accounting']
    require([accounting[key] for key in ('saved_total_delta_pixels', 'common_domain_delta_pixels', 'excluded_domain_delta_pixels')] == [-79601, 0, -79601], 'Section 3.1 foreground accounting mismatch.')
    packet = comparison_packet(bundles[0], bundles[1])
    verify_comparison_packet(packet)
    (output / 'whole-right-comparison.zip').write_bytes(packet)
    save_json(output / 'comparison.json', comparison)
    result = {'passed': True, 'manuscript': 'Section 3.1 and Figure 4', 'measurements': rows,
              'foreground_change_accounting': accounting, 'inference_performed': False,
              'preview': 'Measurement reconstruction; manuscript artwork is in the article source archive.'}
    if records is not None:
        result['archived_metrics'] = recalculate_records(records, output)
    save_json(output / 'summary.json', result)
    print('Paper measurement reproduction: PASS; output: ' + str(output))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('output/paper-results'))
    parser.add_argument('--records', type=Path, help='Published GeoMaskLab_Supplementary_Experiment_Records.zip')
    args = parser.parse_args()
    run(args.output, args.records)


if __name__ == '__main__':
    main()
