"""Binary one-vs-rest scores with explicit ignored pixels and empty-target rules."""
import numpy as np

def scoped_arrays(prediction, ground_truth, valid, scope):
    p,g,v=(np.asarray(x,dtype=bool) for x in (prediction,ground_truth,valid))
    if p.ndim!=2 or p.shape!=g.shape or p.shape!=v.shape:
        raise ValueError('Prediction, human label and valid mask dimensions must match.')
    h,w=p.shape
    boxes={'whole':(0,0,w,h),'right':(w//2,0,w,h),'roi':(w//4,h//4,3*w//4,3*h//4)}
    x1,y1,x2,y2=boxes[scope]
    return tuple(a[y1:y2,x1:x2] for a in (p,g,v))

def score(prediction, ground_truth, valid, scope='whole'):
    p,g,v=scoped_arrays(prediction,ground_truth,valid,scope)
    tp=int((p&g&v).sum());fp=int((p&~g&v).sum());fn=int((~p&g&v).sum());tn=int((~p&~g&v).sum())
    union=tp+fp+fn;denom=2*tp+fp+fn;gt=tp+fn;pred=tp+fp
    return {'tp':tp,'fp':fp,'fn':fn,'tn':tn,'valid_pixels':int(v.sum()),'gt_pixels':gt,'predicted_pixels':pred,
            'iou':tp/union if union else None,'dice':2*tp/denom if denom else None,
            'precision':tp/pred if pred else None,'recall':tp/gt if gt else None,
            'empty_ground_truth':gt==0,'false_positive_image':bool(fp) if gt==0 else None}
