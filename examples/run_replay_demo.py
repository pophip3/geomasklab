"""Verify retained bytes and arithmetic, then reject a one-pixel validity edit.

The expected rejection is a successful demonstration and exits zero. Unsigned
checksums detect inconsistent artifacts; they do not authenticate their author.
"""
import io
from pathlib import Path
import sys
import zipfile
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
        valid = Image.new('L', source.size, 255)
    bundle = create_evidence(image, mask, target='tree', source='Bundled fixture; semantics unvalidated',
        aligned=True, valid_mask=png(valid), valid_source='Explicit all-valid demonstration mask')
    facts, files = load_verified_bundle(bundle)
    if not facts['verified'] or files['original.png'] != image:
        raise ValueError('Retained image bytes or numerical replay did not match.')
    with Image.open(io.BytesIO(files['source_mask.png'])) as original, Image.open(io.BytesIO(files['full_mask.png'])) as retained:
        if original.tobytes() != retained.tobytes():
            raise ValueError('Full-mask pixels did not match the source.')
    print('Replay result: PASS (Bit-for-bit matched: retained inputs and mask pixels; arithmetic verified)')
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    with Image.open(io.BytesIO(members['valid_mask.png'])) as raw:
        changed = raw.copy()
    changed.putpixel((0, 0), 0)
    members['valid_mask.png'] = png(changed)  # Keep the original checksum to expose inconsistency.
    output = Path('reviewer-output/replay-demo')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'original.zip').write_bytes(bundle)
    tampered = io.BytesIO()
    with zipfile.ZipFile(tampered, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, raw in members.items():
            archive.writestr(name, raw)
    (output / 'tampered.zip').write_bytes(tampered.getvalue())
    try:
        load_verified_bundle(tampered.getvalue())
    except ValueError as exc:
        if str(exc) != 'Checksum mismatch: valid_mask.png':
            raise
        print('Replay result: FAIL (Mismatched field: manifest.checksums.valid_mask.png.sha256; expected rejection)')
    else:
        raise ValueError('The one-pixel mutation was incorrectly accepted.')


if __name__ == '__main__':
    main()
