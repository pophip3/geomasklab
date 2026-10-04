"""Build a frozen, previously unused application set from original human labels.

Raw academic-use datasets stay outside Git. No prediction is inspected here.
"""
import argparse, csv, hashlib, io, json, re, zipfile
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import requests
from PIL import Image
from range_archive import RangeReader

SEED='geoscope-softwarex-application-v2-20261004'
LOVE_URL='https://zenodo.org/records/5706578/files/Val.zip?download=1'
DOTA_ID='1uCCCFhFQOJLfjBpcL5MC0DHJ9lgOaXWP'
def sha(data): return hashlib.sha256(data).hexdigest()
def rank(x): return sha((SEED+'|'+x).encode())
def write_json(path, value): path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def write_csv(path, rows):
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def drive_url():
    import html
    from urllib.parse import urlencode
    with requests.get('https://drive.google.com/uc',params={'export':'download','id':DOTA_ID},stream=True,timeout=30) as r:
        r.raise_for_status()
        if 'text/html' not in r.headers.get('Content-Type',''): return r.url
        page=r.text
    form=re.search(r'<form[^>]+action="([^"]+)"[^>]*>(.*?)</form>',page,re.S)
    if not form: raise ValueError('Official public Drive file lacks download form.')
    fields={k:html.unescape(v) for k,v in re.findall(r'<input[^>]+name="([^"]+)"[^>]+value="([^"]*)"',form.group(2))}
    if fields.get('id')!=DOTA_ID or fields.get('confirm')!='t': raise ValueError('Unexpected public file form.')
    return html.unescape(form.group(1))+'?'+urlencode(fields)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True)
    ap.add_argument('--research-root',type=Path,required=True);ap.add_argument('--competition-manifest',type=Path,required=True)
    ap.add_argument('--isaid-masks',type=Path,required=True);a=ap.parse_args()
    root=a.root;root.mkdir(parents=True,exist_ok=True)
    if (root/'manifest.csv').exists(): raise ValueError('Frozen manifest exists; use it without resampling.')
    for d in ['images','ground_truth','valid_masks','source_labels','downloads']: (root/d).mkdir(exist_ok=True)
    lock=root/'acquisition-plan.json'
    if lock.exists(): plan=json.loads(lock.read_text(encoding='utf-8'))
    else:
        excluded_ids=set();excluded_hashes=set();sources=[]
        for p in sorted([a.competition_manifest,*a.research_root.rglob('*.csv')]):
            content=p.read_text(encoding='utf-8-sig',errors='strict')
            rows=list(csv.DictReader(io.StringIO(content)));headers=set(rows[0]) if rows else set()
            is_execution='manifest' in p.name or any('iou' in k.lower() or 'dice' in k.lower() or k in ['prediction_path','pred_path','prediction_sha256'] for k in headers)
            if p!=a.competition_manifest and not is_execution:continue
            excluded_ids.update(re.findall(r'P\d{4}',content));excluded_hashes.update(re.findall(r'\b[0-9a-fA-F]{64}\b',content))
            sources.append({'file':p.name,'sha256':sha(p.read_bytes())})
        plan={'protocol':'geoscope-application-v2.1','locked_utc':datetime.now(timezone.utc).isoformat(),'seed':SEED,
              'pre_inference_correction':'Exclude frozen selections and actually scored/used images; source archive inventories are not model-execution records. A superseded draft incorrectly excluded all 458 archive IDs. No test prediction had occurred.',
              'datasets':['LoveDA validation','iSAID/DOTA-v1.0 validation'],'targets':{'building':[20,10],'aircraft':[20,10]},
              'ground_truth':'Released human pixel annotations; no self-produced human annotations, no pseudo-labels.',
              'maximum_image_pixels':16000000,'maximum_image_file_bytes':12*1024*1024,
              'positive_minimum_target_pixels':1,'valid_rule':'LoveDA label!=0; iSAID all released pixels for one-vs-rest plane evaluation including unlabeled background.',
              'selection':'Hash-order exact positive/negative quotas from GT only. LoveDA 10 Urban and 10 Rural positives; 10 combined negatives selected first. At most one tile per domain/32-consecutive-ID block. Aircraft one full source P ID per image. No cropping, resizing, score-based selection or replacement.',
              'scene_limitation':'LoveDA numeric blocks are spacing proxies, not verified acquisition scenes; exact location overlap and external pretraining membership remain unknown. iSAID IDs identify source images, not necessarily different airports.',
              'love_url':LOVE_URL,'love_archive_md5_official':'84cae2577468ff0b5386758bb386d31d','dota_drive_id':DOTA_ID,
              'isaid_masks_sha256':sha(a.isaid_masks.read_bytes()),'excluded_aircraft_ids':sorted(excluded_ids),
              'excluded_file_hashes':sorted(x.lower() for x in excluded_hashes),'exclusion_inputs':sources,
              'raw_data_redistribution':False,'predictions_inspected':False}
        write_json(lock,plan)
    assert plan['seed']==SEED and not plan['predictions_inspected']
    love_reader=RangeReader(LOVE_URL,root/'downloads/loveda-ranges')
    candidates=[]
    with zipfile.ZipFile(love_reader) as z:
        infos={e.filename:e for e in z.infolist()}
        write_json(root/'loveda-index.json',[{'name':e.filename,'size':e.file_size,'crc32':f'{e.CRC:08x}','offset':e.header_offset} for e in z.infolist()])
        for name in sorted(infos):
            if '/masks_png/' not in name or not name.endswith('.png'):continue
            image_name=name.replace('/masks_png/','/images_png/')
            if image_name not in infos:continue
            source=z.read(name);label=np.asarray(Image.open(io.BytesIO(source)))
            if label.ndim!=2 or not set(np.unique(label)).issubset(range(8)):raise ValueError('LoveDA label contract')
            domain=name.split('/')[1];stem=Path(name).stem;n=int((label==2).sum()); valid=int((label!=0).sum())
            if label.size>plan['maximum_image_pixels'] or infos[image_name].file_size>plan['maximum_image_file_bytes'] or not valid:continue
            candidates.append({'image_id':f'LOVE_{domain}_{stem}','dataset':'LoveDA validation','target':'building','stratum':'positive' if n else 'negative',
                               'domain':domain,'scene_proxy':f'LOVE_{domain}_block{int(stem)//32}','gt_foreground_pixels':n,'valid_pixels':valid,
                               'width':label.shape[1],'height':label.shape[0],'source_label_member':name,'source_image_member':image_name,'rank':rank(name)})
        write_csv(root/'loveda-candidates.csv',candidates)
        chosen=[];groups=set()
        for stratum,domain,count in [('negative',None,10),('positive','Urban',10),('positive','Rural',10)]:
            eligible=sorted((r for r in candidates if r['stratum']==stratum and (domain is None or r['domain']==domain)),key=lambda r:r['rank']);selected=[]
            for r in eligible:
                if r['scene_proxy'] in groups:continue
                groups.add(r['scene_proxy']);selected.append(r)
                if len(selected)==count:break
            if len(selected)!=count:raise ValueError(f'Insufficient LoveDA {stratum}/{domain} independent blocks: {len(selected)}')
            chosen+=selected
        write_json(root/'loveda-selection-lock.json',chosen)
        for i,r in enumerate(chosen):
            label_bytes=z.read(r['source_label_member']);image_bytes=z.read(r['source_image_member'])
            save_pair(root,r,image_bytes,label_bytes,np.array(Image.open(io.BytesIO(label_bytes)))==2,np.array(Image.open(io.BytesIO(label_bytes)))!=0,plan)
            print('LOVE_PAIRED',i+1,r['image_id'],flush=True)
    aircraft=[]
    with zipfile.ZipFile(a.isaid_masks) as z:
        for name in sorted(z.namelist()):
            m=re.search(r'(P\d{4})_instance_color_RGB\.png$',name)
            if not m or m[1] in plan['excluded_aircraft_ids']:continue
            b=z.read(name);im=Image.open(io.BytesIO(b));rgb=np.array(im.convert('RGB'));mask=np.all(rgb==[0,127,255],axis=2);n=int(mask.sum())
            if mask.size>plan['maximum_image_pixels']:continue
            aircraft.append({'image_id':'ISAID_'+m[1],'dataset':'iSAID/DOTA-v1.0 validation','target':'aircraft','stratum':'positive' if n else 'negative',
                             'domain':'source_image','scene_proxy':m[1],'gt_foreground_pixels':n,'valid_pixels':mask.size,
                             'width':im.width,'height':im.height,'source_label_member':name,'source_image_member':'images/'+m[1]+'.png','rank':rank(m[1])})
        rd=RangeReader(drive_url(),root/'downloads/dota-ranges')
        with zipfile.ZipFile(rd) as dz:
            image_infos={Path(e.filename).stem:e for e in dz.infolist() if e.filename.endswith('.png')}
            aircraft=[r for r in aircraft if r['scene_proxy'] in image_infos and image_infos[r['scene_proxy']].file_size<=plan['maximum_image_file_bytes']]
            write_csv(root/'isaid-candidates.csv',aircraft)
            selected=[]
            for stratum,n in [('positive',20),('negative',10)]:
                rows=sorted((r for r in aircraft if r['stratum']==stratum),key=lambda r:r['rank'])[:n]
                if len(rows)!=n:raise ValueError(f'Insufficient new aircraft {stratum}: {len(rows)}')
                selected+=rows
            write_json(root/'isaid-selection-lock.json',selected)
            for i,r in enumerate(selected):
                label_bytes=z.read(r['source_label_member']);image_bytes=dz.read(image_infos[r['scene_proxy']]);rgb=np.array(Image.open(io.BytesIO(label_bytes)).convert('RGB'))
                save_pair(root,r,image_bytes,label_bytes,np.all(rgb==[0,127,255],axis=2),np.ones(rgb.shape[:2],bool),plan)
                print('ISAID_PAIRED',i+1,r['image_id'],flush=True)
            chosen+=selected
    chosen=sorted(chosen,key=lambda r:rank(r['image_id']))
    write_csv(root/'manifest.csv',chosen)
    write_json(root/'data-lock.json',{'locked_utc':datetime.now(timezone.utc).isoformat(),'images':len(chosen),'manifest_sha256':sha((root/'manifest.csv').read_bytes()),
                                   'acquisition_plan_sha256':sha(lock.read_bytes()),'loveda_range_bytes_this_run':love_reader.network_bytes,'dota_range_bytes_this_run':rd.network_bytes,
                                   'full_archive_md5_verified':False,'zip_entry_crc_verified':True,'original_human_labels_preserved':True})
    print('FROZEN',len(chosen),sha((root/'manifest.csv').read_bytes()),flush=True)

def save_pair(root,r,image_bytes,label_bytes,mask,valid,plan):
    if sha(image_bytes) in plan['excluded_file_hashes']:raise ValueError('Used image hash encountered; do not replace after predictions.')
    im=Image.open(io.BytesIO(image_bytes)).convert('RGB')
    if im.size!=(r['width'],r['height']):raise ValueError('Image/label size mismatch')
    names={'image_path':'images','ground_truth_path':'ground_truth','valid_path':'valid_masks','original_label_path':'source_labels'}
    for key,folder in names.items(): r[key]=folder+'/'+r['image_id']+'.png'
    im.save(root/r['image_path']);Image.fromarray(mask.astype('uint8')*255).save(root/r['ground_truth_path']);Image.fromarray(valid.astype('uint8')*255).save(root/r['valid_path'])
    (root/r['original_label_path']).write_bytes(label_bytes)
    r['source_image_sha256']=sha(image_bytes);r['source_label_sha256']=sha(label_bytes)
    for key in ['image_path','ground_truth_path','valid_path']:r[key.replace('_path','_sha256')]=sha((root/r[key]).read_bytes())
    r['label_author']='Original dataset annotators';r['human_annotation_claim']='Released annotation, not newly annotated by this agent'
    r['license']='LoveDA: CC BY-NC-SA 4.0, academic only' if r['target']=='building' else 'iSAID/DOTA: academic only; original imagery terms apply'

if __name__=='__main__':main()
