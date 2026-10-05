"""Score actual anonymous responses; refuse an empty study or invented defaults."""
import argparse
import csv
import json
import math
from pathlib import Path
from statistics import median


def analyze(observations,key):
    answers={r['case_id']:r for r in json.loads(Path(key).read_text(encoding='utf-8'))}
    with Path(observations).open(encoding='utf-8-sig',newline='') as handle:records=list(csv.DictReader(handle))
    if not records:raise ValueError('No participant observations exist. A prepared protocol is not an executed study.')
    seen=set();scored=[]
    for row in records:
        participant=row['participant_id'];case=row['case_id'];condition=row['condition']
        if not participant or condition not in ('loose-files','evidence') or case not in answers:
            raise ValueError('Every actual response needs an anonymous ID, known case and condition.')
        identity=(participant,case)
        if identity in seen:raise ValueError('Duplicate participant/case response.')
        seen.add(identity);expected=answers[case]
        seconds=float(row['elapsed_seconds'])
        if not math.isfinite(seconds) or seconds<=0:raise ValueError('Elapsed time must be a measured positive number.')
        matches={}
        for name in ('foreground_pixels','selected_region_pixels','whole_image_pixels'):
            matches[name]=bool(row[name]) and int(row[name])==expected[name]
        for name in ('whole_image_coverage','within_region_coverage'):
            matches[name]=bool(row[name]) and math.isfinite(float(row[name])) and math.isclose(float(row[name]),expected[name],rel_tol=1e-4,abs_tol=1e-6)
        matches['inference_performed']=row['inference_performed'].strip().lower()=='false'
        scored.append({'participant_id':participant,'case_id':case,'condition':condition,'elapsed_seconds':seconds,
            'all_fields_correct':all(matches.values()),'field_matches':matches})
    groups={}
    for condition in ('loose-files','evidence'):
        group=[r for r in scored if r['condition']==condition]
        groups[condition]={'responses':len(group),'fully_correct':sum(r['all_fields_correct'] for r in group),
            'error_rate':sum(not r['all_fields_correct'] for r in group)/len(group) if group else None,
            'median_elapsed_seconds':median(r['elapsed_seconds'] for r in group) if group else None}
    return {'participants_observed':len({r['participant_id'] for r in scored}),'conditions':groups,'responses':scored,
        'interpretation':'Descriptive observed convenience-sample results; no invented observations or population-level efficacy claim.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('observations',type=Path);parser.add_argument('--answer-key',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=analyze(args.observations,args.answer_key)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
