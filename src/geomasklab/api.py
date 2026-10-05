"""Create and recalculate mask evidence without a model, browser or server."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
import re
import time
import uuid
from PIL import Image, ImageOps
from ._version import VERSION
from .evidence import bundle_contents, load_verified_bundle
from .masks import binary_png, source_text, MAX_IMAGE_BYTES, MAX_MASK_PIXELS
from .measurements import constrain, statistics
from .regions import validate_region, prepare_analysis, region_report
from .review import initial_review
from .domain import (KEEP_VALIDITY, validity_input, configuration,
                     validity_measurements, add_validity_statistics)


def timestamp():return datetime.now(timezone.utc).isoformat()
def identifier():return uuid.uuid4().hex[:12]
def json_bytes(value):return json.dumps(value,indent=2,ensure_ascii=False).encode('utf-8')


def create_evidence(image_bytes, mask_bytes, *, target, source, aligned, scope='all', roi=None,
                    image_source='User-supplied image', session_id=None, run_id=None,
                    parent_run_id=None, version=1, provider_info=None,
                    valid_mask=None, valid_source=None, invert=False):
    """Record an aligned external positive-target mask and an explicit pixel scope.

    Coordinates are those of the normalized, displayed RGB image. This operation
    validates binary pixels and creates pending-review evidence; it makes no
    inference, alignment or authenticated-origin claim.
    """
    start=time.perf_counter();source=source_text(source)
    if type(invert) is not bool:raise ValueError('Complement flag must be boolean.')
    if aligned is not True:raise ValueError('Confirm pixel alignment with the normalized image.')
    if not isinstance(target,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}',target):
        raise ValueError('Target must be an ASCII label of 1 to 64 letters, digits, underscores or hyphens, starting with a letter.')
    for value in (session_id,run_id,parent_run_id):
        if value is not None and (not isinstance(value,str) or not re.fullmatch(r'[a-f0-9]{12}',value)):
            raise ValueError('Result/session identifiers must contain 12 lowercase hexadecimal characters.')
    if type(version) is not int or version<1:raise ValueError('Result version must be a positive integer.')
    if not image_bytes or len(image_bytes)>MAX_IMAGE_BYTES:raise ValueError('Headless images must be 48 MB or smaller.')
    with Image.open(io.BytesIO(image_bytes)) as raw:
        if raw.width*raw.height>MAX_MASK_PIXELS:raise ValueError('Headless images must contain no more than 64 million pixels.')
        if getattr(raw,'n_frames',1)!=1:raise ValueError('Use a single-frame image.')
        preserve=raw.format=='PNG' and raw.mode=='RGB' and raw.getexif().get(274,1)==1
        image=ImageOps.exif_transpose(raw).convert('RGB')
    if not preserve:
        out=io.BytesIO();image.save(out,'PNG');image_bytes=out.getvalue()
    full=binary_png(mask_bytes,image.size)
    if provider_info is not None:
        if not isinstance(provider_info,dict):raise ValueError('Provider metadata must be an object.')
        encoded_provider=json.dumps(provider_info,allow_nan=False)
        if len(encoded_provider)>16_000:raise ValueError('Provider metadata must contain no more than 16,000 characters.')
        if provider_info.get('output_sha256')!=hashlib.sha256(mask_bytes).hexdigest():
            raise ValueError('Provider output identity does not match the supplied mask.')
        provider_info=json.loads(encoded_provider)
    roi=validate_region(scope,roi,*image.size)
    positive=ImageOps.invert(full) if invert else full
    mask=constrain(positive,scope,roi);metrics=statistics(mask,scope,roi,positive)
    task={'action':'segment','target':target,'side':scope,'invert':invert,'roi':roi,
          'scope_rule':'deterministic_pixel_scope','quality_mode':None,'effective_quality_mode':None}
    domain_files={};config=None
    if valid_mask is not None:
        valid,declaration,domain_files=validity_input(valid_mask,image.size,valid_source)
        mask,_,_=validity_measurements(positive,task,valid)
        metrics=statistics(mask,scope,roi,positive)
        add_validity_statistics(metrics,positive,task,valid)
        config=configuration(task,hashlib.sha256(image_bytes).hexdigest(),image.size,declaration)
        domain_files['analysis.json']=json_bytes(config)
    elif valid_source is not None:
        raise ValueError('A validity source requires an explicit valid mask.')
    encoded={}
    overlay=Image.composite(Image.blend(image,Image.new('RGB',image.size,(69,213,152)),.48),image,mask)
    for name,im in (('full_mask.png',full),('mask.png',mask),('overlay.png',overlay)):
        out=io.BytesIO();im.save(out,'PNG');encoded[name]=out.getvalue()
    rid,sid=run_id or identifier(),session_id or identifier()
    result={'id':rid,'session_id':sid,'parent_run_id':parent_run_id,'version':version,
        'software_version':VERSION,'created_at':timestamp(),'mode':'external','execution_kind':'external_mask_import',
        'inference_performed':False,'query':f'Import an external {target} mask.','task':task,'task_options':{'roi':roi},
        'provenance':{'planner':'explicit_mask_import','perception':'User-supplied binary PNG; no model call',
                      'source':image_source,'image_sha256':hashlib.sha256(image_bytes).hexdigest()},
        'external_mask':{'source':source,'origin_authenticated':False,'alignment_user_assertion':True,
                         'upload_sha256':hashlib.sha256(mask_bytes).hexdigest()},
        'full_mask_sha256':hashlib.sha256(encoded['full_mask.png']).hexdigest(),'metrics':metrics,
        'status':'completed' if metrics['pixel_area'] else 'needs_review','semantic_review':initial_review(),
        'message':f'Imported {metrics["pixel_area"]:,} foreground pixels. No model inference. Review target, alignment and boundaries.',
        'trace':[{'step':1,'name':'Validate external mask','state':'completed',
                  'detail':'Exact dimensions and binary PNG pixels; no resizing, thresholding or model calls.'},
                 {'step':2,'name':'Measure explicit pixel scope','state':'completed',
                  'detail':'Retained source bytes, computed both coverage denominators and set review to pending.'}]}
    result['duration_ms']=round((time.perf_counter()-start)*1000,2)
    if config is not None:result['analysis_config']=config
    if provider_info is not None:result['external_mask']['provider']=provider_info
    report='\n'.join(['# GeoMaskLab imported-mask evidence','',
        f'- Target: {target}; scope: {scope}; ROI: {json.dumps(roi)}',
        f'- Mask source (user supplied): {source}',
        '- Execution: external mask import; no model inference.',
        f'- Foreground pixels: {metrics["pixel_area"]}',f'- Whole-image denominator: {metrics["total_pixels"]}',
        f'- Whole-image coverage: {metrics["area_ratio"]}',f'- Selected-region denominator: {metrics["scope_area_pixels"]}',
        f'- Within-region coverage: {metrics["scope_area_ratio"]}',
        '- Review: pending; candidate components are not validated object counts.',
        '- Pixel alignment and source information are user assertions.',
        '- Verify: geomasklab verify bundle.zip',''])
    if config is not None:
        report+='\n## Declared validity\n\n'+json.dumps(config,indent=2)+'\n\n'+json.dumps(metrics['validity_measurements'],indent=2)+'\n'
    files={'original.png':image_bytes,'source_mask.png':mask_bytes,**encoded,**domain_files,
        'result.json':json_bytes({k:v for k,v in result.items() if k!='trace'}),
        'statistics.json':json_bytes(metrics),'run_log.json':json_bytes(result['trace']),'report.md':report.encode()}
    bundle=bundle_contents(files)
    load_verified_bundle(bundle)
    return bundle


def recalculate_evidence(payload, *, scope='all', roi=None, valid_mask=KEEP_VALIDITY, valid_source=None):
    """Derive another scope/validity from a verified bundle, resetting review.

    Omitted valid_mask retains saved validity; None explicitly declares all pixels
    valid. Replacement PNG bytes require their own valid_source description.
    """
    _,source=load_verified_bundle(payload)
    origin=json.loads(source['result.json'])
    result,files=prepare_analysis(payload,scope,roi,run_id=identifier(),created_at=timestamp(),
        version=origin['version']+1,statistics=statistics,constrain=constrain,
        valid_mask=valid_mask,valid_source=valid_source)
    files={**files,'original.png':source['original.png'],'statistics.json':json_bytes(result['metrics']),
        'result.json':json_bytes({k:v for k,v in result.items() if k!='trace'}),
        'run_log.json':json_bytes(result['trace']),'report.md':region_report({},result).encode()}
    output=bundle_contents(files);load_verified_bundle(output)
    return output
