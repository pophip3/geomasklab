"""Exact-mask software validation; simulated inference, never an EO accuracy test."""
from pathlib import Path
import base64
import csv
import io
import json
import os
import random
import sys
import tempfile
import time
from unittest.mock import patch
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from workbench import server
from workbench.agent_bridge import WorkbenchAgent
from workbench.export_bundle import build_bundle,verify_bundle
from workbench.product_contract import VERSION


def run_matrix():
    records=[]
    output=ROOT/'evaluation/results'
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as directory, patch.object(server,'DATA',Path(directory)), patch.dict(os.environ,{
        'GEO_AGENT_BASE_URL':'http://simulated.invalid/v1','GEO_AGENT_MODEL':'SIMULATED-NOT-A-MODEL',
        'GEO_REMOTESAM_URL':'http://simulated.invalid/predict','GEO_REMOTESAM_REVISION':'exact-fixture-v1'}):
        for width,height in [(1,1),(5,3),(11,7),(16,12),(31,23)]:
            rng=random.Random(20261004+width*1000+height)
            bits=[rng.randrange(2) for _ in range(width*height)]
            truth=Image.new('L',(width,height))
            truth.putdata([255*b for b in bits])
            image=Image.new('RGB',(width,height),'#6b8692')
            for side in ['all','left','right','top','bottom']:
                for invert in [False,True]:
                    for use_roi in [False,True]:
                        if use_roi and side != 'all':
                            continue  # API contract: ROI and pixel half are mutually exclusive.
                        roi_box=(width//3,height//3,width,height)
                        roi={'xyxy':list(roi_box),'source':'drawn','image_size':[width,height]} if use_roi else None
                        sid=server.new_session(uploaded=server.image_b64(image),name='SIMULATED exact-mask validation')['id']
                        session=server.SESSIONS[sid]
                        def model_response(self,messages):
                            if isinstance(messages[-1]['content'],str):
                                return '<answer>Simulated reporting response.</answer>'
                            return 'T_call(semantic_segmentation,"bound-by-executor.png",["building"])'
                        fake={'status':'success','masks':{'building':server.image_b64(truth)},
                              'model':{'checkpoint_sha256':'SIMULATED-EXACT-FIXTURE'}}
                        started=time.perf_counter()
                        with patch.object(WorkbenchAgent,'_run_llm',model_response),patch.object(server,'post_json',return_value=fake):
                            result=server.run_task(session,{'query':'Extract non-buildings.' if invert else 'Extract buildings.',
                                                           'mode':'live','scope':side,'roi':roi})
                        accepted=[]
                        for y in range(height):
                            for x in range(width):
                                in_scope=(side=='all' or side=='left' and x<width//2 or side=='right' and x>=width//2
                                          or side=='top' and y<height//2 or side=='bottom' and y>=height//2)
                                in_roi=not use_roi or (roi_box[0]<=x<roi_box[2] and roi_box[1]<=y<roi_box[3])
                                accepted.append(int(bool(bits[y*width+x]) != invert and in_scope and in_roi))
                        expected_area=sum(accepted)
                        if 'metrics' not in result:
                            raise RuntimeError(f'{width}x{height} {side} invert={invert} roi={use_roi}: {result["status"]}: {result["message"]}')
                        saved=Image.open(server.DATA/sid/result['id']/'mask.png')
                        actual=[int(v>0) for v in saved.getdata()]
                        report=verify_bundle(build_bundle(server.DATA/sid/'original.png',server.DATA/sid/result['id']))
                        record={'case_id':f'{width}x{height}-{side}-invert{int(invert)}-roi{int(use_roi)}',
                                'width':width,'height':height,'scope':side,'invert':invert,'roi':use_roi,
                                'expected_pixels':expected_area,'observed_pixels':result['metrics']['pixel_area'],
                                'exact_mask_match':actual==accepted,'offline_verification':report['verified'],
                                'status_correct':result['status']==('completed' if expected_area else 'needs_review'),
                                'wall_ms':round((time.perf_counter()-started)*1000,3),
                                'evidence_kind':'synthetic mask; planner and segmentation transport simulated'}
                        records.append(record)
        server.SESSIONS.clear()
    with (output/'integrity_matrix.csv').open('w',encoding='utf-8',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(records[0]))
        writer.writeheader();writer.writerows(records)
    correct=sum(r['exact_mask_match'] and r['offline_verification'] and r['status_correct'] for r in records)
    summary={'protocol':'integrity-matrix-v1','seed':20261004,'cases':len(records),'passed':correct,
             'software_version':VERSION,'real_model_inference':False,'model_semantic_accuracy_measured':False,
             'measurement_scope':'binary mask postprocessing, persisted pixel metrics and offline export verification',
             'platform':sys.platform,'python':sys.version.split()[0],
             'failure_cases':[r['case_id'] for r in records if not(r['exact_mask_match'] and r['offline_verification'] and r['status_correct'])]}
    (output/'integrity_summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2))
    if correct != len(records):
        raise SystemExit(1)


if __name__=='__main__':
    run_matrix()
