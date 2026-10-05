"""Real NAIP image, explicit exclusions and independently counted replay.

The left quarter is excluded solely to demonstrate declared conditions. These
exclusions are neither detected clouds nor independent quality/accuracy labels.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from PIL import Image
from geomasklab._version import VERSION
from geomasklab.api import create_evidence,recalculate_evidence
from geomasklab.comparison import compare_bundles
from geomasklab.domain import png
from geomasklab.evidence import load_verified_bundle
from geomasklab.report import build_report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('workflow-output/validity'))
    parser.add_argument('--geo',action='store_true',help='Also independently check optional nominal area using Rasterio/NumPy.')
    args=parser.parse_args();data=ROOT/'examples/data/naip-denver'
    provenance=json.loads((data/'provenance.json').read_text(encoding='utf-8'))
    for name,identity in provenance['files'].items():
        raw=(data/name).read_bytes()
        if len(raw)!=identity['bytes'] or hashlib.sha256(raw).hexdigest()!=identity['sha256']:
            raise ValueError('Frozen source example changed: '+name)
    image=(data/'image.png').read_bytes();mask=(data/'mask.png').read_bytes()
    with Image.open(io.BytesIO(mask)) as im:positive=im.convert('L');size=im.size
    valid=Image.new('L',size,255);valid.paste(0,(0,0,size[0]//4,size[1]))
    options=dict(target='tree',source='NAIP excess-green color candidates; semantic accuracy unvalidated',
                 image_source=provenance['credit'],aligned=True)
    original=create_evidence(image,mask,**options)
    bundle=create_evidence(image,mask,valid_mask=png(valid),valid_source='Demonstration exclusion: left quarter; not cloud or quality labels',**options)
    facts,files=load_verified_bundle(bundle)
    # Independent arithmetic uses an explicit index predicate, not domain helpers.
    n=size[0]*size[1]
    expected_foreground=sum(value==255 and i%size[0]>=size[0]//4 for i,value in enumerate(positive.tobytes()))
    expected_domain=(size[0]-size[0]//4)*size[1]
    if facts['pixel_area']!=expected_foreground or facts['validity_measurements']['valid_region_pixels']!=expected_domain:
        raise ValueError('Independent real-image counts do not match.')
    comparison=compare_bundles(original,bundle)
    if comparison['changed_pixels']!=0 or not comparison['full_prediction_pixels_equal']:
        raise ValueError('Validity change was incorrectly reported as a prediction change.')
    derived=recalculate_evidence(bundle,scope='right');load_verified_bundle(derived)
    args.output.mkdir(parents=True,exist_ok=True)
    for name,raw in [('original.zip',original),('valid.zip',bundle),('right.zip',derived),('valid.png',png(valid))]:
        (args.output/name).write_bytes(raw)
    (args.output/'report.html').write_text(build_report(bundle),encoding='utf-8')
    (args.output/'analysis.json').write_bytes(files['analysis.json'])
    summary={'software_version':VERSION,'image_size':list(size),'geometric_image_pixels':n,
             'independent_foreground_pixels':expected_foreground,'independent_valid_pixels':expected_domain,
             'validity_measurements':facts['validity_measurements'],'independent_pixel_check':'passed',
             'mask_comparison_changed_pixels':comparison['changed_pixels'],
             'inference_performed':False,'semantic_accuracy_measured':False,
             'exclusion_meaning':'Explicit demonstration condition, not a cloud or quality annotation',
             'dataset_credit':provenance['credit']}
    if args.geo:
        import numpy as np
        import rasterio
        from geomasklab.geospatial import geospatial_packet,verify_geospatial_packet
        raster=(data/'source.tif').read_bytes();packet=geospatial_packet(bundle,raster)
        measured=verify_geospatial_packet(packet)['measurements']
        with rasterio.io.MemoryFile(raster) as memory,memory.open() as ds:
            inclusion=np.ones((ds.height,ds.width),dtype=bool);inclusion[:,:ds.width//4]=False
            foreground=np.frombuffer(positive.tobytes(),dtype=np.uint8).reshape(ds.height,ds.width)>0
            expected_area=int(np.count_nonzero(inclusion & foreground))*abs(ds.transform.a*ds.transform.e-ds.transform.b*ds.transform.d)
            expected_valid_area=int(np.count_nonzero(inclusion))*abs(ds.transform.a*ds.transform.e-ds.transform.b*ds.transform.d)
        if abs(measured['foreground_area_m2']-expected_area)>1e-8 or abs(measured['valid_region_area_m2']-expected_valid_area)>1e-8:
            raise ValueError('Independent nominal-area calculation does not match.')
        summary['independent_nominal_area_check']='passed';summary['geospatial_measurements']=measured
        (args.output/'geospatial.zip').write_bytes(packet)
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
