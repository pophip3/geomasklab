"""Reproduce the manuscript's procedural example and its verified exports."""
from pathlib import Path
import json
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import server
from export_bundle import build_bundle,verify_bundle


def main():
    output=Path(__file__).parent/'output'
    output.mkdir(parents=True,exist_ok=True)
    reports=[]
    with tempfile.TemporaryDirectory() as temporary,patch.object(server,'DATA',Path(temporary)):
        sid=server.new_session('urban')['id']
        session=server.SESSIONS[sid]
        jobs=[('whole','提取全图建筑',{}),('right','提取右侧建筑',{}),
              ('left','提取左侧建筑',{}),('roi','提取全图框选区域内的建筑',
               {'roi':{'xyxy':[80,50,280,250],'source':'drawn','image_size':[800,600]}})]
        expected={'whole':75350,'right':37350,'left':38000,'roi':12850}
        parent=None
        for label,query,options in jobs:
            result=server.run_task(session,{'query':query,'mode':'demo','parent_run_id':parent,**options})
            assert result['metrics']['pixel_area']==expected[label], (label,result['metrics']['pixel_area'],expected[label])
            payload=build_bundle(server.DATA/sid/'original.png',server.DATA/sid/result['id'])
            report=verify_bundle(payload)
            report.update(example=label,evidence_kind='procedural illustration; no model inference')
            reports.append(report)
            (output/f'{label}.zip').write_bytes(payload)
            parent=result['id'] if label in ('whole','right') else parent
        server.SESSIONS.clear()
    (output/'summary.json').write_text(json.dumps(reports,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(reports,indent=2))


if __name__=='__main__':
    main()
