"""Recompute summary from immutable request receipts; failures stay visible."""
import argparse,csv,json,statistics
from pathlib import Path
import numpy as np

def interval(rows,key,seed=20261004):
    if len(rows)<2:return None
    values=np.array([r[key] for r in rows],float);rng=np.random.default_rng(seed)
    means=[float(rng.choice(values,len(values),replace=True).mean()) for _ in range(2000)]
    return {'lower':float(np.quantile(means,.025)),'upper':float(np.quantile(means,.975)),
            'unit':'image/source-ID bootstrap; geographic independence is unverified; nominal exploratory interval'}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();root=a.root
    manifest=list(csv.DictReader((root/'manifest.csv').open(encoding='utf-8')));records=[];table=[]
    for row in manifest:
        file=root/'runs'/row['image_id']/'receipt.json'
        outcomes=json.loads(file.read_text(encoding='utf-8'))['outcomes'] if file.exists() else []
        for method in ['fixed_direct','whole','right','roi']:
            e=next((x for x in outcomes if x['method']==method),None)
            record={'image_id':row['image_id'],'target':row['target'],'stratum':row['stratum'],'method':method,
                    'success':bool(e and e.get('success')),'error':e.get('error','') if e else 'not executed',
                    'plan_correct':e.get('plan_correct') if e else None,'export_verified':bool(e and e.get('export_verification',{}).get('verified')),
                    'independent_scope_equal':e.get('independent_scope_equal') if e else None,'matched_full_equal':e.get('matched_full_equal') if e else None,
                    'matched_differing_pixels':e.get('matched_differing_pixels') if e else None,'wall_ms':e.get('wall_ms') if e else None}
            if e and e.get('score'):record.update(e['score'])
            records.append(record)
    summaries=[]
    for target in ['building','aircraft']:
        for method in ['fixed_direct','whole','right','roi']:
            subset=[r for r in records if r['target']==target and r['method']==method]
            success=[r for r in subset if r['success']]
            pos=[r for r in success if r.get('gt_pixels',0)>0]
            neg=[r for r in success if r.get('empty_ground_truth')]
            # Primary utility denominators use whole-image positive stratum (20).
            primary=[r for r in subset if r['stratum']=='positive'] if method in ['fixed_direct','whole'] else []
            tp=sum(r.get('tp',0) for r in success);fp=sum(r.get('fp',0) for r in success);fn=sum(r.get('fn',0) for r in success)
            times=[r['wall_ms'] for r in success if r['wall_ms'] is not None]
            s={'target':target,'method':method,'requested':len(subset),'success':len(success),'failures':len(subset)-len(success),
               'positive_scoped_successes':len(pos),'mean_positive_iou':statistics.mean(r['iou'] for r in pos) if pos else None,
               'mean_positive_dice':statistics.mean(r['dice'] for r in pos) if pos else None,
               'positive_iou_nominal_ci':interval(pos,'iou'),'positive_dice_nominal_ci':interval(pos,'dice'),
               'all_positive_request_iou_utility':sum((r.get('iou') or 0) if r['success'] else 0 for r in primary)/len(primary) if primary else None,
               'all_positive_request_dice_utility':sum((r.get('dice') or 0) if r['success'] else 0 for r in primary)/len(primary) if primary else None,
               'pooled_tp':tp,'pooled_fp':fp,'pooled_fn':fn,'pooled_iou_successful_images':tp/(tp+fp+fn) if tp+fp+fn else None,
               'pooled_dice_successful_images':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,
               'empty_gt_successes':len(neg),'empty_gt_false_positive_images':sum(bool(r['fp']) for r in neg),
               'empty_gt_false_positive_rate':sum(bool(r['fp']) for r in neg)/len(neg) if neg else None,
               'empty_gt_total_false_positive_pixels':sum(r['fp'] for r in neg),
               'empty_gt_mean_false_positive_fraction':statistics.mean(r['fp']/r['valid_pixels'] for r in neg if r['valid_pixels']) if neg else None,
               'median_wall_ms':statistics.median(times) if times else None,
               'wall_ms_q25':float(np.quantile(times,.25)) if times else None,'wall_ms_q75':float(np.quantile(times,.75)) if times else None,
               'exports_verified':sum(r['export_verified'] for r in subset),'independent_scope_equal':sum(r['independent_scope_equal'] is True for r in subset),
               'matched_direct_evaluated':sum(r['matched_full_equal'] is not None for r in subset),'matched_full_equal':sum(r['matched_full_equal'] is True for r in subset)}
            summaries.append(s)
    wb=[r for r in records if r['method']!='fixed_direct'];summary={'planned_images':60,'planned_supported_workbench_requests':180,
            'completed_supported_requests':sum(r['success'] for r in wb),'exports_verified':sum(r['export_verified'] for r in wb),
            'category_and_scope_correct':sum(r['plan_correct'] is True for r in wb),'independent_scope_reconstructions_equal':sum(r['independent_scope_equal'] is True for r in wb),
            'matched_direct_evaluated':sum(r['matched_full_equal'] is not None for r in wb),'matched_full_equal':sum(r['matched_full_equal'] is True for r in wb),
            'summaries':summaries,'scope':'Frozen local academic application set; no test-driven tuning, no generalization or new model superiority claim.'}
    (root/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    with (root/'per_request_metrics.csv').open('w',encoding='utf-8',newline='') as f:
        fields=list(dict.fromkeys(k for r in records for k in r));w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(records)
    print(json.dumps({k:v for k,v in summary.items() if k!='summaries'},ensure_ascii=False))
    for s in summaries:print(s['target'],s['method'],s['success'],s['mean_positive_iou'],s['mean_positive_dice'])
if __name__=='__main__':main()
