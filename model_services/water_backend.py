"""Supervised RGB water segmentation with overlapping original-resolution tiles."""
from pathlib import Path
import hashlib
import json
import re

from PIL import Image

WATER_PROMPT = re.compile(
    r'^(?:(?:all|the|all the) )?(?:water(?: bod(?:y|ies))?|lakes?|rivers?|ponds?|reservoirs?)'
    r'(?: in (?:the |this )?image)?$', re.I)


def is_water_request(label, prompt):
    return label == 'water' or (label is None and bool(WATER_PROMPT.fullmatch(prompt.strip())))


def window_starts(length, size=512, stride=256):
    if length <= size:
        return [0]
    starts = list(range(0, length - size + 1, stride))
    if starts[-1] != length - size:
        starts.append(length - size)
    return starts


def default_water_model():
    import os
    configured = os.environ.get('GEO_WATER_MODEL_DIR')
    if configured:
        return Path(configured)
    root = Path(__file__).resolve().parents[1]
    for base in (root.parent, root.parent.parent):
        folder = base / 'models/water-oem-corrected-v7'
        if (folder / 'model.safetensors').is_file():
            return folder
    raise ValueError('Water model files are missing. Set GEO_WATER_MODEL_DIR to the installed water model directory.')


class WaterBackend:
    def __init__(self, model_dir, device='cuda:0'):
        import torch
        import numpy as np
        from transformers import SegformerForSemanticSegmentation, SegformerImageProcessor
        folder = Path(model_dir).resolve(strict=True)
        manifest = json.loads((folder / 'training-manifest.json').read_text(encoding='utf-8'))
        digest = hashlib.sha256((folder / 'model.safetensors').read_bytes()).hexdigest()
        if digest != manifest['weight_sha256']:
            raise ValueError('Water model weight checksum mismatch.')
        self.torch, self.np, self.device = torch, np, device
        self.processor = SegformerImageProcessor.from_pretrained(str(folder), local_files_only=True)
        self.model = SegformerForSemanticSegmentation.from_pretrained(str(folder), local_files_only=True).to(device).eval()
        if self.model.config.id2label.get(6, '').lower() != 'water':
            raise ValueError('The water model class mapping is incorrect.')
        self.metadata = {
            'model_name': 'GeoMaskLab-Water-SegFormer-v1', 'checkpoint_sha256': digest,
            'base_model': manifest['base_model'], 'base_revision': manifest['base_revision'],
            'device': device, 'precision': 'float32', 'water_class_id': 6,
            'strategy': 'supervised_water_overlapping_rgb_tiles',
            'tile_size': 512, 'stride': 256, 'probability_threshold': 0.5,
            'normalization_mean': list(self.processor.image_mean),
            'normalization_std': list(self.processor.image_std),
        }

    def predict(self, image, quality='fast'):
        torch, np = self.torch, self.np
        rgb = np.asarray(image.convert('RGB'))
        ys, xs = window_starts(image.height), window_starts(image.width)
        if len(xs) * len(ys) > 1024:
            raise ValueError('Water inference requires at most 1024 tiles.')
        accumulated = np.zeros((image.height, image.width), dtype=np.float32)
        weights = np.zeros_like(accumulated)
        weight = np.maximum(np.outer(np.hanning(512), np.hanning(512)), 0.05).astype(np.float32)
        flips = ((), (-1,)) if quality == 'accurate' else ((),)
        with torch.inference_mode():
            for top in ys:
                for left in xs:
                    crop = rgb[top:top + 512, left:left + 512]
                    height, width = crop.shape[:2]
                    if height < 512 or width < 512:
                        crop = np.pad(crop, ((0, 512-height), (0, 512-width), (0, 0)), mode='edge')
                    pixels = self._pixels(crop)
                    probability = 0
                    for rotation in range(4):
                        rotated = torch.rot90(pixels, rotation, (-2, -1))
                        for dims in flips:
                            logits = self._logits(rotated.flip(dims) if dims else rotated).float()
                            p = logits.softmax(dim=1)[:, 6:7]
                            p = torch.nn.functional.interpolate(p, size=(512, 512), mode='bilinear', align_corners=False)
                            p = p.flip(dims) if dims else p
                            p = torch.rot90(p, -rotation, (-2, -1))
                            probability = probability + p / (4 * len(flips))
                    p = probability[0, 0, :height, :width].cpu().numpy()
                    weighted = weight[:height, :width]
                    accumulated[top:top+height, left:left+width] += p * weighted
                    weights[top:top+height, left:left+width] += weighted
        mask = accumulated / weights >= 0.5
        if getattr(self, 'refiner', None) is not None:
            mask = self.refiner.refine(image, mask)
        parameters = {**self.metadata, 'tile_count': len(xs)*len(ys),
                      'flip_count': len(flips), 'rotation_count': 4, 'requested_mode': quality, 'resolved_mode': quality,
                      'merge': 'weighted mean of foreground probabilities before one final threshold'}
        return Image.fromarray((mask * 255).astype(np.uint8), mode='L'), parameters

    def predict_mask(self, image, prompt):
        return self.predict(image)[0]

    def _pixels(self, crop):
        return self.processor(images=Image.fromarray(crop), return_tensors='pt')['pixel_values'].to(self.device)

    def _logits(self, pixels):
        return self.model(pixel_values=pixels).logits


class OEMWaterBackend(WaterBackend):
    """OpenEarthMap UNet-B4 with water and background correction training."""
    def __init__(self, model_dir, device='cuda:0'):
        import torch
        import numpy as np
        import segmentation_models_pytorch as smp
        from safetensors.torch import load_file
        folder = Path(model_dir).resolve(strict=True)
        manifest = json.loads((folder/'training-manifest.json').read_text(encoding='utf-8'))
        digest = hashlib.sha256((folder/'model.safetensors').read_bytes()).hexdigest()
        if digest != manifest['weight_sha256'] or manifest['water_class'] != 6 or manifest['classes'] != 9:
            raise ValueError('Water model checksum or class mapping mismatch.')
        self.torch, self.np, self.device = torch, np, device
        self.model = smp.Unet(classes=9, activation=None, encoder_weights=None,
                              encoder_name='efficientnet-b4', decoder_attention_type='scse')
        self.model.load_state_dict(load_file(str(folder/'model.safetensors')), strict=True)
        self.model.to(device).eval()
        from model_services.water_refinement import WaterBoundaryRefiner, default_refiner_checkpoint
        adjacent_refiner = folder.parent / 'sam_vit_h_4b8939.pth'
        self.refiner = WaterBoundaryRefiner(adjacent_refiner if adjacent_refiner.is_file() else default_refiner_checkpoint(), device)
        self.metadata = {
            'model_name': manifest['model_name'], 'checkpoint_sha256': digest,
            'base_model': manifest['base_model'], 'device': device, 'precision': 'float32',
            'water_class_id': 6, 'strategy': 'supervised_water_overlapping_rgb_tiles',
            'tile_size': 512, 'stride': 256, 'probability_threshold': 0.5,
            'normalization': 'RGB / 255',
            **self.refiner.metadata,
            'inference_files_sha256': {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                      for name in ('water_backend.py', 'water_refinement.py', 'sam_service.py')},
        }

    def _pixels(self, crop):
        return self.torch.from_numpy(crop.copy()).permute(2, 0, 1).float().div(255).unsqueeze(0).to(self.device)

    def _logits(self, pixels):
        return self.model(pixels)
