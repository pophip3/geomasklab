"""Replay a retained, actual RemoteSAM mask; no new inference or weights needed."""
import hashlib
import io
import json
from pathlib import Path
import sys
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from geomasklab.api import create_evidence
from geomasklab.evidence import load_verified_bundle


def main():
    data = ROOT / 'examples/data/local-model-mask'
    record = json.loads((data / 'provenance.json').read_text(encoding='utf-8'))
    image = (data / record['input_image']).resolve().read_bytes()
    mask = (data / 'mask.png').read_bytes()
    for raw, field in ((image, 'input_sha256'), (mask, 'mask_sha256')):
        if hashlib.sha256(raw).hexdigest() != record[field]:
            raise ValueError('Bundled input identity mismatch: ' + field)
    with Image.open(io.BytesIO(mask)) as source:
        full = source.copy()
    w, h = full.size
    cases = [('whole', {}, (0, 0, w, h)), ('left', {'scope':'left'}, (0, 0, w//2, h)),
             ('right', {'scope':'right'}, (w//2, 0, w, h)),
             ('rectangle', {'roi':{'xyxy':[w//4,h//4,3*w//4,3*h//4],
                                  'source':'imported','image_size':[w,h]}}, (w//4, h//4, 3*w//4, 3*h//4))]
    out = Path('reviewer-output/model-mask-replay')
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for label, options, box in cases:
        bundle = create_evidence(image, mask, target='building',
            source='Retained RemoteSAM all-buildings prediction; semantics unvalidated', aligned=True, **options)
        facts, files = load_verified_bundle(bundle)
        counted = full.crop(box).tobytes().count(255)
        if files['original.png'] != image or facts['pixel_area'] != counted:
            raise ValueError('Source preservation or independent pixel replay failed.')
        with Image.open(io.BytesIO(files['full_mask.png'])) as retained:
            if retained.tobytes() != full.tobytes():
                raise ValueError('Replay modified full-mask pixels.')
        (out / (label + '.zip')).write_bytes(bundle)
        rows.append({'scope':label, 'foreground_pixels':counted, 'verified':facts['verified']})
        print(f'{label}: {counted} foreground pixels; replay PASS (No new inference)')
    (out / 'summary.json').write_text(json.dumps(rows, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
