"""Synthetic GeoTIFF arithmetic example; no real location or accuracy claim."""
import argparse
import io
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from PIL import Image
from geomasklab.api import create_evidence,recalculate_evidence
from geomasklab.geospatial import dependencies,geospatial_packet,verify_geospatial_packet
from geomasklab.provenance import provenance_document,verify_provenance


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('workflow-output/geospatial'))
    args=parser.parse_args()
    np,rasterio,pyproj=dependencies()
    from affine import Affine
    image=Image.new('RGB',(7,5),(40,120,40))
    mask=Image.new('L',(7,5));mask.paste(255,(1,1,5,4))
    def encode(im):
        out=io.BytesIO();im.save(out,'PNG');return out.getvalue()
    bundle=create_evidence(encode(image),encode(mask),target='tree',aligned=True,
        source='Synthetic 12-pixel fixture; no recognition or real-location claim')
    child=recalculate_evidence(bundle,scope='right')
    with rasterio.io.MemoryFile() as memory:
        with memory.open(driver='GTiff',width=7,height=5,count=3,dtype='uint8',crs='EPSG:32654',
                         transform=Affine(.5,0,500000,0,-.5,3950000)) as dataset:
            dataset.write(np.array(image).transpose(2,0,1))
        source=memory.read()
    packet=geospatial_packet(child,source)
    verified=verify_geospatial_packet(packet)
    assert verified['measurements']['foreground_pixels']==6
    assert verified['measurements']['foreground_area_m2']==1.5
    assert verified['measurements']['selected_region_area_m2']==5
    provenance=provenance_document(child)
    verify_provenance(child,provenance)
    args.output.mkdir(parents=True,exist_ok=True)
    for name,raw in [('right.zip',child),('source.tif',source),('area.zip',packet)]:
        (args.output/name).write_bytes(raw)
    (args.output/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    report={'passed':True,'input':'Synthetic arithmetic fixture, not a real georeferenced observation',
        'area_assessment':verified,'independent_prov_mapping':'replayed'}
    (args.output/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
