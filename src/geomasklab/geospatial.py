"""Optional, replayable GeoTIFF area assessment of a verified pixel result.

The source raster must decode to the exact RGB pixels embedded in the evidence.
Missing CRS, masked/nodata pixels and ambiguous grids are rejected. Core pixel
records remain unchanged; physical quantities live in a separate assessment.
"""
import hashlib
import io
import json
import math
import zipfile
from PIL import Image
from ._version import VERSION
from .evidence import load_verified_bundle
from .measurements import constrain

SCHEMA='geomasklab-geospatial-assessment/1.0'
MAX_RASTER_BYTES=64*1024*1024
MAX_PACKET_BYTES=192*1024*1024
MAX_GEODESIC_PIXELS=500_000
MEMBERS={'evidence.zip','source.tif','mask.tif','geospatial.json','manifest.json'}


def dependencies():
    try:
        import numpy as np
        import rasterio
        import pyproj
    except ImportError as error:
        raise ValueError('This operation needs the optional geo extra: pip install ".[geo]" from the checkout.') from error
    return np,rasterio,pyproj


def source_grid(raw,image):
    """Read only an embedded, bounded GeoTIFF, and verify its complete pixel grid."""
    np,rasterio,pyproj=dependencies()
    if not raw or len(raw)>MAX_RASTER_BYTES:raise ValueError('Source GeoTIFF must be 64 MB or smaller.')
    with Image.open(io.BytesIO(raw)) as header:
        tags=getattr(header,'tag_v2',{})
        if not (34264 in tags or (33550 in tags and 33922 in tags)):
            raise ValueError('GeoTIFF requires a stored affine georeference; a default grid is not assumed.')
    try:
        with rasterio.io.MemoryFile(raw) as memory,memory.open() as dataset:
            if dataset.driver!='GTiff':raise ValueError('Use a GeoTIFF source raster.')
            if (dataset.width,dataset.height)!=image.size:raise ValueError('GeoTIFF dimensions do not match evidence.')
            if dataset.crs is None:raise ValueError('GeoTIFF requires an explicit CRS; no coordinate units are inferred.')
            if dataset.count not in (1,3,4) or any(d!='uint8' for d in dataset.dtypes):
                raise ValueError('Use a one-band grayscale or three/four-band, 8-bit RGB GeoTIFF.')
            if np.any(dataset.dataset_mask()!=255) or np.any(dataset.read_masks()!=255):
                raise ValueError('Nodata or masked pixels require a separate domain contract and are not supported.')
            bands=dataset.read([1,1,1] if dataset.count==1 else [1,2,3])
            if bands.transpose(1,2,0).tobytes()!=image.convert('RGB').tobytes():
                raise ValueError('GeoTIFF RGB pixels do not match the embedded evidence image.')
            transform=dataset.transform
            if not all(math.isfinite(v) for v in tuple(transform)[:6]) or not math.isfinite(transform.determinant) or not transform.determinant:
                raise ValueError('Raster affine transform must be finite and non-singular.')
            crs=pyproj.CRS.from_wkt(dataset.crs.to_wkt())
    except rasterio.errors.RasterioError as error:
        raise ValueError('Cannot read the supplied GeoTIFF.') from error
    return crs,transform


def measure_geospatial(bundle,raster,*,method='nominal'):
    """Return physical-area assumptions, exact identities and a GeoTIFF mask.

    Nominal area is projected coordinate area converted to square metres, with
    no projection-distortion correction. Geodesic area uses four corner points
    and WGS84 geodesic edges, for EPSG:4326, EPSG:3857 and WGS84 UTM only.
    """
    facts,files=load_verified_bundle(bundle)
    np,rasterio,pyproj=dependencies()
    with Image.open(io.BytesIO(files['original.png'])) as original:image=original.convert('RGB')
    crs,transform=source_grid(raster,image)
    result=json.loads(files['result.json'])
    with Image.open(io.BytesIO(files['mask.png'])) as source:foreground=source.tobytes()
    domain=constrain(Image.new('L',image.size,255),result['task']['side'],result['task'].get('roi')).tobytes()
    w,h=image.size
    region_count=domain.count(255)
    if method=='nominal':
        if not crs.is_projected or len(crs.axis_info)<2:raise ValueError('Nominal square-metre area requires a projected CRS with declared linear units.')
        factors=[axis.unit_conversion_factor for axis in crs.axis_info[:2]]
        if any(not math.isfinite(f) or f<=0 for f in factors):raise ValueError('CRS linear units must have positive, finite conversion factors.')
        pixel_area=abs(transform.determinant)*factors[0]*factors[1]
        if not math.isfinite(pixel_area*w*h) or pixel_area<=0:raise ValueError('Projected cell area must be positive and finite.')
        image_area=pixel_area*w*h;region_area=pixel_area*region_count;foreground_area=pixel_area*facts['pixel_area']
        assumptions=['Projected coordinate-cell area converted using declared CRS axis units.',
                     'Projection distortion is not corrected; nominal m2 may differ from ground area.',
                     'Terrain slope, elevation and semantic mask accuracy are not measured.']
        model={'method':'projected_nominal','unit':'m2','pixel_area_m2':pixel_area,'ground_area_corrected':False,
               'axis_units':[axis.unit_name for axis in crs.axis_info[:2]],'axis_unit_to_metre':factors}
    elif method=='geodesic':
        epsg=crs.to_epsg()
        if epsg not in {4326,3857} and not (epsg is not None and (32601<=epsg<=32660 or 32701<=epsg<=32760)):
            raise ValueError('Geodesic area supports EPSG:4326, EPSG:3857 and WGS84 UTM grids only.')
        if w*h>MAX_GEODESIC_PIXELS:raise ValueError('Geodesic corner assessment is limited to 500,000 pixels; use a smaller chip.')
        converter=pyproj.Transformer.from_crs(crs,4326,always_xy=True)
        geod=pyproj.Geod(ellps='WGS84')
        all_areas=[];region_areas=[];positive_areas=[]
        for y in range(h):
            for x in range(w):
                corners=[(transform.a*cx+transform.b*cy+transform.c,transform.d*cx+transform.e*cy+transform.f)
                         for cx,cy in ((x,y),(x+1,y),(x+1,y+1),(x,y+1))]
                try:
                    lon,lat=converter.transform([p[0] for p in corners],[p[1] for p in corners],errcheck=True)
                except pyproj.exceptions.ProjError as error:
                    raise ValueError('Pixel corners cannot be transformed to valid longitude/latitude.') from error
                if any(not math.isfinite(v) for v in [*lon,*lat]) or any(abs(v)>90 for v in lat):
                    raise ValueError('Pixel corners must map to finite Earth longitude/latitude coordinates.')
                area=abs(geod.polygon_area_perimeter(lon,lat)[0])
                if not math.isfinite(area) or area<=0:raise ValueError('A pixel has undefined or zero geodesic area.')
                all_areas.append(area)
                if domain[y*w+x]:region_areas.append(area)
                if foreground[y*w+x]:positive_areas.append(area)
        image_area=math.fsum(all_areas);region_area=math.fsum(region_areas);foreground_area=math.fsum(positive_areas)
        model={'method':'wgs84_geodesic_corners','unit':'m2','ellipsoid':'WGS84','ground_area_corrected':True}
        assumptions=['Pixel corners are transformed to WGS84 with explicit XY axis order.',
                     'Each pixel is approximated by a four-corner polygon with geodesic edges on the WGS84 ellipsoid.',
                     'Raster boundary curvature between corners, terrain slope, elevation and semantic accuracy are not measured.']
    else:raise ValueError('Area method must be nominal or geodesic.')
    mask=np.frombuffer(foreground,dtype=np.uint8).reshape(h,w)
    with rasterio.io.MemoryFile() as output:
        with output.open(driver='GTiff',width=w,height=h,count=1,dtype='uint8',crs=crs.to_wkt(),
                         transform=transform,compress='deflate',nodata=None) as dataset:
            dataset.write(mask,1)
            dataset.update_tags(GeoMaskLab_evidence_sha256=hashlib.sha256(bundle).hexdigest(),
                                foreground_encoding='0=background;255=foreground;all pixels valid')
        mask_tiff=output.read()
    record={'schema':SCHEMA,'software_version':VERSION,
        'source_bundle_sha256':hashlib.sha256(bundle).hexdigest(),'source_geotiff_sha256':hashlib.sha256(raster).hexdigest(),
        'image_sha256':hashlib.sha256(files['original.png']).hexdigest(),
        'grid':{'width':w,'height':h,'transform':list(tuple(transform)[:6]),'crs_wkt':crs.to_wkt(),'epsg':crs.to_epsg()},
        'task':result['task'],'area_model':model,'assumptions':assumptions,
        'measurements':{'foreground_pixels':facts['pixel_area'],'selected_region_pixels':region_count,
            'whole_image_pixels':w*h,'foreground_area_m2':foreground_area,'selected_region_area_m2':region_area,
            'whole_image_area_m2':image_area,'coverage_of_region_area':foreground_area/region_area if region_area else None,
            'coverage_of_image_area':foreground_area/image_area},
        'semantic_accuracy_verified':False,'pixel_alignment':'Exact RGB pixel equality with embedded evidence; no resampling.',
        'dependencies':{'rasterio':rasterio.__version__,'pyproj':pyproj.__version__}}
    return record,mask_tiff


def geospatial_packet(bundle,raster,*,method='nominal'):
    record,mask=measure_geospatial(bundle,raster,method=method)
    files={'evidence.zip':bundle,'source.tif':raster,'mask.tif':mask,
           'geospatial.json':json.dumps(record,indent=2,allow_nan=False).encode('utf-8')}
    manifest={'schema':SCHEMA,'files':{name:{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()} for name,raw in files.items()}}
    files['manifest.json']=json.dumps(manifest,indent=2).encode('utf-8')
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,raw in files.items():archive.writestr(name,raw)
    return output.getvalue()


def verify_geospatial_packet(payload):
    """Recompute physical quantities from exact embedded raster and evidence."""
    if len(payload)>MAX_PACKET_BYTES:raise ValueError('Geospatial packet exceeds size limit.')
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        entries=archive.infolist()
        if (len(entries)!=len(MEMBERS) or set(archive.namelist())!=MEMBERS or
                sum(i.file_size for i in entries)>MAX_PACKET_BYTES):
            raise ValueError('Geospatial packet requires five unique, bounded flat files.')
        files={i.filename:archive.read(i) for i in entries}
    manifest=json.loads(files['manifest.json'])
    if (not isinstance(manifest,dict) or manifest.get('schema')!=SCHEMA or
            not isinstance(manifest.get('files'),dict) or set(manifest['files'])!=MEMBERS-{'manifest.json'}):
        raise ValueError('Geospatial manifest membership mismatch.')
    for name,identity in manifest['files'].items():
        if identity!={'bytes':len(files[name]),'sha256':hashlib.sha256(files[name]).hexdigest()}:
            raise ValueError('Geospatial checksum mismatch: '+name)
    recorded=json.loads(files['geospatial.json'])
    if not isinstance(recorded,dict) or any(not isinstance(recorded.get(k),dict) for k in ('area_model','grid','measurements')):
        raise ValueError('Geospatial record requires area_model, grid and measurements objects.')
    method={'projected_nominal':'nominal','wgs84_geodesic_corners':'geodesic'}.get(recorded.get('area_model',{}).get('method'))
    replay,_=measure_geospatial(files['evidence.zip'],files['source.tif'],method=method)
    np,rasterio,pyproj=dependencies()
    for name in ('source_bundle_sha256','source_geotiff_sha256','image_sha256','task','area_model','assumptions',
                 'semantic_accuracy_verified','pixel_alignment','schema'):
        if recorded.get(name)!=replay[name]:raise ValueError('Geospatial record does not replay: '+name)
    grid=recorded.get('grid',{})
    try:
        grid_crs=pyproj.CRS.from_wkt(grid.get('crs_wkt',''))
    except (pyproj.exceptions.CRSError,TypeError) as error:
        raise ValueError('Geospatial record requires a valid CRS definition.') from error
    if (any(grid.get(k)!=replay['grid'][k] for k in ('width','height','transform','epsg')) or
            grid_crs!=pyproj.CRS.from_wkt(replay['grid']['crs_wkt'])):
        raise ValueError('Geospatial grid does not match its source.')
    values=recorded.get('measurements',{})
    if set(values)!=set(replay['measurements']):raise ValueError('Geospatial measurement membership mismatch.')
    for name,value in replay['measurements'].items():
        saved=values[name]
        if value is None:
            if saved is not None:raise ValueError('Undefined geographic ratio must be null.')
        elif isinstance(value,int):
            if type(saved) is not int or saved!=value:raise ValueError('Geospatial pixel count does not replay: '+name)
        elif (type(saved) not in (int,float) or not math.isfinite(saved) or
              not math.isclose(saved,value,rel_tol=1e-9,abs_tol=1e-9)):
            raise ValueError('Geospatial area does not replay: '+name)
    _,source=load_verified_bundle(files['evidence.zip'])
    with rasterio.io.MemoryFile(files['mask.tif']) as memory,memory.open() as exported:
        with Image.open(io.BytesIO(source['mask.png'])) as mask:expected=mask.tobytes()
        if (exported.width!=grid['width'] or exported.height!=grid['height'] or
                exported.count!=1 or exported.dtypes!=('uint8',) or exported.read(1).tobytes()!=expected or
                list(tuple(exported.transform)[:6])!=grid['transform'] or exported.crs is None or
                pyproj.CRS.from_wkt(exported.crs.to_wkt())!=grid_crs or
                np.any(exported.dataset_mask()!=255)):
            raise ValueError('Exported GeoTIFF mask does not match the measured grid and foreground.')
    return {'verified':True,'schema':SCHEMA,'area_model':recorded['area_model'],'measurements':values,
            'scope':'Physical-area model replay and pixel alignment; no terrain or semantic accuracy claim'}
