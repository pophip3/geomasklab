"""Frozen real-model application evaluation. All outcomes survive interruptions.

The fixed-prompt direct model measures segmentation. Matched direct requests
measure preservation of the planner's actual service request. They are different
comparators when the planner chooses semantic instead of referring segmentation.
"""
import argparse, base64, csv, hashlib, io, json, os, subprocess, sys, time, zipfile
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from PIL import Image
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from workbench.runtime_config import load_settings
from workbench.service_transport import request_json
from workbench.export_bundle import verify_bundle
from segmentation_metrics import score
import urllib.request

PROMPTS={'building':'all buildings','aircraft':'all planes'}
TARGETS={'building':'建筑','aircraft':'飞机'}
def sha(b):return hashlib.sha256(b).hexdigest()
def utc():return datetime.now(timezone.utc).isoformat()
def save(path,obj):
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path)
def csv_save(path,rows):
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def pixels(path):return np.asarray(Image.open(path).convert('L'))>0
def decode_mask(encoded,size):
    b=base64.b64decode(encoded.split(',')[-1],validate=True);im=Image.open(io.BytesIO(b));a=np.asarray(im)
    if im.size!=size or a.ndim!=2 or not set(np.unique(a)).issubset({0,1,255}):raise ValueError('Returned mask dimensions or binary values invalid.')
    return a>0
def direct(payload,size,folder,name):
    started=time.perf_counter();r=request_json(os.environ['GEO_REMOTESAM_URL'],payload,timeout=240)
    save(folder/(name+'-response.json'),r)
    if r.get('status')!='success':raise ValueError('RemoteSAM error: '+str(r.get('message','unknown')))
    if r.get('quality_mode')!='fast':raise ValueError('Unconfirmed fixed quality mode.')
    p=decode_mask(r['mask'],size);Image.fromarray(p.astype('uint8')*255).save(folder/(name+'-mask.png'))
    return p,round((time.perf_counter()-started)*1000,2),r.get('timing_ms',{}),r.get('model',{})
def baseline_protocol(root):
    load_settings()
    rows=list(csv.DictReader((root/'manifest.csv').open(encoding='utf-8')))
    lock=json.loads((root/'data-lock.json').read_text(encoding='utf-8'))
    assert len(rows)==60 and sha((root/'manifest.csv').read_bytes())==lock['manifest_sha256']
    for r in rows:
        for field in ['image','ground_truth','valid']:
            if sha((root/r[field+'_path']).read_bytes())!=r[field+'_sha256']:raise ValueError('Frozen input hash changed.')
    return rows,lock
def workbench_call(path,payload=None):
    base=f'http://127.0.0.1:{os.environ.get("GEO_PORT","4180")}'
    return request_json(base+path,payload,timeout=300)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();root=a.root
    rows,data_lock=baseline_protocol(root);out=root/'runs';out.mkdir(exist_ok=True)
    protocol_path=root/'run-protocol.json'
    if protocol_path.exists():protocol=json.loads(protocol_path.read_text(encoding='utf-8'))
    else:
        ready=workbench_call('/api/check-services',{})
        if not ready['services_ready']:raise ValueError('Models are not ready.')
        sam=request_json(os.environ['GEO_REMOTESAM_URL'].rsplit('/',1)[0]+'/model-info')
        if sam.get('checkpoint_sha256')!='f85dfa044a527f096b9e41eacfe298040d52e77fca642f46dfe1226745e137e7':raise ValueError('Unexpected frozen checkpoint.')
        protocol={'protocol':'geoscope-application-v2.1','locked_utc':utc(),'data_lock':data_lock,'quality_mode':'fast','fixed_prompts':PROMPTS,
                  'scope_tests':['whole','right','roi'],'roi':'[floor(W/4),floor(H/4),floor(3W/4),floor(3H/4)]',
                  'force_perception':True,'threshold':'Service binary masks only; no test-specific threshold adjustment.',
                  'sampling_seed':'geoscope-softwarex-application-v2-20261004','paired_order':'fixed baseline / whole-workbench order by SHA256(image_id)[0] parity; matched direct request follows each workbench call because its actual arguments must be known.',
                  'comparators':'Fixed referring prompt vs workbench as separate application paths. For preservation, replay exactly the planner-selected task/text/classes/quality to the same service; do not call different prompts a matched pair.',
                  'failures':'Retain all 180 planned supported requests. Conditional positive-image IoU/Dice and all-positive-request utility (failure=0) both reported. Empty-GT images reported with FP pixels and image rate; 0/0 not assigned perfect score.',
                  'nondeterminism':'On any exact matched-mask mismatch preserve first observations, obtain two extra direct repetitions, and flag nondeterminism; never replace the initial result.',
                  'software_commit':subprocess.check_output(['git','-c','safe.directory='+str(REPO).replace('\\','/'),'rev-parse','HEAD'],cwd=REPO,text=True).strip(),
                  'evaluator_sha256':{p.name:sha(p.read_bytes()) for p in [Path(__file__),REPO/'evaluation/segmentation_metrics.py',REPO/'workbench/agent_bridge.py',REPO/'workbench/planner_protocol.py',REPO/'workbench/server.py',REPO/'workbench/export_bundle.py']},
                  'python':sys.version,'numpy':np.__version__,'sam_model_info':sam,'agent_model':os.environ['GEO_AGENT_MODEL'],
                  'perception_revision':os.environ.get('GEO_REMOTESAM_REVISION'),
                  'agent_weight_lock':json.loads((root/'remoteagent-weight-lock.json').read_text(encoding='utf-8')) if (root/'remoteagent-weight-lock.json').exists() else {'verified':False,'reason':'weight hashes not supplied'},
                  'warm_start':True,'concurrency':1,'human_label_origin':'Released dataset annotators, not agent-generated annotations.',
                  'geographic_and_pretraining_limitations':'Own observed tuning sets excluded; source-scene location and external model pretraining overlap cannot be guaranteed.'}
        save(protocol_path,protocol)
    if protocol['data_lock']['manifest_sha256']!=data_lock['manifest_sha256']:raise ValueError('Run protocol / data lock mismatch.')
    for fname,digest in protocol['evaluator_sha256'].items():
        p=REPO/'evaluation'/fname if fname in ['run_independent.py','segmentation_metrics.py'] else REPO/fname
        if sha(p.read_bytes())!=digest:raise ValueError('Frozen evaluation source changed: '+fname)
    for index,row in enumerate(rows):
        folder=out/row['image_id'];folder.mkdir(exist_ok=True);receipt=folder/'receipt.json'
        r=json.loads(receipt.read_text(encoding='utf-8')) if receipt.exists() else {'image_id':row['image_id'],'target':row['target'],'stratum':row['stratum'],'outcomes':[]}
        if r.get('finished'):continue
        image=(root/row['image_path']).read_bytes();image_b64=base64.b64encode(image).decode();size=(int(row['width']),int(row['height']))
        gt=pixels(root/row['ground_truth_path']);valid=pixels(root/row['valid_path'])
        if 'session_id' not in r:
            session=workbench_call('/api/session',{'image':image_b64,'name':'Independent application test '+row['image_id']});r['session_id']=session['id'];save(receipt,r)
        methods=['fixed_direct','whole'] if int(sha(row['image_id'].encode())[0],16)%2 else ['whole','fixed_direct']
        methods+=['right','roi']
        for method in methods:
            if any(x['method']==method for x in r['outcomes']):continue
            event={'method':method,'started_utc':utc(),'success':False}
            try:
                if method=='fixed_direct':
                    p,elapsed,timing,model=direct({'task':'referring_seg','text':PROMPTS[row['target']],'image':image_b64,'quality_mode':'fast'},size,folder,method)
                    event.update(success=True,score=score(p,gt,valid),wall_ms=elapsed,service_timing_ms=timing,model=model)
                else:
                    target=TARGETS[row['target']];scope='right' if method=='right' else 'all'
                    query=('提取右半幅' if method=='right' else '提取')+target+'并计算像素覆盖率'
                    payload={'session_id':r['session_id'],'query':query,'mode':'live','scope':scope,'quality_mode':'fast','force_perception':True,'roi':{}}
                    if method=='roi':
                        w,h=size;payload['roi']={'xyxy':[w//4,h//4,3*w//4,3*h//4],'source':'imported','image_size':[w,h]}
                    started=time.perf_counter();result=workbench_call('/api/run',payload);event['wall_ms']=round((time.perf_counter()-started)*1000,2);save(folder/(method+'-result.json'),result)
                    event.update(status=result.get('status'),run_id=result.get('id'),planner_status=result.get('agent_decision',{}).get('status'))
                    if not result.get('mask_url'):raise ValueError('No accepted live mask: '+str(result.get('message','unknown')))
                    task=result['task'];event['plan_correct']=task.get('target')==row['target'] and task.get('side')==scope and not task.get('invert') and task.get('roi')==(payload['roi'] or None)
                    if not event['plan_correct']:raise ValueError('Target or scope mismatches the predeclared request.')
                    url=f'http://127.0.0.1:{os.environ.get("GEO_PORT","4180")}/api/export/{r["session_id"]}/{result["id"]}'
                    exp_start=time.perf_counter()
                    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url,timeout=120) as response:bundle=response.read()
                    (folder/(method+'-evidence.zip')).write_bytes(bundle);verification=verify_bundle(bundle)
                    event['export_verification']=verification;event['export_verify_wall_ms']=round((time.perf_counter()-exp_start)*1000,2)
                    with zipfile.ZipFile(io.BytesIO(bundle)) as z:
                        full=decode_mask(base64.b64encode(z.read('full_mask.png')).decode(),size);p=decode_mask(base64.b64encode(z.read('mask.png')).decode(),size)
                    w,h=size;box={'whole':(0,0,w,h),'right':(w//2,0,w,h),'roi':(w//4,h//4,3*w//4,3*h//4)}[method]
                    x1,y1,x2,y2=box;expected=np.zeros_like(full);expected[y1:y2,x1:x2]=full[y1:y2,x1:x2]
                    event['independent_scope_equal']=bool(np.array_equal(expected,p))
                    if not event['independent_scope_equal']:raise ValueError('Independent NumPy scope reconstruction failed.')
                    event.update(success=True,score=score(p,gt,valid,method),service_metadata=result.get('service_metadata'),duration_ms=result.get('duration_ms'),
                                 trace=result.get('trace'),agent_feedback_status=result.get('agent_feedback',{}).get('status'),full_prediction_sha256=sha(full.tobytes()))
                    service_request=dict(task['service_request']);service_request['image']=image_b64
                    paired,elapsed,timing,model=direct(service_request,size,folder,method+'-matched-direct')
                    event.update(matched_direct_wall_ms=elapsed,matched_direct_service_timing_ms=timing,matched_request={k:v for k,v in service_request.items() if k!='image'},
                                 matched_direct_score=score(paired,gt,valid,method),matched_full_equal=bool(np.array_equal(full,paired)),matched_differing_pixels=int(np.count_nonzero(full!=paired)))
                    if not event['matched_full_equal']:
                        repeats=[]
                        for i in range(2):
                            pm,_,_,_=direct(service_request,size,folder,method+f'-matched-repeat{i+2}')
                            repeats.append({'sha256':sha(pm.tobytes()),'equals_workbench':bool(np.array_equal(full,pm)),'score':score(pm,gt,valid,method)})
                        event['nondeterminism_repeats']=repeats
            except Exception as error:
                event.update(error_type=type(error).__name__,error=str(error))
            event['finished_utc']=utc();r['outcomes'].append(event);save(receipt,r)
            print(json.dumps({'image':index+1,'total':len(rows),'id':row['image_id'],'method':method,'success':event['success'],'iou':event.get('score',{}).get('iou'),'matched':event.get('matched_full_equal'),'error':event.get('error')},ensure_ascii=False),flush=True)
        r['finished']=True;save(receipt,r)
    print('ALL_IMAGES_EXECUTED',len(rows),flush=True)

if __name__=='__main__':main()
