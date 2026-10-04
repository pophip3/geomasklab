"""Run the real workbench executor on tiny procedural data, entirely offline.

No neural inference is claimed. The generated evidence exercises result branches,
ROI arithmetic, self-reported review persistence and portable export verification.
"""
from pathlib import Path
import argparse
import json
import tempfile
import time
from unittest.mock import patch


def run_demo(output):
    started = time.perf_counter()
    import server
    from fixtures import fixture, write_assets
    from export_bundle import build_bundle, verify_bundle
    from product_contract import VERSION
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    records = []
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root/'data').mkdir()
        write_assets(root/'web/assets')
        # Fail loudly if a future demo change accidentally attempts inference.
        with patch.object(server, 'DATA', root/'data'), patch.object(server, 'WEB', root/'web'), \
             patch.object(server, 'SESSIONS', {}), \
             patch.object(server, 'post_json', side_effect=RuntimeError('Offline demo attempted a model call')):
            for sample, jobs in [
                ('urban', [('whole','提取全图建筑',None,75350),
                           ('right','改成右侧建筑',None,37350),
                           ('left_branch','改成左侧建筑',None,38000),
                           ('roi','提取全图框选区域内的建筑',
                            {'xyxy':[80,50,280,250],'source':'drawn','image_size':[800,600]},12850)]),
                ('airport', [('aircraft','提取全图飞机',None,fixture('airport')[1].histogram()[255])])
            ]:
                s = server.SESSIONS[server.new_session(sample)['id']]
                parent = None
                for label, query, roi, expected in jobs:
                    p = {'query':query,'mode':'demo','parent_run_id':parent}
                    if roi: p.update(roi=roi,scope='all')
                    result = server.run_task(s,p)
                    if result.get('metrics',{}).get('pixel_area') != expected:
                        raise ValueError(f'{label}: unexpected result: {result.get("message")}')
                    if parent and result['parent_run_id'] != parent:
                        raise ValueError('Experiment branch identity mismatch')
                    if label == 'right':
                        server.review_result(s,{'run_id':result['id'],'decision':'accepted',
                            'reviewer':'AUTOMATED PROCEDURAL SOFTWARE CHECK',
                            'note':'Software demonstration only: exact fixture area and branch checked; no human EO accuracy judgement.'})
                        server.SESSIONS.clear()
                        s = server.get_session(s['id'])
                        result = next(r for r in s['runs'] if r['id']==result['id'])
                        if result['semantic_review']['state'] != 'accepted':
                            raise ValueError('Review did not survive reload')
                    elif result['semantic_review']['state'] != 'pending':
                        raise ValueError('A new result inherited an earlier review')
                    bundle = build_bundle(server.DATA/s['id']/'original.png',server.DATA/s['id']/result['id'])
                    verified = verify_bundle(bundle)
                    (output/(label+'.zip')).write_bytes(bundle)
                    records.append({'example':label,'expected_pixels':expected,**verified})
                    if label == 'whole': parent=result['id']
    summary = {'software_version':VERSION,'passed':len(records)==5,
               'evidence_kind':'procedural software demonstration; not model inference or accuracy validation',
               'network_required':False,'gpu_required':False,'model_weights_required':False,
               'duration_seconds':round(time.perf_counter()-started,3),'results':records}
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return summary


def main():
    parser=argparse.ArgumentParser(description='Offline GeoScope reviewer workflow: five reproducible tiny examples.')
    parser.add_argument('--output',type=Path,default=Path(__file__).parent/'reviewer-output')
    args=parser.parse_args()
    try: run_demo(args.output)
    except ModuleNotFoundError as exc:
        if exc.name == 'PIL': parser.exit(1,'Pillow is required. Run: python -m pip install -r requirements.txt\n')
        raise


if __name__ == '__main__': main()
