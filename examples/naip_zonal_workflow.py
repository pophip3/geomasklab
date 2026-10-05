"""Real NAIP study regions with an independent Rasterio/NumPy consistency table."""
import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from PIL import Image
from geomasklab._version import VERSION
from geomasklab.api import create_evidence
from geomasklab.providers import ExcessGreenProvider
from geomasklab.geospatial import geospatial_packet,verify_geospatial_packet
from geomasklab.zonal import zonal_packet,verify_zonal_packet


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('workflow-output/naip-zonal'))
    args=parser.parse_args()
    import numpy as np
    import rasterio
    from rasterio.features import rasterize
    from pyproj import Transformer
    data=ROOT/'examples/data/naip-denver'
    provenance=json.loads((data/'provenance.json').read_text(encoding='utf-8'))
    for name,identity in provenance['files'].items():
        raw=(data/name).read_bytes()
        if len(raw)!=identity['bytes'] or hashlib.sha256(raw).hexdigest()!=identity['sha256']:
            raise ValueError('Frozen source example changed: '+name)
    image=(data/'image.png').read_bytes();mask=(data/'mask.png').read_bytes();raster=(data/'source.tif').read_bytes()
    provider=json.loads((data/'mask.png.provider.json').read_text(encoding='utf-8'))
    baseline=ExcessGreenProvider().produce(image)
    with Image.open(io.BytesIO(baseline.mask)) as generated,Image.open(io.BytesIO(mask)) as supplied:
        if generated.tobytes()!=supplied.tobytes():raise ValueError('Baseline pixel reproduction failed.')
    bundle=create_evidence(image,mask,target='tree',source='NAIP excess-green color candidates; accuracy unvalidated',
        image_source=provenance['credit'],aligned=True,provider_info=provider)
    geometry=(data/'zones.geojson').read_bytes()
    packet=zonal_packet(bundle,geometry,coordinates='wgs84',raster=raster)
    measured=verify_zonal_packet(packet)
    area=geospatial_packet(bundle,raster);whole=verify_geospatial_packet(area)
    # Independent path: decoded baseline array, projected GeoJSON geometry,
    # GDAL-backed Rasterio rasterization and direct NumPy counts. No core
    # geometry or measurements are used in the reference calculations.
    with rasterio.io.MemoryFile(raster) as memory,memory.open() as source:
        converter=Transformer.from_crs(4326,source.crs,always_xy=True)
        pixel_area=abs(source.transform.a*source.transform.e-source.transform.b*source.transform.d)
        shape=(source.height,source.width);transform=source.transform
    with Image.open(io.BytesIO(mask)) as prediction:positive=np.asarray(prediction)==255
    def project_ring(ring):
        x,y=converter.transform([p[0] for p in ring],[p[1] for p in ring])
        return [[a,b] for a,b in zip(x,y)]
    rows=[]
    for feature,own in zip(json.loads(geometry)['features'],measured['zones']):
        source=feature['geometry'];kind=source['type']
        coordinates=([project_ring(r) for r in source['coordinates']] if kind=='Polygon' else
                     [[project_ring(r) for r in polygon] for polygon in source['coordinates']])
        zone=rasterize([({'type':kind,'coordinates':coordinates},1)],out_shape=shape,transform=transform,all_touched=False,dtype='uint8').astype(bool)
        foreground=int(np.count_nonzero(positive & zone));domain=int(np.count_nonzero(zone))
        reference_area=foreground*pixel_area
        if foreground!=own['foreground_pixels'] or domain!=own['selected_region_pixels']:
            raise ValueError('Independent Rasterio domain/count mismatch: '+feature['id'])
        if not math.isclose(reference_area,own['foreground_area_m2'],rel_tol=1e-12,abs_tol=1e-9):
            raise ValueError('Independent nominal area mismatch: '+feature['id'])
        rows.append({'zone_id':feature['id'],'geomasklab_foreground_pixels':own['foreground_pixels'],
            'rasterio_numpy_foreground_pixels':foreground,'geomasklab_region_pixels':own['selected_region_pixels'],
            'rasterio_region_pixels':domain,'geomasklab_nominal_area_m2':own['foreground_area_m2'],
            'rasterio_numpy_nominal_area_m2':reference_area,'area_difference_m2':own['foreground_area_m2']-reference_area,
            'whole_image_coverage':own['coverage_of_image'],'within_region_coverage':own['coverage_of_region']})
    args.output.mkdir(parents=True,exist_ok=True)
    for name,raw in [('evidence.zip',bundle),('zonal.zip',packet),('area.zip',area)]:
        (args.output/name).write_bytes(raw)
    with (args.output/'consistency.csv').open('w',encoding='utf-8',newline='') as output:
        writer=csv.DictWriter(output,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    summary={'passed':True,'software_version':VERSION,'source_tile':provenance['acquisition']['catalog_item']['Name'],
        'crs':'EPSG:32613','image_dimensions':[512,512],'zones_compared':len(rows),
        'independent_reference':'Rasterio/GDAL all_touched=False and direct NumPy counts',
        'maximum_area_difference_m2':max(abs(r['area_difference_m2']) for r in rows),'whole_image':whole,
        'comparison':rows,'semantic_accuracy_assessed':False,'human_participants':0,
        'area_interpretation':'Nominal projected exported-grid area; projection distortion and terrain omitted.'}
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
