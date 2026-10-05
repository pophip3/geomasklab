"""Model-independent Polygon/MultiPolygon measurement with pixel-center domains.

Each feature is measured independently. Polygon holes subtract from that polygon;
MultiPolygon members are unioned, including overlaps. A separate packet retains
the source evidence unchanged and binds geometry, domains and both denominators.
"""
import hashlib
import io
import json
import math
import re
import zipfile
from PIL import Image, ImageChops, ImageOps
from ._version import VERSION
from .evidence import load_verified_bundle
from .measurements import constrain

SCHEMA = 'geomasklab-zonal-assessment/1.0'
MAX_GEOMETRY_BYTES = 1024 * 1024
MAX_PACKET_BYTES = 384 * 1024 * 1024
MAX_FEATURES = 32


def _cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def _touch(a, b, c, d):
    """Closed-segment intersection, including touching and collinearity."""
    def on(a,b,c):
        return _cross(a,b,c)==0 and min(a[0],b[0])<=c[0]<=max(a[0],b[0]) and min(a[1],b[1])<=c[1]<=max(a[1],b[1])
    x,y,z,t=_cross(a,b,c),_cross(a,b,d),_cross(c,d,a),_cross(c,d,b)
    return (x*y<0 and z*t<0) or on(a,b,c) or on(a,b,d) or on(c,d,a) or on(c,d,b)


def _inside(point, ring):
    x,y=point;inside=False
    for a,b in zip(ring,ring[1:]):
        if (a[1]>y)!=(b[1]>y) and x<a[0]+(y-a[1])*(b[0]-a[0])/(b[1]-a[1]):inside=not inside
    return inside


def _ring(raw):
    if not isinstance(raw,list) or not 4<=len(raw)<=257:
        raise ValueError('Each closed polygon ring needs 4 to 257 coordinate pairs.')
    points=[]
    for point in raw:
        if (not isinstance(point,list) or len(point)!=2 or
                any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>10_000_000 for v in point)):
            raise ValueError('Polygon positions require two finite, bounded numeric coordinates.')
        points.append(tuple(point))
    if points[0]!=points[-1] or len(set(points[:-1]))!=len(points)-1:
        raise ValueError('Rings must be explicitly closed with distinct internal vertices.')
    if math.fsum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]))==0:
        raise ValueError('Polygon rings must have nonzero coordinate area.')
    edges=list(zip(points,points[1:]))
    for i in range(len(points)-1):
        a,b,c=points[i-1 if i else len(points)-2],points[i],points[i+1]
        if _cross(a,b,c)==0 and (b[0]-a[0])*(c[0]-b[0])+(b[1]-a[1])*(c[1]-b[1])<0:
            raise ValueError('Adjacent polygon edges must not backtrack or overlap.')
    for i,(a,b) in enumerate(edges):
        for j,(c,d) in enumerate(edges[i+1:],i+1):
            if j==i+1 or (i==0 and j==len(edges)-1):continue
            if _touch(a,b,c,d):raise ValueError('Self-intersecting or self-touching rings are unsupported.')
    return points


def _polygon(raw):
    if not isinstance(raw,list) or not 1<=len(raw)<=16:raise ValueError('A polygon needs one exterior and at most 15 holes.')
    rings=[_ring(r) for r in raw]
    for i,hole in enumerate(rings[1:],1):
        if not _inside(hole[0],rings[0]):raise ValueError('Polygon holes must lie strictly inside their exterior.')
        for other in rings[:i]:
            if any(_touch(a,b,c,d) for a,b in zip(hole,hole[1:]) for c,d in zip(other,other[1:])):
                raise ValueError('Polygon holes must not touch or intersect other rings.')
            if other is not rings[0] and (_inside(hole[0],other) or _inside(other[0],hole)):
                raise ValueError('Nested or overlapping holes are unsupported.')
    return rings


def features(document):
    """Return unique feature IDs and validated, bounded polygon components."""
    if not isinstance(document,dict) or 'crs' in document:raise ValueError('Use a geometry document without a legacy CRS member.')
    if document.get('type')=='FeatureCollection':items=document.get('features')
    elif document.get('type')=='Feature':items=[document]
    else:items=[{'type':'Feature','id':'zone-1','geometry':document}]
    if not isinstance(items,list) or not 1<=len(items)<=MAX_FEATURES:
        raise ValueError('Provide between 1 and 32 polygon features.')
    output=[];ids=set();positions=0
    for i,item in enumerate(items,1):
        if not isinstance(item,dict) or item.get('type')!='Feature':raise ValueError('Every zone must be a GeoJSON Feature.')
        fid=item.get('id',f'zone-{i}')
        if type(fid) is int:fid=str(fid)
        if not isinstance(fid,str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,64}',fid) or fid in ids:
            raise ValueError('Zone IDs must be unique ASCII identifiers of at most 64 characters.')
        ids.add(fid);geometry=item.get('geometry')
        if not isinstance(geometry,dict) or 'crs' in geometry:raise ValueError('A zone requires polygon geometry without a CRS member.')
        kind=geometry.get('type');coordinates=geometry.get('coordinates')
        if kind=='Polygon':polygons=[_polygon(coordinates)]
        elif kind=='MultiPolygon' and isinstance(coordinates,list) and 1<=len(coordinates)<=16:
            polygons=[_polygon(p) for p in coordinates]
        else:raise ValueError('Only Polygon and MultiPolygon zones are supported.')
        positions+=sum(len(r) for p in polygons for r in p)
        if positions>4096:raise ValueError('The geometry document exceeds 4,096 positions.')
        output.append((fid,polygons))
    return output


def _fill_ring(ring,size):
    """Even-odd scanline rule at pixel centers; lower edges included, upper excluded."""
    width,height=size;mask=Image.new('L',size)
    first=max(0,math.ceil(min(p[1] for p in ring)-.5))
    last=min(height,math.ceil(max(p[1] for p in ring)-.5))
    for row in range(first,last):
        cy=row+.5;xs=[]
        for a,b in zip(ring,ring[1:]):
            if (a[1]>cy)!=(b[1]>cy):xs.append(a[0]+(cy-a[1])*(b[0]-a[0])/(b[1]-a[1]))
        xs.sort()
        for left,right in zip(xs[::2],xs[1::2]):
            start=max(0,math.ceil(left-.5));stop=min(width,math.ceil(right-.5))
            if start<stop:mask.paste(255,(start,row,stop,row+1))
    return mask


def rasterize(polygons,size):
    """Union polygon components; subtract holes separately within each component."""
    output=Image.new('L',size)
    for polygon in polygons:
        component=_fill_ring(polygon[0],size)
        for hole in polygon[1:]:component=ImageChops.subtract(component,_fill_ring(hole,size))
        output=ImageChops.lighter(output,component)
    return output


def measure_zones(bundle,geometry,*,coordinates='pixel',raster=None):
    """Measure source-scope intersections; optional nominal m2 from a matching TIFF.

    RFC 7946 input uses longitude/latitude and requires a matching source raster.
    Pixel input uses GeoJSON-shaped geometry in EXIF-normalized image coordinates.
    Geographic edges are transformed vertex by vertex without densification.
    """
    if not geometry or len(geometry)>MAX_GEOMETRY_BYTES:raise ValueError('Geometry must contain at most 1 MB.')
    _,files=load_verified_bundle(bundle);items=features(json.loads(geometry))
    with Image.open(io.BytesIO(files['original.png'])) as image:image=image.convert('RGB')
    task=json.loads(files['result.json'])['task']
    with Image.open(io.BytesIO(files['mask.png'])) as mask:positive=mask.copy()
    source_domain=constrain(Image.new('L',image.size,255),task['side'],task.get('roi'))
    pixel_area=None;grid=None
    if coordinates not in ('pixel','wgs84'):raise ValueError('Coordinate mode must be pixel or wgs84.')
    if coordinates=='wgs84' and raster is None:raise ValueError('WGS84 GeoJSON requires a matching source GeoTIFF.')
    if raster is not None:
        from .geospatial import source_grid
        import pyproj
        crs,transform=source_grid(raster,image)
        if not crs.is_projected or len(crs.axis_info)<2:raise ValueError('Zonal m2 requires a projected CRS with linear units.')
        factors=[a.unit_conversion_factor for a in crs.axis_info[:2]]
        if any(not math.isfinite(f) or f<=0 for f in factors):raise ValueError('Invalid linear CRS units.')
        pixel_area=abs(transform.determinant)*factors[0]*factors[1]
        if not math.isfinite(pixel_area*image.width*image.height) or pixel_area<=0:raise ValueError('Invalid physical cell area.')
        grid={'epsg':crs.to_epsg(),'crs_wkt':crs.to_wkt(),'transform':list(tuple(transform)[:6]),
              'pixel_area_m2':pixel_area,'model':'projected_nominal','projection_distortion_corrected':False}
        if coordinates=='wgs84':
            converter=pyproj.Transformer.from_crs(4326,crs,always_xy=True);inverse=~transform
            converted=[]
            for fid,polygons in items:
                new=[]
                for polygon in polygons:
                    rings=[]
                    for ring in polygon:
                        if any(abs(x)>180 or abs(y)>90 for x,y in ring) or max(x for x,y in ring)-min(x for x,y in ring)>180:
                            raise ValueError('GeoJSON must use valid longitude/latitude without antimeridian crossing.')
                        try:xx,yy=converter.transform([p[0] for p in ring],[p[1] for p in ring],errcheck=True)
                        except pyproj.exceptions.ProjError as error:raise ValueError('GeoJSON coordinate transformation failed.') from error
                        rings.append([[inverse.a*x+inverse.b*y+inverse.c,inverse.d*x+inverse.e*y+inverse.f] for x,y in zip(xx,yy)])
                    new.append(_polygon(rings))
                converted.append((fid,new))
            items=converted
    rows=[];masks={};whole=image.width*image.height
    def png(im):
        encoded=io.BytesIO();im.save(encoded,'PNG');return encoded.getvalue()
    for i,(fid,polygons) in enumerate(items,1):
        domain=ImageChops.darker(rasterize(polygons,image.size),source_domain)
        foreground=ImageChops.darker(positive,domain)
        count=foreground.histogram()[255];denominator=domain.histogram()[255]
        row={'zone_id':fid,'foreground_pixels':count,'selected_region_pixels':denominator,'whole_image_pixels':whole,
             'coverage_of_region':count/denominator if denominator else None,'coverage_of_image':count/whole}
        if pixel_area is not None:row.update(foreground_area_m2=count*pixel_area,selected_region_area_m2=denominator*pixel_area,
                                           whole_image_area_m2=whole*pixel_area)
        rows.append(row);masks[f'zone-{i:02d}-domain.png']=png(domain);masks[f'zone-{i:02d}-foreground.png']=png(foreground)
    record={'schema':SCHEMA,'software_version':VERSION,'source_bundle_sha256':hashlib.sha256(bundle).hexdigest(),
            'geometry_sha256':hashlib.sha256(geometry).hexdigest(),'coordinates':coordinates,
            'source_geotiff_sha256':hashlib.sha256(raster).hexdigest() if raster is not None else None,'grid':grid,
            'source_task':task,'inference_performed':False,'semantic_accuracy_verified':False,
            'rasterization':'Pixel centers; even-odd rings; holes subtract; MultiPolygon components union; source-scope intersection.',
            'zone_aggregation':'Independent features; overlaps may count in more than one zone. Do not sum overlapping zones as a union.',
            'edge_transformation':'Vertex-only WGS84-to-grid transformation; no edge densification.' if coordinates=='wgs84' else 'Pixel coordinates; no geographic transformation.',
            'zones':rows}
    return record,masks


def zonal_packet(bundle,geometry,*,coordinates='pixel',raster=None):
    record,masks=measure_zones(bundle,geometry,coordinates=coordinates,raster=raster)
    files={'evidence.zip':bundle,'zones.geojson':geometry,'zonal.json':json.dumps(record,indent=2,allow_nan=False).encode(),**masks}
    if raster is not None:files['source.tif']=raster
    manifest={'schema':SCHEMA,'files':{n:{'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()} for n,b in files.items()}}
    files['manifest.json']=json.dumps(manifest,indent=2).encode();out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,raw in files.items():archive.writestr(name,raw)
    if len(out.getvalue())>MAX_PACKET_BYTES:raise ValueError('Zonal packet exceeds size limit.')
    return out.getvalue()


def verify_zonal_packet(payload):
    """Rebuild every domain and measurement, even if modified bytes were rehashed."""
    if len(payload)>MAX_PACKET_BYTES:raise ValueError('Zonal packet exceeds size limit.')
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        entries=archive.infolist();names=archive.namelist()
        if (len(names)!=len(set(names)) or len(names)>69 or sum(e.file_size for e in entries)>MAX_PACKET_BYTES or
                any('/' in n or '\\' in n for n in names)):
            raise ValueError('Zonal packet requires unique bounded flat files.')
        files={n:archive.read(n) for n in names}
    if not {'evidence.zip','zones.geojson','zonal.json','manifest.json'}<=set(files):raise ValueError('Zonal packet is missing required files.')
    manifest=json.loads(files.pop('manifest.json'))
    if (not isinstance(manifest,dict) or manifest.get('schema')!=SCHEMA or
            not isinstance(manifest.get('files'),dict) or set(manifest['files'])!=set(files)):
        raise ValueError('Zonal manifest membership mismatch.')
    for name,raw in files.items():
        if manifest['files'][name]!={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}:
            raise ValueError('Zonal checksum mismatch: '+name)
    saved=json.loads(files['zonal.json'])
    if not isinstance(saved,dict):raise ValueError('Zonal record must be an object.')
    expected,masks=measure_zones(files['evidence.zip'],files['zones.geojson'],coordinates=saved.get('coordinates'),raster=files.get('source.tif'))
    if not isinstance(saved.get('software_version'),str):raise ValueError('Zonal software version must be recorded.')
    expected['software_version']=saved['software_version']
    if json.dumps(saved,sort_keys=True,allow_nan=False)!=json.dumps(expected,sort_keys=True,allow_nan=False):
        raise ValueError('Zonal geometry or measurements do not replay.')
    required={'evidence.zip','zones.geojson','zonal.json',*masks}
    if 'source.tif' in files:required.add('source.tif')
    if set(files)!=required:raise ValueError('Zonal mask membership mismatch.')
    for name,raw in masks.items():
        with Image.open(io.BytesIO(files[name])) as recorded,Image.open(io.BytesIO(raw)) as replay:
            if recorded.mode!='L' or recorded.size!=replay.size or recorded.tobytes()!=replay.tobytes():
                raise ValueError('Zonal domain or foreground does not replay: '+name)
    return {'verified':True,'schema':SCHEMA,'zones':saved['zones'],'scope':'Geometry, scoped denominators and arithmetic replay; no authenticity or semantic accuracy claim.'}
