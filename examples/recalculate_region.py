"""Verify, import, and investigate saved evidence without agent/model services."""
import argparse
import base64
import hashlib
import io
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageOps

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workbench import server
from workbench.export_bundle import build_bundle, load_verified_bundle


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle',type=Path)
    parser.add_argument('--output',type=Path,default=Path('workflow-output/region-analysis'))
    args=parser.parse_args()
    payload=args.bundle.read_bytes()
    facts,files=load_verified_bundle(payload)
    with Image.open(io.BytesIO(files['full_mask.png'])) as raw:full=raw.copy()
    source=json.loads(files['result.json'])
    if source['task'].get('invert'):full=ImageOps.invert(full)
    w,h=full.size
    selections=[('whole','all',None,(0,0,w,h)),('left','left',None,(0,0,w//2,h)),
                ('right','right',None,(w//2,0,w,h)),
                ('rectangle','all',{'xyxy':[w//4,h//4,3*w//4,3*h//4],
                 'source':'drawn','image_size':[w,h]},(w//4,h//4,3*w//4,3*h//4))]
    if w<2 or h<2:parser.error('This example needs an image at least 2 by 2 pixels.')
    rows=[]
    args.output.mkdir(parents=True,exist_ok=True)
    with (tempfile.TemporaryDirectory() as temporary,
          patch.object(server,'DATA',Path(temporary)),patch.object(server,'SESSIONS',{}),
          patch.object(server,'post_json',side_effect=AssertionError('Model calls are forbidden')),
          patch.object(server,'AgentTurn',side_effect=AssertionError('Agent calls are forbidden'))):
        imported=server.import_evidence({'bundle':base64.b64encode(payload).decode(),'name':args.bundle.name})
        session=server.SESSIONS[imported['id']]
        for name,side,roi,box in selections:
            r=server.recalculate_region(session,{'run_id':imported['runs'][0]['id'],'scope':side,'roi':roi})
            exported=build_bundle(server.DATA/session['id']/'original.png',server.DATA/session['id']/r['id'])
            checked,derived=load_verified_bundle(exported)
            reference=Image.new('L',(w,h),0)
            reference.paste(full.crop(box),box[:2])
            with Image.open(io.BytesIO(derived['mask.png'])) as raw:exact=raw.tobytes()==reference.tobytes()
            denominator=(box[2]-box[0])*(box[3]-box[1])
            m=r['metrics']
            assert exact and m['scope_area_pixels']==denominator
            assert derived['full_mask.png']==files['full_mask.png'] and derived['original.png']==files['original.png']
            (args.output/(name+'.zip')).write_bytes(exported)
            rows.append({'scope':name,'foreground_pixels':m['pixel_area'],
                'whole_image_pixels':m['total_pixels'],'whole_image_coverage':m['area_ratio'],
                'selected_region_pixels':denominator,'within_region_coverage':m['scope_area_ratio'],
                'reference_pillow_crop_exact':exact,'input_and_full_mask_bytes_preserved':True,
                'bundle_verified':checked['verified'],'semantic_review_state':r['semantic_review']['state'],
                'inference_performed':r['inference_performed']})
    report={'schema':'geoscope-region-study/1.0','software_version':server.VERSION,
            'source_bundle_sha256':hashlib.sha256(payload).hexdigest(),'source_mode':facts['mode'],
            'passed':True,'cases':rows,'limits':[
                'The reference is a direct Pillow crop, not a comparison of model accuracy.',
                'Saved-mask recalculation does not improve semantic predictions or correct boundaries.',
                'Procedural fixtures demonstrate software behavior, not accuracy on Earth observation data.']}
    (args.output/'summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'passed':True,'offline_cases':len(rows),'model_calls':0,'summary':str(args.output/'summary.json')}))


if __name__=='__main__':main()
