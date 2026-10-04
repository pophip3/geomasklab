"""Recompute numerical development records; does not validate missing mask pixels."""
from pathlib import Path
from collections import defaultdict
import csv
import hashlib
import json
import math
from statistics import mean

ROOT=Path(__file__).resolve().parent/'historical'


def rows(filename):
    with (ROOT/filename).open(encoding='utf-8',newline='') as handle:
        return list(csv.DictReader(handle))


def main():
    manifest=json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))
    for source in manifest['sources']:
        if hashlib.sha256((ROOT/source['curated_path']).read_bytes()).hexdigest()!=source['curated_sha256']:
            raise ValueError('Historical table checksum mismatch.')
    old,new=rows('planner_baseline.csv'),rows('planner_optimized.csv')
    assert len(old)==len(new)==40
    assert {r['task_id'] for r in old}=={r['task_id'] for r in new}
    routing={label:{'correct':sum(r['routing_correct'].lower()=='true' for r in table),'total':len(table)}
             for label,table in [('baseline',old),('optimized',new)]}
    reports={}
    for filename,group in [('segmentation_diagnostic.csv','class_name'),('aircraft_tuning.csv','experiment_id')]:
        by=defaultdict(list)
        for row in rows(filename):
            tp,fp,fn=[int(row[k]) for k in ('tp','fp','fn')]
            assert min(tp,fp,fn)>=0
            assert int(row['prediction_foreground_pixels'])==tp+fp
            assert int(row['ground_truth_foreground_pixels'])==tp+fn
            assert row['status']=='success' and row['binary_valid'].lower()=='true'
            assert int(row['width'])==int(row['output_width']) and int(row['height'])==int(row['output_height'])
            iou=tp/(tp+fp+fn) if tp+fp+fn else 1
            dice=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 1
            assert math.isclose(iou,float(row['iou']),abs_tol=1e-12)
            assert math.isclose(dice,float(row['dice']),abs_tol=1e-12)
            by[row[group]].append(row)
        reports[filename]={key:{'images':len(table),'mean_iou':mean(float(r['iou']) for r in table),
                               'mean_dice':mean(float(r['dice']) for r in table)} for key,table in sorted(by.items())}
    best=max(reports['aircraft_tuning.csv'],key=lambda k:reports['aircraft_tuning.csv'][k]['mean_iou'])
    result={'verified_record_arithmetic':True,'verified_prediction_pixels':False,'routing':routing,
            'segmentation_diagnostic':reports['segmentation_diagnostic.csv'],
            'best_same_set_aircraft_configuration':{'id':best,**reports['aircraft_tuning.csv'][best]},
            'independent_test':False,'source_commit':manifest['source_commit']}
    print(json.dumps(result,indent=2))
    return result


if __name__=='__main__':
    main()
