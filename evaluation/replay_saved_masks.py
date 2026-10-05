"""Current-core replay of historical real-image predictions, with no new inference.

Raw datasets and evidence stay outside the public source. Reported integrity
results are attributed to the current analysis commit; prediction provenance
retains the separately supplied historical commit. This is not a rerun of models.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from PIL import Image,ImageOps
from geomasklab._version import VERSION
from geomasklab.api import recalculate_evidence
from geomasklab.evidence import load_verified_bundle


def identity():
    command=['git','-c',f'safe.directory={ROOT.as_posix()}']
    try:
        commit=subprocess.check_output([*command,'rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        dirty=bool(subprocess.check_output([*command,'status','--porcelain'],cwd=ROOT,text=True))
    except (OSError,subprocess.CalledProcessError):
        commit=None;dirty=None
    return commit,dirty


def replay(input_root,output,prediction_commit):
    """Verify original bundles and independently count two new scopes per image."""
    if not re.fullmatch('[a-f0-9]{40}',prediction_commit):raise ValueError('Supply the full historical prediction commit.')
    archives=sorted(Path(input_root).glob('*/whole-evidence.zip'))
    if not archives:raise ValueError('No case/whole-evidence.zip files found.')
    commit,dirty=identity()
    if dirty:raise ValueError('Commit the analysis implementation before attributing replay results.')
    records=[];legacy_checked=0
    for archive in archives:
        source=archive.read_bytes()
        _,files=load_verified_bundle(source)
        result=json.loads(files['result.json'])
        with Image.open(io.BytesIO(files['full_mask.png'])) as im:positive=im.copy()
        if result['task'].get('invert'):positive=ImageOps.invert(positive)
        w,h=positive.size
        if w<2 or h<2:raise ValueError('Replay study requires images at least two pixels wide and high.')
        # Also test interoperability with the original source version's scoped exports.
        for original in archive.parent.glob('*-evidence.zip'):
            load_verified_bundle(original.read_bytes());legacy_checked+=1
        box=[w//4,h//4,max(w//4+1,3*w//4),max(h//4+1,3*h//4)]
        cases=[('right',None,[w//2,0,w,h]),
               ('rectangle',{'xyxy':box,'source':'imported','image_size':[w,h]},box)]
        for name,roi,bounds in cases:
            child=recalculate_evidence(source,scope='all' if roi else 'right',roi=roi)
            _,derived=load_verified_bundle(child)
            metrics=json.loads(derived['statistics.json'])
            direct=positive.crop(tuple(bounds)).histogram()[255]
            domain=(bounds[2]-bounds[0])*(bounds[3]-bounds[1])
            retained=all(derived[key]==files[key] for key in ('original.png','full_mask.png'))
            if metrics['pixel_area']!=direct or metrics['scope_area_pixels']!=domain or not retained:
                raise ValueError('Independent scope reconstruction disagrees: '+archive.parent.name+'/'+name)
            records.append({'case_id':archive.parent.name,'target':result['task']['target'],'scope':name,
                'source_bundle_sha256':hashlib.sha256(source).hexdigest(),'source_image_sha256':hashlib.sha256(files['original.png']).hexdigest(),
                'source_prediction_commit':prediction_commit,'analysis_commit':commit,'analysis_version':VERSION,
                'foreground_pixels':metrics['pixel_area'],'whole_image_pixels':metrics['total_pixels'],
                'selected_region_pixels':metrics['scope_area_pixels'],'coverage_of_image':metrics['area_ratio'],
                'coverage_of_region':metrics['scope_area_ratio'],'direct_foreground_pixels':direct,
                'direct_region_pixels':domain,'exact_source_retained':retained,'inference_performed':False})
        if len(records)%20==0:print(f'Replayed {len(records)//2}/{len(archives)} saved cases',flush=True)
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    with (output/'scope-replay.csv').open('w',newline='',encoding='utf-8') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
    summary={'passed':True,'schema':'geomasklab-historical-mask-replay/1.0','analysis_version':VERSION,
        'analysis_commit':commit,'working_tree_dirty':dirty,'prediction_commit':prediction_commit,
        'images':len(archives),'historical_bundles_verified':legacy_checked,'new_scopes_replayed':len(records),
        'exact_direct_count_matches':len(records),'exact_source_preservation':len(records),'new_model_calls':0,
        'interpretation':'Current software verification and scoped recomputation of historical predictions; no fresh model run or semantic-accuracy claim.',
        'human_participants':0,'raw_data_redistributed':False}
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--prediction-commit',required=True)
    args=parser.parse_args()
    replay(args.input,args.output,args.prediction_commit)


if __name__=='__main__':main()
