"""Explicit local raster-window rendering with retained georeference and provenance."""
import hashlib
import io
import math
from pathlib import Path
from PIL import Image
from .masks import MAX_MASK_PIXELS


def render_raster(path,*,bands,window=None,value_range=None):
    """Return RGB PNG/TIFF plus the exact band, window and scaling contract.

    Non-uint8 inputs require a caller-specified common value range. No automatic
    histogram stretch, reprojection, resizing or nodata filling is performed.
    The full input remains external; its streaming hash is retained in metadata.
    """
    from .geospatial import dependencies
    np,rasterio,_=dependencies();path=Path(path)
    if not path.is_file():raise ValueError('Raster input must be a local file.')
    if not isinstance(bands,(list,tuple)) or len(bands)!=3 or any(type(b) is not int or b<1 for b in bands):
        raise ValueError('Select exactly three one-based RGB band indexes.')
    digest=hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda:source.read(1024*1024),b''):digest.update(block)
    with rasterio.open(path) as source:
        if source.driver!='GTiff' or source.crs is None:raise ValueError('Use a GeoTIFF with an explicit CRS.')
        if max(bands)>source.count:raise ValueError('Selected band index exceeds the source band count.')
        bounds=[0,0,source.width,source.height] if window is None else window
        if (not isinstance(bounds,(list,tuple)) or len(bounds)!=4 or any(type(v) is not int for v in bounds)):
            raise ValueError('Window requires integer column, row, width and height.')
        x,y,w,h=bounds
        if min(x,y)<0 or min(w,h)<1 or x+w>source.width or y+h>source.height or w*h>MAX_MASK_PIXELS:
            raise ValueError('Window must be inside the raster and contain at most 64 million pixels.')
        selection=rasterio.windows.Window(x,y,w,h)
        if np.any(source.read_masks(bands,window=selection)!=255):raise ValueError('Selected window contains nodata or masked pixels.')
        raw=source.read(bands,window=selection)
        if not np.all(np.isfinite(raw)):raise ValueError('Selected pixels must all be finite.')
        if value_range is None:
            if raw.dtype!=np.uint8:raise ValueError('Non-uint8 input requires an explicit --value-range LOW HIGH.')
            rgb=raw
            scale={'method':'identity_uint8'}
        else:
            if (not isinstance(value_range,(list,tuple)) or len(value_range)!=2 or
                    any(type(v) not in (int,float) or not math.isfinite(v) for v in value_range) or value_range[0]>=value_range[1]):
                raise ValueError('Scaling range must contain finite LOW < HIGH.')
            low,high=value_range
            values=(raw.astype('float64')-low)*255/(high-low)
            rgb=np.floor(np.clip(values,0,255)+.5).astype('uint8')
            scale={'method':'clip_linear_round_half_up','input_range':[low,high],'output_range':[0,255],
                   'clipped_values':int(np.count_nonzero((raw<low)|(raw>high)))}
        transform=source.window_transform(selection);crs=source.crs
        if not all(math.isfinite(v) for v in tuple(transform)[:6]) or not transform.determinant:
            raise ValueError('Source window requires a finite non-singular affine transform.')
        dtypes=[source.dtypes[i-1] for i in bands];source_size=[source.width,source.height]
    with rasterio.io.MemoryFile() as memory:
        with memory.open(driver='GTiff',width=w,height=h,count=3,dtype='uint8',crs=crs,transform=transform,compress='deflate') as output:
            output.write(rgb)
        tiff=memory.read()
    out=io.BytesIO();Image.fromarray(rgb.transpose(1,2,0)).save(out,'PNG');png=out.getvalue()
    metadata={'schema':'geomasklab-raster-rendering/1.0','source_sha256':digest.hexdigest(),'source_bytes':path.stat().st_size,
        'source_dimensions':source_size,'source_band_types':dtypes,'rgb_band_indexes':list(bands),'window':list(bounds),
        'scaling':scale,'crs_wkt':crs.to_wkt(),'transform':list(tuple(transform)[:6]),
        'png_sha256':hashlib.sha256(png).hexdigest(),'rendered_geotiff_sha256':hashlib.sha256(tiff).hexdigest(),
        'resampling_performed':False,'reprojection_performed':False,'source_embedded':False}
    return png,tiff,metadata
