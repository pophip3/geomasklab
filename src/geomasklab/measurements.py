"""Deterministic mask clipping and pixel measurements, without a server."""
from PIL import Image
from .geometry import candidate_statistics, scope_area_pixels
SCOPE_NAMES = {'all': 'Whole image', 'left': 'Left half', 'right': 'Right half', 'top': 'Top half', 'bottom': 'Bottom half'}

def constrain(mask, side, roi=None):
    w,h=mask.size; region=Image.new('L',(w,h),0)
    boxes={'all':(0,0,w,h),'left':(0,0,w//2,h),'right':(w//2,0,w,h),'top':(0,0,w,h//2),'bottom':(0,h//2,w,h)}
    box=boxes[side]; region.paste(mask.crop(box),box[:2])
    if roi:
        x1,y1,x2,y2=roi['xyxy']
        clipped=Image.new('L',(w,h),0)
        clipped.paste(region.crop((x1,y1,x2,y2)),(x1,y1))
        return clipped
    return region

def foreground_area(mask):
    return sum(mask.histogram()[1:])

def statistics(mask,side,roi=None,full_mask=None):
    w,h=mask.size; area=sum(mask.histogram()[1:]); bbox=mask.getbbox()
    scope_area=scope_area_pixels(w,h,side,roi)
    full=full_mask if full_mask is not None else mask
    left=foreground_area(full.crop((0,0,w//2,h)))
    right=foreground_area(full.crop((w//2,0,w,h)))
    distribution={'basis':'full_mask_before_scope','left_pixels':left,'right_pixels':right}
    if roi:
        distribution['roi_inside_pixels']=area
        distribution['roi_outside_pixels']=left+right-area
    return {'pixel_area':area,'total_pixels':w*h,'area_ratio':area/(w*h),'bbox_xyxy':list(bbox) if bbox else None,
            'scope_area_pixels':scope_area,'scope_area_ratio':area/scope_area if scope_area else None,
            'width':w,'height':h,'scope':side,'scope_label':SCOPE_NAMES[side], 'unit':'pixel',
            'spatial_rule':'Pixel-scope clipping; area_ratio always uses the whole image as its denominator.',
            'spatial_check':mask.tobytes()==constrain(mask,side,roi).tobytes(),
            'roi':roi,'candidate_stats':candidate_statistics(mask),'distribution':distribution,'ground_area_available':False}

