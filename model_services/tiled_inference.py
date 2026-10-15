"""Contextual crops with non-overlapping core stitching; no accuracy claim."""
from math import ceil

from PIL import Image

TILED_PARAMETERS = {
    'strategy': 'contextual_tiles_core_stitch',
    'core_size_pixels': 512,
    'context_margin_pixels': 64,
    'max_tiles': 256,
    'merge': 'copy each non-overlapping core once; no averaging or binary union',
    'coordinates': 'original image xyxy; half-open intervals',
    'scope': 'whole image; workbench applies the requested region afterwards',
    'accuracy_claim': 'not validated; tiled inference can change predictions',
}


def predict_tiled(backend, image, prompt):
    """Each crop is inferred by the real backend; only its core is retained."""
    size, margin = TILED_PARAMETERS['core_size_pixels'], TILED_PARAMETERS['context_margin_pixels']
    count = ceil(image.width / size) * ceil(image.height / size)
    if count > TILED_PARAMETERS['max_tiles']:
        raise ValueError('Tiled inference requires at most 256 tiles. Split this image before inference.')
    stitched = Image.new('L', image.size, 0)
    windows = []
    for top in range(0, image.height, size):
        for left in range(0, image.width, size):
            right, bottom = min(left + size, image.width), min(top + size, image.height)
            read = (max(0, left - margin), max(0, top - margin),
                    min(image.width, right + margin), min(image.height, bottom + margin))
            crop = image.crop(read)
            mask = backend.predict_mask(crop, prompt)
            if (not isinstance(mask, Image.Image) or mask.mode != 'L' or mask.size != crop.size
                    or set(mask.tobytes()) - {0, 255}):
                raise ValueError('A tile returned an invalid binary mask or dimensions. No partial mask is returned.')
            core = mask.crop((left - read[0], top - read[1], right - read[0], bottom - read[1]))
            stitched.paste(core, (left, top))
            windows.append({'core_xyxy': [left, top, right, bottom], 'read_xyxy': list(read)})
    return stitched, {**TILED_PARAMETERS, 'tile_count': count, 'tile_windows': windows}
