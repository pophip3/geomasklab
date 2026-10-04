"""Portable evidence bundle construction and offline pixel-level verification."""
from pathlib import Path
import hashlib
import io
import json
import math
import zipfile
from PIL import Image, ImageOps

SCHEMA = 'geoscope-evidence/1.0'
MAX_BUNDLE_BYTES = 96 * 1024 * 1024
MAX_IMAGE_PIXELS = 16 * 1024 * 1024
REQUIRED = {'original.png','full_mask.png','mask.png','overlay.png',
            'result.json','statistics.json','run_log.json'}


def build_bundle(original, run_folder):
    folder = Path(run_folder)
    contents = {'original.png': Path(original).read_bytes()}
    for name in sorted(REQUIRED - {'original.png'}):
        contents[name] = (folder / name).read_bytes()
    if (folder / 'report.md').is_file():
        contents['report.md'] = (folder / 'report.md').read_bytes()
    manifest = {'schema': SCHEMA, 'software_version': '0.8.0-research.1',
                'checksums': {name: {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
                              for name, raw in contents.items()},
                'verification_scope': 'file integrity and deterministic pixel arithmetic; not model accuracy or authorship'}
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, raw in contents.items():
            archive.writestr(name, raw)
        archive.writestr('manifest.json', json.dumps(manifest, indent=2))
    return output.getvalue()


def verify_bundle(payload):
    """Read ZIP in memory only. Return verified facts or raise ValueError."""
    if len(payload) > MAX_BUNDLE_BYTES:
        raise ValueError('Bundle exceeds size limit.')
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        if len(names) != len(set(names)) or any('/' in n or '\\' in n or n in {'.','..'} for n in names):
            raise ValueError('Duplicate or non-flat archive paths.')
        if not REQUIRED | {'manifest.json'} <= set(names):
            raise ValueError('Required evidence is missing.')
        if len(names) > 16 or sum(item.file_size for item in infos) > MAX_BUNDLE_BYTES:
            raise ValueError('Expanded bundle exceeds size limit.')
        manifest = json.loads(archive.read('manifest.json'))
        if manifest.get('schema') != SCHEMA:
            raise ValueError('Unsupported bundle schema.')
        checksums = manifest.get('checksums', {})
        if set(checksums) != set(names) - {'manifest.json'}:
            raise ValueError('Manifest membership mismatch.')
        contents = {name: archive.read(name) for name in checksums}
    for name, raw in contents.items():
        saved = checksums[name]
        if len(raw) != saved['bytes'] or hashlib.sha256(raw).hexdigest() != saved['sha256']:
            raise ValueError('Checksum mismatch: ' + name)
    def load_image(name):
        with Image.open(io.BytesIO(contents[name])) as image:
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValueError('Image exceeds pixel limit.')
            image.load()
            return image.copy()
    original, full, mask, overlay = [load_image(n) for n in ('original.png','full_mask.png','mask.png','overlay.png')]
    if any(image.size != original.size for image in (full,mask,overlay)):
        raise ValueError('Image dimensions disagree.')
    for image in (full,mask):
        if image.mode != 'L' or any(value not in (0,255) for value in set(image.tobytes())):
            raise ValueError('Mask is not a binary L-mode image.')
    result = json.loads(contents['result.json'])
    stats = json.loads(contents['statistics.json'])
    if result.get('metrics') != stats:
        raise ValueError('Recorded metrics disagree.')
    if result['provenance']['image_sha256'] != checksums['original.png']['sha256']:
        raise ValueError('Input identity mismatch.')
    if result['full_mask_sha256'] != checksums['full_mask.png']['sha256']:
        raise ValueError('Full-mask identity mismatch.')
    w,h = original.size
    task = result['task']
    side = task['side']
    boxes = {'all':(0,0,w,h),'left':(0,0,w//2,h),'right':(w//2,0,w,h),
             'top':(0,0,w,h//2),'bottom':(0,h//2,w,h)}
    if side not in boxes:
        raise ValueError('Unknown scope.')
    positive = ImageOps.invert(full) if task.get('invert') else full
    expected = Image.new('L',(w,h),0)
    box = boxes[side]
    expected.paste(positive.crop(box),box[:2])
    roi = stats.get('roi')
    if roi:
        x1,y1,x2,y2 = roi['xyxy']
        if not all(type(x) is int for x in (x1,y1,x2,y2)) or not (0<=x1<x2<=w and 0<=y1<y2<=h):
            raise ValueError('Invalid ROI coordinates.')
        cropped = Image.new('L',(w,h),0)
        cropped.paste(expected.crop((x1,y1,x2,y2)),(x1,y1))
        expected = cropped
    if expected.tobytes() != mask.tobytes():
        raise ValueError('Scope/complement replay disagrees with saved mask.')
    area = mask.histogram()[255]
    bbox = list(mask.getbbox()) if mask.getbbox() else None
    if (stats.get('pixel_area'),stats.get('total_pixels'),stats.get('width'),stats.get('height'),stats.get('bbox_xyxy')) != (area,w*h,w,h,bbox):
        raise ValueError('Pixel statistics disagree with saved mask.')
    ratio = stats.get('area_ratio')
    if not isinstance(ratio,(int,float)) or not math.isfinite(ratio) or not math.isclose(ratio,area/(w*h),rel_tol=1e-12,abs_tol=1e-12):
        raise ValueError('Coverage denominator or ratio is incorrect.')
    if stats.get('scope') != side or stats.get('ground_area_available') is not False or stats.get('unit') != 'pixel':
        raise ValueError('Spatial interpretation is inconsistent.')
    distribution = stats['distribution']
    left = positive.crop((0,0,w//2,h)).histogram()[255]
    right = positive.crop((w//2,0,w,h)).histogram()[255]
    if distribution['left_pixels'] != left or distribution['right_pixels'] != right:
        raise ValueError('Full-mask distribution disagrees.')
    if roi and (distribution['roi_inside_pixels'] != area or distribution['roi_outside_pixels'] != left+right-area):
        raise ValueError('ROI distribution disagrees.')
    return {'verified': True, 'schema':SCHEMA, 'files_checked':len(checksums),
            'pixel_area':area,'area_ratio':area/(w*h),'mode':result['mode'],
            'scope':side,'width':w,'height':h,
            'semantic_accuracy_verified':False,'origin_authenticated':False}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Verify GeoScope export integrity and replay pixel operations offline.')
    parser.add_argument('bundle',type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify_bundle(args.bundle.read_bytes()),indent=2))
    except (ValueError,KeyError,TypeError,zipfile.BadZipFile) as error:
        parser.exit(1,'Verification failed: ' + str(error) + '\n')
