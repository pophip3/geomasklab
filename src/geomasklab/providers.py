"""Local mask adapters; their outputs remain user-reviewed candidates.

The command adapter is available only through the local Python API and CLI.
It receives an argument array, runs without a shell, and must create a fresh,
aligned binary PNG. Provider execution is separate from evidence verification.
"""
from dataclasses import dataclass
import hashlib
import io
import math
from pathlib import Path
import subprocess
import tempfile
from typing import Protocol

from PIL import Image, ImageOps
from .masks import binary_png, MAX_MASK_BYTES


@dataclass(frozen=True)
class MaskProduct:
    mask: bytes
    metadata: dict


class MaskProvider(Protocol):
    def produce(self, image_bytes: bytes) -> MaskProduct:
        """Return a binary PNG on the normalized image grid and source metadata."""


def normalized_image(image_bytes):
    """Use the same displayed orientation as external-mask evidence creation."""
    if not image_bytes or len(image_bytes) > MAX_MASK_BYTES:
        raise ValueError('Images must be 12 MB or smaller.')
    with Image.open(io.BytesIO(image_bytes)) as raw:
        if raw.width * raw.height > 16_000_000 or getattr(raw, 'n_frames', 1) != 1:
            raise ValueError('Use a single image containing no more than 16 million pixels.')
        return ImageOps.exif_transpose(raw).convert('RGB')


def encode_png(image):
    output = io.BytesIO()
    image.save(output, 'PNG')
    return output.getvalue()


def otsu_threshold(histogram):
    """Choose the lowest maximizing threshold on integer contrasts [-510, 510]."""
    total = sum(histogram)
    moment = sum(i * n for i, n in enumerate(histogram))
    left_count = left_moment = 0
    best_score, best_index = -1., next((i for i, n in enumerate(histogram) if n), 510)
    for i, n in enumerate(histogram):
        left_count += n
        left_moment += i * n
        right_count = total - left_count
        if not left_count or not right_count:
            continue
        score = (moment * left_count - left_moment * total) ** 2 / (left_count * right_count)
        if score > best_score:
            best_score, best_index = score, i
    return best_index - 510


@dataclass(frozen=True)
class ExcessGreenProvider:
    """Reproducible RGB contrast baseline, with no trained model or ground truth."""
    threshold: float | None = None

    def produce(self, image_bytes):
        image = normalized_image(image_bytes)
        if self.threshold is not None and (isinstance(self.threshold, bool)
                or not math.isfinite(self.threshold) or not -510 <= self.threshold <= 510):
            raise ValueError('Contrast threshold must be finite and within [-510, 510].')
        rgb = image.tobytes()
        histogram = [0] * 1021
        for i in range(0, len(rgb), 3):
            histogram[2 * rgb[i + 1] - rgb[i] - rgb[i + 2] + 510] += 1
        threshold = otsu_threshold(histogram) if self.threshold is None else self.threshold
        pixels = bytes(255 if 2 * rgb[i + 1] - rgb[i] - rgb[i + 2] > threshold else 0
                       for i in range(0, len(rgb), 3))
        mask = encode_png(Image.frombytes('L', image.size, pixels))
        return MaskProduct(mask, {
            'name': 'excess-green-rgb', 'kind': 'local_baseline',
            'index': '2*G-R-B using 8-bit RGB channels', 'foreground_rule': 'contrast > threshold',
            'threshold': threshold, 'threshold_source': 'otsu_integer_lowest_tie' if self.threshold is None else 'user',
            'neural_model': False, 'input_grid': 'EXIF-normalized RGB',
            'output_sha256': hashlib.sha256(mask).hexdigest(),
            'semantic_status': 'Green-color candidates; vegetation/tree accuracy has not been established.'})


@dataclass(frozen=True)
class CommandProvider:
    """Invoke an explicitly supplied local executable through an argv template.

    At least one argument must contain each of {image} and {output}. Template
    substitution occurs per argument, preserving paths with spaces on Windows.
    Arguments and process output are omitted from exported metadata.
    """
    argv: list[str]
    timeout: float = 300

    def produce(self, image_bytes):
        if (not isinstance(self.argv, list) or not self.argv or
                any(not isinstance(a, str) or not a or '\0' in a for a in self.argv)):
            raise ValueError('Provide a non-empty JSON array of executable arguments.')
        if not all(any(marker in arg for arg in self.argv) for marker in ('{image}', '{output}')):
            raise ValueError('Command arguments must include {image} and {output}.')
        if isinstance(self.timeout, bool) or not math.isfinite(self.timeout) or not 0 < self.timeout <= 3600:
            raise ValueError('Command timeout must be finite and between 0 and 3600 seconds.')
        image = normalized_image(image_bytes)
        with tempfile.TemporaryDirectory(prefix='geomasklab-provider-') as folder:
            root = Path(folder)
            input_path, output_path = root / 'image.png', root / 'mask.png'
            image.save(input_path)
            argv = [a.replace('{image}', str(input_path)).replace('{output}', str(output_path)) for a in self.argv]
            # Fresh output path: a no-op cannot be mistaken for a successful prediction.
            try:
                process = subprocess.run(argv, shell=False, stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=self.timeout, check=False)
            except subprocess.TimeoutExpired as error:
                raise ValueError('External mask command timed out.') from error
            if process.returncode:
                raise ValueError(f'External mask command exited with code {process.returncode}.')
            if not output_path.is_file() or output_path.stat().st_size > MAX_MASK_BYTES:
                raise ValueError('External command must create a fresh binary PNG of at most 12 MB.')
            source = output_path.read_bytes()
            mask = encode_png(binary_png(source, image.size))
        return MaskProduct(mask, {
            'name': Path(self.argv[0]).name, 'kind': 'external_command',
            'shell': False, 'argument_count': len(argv), 'returncode': process.returncode,
            'input_grid': 'EXIF-normalized RGB', 'input_sha256': hashlib.sha256(encode_png(image)).hexdigest(),
            'source_output_sha256': hashlib.sha256(source).hexdigest(),
            'output_sha256': hashlib.sha256(mask).hexdigest(), 'origin_authenticated': False,
            'semantic_status': 'Caller-supplied external tool; model and weights are not authenticated.'})
