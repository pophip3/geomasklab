"""Original inference adapter for a separately obtained RemoteSAM architecture.

This module imports the user's external source tree. It does not contain the
RemoteSAM architecture, training code, or checkpoint. Its probability restoration
matches the six-image SoftwareX demonstration, rather than the competition
service's argmax / nearest-neighbour restoration.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

from PIL import Image

OFFICIAL_CHECKPOINT_SHA256 = "f85dfa044a527f096b9e41eacfe298040d52e77fca642f46dfe1226745e137e7"
SERVICE_VERSION = "geomasklab-remotesam-adapter/1.0"
STRATEGY = "whole_image_probability_threshold"
PARAMETERS = {
    "strategy": STRATEGY,
    "input_size": [896, 896],
    "image_resize": "bilinear",
    "normalization_mean": [0.485, 0.456, 0.406],
    "normalization_std": [0.229, 0.224, 0.225],
    "max_tokens": 20,
    "probability": "float32 two-class softmax foreground channel 1",
    "restoration": "bilinear",
    "align_corners": False,
    "probability_threshold": 0.5,
    "threshold_operator": ">=",
    "epoc": False,
    "scope": "whole image; region operations belong to the workbench",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_identity(root: Path) -> dict:
    """Identify the files actually available, even for an unversioned archive."""
    files = {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(root.rglob("*.py"))
        if "__pycache__" not in path.parts and ".git" not in path.parts
    }
    if not files:
        raise ValueError("The external source directory contains no Python files.")
    digest = hashlib.sha256()
    for name, file_hash in files.items():
        digest.update((name + "\0" + file_hash + "\n").encode("utf-8"))
    revision = None
    dirty = None
    try:
        revision = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"], check=True,
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--", "."],
            check=True, capture_output=True, text=True, timeout=10,
        ).stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return {"source_git_revision": revision, "source_dirty": dirty,
            "source_tree_sha256": digest.hexdigest(), "source_files_sha256": files}


def validate_source_files(root: Path, lock=None) -> dict:
    """Verify the imported architecture files against the fixed official snapshot."""
    if lock is None:
        lock = json.loads(Path(__file__).with_name('model-lock.json').read_text(encoding='utf-8'))
    expected = lock.get('sam_source_files')
    if not isinstance(expected, dict) or not expected:
        raise ValueError('A fixed RemoteSAM architecture file lock is required.')
    for name, digest in expected.items():
        path = root / name
        if not path.resolve().is_relative_to(root.resolve()) or not path.is_file() or sha256_file(path) != digest:
            raise ValueError('External RemoteSAM source differs from the fixed official snapshot: ' + name)
    return {'verified_architecture_revision': lock['sam_source_revision'],
            'architecture_files_sha256': dict(expected), 'architecture_file_lock_verified': True}


def validate_checkpoint_diagnostics(missing, unexpected, tensor_count: int) -> dict:
    """Allow only the generated BERT position-id buffer to be absent."""
    missing, unexpected = list(missing), list(unexpected)
    if set(missing) - {"text_encoder.embeddings.position_ids"} or unexpected:
        raise ValueError("Checkpoint architecture mismatch: missing trained tensors or unexpected keys.")
    if tensor_count != 1107:
        raise ValueError("The fixed RemoteSAMv1 checkpoint must contain 1107 state tensors.")
    return {"missing_keys": missing, "unexpected_keys": unexpected,
            "checkpoint_tensor_count": tensor_count}


class RemoteSAMBackend:
    """Own one model instance; the HTTP service serializes all inference calls."""

    def __init__(self, source_root, checkpoint, tokenizer, *, device="cuda:0",
                 fp16=True, expected_checkpoint_sha256=OFFICIAL_CHECKPOINT_SHA256):
        root = Path(source_root).expanduser().resolve(strict=True)
        checkpoint = Path(checkpoint).expanduser().resolve(strict=True)
        tokenizer = Path(tokenizer).expanduser().resolve(strict=True)
        for name in ("args.py", "lib/segmentation.py", "lib/_utils.py"):
            if not (root / name).is_file():
                raise ValueError("--source-root must contain the external RemoteSAM architecture: " + name)
        if not checkpoint.is_file() or not tokenizer.is_dir() or not (tokenizer / "vocab.txt").is_file():
            raise ValueError("Provide the checkpoint file and a local bert-base-uncased tokenizer with vocab.txt.")
        if not isinstance(expected_checkpoint_sha256, str) or len(expected_checkpoint_sha256) != 64:
            raise ValueError("An expected checkpoint SHA-256 is required.")
        actual_hash = sha256_file(checkpoint)
        if actual_hash != expected_checkpoint_sha256.lower():
            raise ValueError("Checkpoint SHA-256 does not match the expected model snapshot.")
        if actual_hash != OFFICIAL_CHECKPOINT_SHA256:
            raise ValueError("This adapter is locked to the official RemoteSAMv1 checkpoint.")

        # Heavy packages are loaded only when a real backend is explicitly built.
        import numpy as np
        import torch
        from transformers import BertConfig, BertModel, BertTokenizer
        from torchvision.transforms import functional as vision

        if device.startswith("cuda") and not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested but no CUDA device is available.")
        if device != "cpu" and not device.startswith("cuda:"):
            raise ValueError("Use cpu or an explicit CUDA device such as cuda:0.")
        self.torch, self.np, self.vision = torch, np, vision
        self.device = device
        self.fp16 = bool(fp16 and device.startswith("cuda:"))
        self.identity = {**source_identity(root), **validate_source_files(root)}

        # Avoid accidentally using similarly named modules from another checkout.
        for name in ("args", "lib", "lib.segmentation", "lib._utils", "arc"):
            old = sys.modules.get(name)
            filename = getattr(old, "__file__", None)
            if old is not None and (not filename or not Path(filename).resolve().is_relative_to(root)):
                raise RuntimeError("An incompatible external module is already imported: " + name)
        sys.path.insert(0, str(root))
        args_module = importlib.import_module("args")
        segmentation = importlib.import_module("lib.segmentation")
        args = args_module.get_parser().parse_args([])
        args.device, args.window12, args.swin_type = device, True, "base"

        # RemoteSAMv1 contains all trained BERT tensors. The original architecture
        # calls from_pretrained only for initialization; substitute a local standard
        # BERT structure during this one construction, then verify every loaded key.
        with patch.object(BertModel, "from_pretrained", side_effect=lambda *a, **k: BertModel(BertConfig())):
            model = segmentation.lavt_one(pretrained="", args=args)

        if not hasattr(torch.serialization, "safe_globals"):
            raise RuntimeError("Use the documented PyTorch version with safe_globals checkpoint loading.")
        with torch.serialization.safe_globals([argparse.Namespace]):
            payload = torch.load(checkpoint, map_location="cpu", weights_only=True, mmap=True)
        if not isinstance(payload, dict) or not isinstance(payload.get("model"), dict):
            raise ValueError("Checkpoint has no model state dictionary.")
        state = payload["model"]
        if any(not isinstance(name, str) or not torch.is_tensor(tensor) for name, tensor in state.items()):
            raise ValueError("The model state must contain named tensors only.")
        incompatible = model.load_state_dict(state, strict=False)
        diagnostics = validate_checkpoint_diagnostics(
            incompatible.missing_keys, incompatible.unexpected_keys, len(state))
        # Generated buffers are the only permitted missing values, never parameters.
        if set(incompatible.missing_keys) & set(dict(model.named_parameters())):
            raise ValueError("Checkpoint is missing a trained parameter.")
        del payload, state
        self.model = model.to(device).eval()
        self.tokenizer = BertTokenizer.from_pretrained(str(tokenizer), local_files_only=True)
        torch.set_num_threads(1)
        torch.manual_seed(0)
        torch.backends.cudnn.benchmark = False
        self.metadata = {
            "service_version": SERVICE_VERSION, "model_name": "RemoteSAMv1",
            "checkpoint_sha256": actual_hash, "checkpoint_diagnostics": diagnostics,
            "device": device, "fp16": self.fp16, "epoc": False,
            "precision": "FP16 CUDA autocast" if self.fp16 else "float32",
            "supported_quality_modes": ["fast"], "adapter_parameters": dict(PARAMETERS),
            "packages": {name: importlib.metadata.version(name) for name in
                         ("torch", "torchvision", "transformers", "numpy", "Pillow", "timm", "mmcv")},
            "tokenizer_files_sha256": {
                name: sha256_file(tokenizer / name) for name in
                ("vocab.txt", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json", "config.json")
                if (tokenizer / name).is_file()
            },
            **self.identity,
        }
        if device.startswith("cuda:"):
            self.metadata["gpu"] = torch.cuda.get_device_name(torch.device(device))

    def predict_mask(self, image: Image.Image, prompt: str) -> Image.Image:
        """Return a restored L-mode binary PNG-compatible mask, never an ROI."""
        from contextlib import nullcontext
        torch, np = self.torch, self.np
        scaled = self.vision.resize(image.convert("RGB"), [896, 896])
        tensor = self.vision.to_tensor(scaled)
        tensor = self.vision.normalize(tensor, PARAMETERS["normalization_mean"],
                                       PARAMETERS["normalization_std"]).unsqueeze(0).to(self.device)
        tokens = self.tokenizer.encode(prompt, add_special_tokens=True)[:20]
        padded = tokens + [0] * (20 - len(tokens))
        attention = [1] * len(tokens) + [0] * (20 - len(tokens))
        token_tensor = torch.tensor([padded], dtype=torch.long, device=self.device)
        attention_tensor = torch.tensor([attention], dtype=torch.long, device=self.device)
        context = torch.autocast("cuda", dtype=torch.float16) if self.fp16 else nullcontext()
        with torch.inference_mode(), context:
            output = self.model(tensor, token_tensor, l_mask=attention_tensor)
        if output.ndim != 4 or tuple(output.shape[:2]) != (1, 2):
            raise ValueError("RemoteSAM returned unexpected logits dimensions.")
        logits = output.detach().float()
        probability = torch.softmax(logits, dim=1)[:, 1:2]
        restored = torch.nn.functional.interpolate(
            probability, size=(image.height, image.width), mode="bilinear", align_corners=False)[0, 0]
        if not bool(torch.isfinite(restored).all()):
            raise ValueError("RemoteSAM returned nonfinite foreground probabilities.")
        mask = (restored >= 0.5).to(torch.uint8).cpu().numpy() * np.uint8(255)
        return Image.fromarray(mask)
