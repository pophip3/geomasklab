"""Supervised buildings, roads and vegetation on the original pixel grid."""
import hashlib
import json
import os
import re
from pathlib import Path
from PIL import Image
from model_services.water_backend import window_starts

TARGET_CLASSES={'building':(8,), 'road':(4,), 'tree':(5,), 'vegetation':(2,5,7)}
PROMPTS={'building':r'(?:(?:all|the|all the) )?(?:buildings?|rooftops?)(?: in (?:the |this )?image)?',
         'road':r'(?:all )?roads?(?: in (?:the |this )?image)?',
         'tree':r'(?:all )?trees?(?: in (?:the |this )?image)?',
         'vegetation':r'(?:all )?(?:vegetation|trees and vegetation)(?: in (?:the |this )?image)?'}
def landcover_target(label,prompt):
    if label in TARGET_CLASSES:return label
    if label is not None:return None
    return next((target for target,pattern in PROMPTS.items() if re.fullmatch(pattern,prompt.strip(),re.I)),None)

def default_landcover_model(target):
    name='road-oem-corrected-v1' if target=='road' else 'landcover-oem-base'
    configured=os.environ.get('GEO_ROAD_MODEL_DIR' if target=='road' else
                              'GEO_BUILDING_MODEL_DIR' if target=='building' else 'GEO_LANDCOVER_MODEL_DIR')
    if configured:return Path(configured)
    root=Path(__file__).resolve().parents[1]
    for base in (root.parent,root.parent.parent):
        folder=base/'models'/name
        if (folder/'model.safetensors').is_file():return folder
    raise ValueError('Land-cover model files are missing: '+name)

class LandcoverBackend:
    def __init__(self,folder,device='cuda:0'):
        import torch,numpy as np
        import segmentation_models_pytorch as smp
        from safetensors.torch import load_file
        folder=Path(folder);manifest=json.loads((folder/'training-manifest.json').read_text(encoding='utf-8'))
        digest=hashlib.sha256((folder/'model.safetensors').read_bytes()).hexdigest()
        if digest!=manifest['weight_sha256'] or manifest['classes']!=9:raise ValueError('Land-cover checkpoint identity mismatch.')
        self.torch,self.np,self.device=torch,np,device
        self.model=smp.Unet(classes=9,activation=None,encoder_weights=None,encoder_name='efficientnet-b4',decoder_attention_type='scse')
        self.model.load_state_dict(load_file(str(folder/'model.safetensors')),strict=True);self.model.to(device).eval()
        self.metadata={'model_name':manifest['model_name'],'checkpoint_sha256':digest,'base_model':manifest['base_model'],
                       'device':device,'precision':'float32','normalization':'RGB / 255',
                       'supported_targets':list(TARGET_CLASSES),
                       'inference_parameters':{'tile_size':512,'stride':256,'rotation_count':4,
                           'probability_threshold':.5,'merge':'Hann-weighted foreground probabilities',
                           'class_ids':{k:list(v) for k,v in TARGET_CLASSES.items()}},
                       'inference_files_sha256':{n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in ('landcover_backend.py','sam_service.py')}}
    def predict(self,image,target,quality='fast'):
        torch,np=self.torch,self.np;classes=TARGET_CLASSES[target]
        rgb=np.asarray(image.convert('RGB'));h,w=rgb.shape[:2]
        ys,xs=window_starts(h),window_starts(w)
        if len(ys)*len(xs)>1024:raise ValueError('Land-cover inference requires at most 1024 tiles.')
        sums=np.zeros((h,w),np.float32);weights=np.zeros_like(sums)
        window=np.maximum(np.outer(np.hanning(512),np.hanning(512)),.05).astype(np.float32)
        flips=(False,True) if quality=='accurate' else (False,)
        with torch.inference_mode():
            for y in ys:
                for x in xs:
                    crop=rgb[y:y+512,x:x+512];ch,cw=crop.shape[:2]
                    crop=np.pad(crop,((0,512-ch),(0,512-cw),(0,0)),mode='edge')
                    t=torch.from_numpy(crop.copy()).permute(2,0,1).float()[None].to(self.device)/255;p=0
                    for k in range(4):
                        rotated=torch.rot90(t,k,(-2,-1))
                        for flip in flips:
                            logits=self.model(rotated.flip(-1) if flip else rotated)
                            v=logits.softmax(1)[:,list(classes)].sum(1)
                            if flip:v=v.flip(-1)
                            p=p+torch.rot90(v,-k,(-2,-1))/(4*len(flips))
                    weighted=window[:ch,:cw]
                    sums[y:y+ch,x:x+cw]+=p[0,:ch,:cw].cpu().numpy()*weighted
                    weights[y:y+ch,x:x+cw]+=weighted
        mask=sums/weights>=.5
        return Image.fromarray(mask.astype(np.uint8)*255),{**self.metadata,'target':target,'class_ids':list(classes),
            'target_definition':{'building':'Building roof surfaces','road':'Road surfaces','tree':'Tree canopy','vegetation':'Trees, low vegetation and agricultural vegetation'}[target],
            'tile_size':512,'stride':256,'tile_count':len(xs)*len(ys),'rotation_count':4,'flip_count':len(flips),
            'probability_threshold':.5,'merge':'Hann-weighted foreground probabilities; threshold once on original image grid',
            'requested_mode':quality,'resolved_mode':quality}
