"""Image-edge refinement from automatic water and non-water prompts."""
from pathlib import Path
import hashlib

SAM_SHA256 = 'a7bf3b02f3ebf1267aba913ff637d9a2d5c33d3173bb679e46d9f338c26f262e'


def checkpoint_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def merge_boundaries(mask, edges):
    import cv2
    import numpy as np
    positive = mask.astype(np.uint8)
    outer = cv2.dilate(positive, np.ones((17, 17), np.uint8)).astype(bool)
    inner = cv2.erode(positive, np.ones((17, 17), np.uint8)).astype(bool)
    # Preserve both semantic interiors. Otherwise SAM can refill thin piers
    # that the classifier correctly excluded, especially after oblique rotation.
    nonwater_interior = cv2.erode((~mask).astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    return (inner | (edges.astype(bool) & outer)) & ~nonwater_interior


def default_refiner_checkpoint():
    import os
    configured = os.environ.get('GEO_WATER_REFINER_CHECKPOINT')
    if configured:
        return Path(configured)
    root = Path(__file__).resolve().parents[1]
    for base in (root.parent, root.parent.parent):
        path = base / 'models/sam_vit_h_4b8939.pth'
        if path.is_file():
            return path
    raise ValueError('SAM edge-refiner checkpoint is missing.')


def sample_points(area, count, spacing=30):
    import cv2
    import numpy as np
    distance = cv2.distanceTransform(area.astype(np.uint8), cv2.DIST_L2, 5)
    points = []
    for _ in range(count):
        _, maximum, _, position = cv2.minMaxLoc(distance)
        if maximum < 1:
            break
        points.append(position)
        cv2.circle(distance, position, spacing, 0, -1)
    return points


class WaterBoundaryRefiner:
    def __init__(self, checkpoint, device='cuda:0'):
        import torch
        from segment_anything import sam_model_registry, SamPredictor
        path = Path(checkpoint).resolve(strict=True)
        digest = checkpoint_sha256(path)
        if digest != SAM_SHA256:
            raise ValueError('SAM edge-refiner checkpoint checksum mismatch.')
        self.torch, self.device = torch, device
        self.predictor = SamPredictor(sam_model_registry['vit_h'](checkpoint=str(path)).eval())
        self.metadata = {'boundary_refiner': 'SAM-ViT-H', 'refiner_checkpoint_sha256': digest,
                         'positive_points': 20, 'negative_points': 40, 'prompt_spacing': 30,
                         'boundary_band_pixels': 8, 'nonwater_interior_margin_pixels': 1,
                         'refinement': 'image edges with preserved water and non-water interiors'}

    def refine(self, image, mask):
        import cv2
        import numpy as np
        if not mask.any():
            return mask
        torch = self.torch
        execution_device = self.device
        if str(self.device).startswith('cuda'):
            free, _ = torch.cuda.mem_get_info(self.device)
            if free < 4.5 * 1024**3:
                execution_device = 'cpu'
        positive = sample_points(mask, 20)
        border = cv2.dilate(mask.astype(np.uint8), np.ones((31, 31), np.uint8)).astype(bool) & ~mask
        negative = sample_points(border, 40)
        points = np.asarray(positive + negative)
        labels = np.asarray([1] * len(positive) + [0] * len(negative))
        try:
            self.predictor.model.to(execution_device)
            self.predictor.set_image(np.asarray(image.convert('RGB')))
            logits = torch.tensor(np.where(mask, 4., -4.), dtype=torch.float32)[None, None]
            logits = torch.nn.functional.interpolate(logits, size=self.predictor.input_size,
                                                     mode='bilinear', align_corners=False)
            logits = torch.nn.functional.pad(logits, (0, 1024-logits.shape[-1], 0, 1024-logits.shape[-2]), value=-4)
            logits = torch.nn.functional.interpolate(logits, size=(256, 256), mode='bilinear', align_corners=False)[0].numpy()
            with torch.inference_mode():
                masks, _, _ = self.predictor.predict(point_coords=points, point_labels=labels,
                                                     mask_input=logits, multimask_output=False)
            return merge_boundaries(mask, masks[0])
        finally:
            self.predictor.reset_image()
            self.predictor.model.to('cpu')
            if str(execution_device).startswith('cuda'):
                torch.cuda.empty_cache()
