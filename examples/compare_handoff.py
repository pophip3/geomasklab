"""Controlled workflow study, not a comparison of segmentation model accuracy.

Actual third-party component: Label Studio SDK 2.1.2 official brush converter.
Only that component is run; no claim to exercise Label Studio web or QGIS.
"""
import argparse
import base64
import hashlib
import io
import json
import platform
import sys
import tempfile
import time
import zipfile
from contextlib import redirect_stdout
from importlib.metadata import version
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
from export_bundle import build_bundle, verify_bundle
from label_studio_export import convert_bundle, official_brush
from reviewer_demo import run_demo


def changed_bundle(payload,kind):
    with zipfile.ZipFile(io.BytesIO(payload)) as z:files={n:z.read(n) for n in z.namelist()}
    r=json.loads(files['result.json'])
    if kind=='coverage_denominator':
        r['metrics']['area_ratio']=r['metrics']['pixel_area']/(r['metrics']['total_pixels']//2)
        files['statistics.json']=json.dumps(r['metrics']).encode()
    elif kind=='roi_intent':r['task']['roi']={'xyxy':[1,1,100,100]}
    elif kind=='review_binding':r['semantic_review']['events'][0]['mask_sha256']='0'*64
    elif kind=='candidate_count':
        r['metrics']['candidate_stats']['candidate_count']+=10
        files['statistics.json']=json.dumps(r['metrics']).encode()
    files['result.json']=json.dumps(r).encode()
    m=json.loads(files['manifest.json'])
    m['checksums']={n:{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
                    for n,raw in files.items() if n!='manifest.json'}
    files['manifest.json']=json.dumps(m).encode()
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for n,raw in files.items():z.writestr(n,raw)
    return out.getvalue()


def raw_converter_roundtrip(payload,brush):
    """Existing-tool baseline: PNG -> official RLE -> official decoded PNG pixels."""
    import numpy as np
    from PIL import Image
    with zipfile.ZipFile(io.BytesIO(payload)) as z:raw=z.read('mask.png')
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp)/'mask.png';p.write_bytes(raw)
        rle,w,h=brush.image2rle(str(p))
    decoded=brush.decode_rle(rle).reshape((h,w,4))[:,:,3]
    with Image.open(io.BytesIO(raw)) as original:expected=np.asarray(original)
    return bool(np.array_equal(decoded,expected))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk-path',type=Path,help='Optional isolated official SDK installation directory.')
    parser.add_argument('--output',type=Path,default=Path('workflow-output'))
    args=parser.parse_args()
    if args.sdk_path:sys.path.insert(0,str(args.sdk_path.resolve()))
    brush=official_brush()
    import numpy as np
    from PIL import Image
    args.output.mkdir(parents=True,exist_ok=True)
    with redirect_stdout(io.StringIO()):run_demo(args.output/'fixtures')
    rows=[];faults=[]
    with tempfile.TemporaryDirectory() as temp,patch.object(server,'DATA',Path(temp)),patch.object(server,'SESSIONS',{}):
        for bundle in sorted((args.output/'fixtures').glob('*.zip')):
            payload=bundle.read_bytes();facts=verify_bundle(payload)
            t=time.perf_counter();exact=raw_converter_roundtrip(payload,brush);converter_seconds=time.perf_counter()-t
            task,config,_=convert_bundle(payload,brush)
            region=task['predictions'][0]['result'][0]
            decoded=brush.decode_rle(region['value']['rle']).reshape((facts['height'],facts['width'],4))[:,:,3]
            with zipfile.ZipFile(io.BytesIO(payload)) as z:
                with Image.open(io.BytesIO(z.read('mask.png'))) as mask:adapter_exact=bool(np.array_equal(decoded,np.asarray(mask)))
            # Forbid inference explicitly, rather than infer it from a short elapsed time.
            with patch.object(server,'post_json',side_effect=AssertionError('Import must not call model')):
                t=time.perf_counter();s=server.import_evidence({'bundle':base64.b64encode(payload).decode(),'name':bundle.name});handoff_seconds=time.perf_counter()-t
            sid=s['id'];r=s['runs'][0];server.SESSIONS.clear();reloaded=server.get_session(sid)
            again=build_bundle(server.DATA/sid/'original.png',server.DATA/sid/r['id'])
            with zipfile.ZipFile(io.BytesIO(payload)) as before,zipfile.ZipFile(io.BytesIO(again)) as after:
                artifacts_exact=all(before.read(n)==after.read(n) for n in ('original.png','full_mask.png','mask.png','statistics.json'))
            row={'case':bundle.stem,'pixel_area':facts['pixel_area'],'sdk_converter_mask_roundtrip_exact':exact,
                 'geoscope_adapter_mask_roundtrip_exact':adapter_exact,'restored_pixel_artifacts_exact':artifacts_exact,
                 'restored_review_state':reloaded['runs'][0]['semantic_review']['state'],
                 'model_calls_on_import':0,'sdk_converter_seconds_observed':round(converter_seconds,6),
                 'geoscope_import_seconds_observed':round(handoff_seconds,6)}
            rows.append(row)
            if bundle.stem=='right':
                for kind in ('coverage_denominator','roi_intent','review_binding','candidate_count'):
                    changed=changed_bundle(payload,kind)
                    baseline=raw_converter_roundtrip(changed,brush)
                    try:server.import_evidence({'bundle':base64.b64encode(changed).decode()});rejected=False;reason=''
                    except ValueError as e:rejected=True;reason=str(e)
                    faults.append({'fault':kind,'all_manifest_checksums_updated':True,
                                   'sdk_mask_converter_succeeds':baseline,'geoscope_import_rejected':rejected,'reason':reason})
            (args.output/(bundle.stem+'-label-config.xml')).write_text(config,encoding='utf-8')
            (args.output/(bundle.stem+'-label-studio.json')).write_text(json.dumps([task],ensure_ascii=False),encoding='utf-8')
    assert len(rows)==5 and len(faults)==4
    assert all(r['sdk_converter_mask_roundtrip_exact'] and r['geoscope_adapter_mask_roundtrip_exact'] and r['restored_pixel_artifacts_exact'] for r in rows)
    assert all(f['geoscope_import_rejected'] and f['sdk_mask_converter_succeeds'] for f in faults)
    report={'schema':'geoscope-workflow-study/1.0','software_version':server.VERSION,
            'third_party':{'component':'label_studio_sdk.converter.brush','package_version':version('label-studio-sdk'),
                           'module_sha256':hashlib.sha256(Path(brush.__file__).read_bytes()).hexdigest()},
            'environment':{'python':platform.python_version(),'platform':platform.platform(),'numpy':version('numpy'),'pillow':version('Pillow')},
            'protocol':'Same procedural inputs and saved masks; no model rerun or true EO accuracy comparison.',
            'passed':True,'cases':rows,'controlled_faults':faults,
            'limits':['SDK converter only; Label Studio GUI, QGIS and SAMGeo not benchmarked.',
                      'Metadata validation is outside the brush converter scope; not a defect in Label Studio.',
                      'Observed operation times perform different work; do not report as a speed ranking.',
                      'No user-study labor savings, semantic improvement or first-of-kind claim.']}
    (args.output/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':True,'cases':len(rows),'controlled_faults':len(faults),'third_party':report['third_party']}))


if __name__=='__main__':main()
