"""Replay a credited real-image mask with explicit coverage denominators."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import io
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from geomasklab.api import create_evidence,recalculate_evidence
from geomasklab.evidence import load_verified_bundle
from geomasklab.providers import ExcessGreenProvider
from geomasklab.report import build_report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('workflow-output/real-image'))
    args=parser.parse_args()
    data=ROOT/'examples/data/san-francisco-bay'
    metadata=json.loads((data/'provenance.json').read_text())
    for name,digest in metadata['files'].items():
        if hashlib.sha256((data/name).read_bytes()).hexdigest()!=digest:raise ValueError('Example asset identity mismatch: '+name)
    image,mask=(data/'image.png').read_bytes(),(data/'mask.png').read_bytes()
    product=ExcessGreenProvider().produce(image)
    with Image.open(io.BytesIO(product.mask)) as generated,Image.open(io.BytesIO(mask)) as recorded:
        if generated.size!=recorded.size or generated.tobytes()!=recorded.tobytes():
            raise ValueError('Local provider does not reproduce the packaged mask pixels.')
    provider=json.loads((data/'mask.png.provider.json').read_text())
    bundle=create_evidence(image,mask,target='tree',aligned=True,
        source='Local RGB excess-green candidates; tree/vegetation accuracy unvalidated.',
        image_source=metadata['credit']+'; image '+metadata['image_id'],provider_info=provider)
    derived=recalculate_evidence(bundle,scope='right')
    args.output.mkdir(parents=True,exist_ok=True)
    records=[]
    for name,raw in [('whole',bundle),('right',derived)]:
        _,files=load_verified_bundle(raw)
        (args.output/(name+'.zip')).write_bytes(raw)
        (args.output/(name+'.html')).write_text(build_report(raw),encoding='utf-8')
        metrics=json.loads(files['statistics.json'])
        records.append({'scope':name,**{k:metrics[k] for k in
            ('pixel_area','total_pixels','area_ratio','scope_area_pixels','scope_area_ratio')}})
    # Same numerator, two explicitly different denominators: no inference needed.
    scoped=records[1]
    assert scoped['scope_area_pixels']<scoped['total_pixels']
    assert scoped['scope_area_ratio']>scoped['area_ratio']
    report={'passed':True,'example':'NASA ISS004-E-10288','records':records,
        'claims':'Real photograph and reproducible color baseline; pixel-workflow demonstration, not semantic accuracy.',
        'geographic_area_available':False,'human_participants':0}
    (args.output/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
