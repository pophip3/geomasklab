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
MAX_BUNDLE_BYTES = 192 * 1024 * 1024
MAX_IMAGE_PIXELS = 64_000_000
REQUIRED = {'original.png','full_mask.png','mask.png','overlay.png',
            'result.json','statistics.json','run_log.json'}


def _same_value(actual, expected):
    """Compare replayed values while keeping booleans distinct from numbers.

    Integer measurements require JSON integers. Float quantities accept finite
    JSON numbers, retaining numeric compatibility for older serialized records.
    """
    if isinstance(expected,dict):
        return isinstance(actual,dict) and set(actual)==set(expected) and all(_same_value(actual[key],value) for key,value in expected.items())
    if isinstance(expected,list):
        return isinstance(actual,list) and len(actual)==len(expected) and all(_same_value(a,b) for a,b in zip(actual,expected))
    if type(expected) is float:
        return type(actual) in (int,float) and math.isfinite(actual) and actual==expected
    return type(actual) is type(expected) and actual==expected


def build_bundle(original, run_folder):
    folder = Path(run_folder)
    contents = {'original.png': Path(original).read_bytes()}
    for name in sorted(REQUIRED - {'original.png'}):
        contents[name] = (folder / name).read_bytes()
    if (folder / 'report.md').is_file():
        contents['report.md'] = (folder / 'report.md').read_bytes()
    for name in ('source_mask.png','analysis.json','valid_mask.png','source_valid_mask.png'):
        if (folder / name).is_file():contents[name]=(folder / name).read_bytes()
    return bundle_contents(contents)


def bundle_contents(contents):
    """Serialize a flat evidence file map without creating a server or directories."""
    if not REQUIRED <= set(contents) or any('/' in n or '\\' in n for n in contents):
        raise ValueError('Evidence contents must include the required flat files.')
    result = json.loads(contents['result.json'])
    from .domain import EVIDENCE_SCHEMA
    manifest = {'schema': EVIDENCE_SCHEMA if 'analysis_config' in result else SCHEMA, 'software_version': result.get('software_version','unrecorded'),
                'export_generator_version': VERSION,
                'checksums': {name: {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
                              for name, raw in contents.items()},
                'verification_scope': 'file integrity and deterministic pixel arithmetic; not model accuracy or authorship'}
    if 'analysis_config' in result:
        v=result['metrics']['validity_measurements']
        manifest['valid_pixels']={'config_sha256':hashlib.sha256(contents['analysis.json']).hexdigest(),
            'mask_sha256':hashlib.sha256(contents['valid_mask.png']).hexdigest(),
            'valid_image_pixels':v['valid_image_pixels'],'valid_region_pixels':v['valid_region_pixels']}
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
        if not isinstance(manifest,dict):raise ValueError('Evidence manifest must be a JSON object.')
        from .domain import EVIDENCE_SCHEMA,DOMAIN_FILES
        schema=manifest.get('schema')
        if schema not in (SCHEMA,EVIDENCE_SCHEMA):
            raise ValueError('Unsupported bundle schema.')
        checksums = manifest.get('checksums', {})
        if not isinstance(checksums,dict) or set(checksums) != set(names) - {'manifest.json'}:
            raise ValueError('Manifest membership mismatch.')
        contents = {name: archive.read(name) for name in checksums}
    for name, raw in contents.items():
        saved = checksums[name]
        if not isinstance(saved,dict) or type(saved.get('bytes')) is not int or len(raw) != saved['bytes'] or hashlib.sha256(raw).hexdigest() != saved.get('sha256'):
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
    if not isinstance(result,dict) or not isinstance(stats,dict) or not _same_value(result.get('metrics'),stats):
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
    validity=None;valid_record=None
    if schema==EVIDENCE_SCHEMA:
        from .domain import validity_input,configuration,validity_measurements
        if not {'analysis.json','valid_mask.png'}<=set(contents):raise ValueError('Declared validity files are missing.')
        if set(contents)-(REQUIRED|{'report.md','source_mask.png'}|DOMAIN_FILES):raise ValueError('Unsupported validity-bundle member.')
        config=json.loads(contents['analysis.json'])
        if not isinstance(config,dict):raise ValueError('Analysis configuration must be an object.')
        declaration=config.get('validity')
        if not isinstance(declaration,dict):raise ValueError('Validity declaration is missing.')
        policy=declaration.get('policy')
        if policy=='explicit_binary_mask':
            if 'source_valid_mask.png' not in contents:raise ValueError('Source validity mask is missing.')
            validity,replayed,_=validity_input(contents['source_valid_mask.png'],original.size,declaration.get('source'))
        elif policy=='all_pixels_declared_valid':
            if 'source_valid_mask.png' in contents:raise ValueError('All-valid declaration cannot contain a source validity mask.')
            validity,replayed,_=validity_input(None,original.size)
        else:raise ValueError('Unknown validity policy.')
        normalized=load_image('valid_mask.png')
        if normalized.mode!='L' or normalized.size!=original.size or normalized.tobytes()!=validity.tobytes():
            raise ValueError('Validity mask normalization does not replay.')
        expected_config=configuration(task,checksums['original.png']['sha256'],original.size,replayed)
        canonical=lambda obj:json.dumps(obj,sort_keys=True,allow_nan=False)
        if canonical(config)!=canonical(expected_config) or canonical(result.get('analysis_config'))!=canonical(config):
            raise ValueError('Analysis configuration does not match realized inputs and conditions.')
    elif DOMAIN_FILES&set(contents) or 'analysis_config' in result or 'validity_measurements' in stats:
        raise ValueError('Validity extension requires geomasklab-evidence/2.0.')
    if type(task.get('invert', False)) is not bool:
        raise ValueError('Complement flag must be boolean.')
    if not _same_value(task.get('roi'),stats.get('roi')):
        raise ValueError('Task and statistics ROI disagree.')
    options=result.get('task_options') or {}
    if 'roi' in options and not _same_value(options['roi'],stats.get('roi')):
        raise ValueError('Report options and statistics ROI disagree.')
    side = task['side']
    if validity is not None:
        from .regions import validate_region
        validate_region(side,stats.get('roi'),w,h)
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
        if 'image_size' in roi and not _same_value(roi['image_size'],[w,h]):
            raise ValueError('ROI image dimensions disagree with the source image.')
        x1,y1,x2,y2 = roi['xyxy']
        if not all(type(x) is int for x in (x1,y1,x2,y2)) or not (0<=x1<x2<=w and 0<=y1<y2<=h):
            raise ValueError('Invalid ROI coordinates.')
        cropped = Image.new('L',(w,h),0)
        cropped.paste(expected.crop((x1,y1,x2,y2)),(x1,y1))
        expected = cropped
    geometric_expected_area=expected.histogram()[255]
    if validity is not None:
        expected,_,valid_record=validity_measurements(positive,task,validity)
        if json.dumps(stats.get('validity_measurements'),sort_keys=True,allow_nan=False)!=json.dumps(valid_record,sort_keys=True,allow_nan=False):
            raise ValueError('Validity measurements or denominators do not replay.')
        expected_summary={'config_sha256':checksums['analysis.json']['sha256'],
            'mask_sha256':checksums['valid_mask.png']['sha256'],
            'valid_image_pixels':valid_record['valid_image_pixels'],'valid_region_pixels':valid_record['valid_region_pixels']}
        if json.dumps(manifest.get('valid_pixels'),sort_keys=True,allow_nan=False)!=json.dumps(expected_summary,sort_keys=True):
            raise ValueError('Manifest valid-pixel summary does not replay.')
    if expected.tobytes() != mask.tobytes():
        raise ValueError('Scope/complement replay disagrees with saved mask.')
    area = mask.histogram()[255]
    bbox = list(mask.getbbox()) if mask.getbbox() else None
    if not _same_value([stats.get('pixel_area'),stats.get('total_pixels'),stats.get('width'),stats.get('height'),stats.get('bbox_xyxy')],[area,w*h,w,h,bbox]):
        raise ValueError('Pixel statistics disagree with saved mask.')
    ratio = stats.get('area_ratio')
    if type(ratio) not in (int,float) or not math.isfinite(ratio) or not math.isclose(ratio,area/(w*h),rel_tol=1e-12,abs_tol=1e-12):
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
    if not _same_value([distribution['left_pixels'],distribution['right_pixels']],[left,right]):
        raise ValueError('Full-mask distribution disagrees.')
    inside=geometric_expected_area if validity is not None else area
    if validity is not None:
        if distribution.get('basis')!='full_mask_before_scope_and_validity':raise ValueError('Validity distribution basis disagrees.')
        if roi and not _same_value([distribution.get('roi_valid_foreground_pixels'),distribution.get('roi_excluded_foreground_pixels')],[area,inside-area]):
            raise ValueError('ROI validity distribution disagrees.')
    if roi and not _same_value([distribution['roi_inside_pixels'],distribution['roi_outside_pixels']],[inside,left+right-inside]):
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
                not _same_value(saved_fields,measured_fields)):
            raise ValueError('Candidate measurements disagree with saved mask.')
    facts = {'verified': True, 'schema':schema, 'files_checked':len(checksums),
            'pixel_area':area,'area_ratio':area/(w*h),'mode':result['mode'],
            'scope':side,'width':w,'height':h,
            'semantic_review_state':review['state'] if review else 'unrecorded',
            'semantic_accuracy_verified':False,'origin_authenticated':False}
    if valid_record is not None:facts['validity_measurements']=valid_record
    return facts, contents


def verify_bundle(payload):
    """Return verified pixel facts, not accuracy or authenticated origin."""
    return load_verified_bundle(payload)[0]
