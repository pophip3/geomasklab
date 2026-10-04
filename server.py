"""GeoScope prototype: traceable sessions, real geometry, explicit demo/live modes."""
from __future__ import annotations
import base64
import csv
import hashlib
import io
import json
import os
import re
import threading
import time
import uuid
import zipfile
from collections import deque
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from PIL import Image, ImageDraw, ImageOps
from runtime_config import load_settings, settings_status
from service_transport import request_json, inspect_services
from agent_bridge import AgentTurn, Clarification, decision_record, resolve_scope, segmentation_plan
from v07_contract import batch_requested, has_target_intent, resolve_quality, resolve_roi, target_intent, validate_target_intent

load_settings()

ROOT = Path(__file__).resolve().parent
WEB = ROOT / 'web'
DATA = ROOT / 'experiments'
DATA.mkdir(exist_ok=True)
SESSIONS = {}
BATCHES = {}
LOCK = threading.RLock()
SID_RE = re.compile(r'^[a-f0-9]{12}$')
SIDES = {'all': '全图', 'left': '左半幅', 'right': '右半幅', 'top': '上半幅', 'bottom': '下半幅'}
TARGETS = {'building': '建筑', 'aircraft': '飞机', 'road': '道路', 'water': '水体', 'tree': '植被', 'ship': '船舶'}
DESCRIPTIONS = {'building':'all buildings','aircraft':'all planes','road':'all roads','water':'water bodies','tree':'trees and vegetation','ship':'all ships'}
SAMPLES = {
 'urban': {'name': '合成街区流程样例', 'file': 'urban.png', 'target': 'building', 'size': [800,600],
  'source': 'GeoScope fixtures.py 程序生成的合成街区；仅演示像素运算，不是遥感观测或模型预测。',
  'scene': '这是一幅包含建筑、道路和集中绿地的合成街区流程图。可以提取建筑区域，比较影像两侧的覆盖占比。此说明为样例预置文本，并非模型看图结果。'},
 'airport': {'name': '合成飞机流程样例', 'file': 'airport.jpg', 'target': 'aircraft', 'size': [800,800],
  'source': 'GeoScope fixtures.py 程序生成的合成飞机图形；仅演示像素运算，不是遥感观测或模型预测。',
  'scene': '这幅合成流程图包含两个飞机形状。可以提取左侧或右侧飞机并计算像素覆盖。此说明为样例预置文本，并非模型看图结果。'},
}

def uid(): return uuid.uuid4().hex[:12]
def now(): return datetime.now(timezone.utc).isoformat()
def save_json(path, value):
    temporary=path.with_name(path.name+'.'+uid()+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    os.replace(temporary,path)
def image_b64(image):
    b=io.BytesIO(); image.save(b,format='PNG'); return base64.b64encode(b.getvalue()).decode()

def demo_mask(sample):
    """Exact procedural fixture mask; not an EO model prediction."""
    from fixtures import fixture
    return fixture(sample)[1]

def constrain(mask, side, roi=None):
    w,h=mask.size; region=Image.new('L',(w,h),0)
    boxes={'all':(0,0,w,h),'left':(0,0,w//2,h),'right':(w//2,0,w,h),'top':(0,0,w,h//2),'bottom':(0,h//2,w,h)}
    box=boxes[side]; region.paste(mask.crop(box),box[:2])
    if roi:
        x1,y1,x2,y2=roi['xyxy']
        clipped=Image.new('L',(w,h),0)
        clipped.paste(region.crop((x1,y1,x2,y2)),(x1,y1))
        return clipped
    return region

def foreground_area(mask):
    return sum(mask.histogram()[1:])

def statistics(mask,side,roi=None,full_mask=None):
    w,h=mask.size; area=sum(mask.histogram()[1:]); bbox=mask.getbbox()
    full=full_mask if full_mask is not None else mask
    left=foreground_area(full.crop((0,0,w//2,h)))
    right=foreground_area(full.crop((w//2,0,w,h)))
    distribution={'basis':'full_mask_before_scope','left_pixels':left,'right_pixels':right}
    if roi:
        distribution['roi_inside_pixels']=area
        distribution['roi_outside_pixels']=left+right-area
    return {'pixel_area':area,'total_pixels':w*h,'area_ratio':area/(w*h),'bbox_xyxy':list(bbox) if bbox else None,
            'width':w,'height':h,'scope':side,'scope_label':SIDES[side], 'unit':'pixel',
            'spatial_rule':'像素范围裁切；面积比例的分母始终为整幅影像',
            'spatial_check':mask.tobytes()==constrain(mask,side,roi).tobytes(),
            'roi':roi,'candidate_stats':candidate_statistics(mask),'distribution':distribution,'ground_area_available':False}

def candidate_statistics(mask, min_area_pixels=1):
    """Eight-connected candidate regions on the final, spatially constrained mask."""
    w,h=mask.size
    pixels=mask.tobytes()
    seen=bytearray(len(pixels))
    candidates=[]
    raw_count=0
    for seed,value in enumerate(pixels):
        if not value or seen[seed]: continue
        raw_count+=1
        seen[seed]=1
        queue=deque([seed])
        area=0; sx=sy=0; left=w; top=h; right=bottom=0
        while queue:
            index=queue.popleft(); y,x=divmod(index,w)
            area+=1; sx+=x; sy+=y
            left=min(left,x); top=min(top,y); right=max(right,x+1); bottom=max(bottom,y+1)
            for ny in range(max(0,y-1),min(h,y+2)):
                row=ny*w
                for nx in range(max(0,x-1),min(w,x+2)):
                    neighbor=row+nx
                    if pixels[neighbor] and not seen[neighbor]:
                        seen[neighbor]=1; queue.append(neighbor)
        if area>=min_area_pixels:
            candidates.append({'candidate_id':len(candidates)+1,'area_pixels':area,
                               'bbox':{'x':left,'y':top,'width':right-left,'height':bottom-top},
                               'center':{'x':round(sx/area,3),'y':round(sy/area,3)}})
    areas=[item['area_pixels'] for item in candidates]
    return {'label':'candidate_regions','connectivity':8,'min_area_pixels':min_area_pixels,
            'raw_candidate_count':raw_count,'candidate_count':len(candidates),
            'filtered_out_count':raw_count-len(candidates),'total_area_pixels':sum(areas),
            'min_area':min(areas,default=0),'max_area':max(areas,default=0),
            'mean_area':round(sum(areas)/len(areas),3) if areas else 0.0,
            'candidates':candidates,
            'notice':'语义蒙版的连通区域只是候选目标，数量和边界需人工复核。'}

def experiment_report(session, result):
    """Build a readable report strictly from persisted, deterministic run fields."""
    metrics=result['metrics']; task=result['task']; candidates=metrics['candidate_stats']
    options=result.get('task_options',{})
    service=result.get('service_metadata') or {}
    decision=result.get('agent_decision') or {}
    call=decision.get('tool_call') or {}
    roi=options.get('roi')
    quality=options.get('effective_quality_mode') or '服务未确认'
    lines=[f'# GeoScope 实验报告：{session["name"]}', '',
           f'- 实验编号：{result["id"]}',f'- 运行状态：{result["status"]}（语义与边界仍需人工复核）',
           f'- 输入影像：{session["width"]} × {session["height"]} 像素',
           f'- 数据来源：{session["source"]}',f'- 用户任务：{result["query"]}',
           f'- 运行来源：{"程序生成的合成样例及确定性掩膜，非模型预测" if result["mode"]=="demo" else "真实模型服务返回"}',
           f'- 规划器：{result["provenance"]["planner"]}',
           f'- 感知工具：{result["provenance"]["perception"]}',
           f'- 目标：{TARGETS.get(task["target"],task["target"])}',
           f'- 范围：{SIDES[task["side"]]}'+(f'；矩形 ROI {roi["xyxy"]}' if roi else ''),
           f'- 请求模式：{options.get("quality_mode", "未记录")}',
           f'- 服务确认的执行模式：{quality}',
           f'- 受限工具调用：{call.get("name", "演示流程，未调用模型工具")}',
           f'- Harness 校验：目标、影像、ROI、模式、二值蒙版尺寸与范围由程序检查',
           f'- RemoteSAM 提示词：{DESCRIPTIONS[task["target"]]}',
           f'- 服务版本：{service.get("service_version", "未记录")}',
           f'- 模式参数：{json.dumps(service.get("mode_parameters", {}),ensure_ascii=False,sort_keys=True)}',
           f'- 服务耗时：{json.dumps(service.get("timing_ms", {}),ensure_ascii=False,sort_keys=True)}',
           f'- 推理与统计总耗时：{result["duration_ms"]} ms',
           '', '## 定量结果', '',
           f'- 前景面积：{metrics["pixel_area"]:,} 像素',
           f'- 整图面积：{metrics["total_pixels"]:,} 像素',
           f'- 面积占比：{metrics["area_ratio"]*100:.2f}%',
           f'- 候选连通区域：{candidates["candidate_count"]} 个；仅供人工复核，不等同准确实例数',
           f'- 连通方式：{candidates["connectivity"]}；最小候选面积阈值：{candidates["min_area_pixels"]} 像素',
           f'- 过滤前/后候选数：{candidates["raw_candidate_count"]} / {candidates["candidate_count"]}',
           f'- 候选区域平均面积：{candidates["mean_area"]} 像素',
           f'- 完整蒙版左/右半幅前景：{metrics["distribution"]["left_pixels"]:,} / {metrics["distribution"]["right_pixels"]:,} 像素',
           *(([f'- 完整蒙版 ROI 内/外前景：{metrics["distribution"]["roi_inside_pixels"]:,} / {metrics["distribution"]["roi_outside_pixels"]:,} 像素'] if roi else [])),
           '', '## 复核与复现', '',
           f'- 影像 SHA-256：{result["provenance"]["image_sha256"]}',
           f'- 感知版本：{result["provenance"].get("perception_revision","未记录")}',
           f'- mask 与原图对齐：{metrics["width"]==session["width"] and metrics["height"]==session["height"]}',
           f'- 空间范围检查：{metrics["spatial_check"]}',
           '- 同包附件：original.png、full_mask.png、mask.png、overlay.png、statistics.json、result.json、run_log.json、manifest.json。',
           '- 离线复核：python export_bundle.py 实验包.zip；复算范围、反选、像素面积和整图覆盖率。',
           '- 当前统计基于像素，不代表平方米、公顷或地理坐标。',
           '- 模型语义准确性和候选边界需要人工核查。', '']
    return '\n'.join(lines)

def batch_csv(batch):
    output=io.StringIO(newline='')
    writer=csv.writer(output)
    writer.writerow(['session_id','run_id','status','pixel_area','area_ratio','candidate_count','duration_ms','failure_reason'])
    for item in batch['items']:
        metrics=item.get('metrics') or {}
        writer.writerow([item['session_id'],item.get('run_id'),item['status'],metrics.get('pixel_area'),
                         metrics.get('area_ratio'),(metrics.get('candidate_stats') or {}).get('candidate_count'),
                         item.get('duration_ms'),item.get('failure_reason')])
    return '\ufeff'+output.getvalue()

def parse_task(query,context):
    q=query.strip().lower()
    if re.search(r'靠近|附近|之间|东侧|西侧|平方米|公顷|米以内',q):
        return {'action':'clarify','question':'当前只支持影像坐标中的左右、上下范围和像素占比。请改用这类条件；真实距离或地理面积需要额外的空间参考数据。'}
    if re.search(r'那个|那片|那块|这块',q) and not re.search(r'建筑|飞机|左|右|上|下',q):
        return {'action':'clarify','question':'请确认要处理的目标和范围。你是指当前目标，还是影像中的其他区域？'}
    if re.search(r'场景|什么地方|介绍.*影像|什么类型',q): return {'action':'scene'}
    if re.search(r'导出|下载',q): return {'action':'export'}
    target=None
    for key,pattern in [('building',r'建筑|房屋|楼|building'),('aircraft',r'飞机|aircraft|airplane'),('road',r'道路|公路|road'),('water',r'水体|河流|water'),('tree',r'植被|树木|tree'),('ship',r'船|ship')]:
        if re.search(pattern,q): target=key; break
    side=None
    for key,pattern in [('left',r'左|left'),('right',r'右|right'),('top',r'上半|上方|top'),('bottom',r'下半|下方|bottom'),('all',r'全图|全部|整幅.*提取|all')]:
        if re.search(pattern,q): side=key; break
    inherited=target is None
    target=target or context.get('target')
    if not target or not re.search(r'提取|分割|建筑|飞机|改|换|占比|面积|统计|左|右|上半|下半|全部|全图|框选|选区|研究区|模式|快一点|小目标|整批|批量|segment|building|aircraft',q):
        return {'action':'clarify','question':'请说明想提取什么目标，以及要分析全图还是某一侧。例如：提取右侧建筑并计算面积占比。'}
    return {'action':'segment','target':target,'side':side or context.get('side','all'),
            'invert':resolve_invert(query,context),'inherited_target':inherited,
            'reuse':bool(re.search(r'统计|占比|面积',q) and not re.search(r'提取|分割|改|换',q) and side is None and context.get('target')==target)}

def requires_dense_result(query, context=None):
    q=query.lower()
    if re.search(r'提取|分割|标注|标记|圈出|勾勒|蒙版|掩膜|面积|占比|像素|\b(segment|segmentation|mask|extract|annotate)\b',q):
        return True
    # A short follow-up such as "改成左侧" inherits the selected segmentation
    # result. Without a selected target the same wording remains ordinary VQA.
    return bool((context or {}).get('target') and
                re.search(r'改|换|左|右|上半|下半|全部|全图|重新|重跑|统计|框选|选区|研究区|模式|快一点|小目标|整批|批量',q))

def resolve_invert(query, context=None):
    q=query.lower()
    explicit=bool(re.search(
        r'非\s*(?:建筑|房屋|楼|飞机|道路|公路|水体|河流|植被|树木|船舶?|building|aircraft|airplane|road|water|tree|ship)'
        r'|(?:建筑|房屋|楼|飞机|道路|公路|水体|河流|植被|树木|船舶?|building|aircraft|airplane|road|water|tree|ship)\s*(?:之外|以外)',q))
    positive=bool(re.search(r'只要|仅要|仅标注|只标注|只提取',q))
    if explicit:
        return True
    if positive:
        return False
    return bool((context or {}).get('invert'))

def post_json(url,payload,timeout=120,headers=None):
    return request_json(url,payload,timeout,headers)

def public_session(s):
    return {k:v for k,v in s.items() if k not in ('lock',)}

def get_session(sid):
    if not isinstance(sid,str) or not SID_RE.fullmatch(sid): return None
    with LOCK:
        if sid in SESSIONS: return SESSIONS[sid]
        folder=DATA/sid
        try:
            s=json.loads((folder/'session.json').read_text(encoding='utf-8'))
            if s.get('id')!=sid or not (folder/'original.png').is_file(): return None
            if not isinstance(s.get('runs'),list) or not isinstance(s.get('context'),dict): return None
            if any(not isinstance(s.get(k),str) for k in ('name','created_at','image_url','source')): return None
            if any(type(s.get(k)) is not int or s[k]<=0 for k in ('width','height')): return None
            for r in s['runs']:
                if not SID_RE.fullmatch(r.get('id','')) or r.get('session_id')!=sid: return None
            s['lock']=threading.Lock(); SESSIONS[sid]=s; return s
        except (OSError,ValueError,TypeError,AttributeError): return None

def session_index():
    items=[]
    for folder in DATA.iterdir():
        if not folder.is_dir() or not SID_RE.fullmatch(folder.name): continue
        s=get_session(folder.name)
        if s:
            items.append({k:s[k] for k in ('id','name','created_at','width','height')})
            items[-1]['run_count']=len(s['runs'])
    return sorted(items,key=lambda item:item['created_at'],reverse=True)[:100]

def binary_mask(mask):
    mask=mask.convert('L'); values={i for i,count in enumerate(mask.histogram()) if count}
    if values.issubset({0,1}): return mask.point(lambda value:255 if value else 0)
    if values.issubset({0,255}): return mask
    raise ValueError('RemoteSAM须返回0/1或0/255二值蒙版，不能把概率图或多类标签直接计算为目标面积')

def mask_cache_key(s,mode,target,service_request=None):
    revision='synthetic-fixtures-v1' if mode=='demo' else os.environ.get('GEO_REMOTESAM_REVISION','')
    if not revision: return None  # Unknown live model revision cannot be safely reused.
    value={'image':hashlib.sha256((DATA/s['id']/'original.png').read_bytes()).hexdigest(),
           'mode':mode,'target':target,'prompt':DESCRIPTIONS[target],'revision':revision,
           'endpoint':os.environ.get('GEO_REMOTESAM_URL','') if mode=='live' else '',
           'service_request':service_request}
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()

def new_session(sample='urban',uploaded=None,name=None):
    sid=uid(); folder=DATA/sid; folder.mkdir()
    if uploaded is None:
        if sample not in SAMPLES: raise ValueError('未知样例')
        image=Image.open(WEB/'assets'/SAMPLES[sample]['file']).convert('RGB')
    else:
        raw=base64.b64decode(uploaded.split(',')[-1],validate=True)
        if len(raw)>12*1024*1024: raise ValueError('影像不能超过12MB')
        image=Image.open(io.BytesIO(raw))
        if image.width*image.height>16_000_000: raise ValueError('首版支持不超过1600万像素的影像')
        image=ImageOps.exif_transpose(image).convert('RGB'); sample=None
    image.save(folder/'original.png')
    s={'id':sid,'sample':sample,'name':(name or (SAMPLES[sample]['name'] if sample else '上传影像'))[:120], 'width':image.width,'height':image.height,
       'image_url':f'/experiments/{sid}/original.png','created_at':now(),'runs':[], 'context':{},
       'source':SAMPLES[sample]['source'] if sample else '用户上传影像', 'lock':threading.Lock()}
    with LOCK: SESSIONS[sid]=s
    save_json(folder/'session.json',public_session(s)); return public_session(s)

def run_task(s,p,allow_batch=False):
    if p.get('batch_id') and not allow_batch:
        raise ValueError('batch_id 只能由 Harness 批量任务生成')
    if not s['lock'].acquire(blocking=False): raise ValueError('当前实验仍在执行，请稍后再试')
    try: return _run_task(s,p,allow_batch=allow_batch)
    finally: s['lock'].release()

def run_batch(p, progress=None, batch_id=None):
    ids=p.get('session_ids')
    if (not isinstance(ids,list) or not 2<=len(ids)<=5 or
        any(not isinstance(sid,str) or not SID_RE.fullmatch(sid) for sid in ids) or
        len(set(ids))!=len(ids)):
        raise ValueError('批量任务需要 2 至 5 个不重复的 session_ids')
    sessions=[get_session(sid) for sid in ids]
    if any(s is None for s in sessions):
        raise ValueError('批量任务包含不存在的影像')
    query=p.get('query')
    if not isinstance(query,str) or not query.strip() or len(query)>1800:
        raise ValueError('请填写不超过1800字的批量任务')
    if p.get('mode','live') not in ('demo','live'):
        raise ValueError('未知模式')
    if p.get('quality_mode') is not None and (not isinstance(p['quality_mode'],str) or p['quality_mode'] not in ('fast','accurate','auto')):
        raise ValueError('非法 quality_mode')
    batch_quality,batch_effective_quality,_=resolve_quality(query,{},p.get('quality_mode'))
    if not has_target_intent(query):
        inherited={s['context'].get('target') for s in sessions}
        if len(inherited)!=1 or None in inherited:
            raise Clarification('批量任务缺少所有影像共同的目标类别')
    batch_id=batch_id or uid()
    results=[]
    for index,s in enumerate(sessions,1):
        item_id=uid()
        item={key:p[key] for key in ('query','mode','quality_mode','roi','scope','force_perception') if key in p}
        item['quality_mode']=batch_quality
        item.update(batch_id=batch_id,item_id=item_id)
        try:
            result=run_task(s,item,allow_batch=True)
            results.append({'item_id':item_id,'session_id':s['id'],'run_id':result['id'],
                            'status':result['status'],'failure_reason':result.get('message') if result['status'] in ('failed','needs_clarification') else None,
                            'metrics':result.get('metrics'),'duration_ms':result['duration_ms']})
        except Exception as exc:
            results.append({'item_id':item_id,'session_id':s['id'],'run_id':None,'status':'failed',
                            'failure_reason':str(exc) if isinstance(exc,ValueError) else type(exc).__name__,
                            'metrics':None,'duration_ms':None})
        if progress:
            progress({'batch_id':batch_id,'status':'running','total_count':len(sessions),
                      'completed_items':len(results),'items':list(results)})
    batch={'batch_id':batch_id,'query':query,'mode':p.get('mode','live'),
           'quality_mode':batch_quality,'effective_quality_mode':batch_effective_quality,'created_at':now(),
           'items':results,'total_count':len(sessions),'completed_count':sum(r['status'] in ('completed','needs_review') for r in results),
           'failed_count':sum(r['status'] in ('failed','needs_clarification') for r in results)}
    folder=DATA/'batches'; folder.mkdir(exist_ok=True)
    save_json(folder/f'{batch_id}.json',batch)
    (folder/f'{batch_id}.csv').write_text(batch_csv(batch),encoding='utf-8')
    return batch

def start_batch(p):
    batch_id=uid()
    with LOCK:
        BATCHES[batch_id]={'batch_id':batch_id,'status':'running','total_count':len(p.get('session_ids',[])) if isinstance(p.get('session_ids'),list) else 0,
                           'completed_items':0,'items':[]}
    def progress(update):
        with LOCK: BATCHES[batch_id]=update
    def worker():
        try:
            result=run_batch(p,progress=progress,batch_id=batch_id)
            with LOCK: BATCHES[batch_id]={**result,'status':'completed','completed_items':len(result['items'])}
        except Exception as exc:
            with LOCK: BATCHES[batch_id]={'batch_id':batch_id,'status':'failed','error':str(exc) if isinstance(exc,ValueError) else type(exc).__name__,
                                         'total_count':BATCHES[batch_id]['total_count'],'completed_items':0,'items':[]}
    threading.Thread(target=worker,daemon=True,name=f'geoscope-batch-{batch_id}').start()
    return BATCHES[batch_id]

def _run_task(s,p,allow_batch=False):
    query=str(p.get('query','')).strip()
    if not query or len(query)>1800: raise ValueError('请填写不超过1800字的任务')
    mode=p.get('mode','demo')
    if mode not in ('demo','live'): raise ValueError('未知模式')
    previous=next((r for r in s['runs'] if r['id']==p.get('parent_run_id')),None)
    if p.get('parent_run_id') and previous is None: raise ValueError('结果版本不属于当前影像')
    context=previous.get('task',{}) if previous else s['context']
    start=time.perf_counter(); trace=[]; runid=uid(); folder=DATA/s['id']/runid; folder.mkdir()
    def event(name,detail,state='completed',elapsed=0): trace.append({'step':len(trace)+1,'name':name,'detail':detail,'state':state,'duration_ms':round(elapsed,2),'at':now()})
    result={'id':runid,'session_id':s['id'],'parent_run_id':previous['id'] if previous else None,
            'version':len(s['runs'])+1,'query':query,'mode':mode,'created_at':now(),'status':'failed','trace':trace,
            'provenance':{'planner':'演示规则解析器' if mode=='demo' else os.environ.get('GEO_AGENT_MODEL','未配置'),
                          'perception':'fixtures.py 程序生成的确定性合成掩膜，非遥感观测、非模型预测' if mode=='demo' else 'RemoteSAM服务',
                          'source':s['source'],'image_sha256':hashlib.sha256((DATA/s['id']/'original.png').read_bytes()).hexdigest()}}
    image_path=DATA/s['id']/'original.png'
    image=Image.open(image_path).convert('RGB')
    agent_turn=None
    def feedback(payload):
        if agent_turn is None or agent_turn.decision.status!='tool_call': return
        result['tool_feedback']=payload
        try:
            answer=agent_turn.feedback(payload)
            result['agent_feedback']=decision_record(answer)
            if answer.status!='completed':
                result['feedback_warning']='模型未返回最终回答；未执行额外工具调用，当前产物及统计保留。'
            event('反馈执行结果给 RemoteAgent',
                  '已回传确定性结果；模型原文保留在记录中，页面统计不由模型改写。' if answer.status=='completed' else result['feedback_warning'],
                  'completed' if answer.status=='completed' else 'warning')
        except Exception as exc:
            result['feedback_warning']='模型结果反馈失败，已完成的工具产物与统计仍然保留。'
            result['agent_feedback']={'status':'transport_failed','error_type':type(exc).__name__}
            event('模型结果反馈未完成',result['feedback_warning'],'warning')
    try:
        event('读取实验上下文',f'影像 {s["width"]} × {s["height"]}；'+('继承所选结果条件' if context else '新建任务'))
        try: validate_target_intent(query)
        except ValueError as exc: raise Clarification(str(exc)) from exc
        if batch_requested(query) and not has_target_intent(query) and not context.get('target'):
            raise Clarification('批量任务缺少明确目标类别，请指定目标或从已有目标结果继续。')
        roi,roi_source=resolve_roi(query,context,p.get('roi'),s['width'],s['height'])
        quality_mode,effective_quality,quality_source=resolve_quality(query,context,p.get('quality_mode'))
        if roi and p.get('scope') not in (None,'all'):
            raise ValueError('矩形 ROI 与半幅范围不能同时选择')
        if batch_requested(query) and not allow_batch:
            raise Clarification('批量任务需要通过 /api/batch 指定 2 至 5 幅已绑定影像。')
        result['task_options']={'roi':roi,'roi_source':roi_source,'quality_mode':quality_mode,
                                'effective_quality_mode':effective_quality,'quality_source':quality_source,
                                'batch_id':p.get('batch_id'),'item_id':p.get('item_id')}
        if p.get('simulate_failure'):
            event('注入演示故障','用户主动触发的工具不可用测试','failed')
            raise ValueError('故障演示：工具未返回结果。已有版本保留，本次不生成蒙版或统计。')
        t=time.perf_counter()
        if mode=='demo':
            plan=parse_task(query,context)
            if plan.get('action')=='segment':
                demo_side,demo_scope_source=resolve_scope(query,context,p.get('scope'))
                if roi and demo_side!='all':
                    raise ValueError('矩形 ROI 与半幅范围不能同时选择；请清除矩形或改为全图条件。')
                plan.update(side=demo_side,scope_source=demo_scope_source)
        elif re.fullmatch(r'(?:请)?(?:导出|下载)(?:刚才的|当前|这个|所选)?(?:实验包|结果)?[。！! ]*',query):
            plan={'action':'export','planner_protocol':'harness_export_command'}
        else:
            dense_task=requires_dense_result(query,context)
            if dense_task and not has_target_intent(query) and not context.get('target'):
                raise Clarification('请明确要提取的单一目标类别；当前不能提取所有物体的轮廓。')
            invert=resolve_invert(query,context) if dense_task else False
            side,scope_source=resolve_scope(query,context,p.get('scope'))
            if roi and side!='all':
                raise ValueError('矩形 ROI 与半幅范围不能同时选择；请清除矩形或改为全图条件。')
            if re.search(r'那个|那片|那块|这块',query):
                raise Clarification('请明确目标类别与像素范围，或从已有结果版本继续；本次没有执行分割。')
            agent_turn=AgentTurn(query,image_path,context,side,scope_source,
                                 task_route='dense' if dense_task else 'internal',invert=invert,
                                 roi=roi,quality_mode=quality_mode,batch_id=p.get('batch_id'))
            decision=agent_turn.decision
            result['agent_decision']=decision_record(decision)
            result['provenance']['planner_protocol']='remoteagent'
            if decision.status=='completed':
                if dense_task:
                    raise ValueError('这是需要生成像素结果的任务，但 RemoteAgent 只返回了文字回答；未调用工具，也未生成统计。')
                plan={'action':'scene','answer':decision.text,'planner_protocol':'remoteagent'}
            elif decision.status=='tool_call':
                if not dense_task:
                    raise ValueError('这是看图问答任务，RemoteAgent 不应调用像素分割工具；系统已阻止错误执行。')
                plan=segmentation_plan(decision,image_path,side,scope_source,invert=invert,
                                       expected_target=target_intent(query) or context.get('target'))
                event('确认执行边界',f'目标由 Agent 工具参数提供；范围 {SIDES[side]}，来源 {scope_source}；先全图分割再裁切')
            else:
                raise ValueError(f'RemoteAgent 决策未通过校验（{decision.status}），未执行工具。')
        event('理解任务与选择路径',f'{result["provenance"]["planner"]} · {plan["action"]}',elapsed=(time.perf_counter()-t)*1000)
        if plan['action']=='segment':
            plan.update(roi=roi,roi_source=roi_source,quality_mode=quality_mode,
                        effective_quality_mode=effective_quality,quality_source=quality_source,
                        batch_id=p.get('batch_id'),item_id=p.get('item_id'))
            if mode=='live':
                plan['service_request']['quality_mode']=effective_quality
        result['task']=plan
        if plan['action']=='clarify':
            result.update(status='needs_clarification',message=plan['question']); event('等待条件确认','需求尚未执行','waiting')
        elif plan['action']=='scene':
            if mode=='demo' and not s['sample']: raise ValueError('演示模式无法理解新上传影像。请连接认知核心后切换模型模式。')
            result.update(status='answered',message=plan.get('answer') if mode=='live' else SAMPLES[s['sample']]['scene'])
            event('返回场景说明','此路径未调用分割工具')
        elif plan['action']=='export':
            candidate=previous if previous and previous.get('mask_url') else next((r for r in reversed(s['runs']) if r.get('mask_url')),None)
            if not candidate: raise ValueError('还没有可导出的目标结果，请先完成提取')
            result.update(status='export_ready',message='实验包已可下载，包含影像、蒙版、叠加图、统计与运行记录。',export_url=candidate['export_url'])
            event('准备实验包','引用所选或最近有效结果；不重新推理')
        else:
            target,side=plan['target'],plan['side']; t=time.perf_counter()
            cache_key=mask_cache_key(s,mode,target,plan.get('service_request'))
            cached=DATA/s['id']/previous['id']/'full_mask.png' if previous else None
            reusable=bool(cache_key and previous and previous.get('mask_cache_key')==cache_key and cached.is_file()
                          and not p.get('force_perception') and not re.search(r'重新|重跑|不要复用',query))
            if reusable and hashlib.sha256(cached.read_bytes()).hexdigest()!=previous.get('full_mask_sha256'):
                reusable=False
            if reusable:
                mask=Image.open(cached).convert('L'); event('复用完整目标蒙版','复用同影像、目标、提示与模型版本的全图结果，再按当前范围筛选')
                result['provenance']['perception']=previous['provenance']['perception']
                result['reused_from_run_id']=previous['id']
                result['service_metadata']=previous.get('service_metadata',{})
                if result['service_metadata'].get('quality_confirmation')=='legacy_service_unconfirmed':
                    result['task_options']['effective_quality_mode']=None
                    plan['effective_quality_mode']=None
                    plan['quality_confirmation']='legacy_service_unconfirmed'
            elif mode=='demo':
                if not s['sample']: raise ValueError('上传影像没有预置标注。请选择模型模式，或返回内置样例体验流程。')
                if target!=SAMPLES[s['sample']]['target']: raise ValueError(f'这个样例只提供{TARGETS[SAMPLES[s["sample"]]["target"]]}的演示标注，不能据此判断其他类别。')
                mask=demo_mask(s['sample']); event('生成合成样例掩膜','由 fixtures.py 几何规则生成；未调用RemoteSAM',elapsed=(time.perf_counter()-t)*1000)
            else:
                url=os.environ.get('GEO_REMOTESAM_URL','')
                if not url: raise ValueError('RemoteSAM 服务未配置，未执行分割')
                data=post_json(url,{**plan['service_request'],'image':image_b64(image)})
                confirmed_quality=data.get('quality_mode')
                if confirmed_quality!=effective_quality:
                    if confirmed_quality is not None or quality_mode!='auto' or p.get('quality_mode') is not None:
                        raise ValueError('RemoteSAM 未确认所选质量模式，不能将结果标记为该模式')
                    result['task_options']['effective_quality_mode']=None
                    plan['effective_quality_mode']=None
                    plan['quality_confirmation']='legacy_service_unconfirmed'
                encoded=data.get('masks',{}).get(plan['mask_field']) if plan.get('mask_field') else data.get('mask')
                if data.get('status')!='success' or not encoded: raise ValueError('RemoteSAM未返回有效蒙版')
                mask=Image.open(io.BytesIO(base64.b64decode(encoded,validate=True))).convert('L')
                if mask.size!=image.size: raise ValueError('RemoteSAM蒙版尺寸与原图不一致，请检查服务端坐标还原')
                result['service_metadata']={key:data[key] for key in (
                    'model','timing_ms','quality','quality_mode','requested_quality_mode',
                    'parameters','service_version','mode_parameters',
                    'original_size','output_size','peak_vram_mb') if key in data}
                if 'candidate_stats' in data:
                    result['service_metadata']['full_mask_candidate_stats']=data['candidate_stats']
                if confirmed_quality is None:
                    result['service_metadata']['quality_confirmation']='legacy_service_unconfirmed'
                event('RemoteSAM目标提取','真实服务调用；范围由确定性几何工具约束',elapsed=(time.perf_counter()-t)*1000)
            mask=binary_mask(mask)
            if mask.size!=image.size: raise ValueError('完整蒙版尺寸与原图不一致')
            mask.save(folder/'full_mask.png')
            result['mask_cache_key']=cache_key
            result['full_mask_sha256']=hashlib.sha256((folder/'full_mask.png').read_bytes()).hexdigest()
            result['provenance']['perception_revision']='synthetic-fixtures-v1' if mode=='demo' else os.environ.get('GEO_REMOTESAM_REVISION','未记录')
            if plan.get('invert'):
                mask=ImageOps.invert(mask)
            full_mask=mask
            mask=constrain(mask,side,roi)
            metrics=statistics(mask,side,roi,full_mask); event('范围筛选与像素统计',f'{SIDES[side]}；整图分母 {image.width*image.height:,} px')
            overlay=image.copy(); tint=Image.new('RGB',image.size,(69,213,152)); colored=Image.blend(image,tint,.48); overlay.paste(colored,(0,0),mask)
            mask.save(folder/'mask.png'); overlay.save(folder/'overlay.png')
            status='completed' if metrics['pixel_area'] else 'needs_review'
            event('结果检查','尺寸对齐、空间范围、统计与文件有效性已检查；语义精度待复核')
            base=f'/experiments/{s["id"]}/{runid}'
            result.update(status=status,metrics=metrics,mask_url=base+'/mask.png',overlay_url=base+'/overlay.png',export_url=f'/api/export/{s["id"]}/{runid}',
              message=f'已生成{SIDES[side]}{"非" if plan.get("invert") else ""}{TARGETS[target]}区域：{metrics["pixel_area"]:,} px，占整幅影像 {metrics["area_ratio"]*100:.2f}%。'+('这是预置标注的流程演示，尚未进行模型推理。' if mode=='demo' else '请结合叠加图复核目标语义与边界。') if metrics['pixel_area'] else '本次未检出有效区域，需要复核，不能据此断言目标不存在。')
            s['context']={'target':target,'side':side,'invert':bool(plan.get('invert')),
                          'roi':roi,'quality_mode':quality_mode}; save_json(folder/'statistics.json',metrics)
            if mode=='live':
                feedback({'status':'success','tool_name':plan['tool_name'],'metrics':metrics,
                          'scope_rule':plan['scope_rule'],'actual_service_request':plan['service_request'],
                          'artifact_ids':{'session_id':s['id'],'run_id':runid,'mask_url':result['mask_url']},
                          'reused_from_run_id':result.get('reused_from_run_id'),
                          'service_metadata':result.get('service_metadata',{})})
                if result.get('feedback_warning'): result['message']+=' '+result['feedback_warning']
    except Clarification as exc:
        result.update(status='needs_clarification',message=str(exc))
        event('等待条件确认',str(exc),'waiting')
    except Exception as exc:
        result.update(status='failed',message=str(exc) if isinstance(exc,ValueError) else f'服务调用失败（{type(exc).__name__}），请检查模型服务。')
        if not trace or trace[-1]['state']!='failed': event('执行未完成',result['message'],'failed')
        feedback({'status':'error','message':result['message'],'artifacts_created':False})
    result['duration_ms']=round((time.perf_counter()-start)*1000,2)
    if result.get('mask_url'):
        result['report_url']=f'/api/report/{s["id"]}/{runid}'
        (folder/'report.md').write_text(experiment_report(s,result),encoding='utf-8')
    save_json(folder/'result.json',{k:v for k,v in result.items() if k!='trace'}); save_json(folder/'run_log.json',trace)
    s['runs'].append(result); save_json(DATA/s['id']/'session.json',public_session(s)); return result

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw): super().__init__(*a,directory=str(WEB),**kw)
    def json(self,value,status=200):
        raw=json.dumps(value,ensure_ascii=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        path=self.path.split('?')[0]
        if path=='/api/status': return self.json({**settings_status(),'samples':SAMPLES,'version':'0.8.0-research.1'})
        if path=='/api/sessions': return self.json({'sessions':session_index()})
        if path.startswith('/api/batch/'):
            bid=path.rsplit('/',1)[-1]
            if not SID_RE.fullmatch(bid): return self.json({'error':'批次编号无效'},404)
            with LOCK: batch=BATCHES.get(bid)
            if batch is None:
                file=DATA/'batches'/f'{bid}.json'
                if file.is_file(): batch={**json.loads(file.read_text(encoding='utf-8')),'status':'completed'}
            return self.json(batch) if batch else self.json({'error':'批次不存在'},404)
        if path.startswith('/api/batch-export/'):
            bid=path.rsplit('/',1)[-1]
            if not SID_RE.fullmatch(bid): return self.send_error(404)
            file=DATA/'batches'/f'{bid}.csv'
            if not file.is_file(): return self.send_error(404)
            raw=file.read_bytes(); self.send_response(200)
            self.send_header('Content-Type','text/csv; charset=utf-8')
            self.send_header('Content-Disposition',f'attachment; filename="geoscope_batch_{bid}.csv"')
            self.send_header('Content-Length',str(len(raw))); self.end_headers(); return self.wfile.write(raw)
        if path.startswith('/api/session/'):
            sid=path.rsplit('/',1)[-1]; s=get_session(sid)
            return self.json(public_session(s)) if s else self.json({'error':'实验不存在或存储文件不完整'},404)
        if path.startswith('/api/export/'):
            parts=path.split('/'); sid,rid=parts[-2:]
            if len(parts)!=5 or not SID_RE.fullmatch(sid) or not SID_RE.fullmatch(rid): return self.send_error(404)
            folder=DATA/sid/rid
            if not (folder/'mask.png').exists(): return self.send_error(404)
            from export_bundle import build_bundle
            raw=build_bundle(DATA/sid/'original.png',folder); self.send_response(200); self.send_header('Content-Type','application/zip'); self.send_header('Content-Disposition',f'attachment; filename="geoscope_{rid}.zip"'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); return self.wfile.write(raw)
        if path.startswith('/api/report/'):
            parts=path.split('/'); sid,rid=parts[-2:]
            if len(parts)!=5 or not SID_RE.fullmatch(sid) or not SID_RE.fullmatch(rid): return self.send_error(404)
            file=DATA/sid/rid/'report.md'
            if not file.is_file(): return self.send_error(404)
            raw=file.read_bytes(); self.send_response(200)
            self.send_header('Content-Type','text/markdown; charset=utf-8')
            self.send_header('Content-Disposition',f'attachment; filename="geoscope_{rid}_report.md"')
            self.send_header('Content-Length',str(len(raw))); self.end_headers(); return self.wfile.write(raw)
        if path.startswith('/experiments/'):
            parts=path.strip('/').split('/')
            if len(parts) not in (3,4) or not SID_RE.fullmatch(parts[1]) or (len(parts)==4 and not SID_RE.fullmatch(parts[2])) or parts[-1] not in ('original.png','mask.png','overlay.png'): return self.send_error(404)
            file=DATA.joinpath(*parts[1:])
            if not file.is_file(): return self.send_error(404)
            raw=file.read_bytes(); self.send_response(200); self.send_header('Content-Type','image/png'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); return self.wfile.write(raw)
        return super().do_GET()
    def do_POST(self):
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<=0 or length>18*1024*1024: raise ValueError('请求大小不支持')
            p=json.loads(self.rfile.read(length))
            if self.path=='/api/check-services': return self.json(inspect_services())
            if self.path=='/api/session': return self.json(new_session(p.get('sample','urban'),p.get('image'),p.get('name')))
            if self.path=='/api/run':
                s=get_session(p.get('session_id'))
                if not s: raise ValueError('实验不存在，请重新选择影像')
                return self.json(run_task(s,p))
            if self.path=='/api/batch': return self.json(run_batch(p))
            if self.path=='/api/batch/start': return self.json(start_batch(p))
            return self.json({'error':'接口不存在'},404)
        except (ValueError,KeyError,Image.UnidentifiedImageError) as exc: return self.json({'error':str(exc)},400)
        except Exception: return self.json({'error':'无法处理影像或请求，请检查输入格式'},500)

if __name__=='__main__':
    port=int(os.environ.get('GEO_PORT','4180'))
    print(f'GeoScope: http://127.0.0.1:{port}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()
