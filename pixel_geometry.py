"""Deterministic connected-component measurements, independent of model services."""
from collections import deque


def scope_area_pixels(width, height, side, roi=None):
    """Return the selected rectangle's area, including odd-sized half images.

    Coordinates are zero-based and the upper bounds are exclusive. An empty
    half-image can have zero pixels; its coverage ratio must be reported as null.
    """
    boxes = {'all': (0, 0, width, height), 'left': (0, 0, width // 2, height),
             'right': (width // 2, 0, width, height),
             'top': (0, 0, width, height // 2),
             'bottom': (0, height // 2, width, height)}
    if side not in boxes:
        raise ValueError('Unknown analysis scope.')
    x1, y1, x2, y2 = boxes[side]
    if roi:
        rx1, ry1, rx2, ry2 = roi['xyxy']
        x1, y1, x2, y2 = max(x1, rx1), max(y1, ry1), min(x2, rx2), min(y2, ry2)
    return max(0, x2 - x1) * max(0, y2 - y1)

def candidate_statistics(mask, min_area_pixels=1):
    """Eight-connected candidate regions on the final, spatially constrained mask."""
    w,h=mask.size
    pixels=mask.tobytes()
    seen=bytearray(len(pixels))
    candidates=[]
    raw_count=0
    for seed,value in enumerate(pixels):
        if not value or seen[seed]: continue
        raw_count+=1
        seen[seed]=1
        queue=deque([seed])
        area=0; sx=sy=0; left=w; top=h; right=bottom=0
        while queue:
            index=queue.popleft(); y,x=divmod(index,w)
            area+=1; sx+=x; sy+=y
            left=min(left,x); top=min(top,y); right=max(right,x+1); bottom=max(bottom,y+1)
            for ny in range(max(0,y-1),min(h,y+2)):
                row=ny*w
                for nx in range(max(0,x-1),min(w,x+2)):
                    neighbor=row+nx
                    if pixels[neighbor] and not seen[neighbor]:
                        seen[neighbor]=1; queue.append(neighbor)
        if area>=min_area_pixels:
            candidates.append({'candidate_id':len(candidates)+1,'area_pixels':area,
                               'bbox':{'x':left,'y':top,'width':right-left,'height':bottom-top},
                               'center':{'x':round(sx/area,3),'y':round(sy/area,3)}})
    areas=[item['area_pixels'] for item in candidates]
    return {'label':'candidate_regions','connectivity':8,'min_area_pixels':min_area_pixels,
            'raw_candidate_count':raw_count,'candidate_count':len(candidates),
            'filtered_out_count':raw_count-len(candidates),'total_area_pixels':sum(areas),
            'min_area':min(areas,default=0),'max_area':max(areas,default=0),
            'mean_area':round(sum(areas)/len(areas),3) if areas else 0.0,
            'candidates':candidates,
            'notice':'Connected components are candidates; review their counts and boundaries separately.'}

