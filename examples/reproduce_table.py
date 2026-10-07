"""Recompute the retained NAIP domain example (Manuscript section 3.1, Fig. 2).

The left-quarter exclusion is a declared fixture, not detected cloud/NoData.
All image/mask bytes are bundled; no model, server or download is required.
"""
import json
from pathlib import Path
import sys
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from geomasklab.api import create_evidence
from geomasklab.domain import png
from geomasklab.evidence import load_verified_bundle


def main():
    data = ROOT / 'examples/data/naip-denver'
    image, mask = (data / 'image.png').read_bytes(), (data / 'mask.png').read_bytes()
    with Image.open(data / 'image.png') as source:
        size = source.size
    valid = Image.new('L', size, 255)
    valid.paste(0, (0, 0, size[0] // 4, size[1]))
    cases = [('Whole image', {}, 'area_ratio', None, 'Fig. 2a'),
             ('Right half', {'scope': 'right'}, 'scope_area_ratio', None, 'Fig. 2b'),
             ('Declared valid domain', {'valid_mask': png(valid), 'valid_source':
              'Fixture exclusion: left quarter'}, None, 'coverage_of_valid_region', 'Fig. 2c')]
    output = Path('reviewer-output/denominators')
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, (label, options, geometric, effective, reference) in enumerate(cases):
        bundle = create_evidence(image, mask, target='tree', source='Bundled excess-green fixture; semantics unvalidated', aligned=True, **options)
        facts, files = load_verified_bundle(bundle)
        metrics = json.loads(files['statistics.json'])
        ratio = metrics[geometric] if geometric else metrics['validity_measurements'][effective]
        (output / f'case-{index + 1}.zip').write_bytes(bundle)
        rows.append({'case': label, 'foreground_pixels': facts['pixel_area'], 'coverage': ratio})
        print(f'{label}: {100 * ratio:.2f}% (Reflects Manuscript section 3.1 / {reference})')
    spread = 100 * (max(row['coverage'] for row in rows) - min(row['coverage'] for row in rows))
    print(f'spread = {spread:.2f} pp (Different analysis supports; not a prediction change)')
    (output / 'summary.json').write_text(json.dumps(rows, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
