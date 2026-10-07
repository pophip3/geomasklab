"""Local HTTP mask adapter; no upstream source or weights are redistributed."""
from __future__ import annotations

import argparse
import base64
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time

from PIL import Image, UnidentifiedImageError

from model_services.sam_backend import PARAMETERS, SERVICE_VERSION, RemoteSAMBackend

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 64_000_000
MAX_REQUEST_BYTES = 28 * 1024 * 1024
CLASSES = {"building", "aircraft", "road", "water", "tree", "ship"}


def decode_image(encoded: str) -> Image.Image:
    if not isinstance(encoded, str) or len(encoded) > MAX_REQUEST_BYTES:
        raise ValueError("The image must be a size-limited base64 string.")
    if encoded.startswith("data:"):
        if not encoded.startswith("data:image/png;base64,"):
            raise ValueError("Only PNG data URLs are accepted.")
        encoded = encoded.split(",", 1)[1]
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error):
        raise ValueError("Invalid base64 image data.") from None
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("Decoded image exceeds the 20 MiB limit or is empty.")
    try:
        image = Image.open(io.BytesIO(raw))
        if image.format != "PNG":
            raise ValueError("The workbench contract requires a normalized PNG image.")
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise ValueError("Image exceeds the 64-million-pixel limit.")
        image.load()
        return image.convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError("The payload is not a supported PNG image.") from None


def encode_binary_mask(mask: Image.Image, size: tuple[int, int]) -> tuple[str, int]:
    if not isinstance(mask, Image.Image) or mask.mode != "L" or mask.size != size:
        raise ValueError("Backend mask must be L-mode and match the original image dimensions.")
    pixels = mask.tobytes()
    if set(pixels) - {0, 255}:
        raise ValueError("Backend returned a nonbinary mask; measurement requires values 0 and 255.")
    output = io.BytesIO()
    mask.save(output, format="PNG")
    return base64.b64encode(output.getvalue()).decode("ascii"), pixels.count(255)


def validate_request(payload: dict) -> tuple[str, str, str | None, str]:
    if not isinstance(payload, dict):
        raise ValueError("The request must be a JSON object.")
    if set(payload) - {"task", "image", "text", "classes", "quality_mode", "return_probability"}:
        raise ValueError("Unknown request fields; ROI and mask resizing are workbench operations.")
    requested = payload.get("quality_mode", "fast")
    if requested not in ("fast", "auto"):
        raise ValueError("This adapter supports fast only. Accurate tiled inference is not implemented.")
    if payload.get("return_probability", False) is not False:
        raise ValueError("This adapter returns a binary mask only.")
    task = payload.get("task")
    if task == "referring_seg":
        prompt = payload.get("text")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 256 or not prompt.isascii():
            raise ValueError("Referring segmentation requires a nonempty English prompt of at most 256 characters.")
        if payload.get("classes"):
            raise ValueError("A referring request cannot also provide semantic classes.")
        return task, prompt.strip(), None, requested
    if task == "semantic_seg":
        classes = payload.get("classes")
        if (not isinstance(classes, list) or len(classes) != 1 or
                not isinstance(classes[0], str) or classes[0] not in CLASSES):
            raise ValueError("Provide one supported semantic class: building, aircraft, road, water, tree or ship.")
        if payload.get("text"):
            raise ValueError("A semantic request cannot also provide a referring prompt.")
        label = classes[0]
        return task, label + " in the image", label, requested
    raise ValueError("Use task referring_seg or semantic_seg.")


class SAMService:
    """Protocol facade with an injectable backend for CPU-only contract tests."""

    def __init__(self, backend=None, load_error=None):
        self.backend = backend
        self.load_error = load_error
        self.lock = threading.Lock()

    @property
    def ready(self):
        return self.backend is not None

    def metadata(self):
        return dict(getattr(self.backend, "metadata", {}))

    def predict(self, payload):
        if not self.ready:
            raise RuntimeError("RemoteSAM is not ready; inspect /model-info and the startup log.")
        started = time.perf_counter()
        task, prompt, label, requested = validate_request(payload)
        image = decode_image(payload.get("image"))
        with self.lock:
            mask = self.backend.predict_mask(image, prompt)
            encoded, area = encode_binary_mask(mask, image.size)
        parameters = {**PARAMETERS, "requested_mode": requested, "resolved_mode": "fast", "tile_count": 1}
        result = {
            "status": "success", "task": task, "mask": encoded,
            "original_size": list(image.size), "output_size": list(mask.size),
            "quality_mode": "fast", "requested_quality_mode": requested,
            "mode_parameters": parameters, "parameters": dict(PARAMETERS),
            "service_version": SERVICE_VERSION, "model": self.metadata(),
            "quality": {"foreground_pixels": area, "foreground_ratio": area / (image.width * image.height),
                        "empty_mask": area == 0},
            "warnings": ["An empty prediction does not prove target absence."] if not area else [],
            "timing_ms": {"total": round((time.perf_counter() - started) * 1000, 2)},
        }
        if label:
            result["masks"] = {label: encoded}
        return result


def make_handler(service: SAMService):
    """Create an isolated handler class for the supplied model instance."""
    class Handler(BaseHTTPRequestHandler):
        server_version = "GeoMaskLab-RemoteSAM"

        def send_json(self, code, value):
            body = json.dumps(value, allow_nan=False, separators=(",", ":")).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                return self.send_json(200, {"status": "ok", "model_ready": service.ready,
                                            "service_version": SERVICE_VERSION})
            if self.path == "/ready":
                return self.send_json(200 if service.ready else 503,
                    {"status": "ready" if service.ready else "not_ready", "model_ready": service.ready,
                     "supported_quality_modes": ["fast"], **service.metadata()})
            if self.path == "/model-info":
                return self.send_json(200, {"ready": service.ready, "error": service.load_error,
                                            "service_version": SERVICE_VERSION, **service.metadata()})
            self.send_json(404, {"status": "error", "message": "Unknown endpoint."})

        def do_POST(self):
            if self.path != "/predict":
                return self.send_json(404, {"status": "error", "message": "Unknown endpoint."})
            try:
                raw_length = self.headers.get("Content-Length", "")
                if not raw_length.isdigit() or not 0 < int(raw_length) <= MAX_REQUEST_BYTES:
                    raise ValueError("Missing or excessive request Content-Length.")
                self.connection.settimeout(30)
                raw = self.rfile.read(int(raw_length))
                if len(raw) != int(raw_length):
                    raise ValueError("Incomplete request body.")
                # Consume a bounded body before replying. Closing a Windows
                # socket with unread bytes can discard the HTTP error response.
                if self.headers.get("Transfer-Encoding"):
                    raise ValueError("Chunked requests are unsupported; provide Content-Length.")
                if self.headers.get_content_type() != "application/json":
                    raise ValueError("Use Content-Type application/json.")
                if not service.ready:
                    return self.send_json(503, {"status": "error", "message": "RemoteSAM is not ready."})
                payload = json.loads(raw.decode("utf-8"))
                self.send_json(200, service.predict(payload))
            except (ValueError, TypeError, UnicodeDecodeError) as exc:
                self.send_json(400, {"status": "error", "message": str(exc)})
            except Exception:
                self.send_json(500, {"status": "error", "message": "Model inference failed; inspect the service log."})
                import traceback
                traceback.print_exc()

    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, help="Separately obtained external RemoteSAM architecture directory")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--tokenizer", required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--no-fp16", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=6657)
    args = parser.parse_args(argv)
    try:
        backend = RemoteSAMBackend(args.source_root, args.checkpoint, args.tokenizer,
                                   device=args.device, fp16=not args.no_fp16)
        service = SAMService(backend)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        service = SAMService(load_error=type(exc).__name__ + ": " + str(exc))
    server = ThreadingHTTPServer((args.host, args.port), make_handler(service))
    print(f"RemoteSAM adapter: http://{args.host}:{server.server_port}; model_ready={service.ready}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
