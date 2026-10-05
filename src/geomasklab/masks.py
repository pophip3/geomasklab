"""Lossless binary PNG inputs in the displayed image's pixel coordinates."""
import base64
import io
from PIL import Image, ImageChops

MAX_MASK_BYTES = 12 * 1024 * 1024
MAX_MASK_PIXELS = 16 * 1024 * 1024


def decode_mask(value):
    """Decode a bounded JSON upload, without interpreting filenames as paths."""
    if not isinstance(value, str) or len(value) > 16 * 1024 * 1024 + 100:
        raise ValueError('Upload a binary PNG mask no larger than 12 MB.')
    try:
        raw = base64.b64decode(value.split(',')[-1], validate=True)
    except ValueError as error:
        raise ValueError('The mask upload is not valid base64.') from error
    if not raw or len(raw) > MAX_MASK_BYTES:
        raise ValueError('Upload a binary PNG mask no larger than 12 MB.')
    return raw


def binary_png(raw, size):
    """Accept only exact binary pixels; never resize, orient or threshold labels.

    Grayscale values must be 0/1 or 0/255. RGB masks are accepted only when
    all channels are identical; alpha must be opaque. Palette, probability,
    multiclass and animated images require explicit conversion by the user.
    """
    if not raw or len(raw) > MAX_MASK_BYTES:
        raise ValueError('Binary PNG masks must be 12 MB or smaller.')
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format != 'PNG' or getattr(image, 'n_frames', 1) != 1:
                raise ValueError('Use a single-frame binary PNG mask.')
            if image.size != tuple(size) or image.width * image.height > MAX_MASK_PIXELS:
                raise ValueError('Mask dimensions must exactly match the displayed image; no resizing is performed.')
            if image.getexif().get(274, 1) != 1:
                raise ValueError('Orient the mask explicitly to the displayed image before importing.')
            image.load()
            if image.mode in ('RGBA', 'LA'):
                if image.getchannel('A').getextrema() != (255, 255):
                    raise ValueError('Transparent masks are not supported; use opaque binary pixels.')
                image = image.convert('RGB' if image.mode == 'RGBA' else 'L')
            if image.mode == 'RGB':
                r, g, b = image.split()
                if ImageChops.difference(r, g).getbbox() or ImageChops.difference(r, b).getbbox():
                    raise ValueError('Color-coded masks are not supported; export a binary grayscale PNG.')
                image = r
            elif image.mode == '1':
                image = image.convert('L')
            elif image.mode != 'L':
                raise ValueError('Export an 8-bit binary grayscale PNG, not a palette or multiclass image.')
            values = {i for i, count in enumerate(image.histogram()) if count}
            if values <= {0, 1}:
                return image.point(lambda v: 255 if v else 0)
            if values <= {0, 255}:
                return image.copy()
            raise ValueError('Mask values must be 0/1 or 0/255; thresholds and class mappings are never inferred.')
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError('Could not read a supported binary PNG mask.') from error


def source_text(value):
    """Require explicit, bounded provenance without claiming its authenticity."""
    if not isinstance(value, str) or not value.strip() or len(value) > 1000 or '\x00' in value:
        raise ValueError('Describe the mask source in 1–1,000 characters.')
    return value.strip()
