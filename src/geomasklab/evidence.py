"""Portable evidence bundle construction and offline pixel-level verification."""
from pathlib import Path
import hashlib
import io
import json
import math
import zipfile
from PIL import Image, ImageOps
from .contract import VERSION
from .review import verify_review
from .geometry import candidate_statistics

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
    if (folder / 'source_mask.png').is_file():
        contents['source_mask.png'] = (folder / 'source_mask.png').read_bytes()
    return bundle_contents(contents)


def bundle_contents(contents):
    """Serialize a flat evidence file map without creating a server or directories."""
    if not REQUIRED <= set(contents) or any('/' in n or '\\' in n for n in contents):
        raise ValueError('Evidence contents must include the required flat files.')
    result = json.loads(contents['result.json'])
    manifest = {'schema': SCHEMA, 'software_version': result.get('software_version','unrecorded'),
                'export_generator_version': VERSION,
                'checksums': {name: {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
                              for name, raw in contents.items()},
                'verification_scope': 'file integrity and deterministic pixel arithmetic; not model accuracy or authorship'}
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, raw in contents.items():
            archive.writestr(name, raw)
        archive.writestr('manifest.json', json.dumps(manifest, indent=2))
    return output.getvalue()


def load_verified_bundle(payload):
    """Validate once and return facts and flat file bytes; never extract."""
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
    external = result.get('external_mask')
    if result.get('mode') == 'external' and external is None:
        raise ValueError('External mask origin is missing.')
    if external is not None:
        from .masks import binary_png, source_text
        if (not isinstance(external, dict) or external.get('origin_authenticated') is not False or
            external.get('alignment_user_assertion') is not True):
            raise ValueError('Invalid external mask provenance assertions.')
        source_text(external.get('source'))
        if external.get('provider') is not None:
            provider=external['provider']
            if not isinstance(provider,dict) or provider.get('output_sha256')!=external.get('upload_sha256'):
                raise ValueError('Provider output identity does not match the external source mask.')
        if ('source_mask.png' not in contents or
            external.get('upload_sha256') != checksums['source_mask.png']['sha256'] or
            binary_png(contents['source_mask.png'], original.size).tobytes() != full.tobytes()):
            raise ValueError('External mask provenance or lossless normalization disagrees.')
    review=result.get('semantic_review')
    if review is not None:
        verify_review(review,run_id=result['id'],image_sha256=checksums['original.png']['sha256'],
                      mask_sha256=checksums['mask.png']['sha256'])
    w,h = original.size
    task = result['task']
    if type(task.get('invert', False)) is not bool:
        raise ValueError('Complement flag must be boolean.')
    if task.get('roi') != stats.get('roi'):
        raise ValueError('Task and statistics ROI disagree.')
    options=result.get('task_options') or {}
    if 'roi' in options and options['roi'] != stats.get('roi'):
        raise ValueError('Report options and statistics ROI disagree.')
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
    if 'scope_area_pixels' in stats or 'scope_area_ratio' in stats:
        # Older bundles contain only whole-image coverage and remain readable.
        x1,y1,x2,y2=boxes[side]
        if roi:
            rx1,ry1,rx2,ry2=roi['xyxy']
            x1,y1,x2,y2=max(x1,rx1),max(y1,ry1),min(x2,rx2),min(y2,ry2)
        selected_area=max(0,x2-x1)*max(0,y2-y1)
        within=stats.get('scope_area_ratio')
        if type(stats.get('scope_area_pixels')) is not int or stats['scope_area_pixels']!=selected_area:
            raise ValueError('Selected-region denominator is incorrect.')
        if selected_area:
            if (type(within) not in (int,float) or not math.isfinite(within) or
                not math.isclose(within,area/selected_area,rel_tol=1e-12,abs_tol=1e-12)):
                raise ValueError('Within-region coverage is incorrect.')
        elif 'scope_area_ratio' not in stats or within is not None:
            raise ValueError('An empty analysis scope must have null coverage.')
    if stats.get('scope') != side or stats.get('ground_area_available') is not False or stats.get('unit') != 'pixel':
        raise ValueError('Spatial interpretation is inconsistent.')
    distribution = stats['distribution']
    left = positive.crop((0,0,w//2,h)).histogram()[255]
    right = positive.crop((w//2,0,w,h)).histogram()[255]
    if distribution['left_pixels'] != left or distribution['right_pixels'] != right:
        raise ValueError('Full-mask distribution disagrees.')
    if roi and (distribution['roi_inside_pixels'] != area or distribution['roi_outside_pixels'] != left+right-area):
        raise ValueError('ROI distribution disagrees.')
    candidates=stats.get('candidate_stats')
    if candidates is not None:
        minimum=candidates.get('min_area_pixels')
        # Historical bundles localized the notice. Replay numerical and
        # structural fields while retaining the original prose and file hash.
        measured=candidate_statistics(mask,minimum) if type(minimum) is int and minimum>=1 else {}
        saved_fields={k:v for k,v in candidates.items() if k!='notice'}
        measured_fields={k:v for k,v in measured.items() if k!='notice'}
        if (type(minimum) is not int or minimum<1 or not isinstance(candidates.get('notice'),str) or
                saved_fields!=measured_fields):
            raise ValueError('Candidate measurements disagree with saved mask.')
    facts = {'verified': True, 'schema':SCHEMA, 'files_checked':len(checksums),
            'pixel_area':area,'area_ratio':area/(w*h),'mode':result['mode'],
            'scope':side,'width':w,'height':h,
            'semantic_review_state':review['state'] if review else 'unrecorded',
            'semantic_accuracy_verified':False,'origin_authenticated':False}
    return facts, contents


def verify_bundle(payload):
    """Return verified pixel facts, not accuracy or authenticated origin."""
    return load_verified_bundle(payload)[0]
