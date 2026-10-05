"""Prepare matched-information handoff tasks; never fabricate participant observations."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from geomasklab.api import create_evidence,recalculate_evidence
from geomasklab.evidence import load_verified_bundle


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('workflow-output/handoff-study'))
    args=parser.parse_args();data=ROOT/'examples/data/naip-denver'
    image=(data/'image.png').read_bytes();mask=(data/'mask.png').read_bytes()
    whole=create_evidence(image,mask,target='tree',source='NAIP color baseline; unvalidated vegetation candidates',aligned=True)
    cases=[];answers=[]
    for case,scope in [('A','right'),('B','left')]:
        bundle=recalculate_evidence(whole,scope=scope);_,files=load_verified_bundle(bundle)
        folder=args.output/'participant-materials'/case
        baseline=folder/'loose-files';baseline.mkdir(parents=True,exist_ok=True)
        # Both conditions expose identical information. The baseline differs in
        # packaging and has no automatic domain-replay validator.
        for name,raw in files.items():(baseline/name).write_bytes(raw)
        (folder/'evidence.zip').write_bytes(bundle)
        facts=json.loads(files['statistics.json'])
        cases.append({'case_id':case,'scope':scope,'baseline':str(Path(case)/'loose-files'),'evidence':str(Path(case)/'evidence.zip')})
        answers.append({'case_id':case,'foreground_pixels':facts['pixel_area'],'selected_region_pixels':facts['scope_area_pixels'],
            'whole_image_pixels':facts['total_pixels'],'whole_image_coverage':facts['area_ratio'],'within_region_coverage':facts['scope_area_ratio'],
            'evidence_sha256':hashlib.sha256(bundle).hexdigest()})
    protocol={'schema':'geomasklab-handoff-study-protocol/1.0','status':'Prepared; no participants tested',
        'participants_planned':[3,5],'participants_observed':0,'cases':cases,
        'assignment':'Odd anonymous participant IDs: A loose-files then B evidence. Even IDs: A evidence then B loose-files.',
        'task':'Report foreground pixels, both denominators and both coverage ratios; identify whether a model was called during scope derivation.',
        'controls':['Same image, mask, geometry, metadata and English instructions in both conditions.',
            'Allow equivalent Python/GIS tools; record prior familiarity and tool versions.',
            'Counterbalance condition order; do not show the answer key or let participants observe others.',
            'Measure elapsed time with the same method; allow a predefined maximum duration.',
            'Report raw counts and uncertainty; 3-5 convenience participants cannot establish population-level efficacy.'],
        'ethics':'Obtain voluntary consent and check local ethics/privacy requirements before collecting observations. Use anonymous IDs; no personal data are required.'}
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n',encoding='utf-8')
    (args.output/'administrator-answer-key.json').write_text(json.dumps(answers,indent=2)+'\n',encoding='utf-8')
    columns=['participant_id','case_id','condition','order','elapsed_seconds','foreground_pixels','selected_region_pixels',
        'whole_image_pixels','whole_image_coverage','within_region_coverage','inference_performed','tool_versions','notes']
    with (args.output/'observations.csv').open('w',encoding='utf-8',newline='') as output:csv.writer(output).writerow(columns)
    instructions='''GeoMaskLab handoff task

You are given a real NAIP image and a color-baseline mask. The mask is not
validated vegetation ground truth. Reproduce the reported spatial measurement.
Record foreground pixels, selected-region pixels, whole-image pixels, both
coverage ratios and whether scope derivation called a model.

For loose files, inspect result.json/statistics.json and reconstruct the mask
calculation with your preferred local tools. For the evidence condition, install
GeoMaskLab and run `geomasklab verify evidence.zip`, then inspect its metadata.
Both conditions contain the same information. Do not consult the administrator's
answer key. Record your tool versions and report any failure or ambiguity.
The investigator records elapsed time and collects the anonymous response.
'''
    (args.output/'participant-materials/INSTRUCTIONS.txt').write_text(instructions,encoding='utf-8')
    print(json.dumps({'prepared':True,'output':str(args.output),'participants_observed':0,'observations_generated':0},indent=2))


if __name__=='__main__':main()
