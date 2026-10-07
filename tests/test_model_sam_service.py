"""Contract tests for the optional adapter; fixtures are never model evidence."""
import base64
from http.server import ThreadingHTTPServer
import io
import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image

from model_services.sam_backend import validate_checkpoint_diagnostics
from model_services.sam_service import SAMService, make_handler


def encoded(image):
    output = io.BytesIO()
    image.save(output, "PNG")
    return base64.b64encode(output.getvalue()).decode("ascii")


class FixtureBackend:
    metadata = {"checkpoint_sha256": "fixture-only", "service_version": "fixture-only"}

    def __init__(self):
        self.calls = []
        self.result = Image.new("L", (13, 7), 0)
        self.result.paste(255, (6, 0, 13, 7))

    def predict_mask(self, image, prompt):
        self.calls.append((image.size, prompt))
        return self.result.copy()


class OptionalSAMServiceTests(unittest.TestCase):
    def setUp(self):
        self.backend = FixtureBackend()
        self.service = SAMService(self.backend)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.service))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.image = encoded(Image.new("RGB", (13, 7), (40, 90, 120)))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def request(self, path="/predict", payload=None):
        raw = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(self.base + path, data=raw, headers={"Content-Type": "application/json"})
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as exc:
            response = exc
        with response:
            return response.status, json.load(response)

    def referring(self, **fields):
        return self.request(payload={"task": "referring_seg", "image": self.image,
                                     "text": "all planes", "quality_mode": "fast", **fields})

    def test_original_dimensions_binary_values_and_traceable_mode(self):
        code, result = self.referring()
        self.assertEqual(code, 200)
        self.assertEqual(result["output_size"], [13, 7])
        mask = Image.open(io.BytesIO(base64.b64decode(result["mask"])))
        self.assertEqual(set(mask.tobytes()), {0, 255})
        self.assertEqual(result["quality"]["foreground_pixels"], 49)
        self.assertEqual(result["quality_mode"], "fast")
        self.assertEqual(result["parameters"]["restoration"], "bilinear")
        self.assertEqual(result["parameters"]["probability_threshold"], 0.5)
        self.assertEqual(result["model"]["checkpoint_sha256"], "fixture-only")

    def test_semantic_field_is_keyed_by_the_requested_class(self):
        code, result = self.request(payload={"task": "semantic_seg", "classes": ["aircraft"], "image": self.image})
        self.assertEqual(code, 200)
        self.assertEqual(result["masks"], {"aircraft": result["mask"]})
        self.assertEqual(self.backend.calls[-1], ((13, 7), "aircraft in the image"))

    def test_auto_reports_actual_fast_while_accurate_is_rejected_before_inference(self):
        code, result = self.referring(quality_mode="auto")
        self.assertEqual(code, 200)
        self.assertEqual((result["requested_quality_mode"], result["quality_mode"]), ("auto", "fast"))
        before = len(self.backend.calls)
        code, result = self.referring(quality_mode="accurate")
        self.assertEqual(code, 400)
        self.assertNotIn("mask", result)
        self.assertEqual(len(self.backend.calls), before)

    def test_invalid_base64_unknown_region_fields_and_multiple_classes_fail_closed(self):
        for payload in (
            {"task": "referring_seg", "text": "all planes", "image": "not-base64"},
            {"task": "referring_seg", "text": "all planes", "image": self.image, "roi": [0, 0, 1, 1]},
            {"task": "semantic_seg", "classes": ["aircraft", "building"], "image": self.image},
        ):
            code, result = self.request(payload=payload)
            self.assertEqual(code, 400)
            self.assertNotIn("mask", result)
        self.assertEqual(self.backend.calls, [])

    def test_backend_size_mismatch_and_probability_mask_are_never_measured(self):
        for bad in (Image.new("L", (2, 2), 255), Image.new("L", (13, 7), 128)):
            self.backend.result = bad
            code, result = self.referring()
            self.assertEqual(code, 400)
            self.assertNotIn("mask", result)

    def test_empty_prediction_is_explicit_and_health_is_not_readiness(self):
        self.backend.result = Image.new("L", (13, 7), 0)
        code, result = self.referring()
        self.assertEqual(code, 200)
        self.assertTrue(result["quality"]["empty_mask"])
        self.assertTrue(result["warnings"])
        self.service.backend = None
        self.service.load_error = "test missing checkpoint"
        code, health = self.request("/health")
        self.assertEqual(code, 200)
        self.assertFalse(health["model_ready"])
        code, ready = self.request("/ready")
        self.assertEqual(code, 503)
        self.assertEqual(ready["status"], "not_ready")
        code, result = self.referring()
        self.assertEqual(code, 503)
        self.assertNotIn("mask", result)

    def test_checkpoint_diagnostics_require_complete_trained_parameters(self):
        accepted = validate_checkpoint_diagnostics(["text_encoder.embeddings.position_ids"], [], 1107)
        self.assertEqual(accepted["checkpoint_tensor_count"], 1107)
        for missing, unexpected, count in ((["backbone.weight"], [], 1107), ([], ["unknown"], 1107), ([], [], 1106)):
            with self.assertRaises(ValueError):
                validate_checkpoint_diagnostics(missing, unexpected, count)

    def test_wrong_content_type_returns_readable_http_error(self):
        request = Request(self.base + "/predict", data=b"x" * 16384,
                          headers={"Content-Type": "text/plain"})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=5)
        with caught.exception as response:
            self.assertEqual(response.code, 400)
            self.assertIn("application/json", json.load(response)["message"])
        self.assertEqual(self.backend.calls, [])


if __name__ == "__main__":
    unittest.main()
