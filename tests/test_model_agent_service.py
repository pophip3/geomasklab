"""Optional Agent HTTP contract tests with an explicit fake backend.

These fixtures test request handling only. They never load model weights and
must not be described as evidence of RemoteAgent inference quality.
"""
import base64
import http.client
from http.server import ThreadingHTTPServer
import io
import json
import math
from pathlib import Path
import subprocess
import struct
import socket
import sys
import threading
import unittest
import zlib
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image

from model_services.agent_service import AgentApplication, MAX_BODY, make_handler, prepare_messages


def image_url(fmt="PNG", mode="RGB"):
    image = Image.new(mode, (13, 7), 100 if mode == "L" else (40, 90, 120))
    output = io.BytesIO()
    image.save(output, fmt)
    mime = "jpeg" if fmt == "JPEG" else fmt.lower()
    return "data:image/" + mime + ";base64," + base64.b64encode(output.getvalue()).decode("ascii")


def image_message(url=None):
    return {"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": url or image_url()}},
        {"type": "text", "text": "Describe this image."},
    ]}


class ExplicitFakeAgentBackend:
    """Synthetic HTTP fixture; this is deliberately never a model substitute."""
    metadata = {"backend": "explicit-fake-test-only", "model_evidence": False}

    def __init__(self):
        self.calls = []
        self.failure = None
        self.entered = threading.Event()
        self.release = None

    def complete(self, messages, max_tokens, temperature):
        self.calls.append((messages, max_tokens, temperature))
        self.entered.set()
        if self.release is not None and not self.release.wait(timeout=4):
            raise RuntimeError("Explicit fake fixture timed out.")
        if self.failure is not None:
            raise self.failure
        completion = min(max_tokens, 3)
        return "<answer>Explicit fake fixture response.</answer>", {
            "prompt_tokens": 19,
            "completion_tokens": completion,
            "total_tokens": 19 + completion,
        }


class OptionalAgentHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = AgentApplication("RemoteAgent-test-alias", max_output_tokens=64)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.application))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        self.backend = ExplicitFakeAgentBackend()
        self.application.backend = self.backend
        self.application.error = None
        self.payload = {"model": "RemoteAgent-test-alias", "messages": [image_message()],
                        "max_tokens": 32, "temperature": 0}

    def request(self, path="/v1/chat/completions", payload=None, raw=None, headers=None):
        if raw is None and payload is not None:
            raw = json.dumps(payload).encode("utf-8")
        request = Request(self.base + path, data=raw,
                          headers={"Content-Type": "application/json", **(headers or {})})
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as exc:
            response = exc
        with response:
            self.assertEqual(response.headers.get_content_type(), "application/json")
            data = response.read()
            self.assertEqual(int(response.headers["Content-Length"]), len(data))
            return response.status, json.loads(data)

    def assert_rejected_without_backend(self, payload, status=400):
        count = len(self.backend.calls)
        code, result = self.request(payload=payload)
        self.assertEqual(code, status, result)
        self.assertIn("error", result)
        self.assertNotIn("choices", result)
        self.assertEqual(len(self.backend.calls), count)

    def test_models_and_health_endpoints_declare_the_alias_and_explicit_fake_metadata(self):
        code, models = self.request("/v1/models")
        self.assertEqual(code, 200)
        self.assertEqual(models["data"], [{"id": "RemoteAgent-test-alias"}])
        for path in ("/health", "/ready", "/model-info"):
            with self.subTest(path=path):
                code, result = self.request(path)
                self.assertEqual(code, 200)
                self.assertTrue(result["ready"])
                self.assertEqual(result["metadata"]["backend"], "explicit-fake-test-only")
                self.assertFalse(result["metadata"]["model_evidence"])

    def test_chat_returns_openai_message_usage_finish_reason_and_traceable_fixture_metadata(self):
        code, result = self.request(payload=self.payload)
        self.assertEqual(code, 200)
        self.assertEqual(result["object"], "chat.completion")
        self.assertEqual(result["model"], "RemoteAgent-test-alias")
        choice = result["choices"][0]
        self.assertEqual(choice["message"]["role"], "assistant")
        self.assertIn("Explicit fake fixture", choice["message"]["content"])
        self.assertEqual(choice["finish_reason"], "stop")
        self.assertEqual(result["usage"], {"prompt_tokens": 19, "completion_tokens": 3, "total_tokens": 22})
        self.assertFalse(result["service_metadata"]["model_evidence"])
        self.assertGreaterEqual(result["service_metadata"]["inference_ms"], 0)
        self.assertEqual(self.backend.calls, [(self.payload["messages"], 32, 0)])
        self.payload["max_tokens"] = 1
        code, result = self.request(payload=self.payload)
        self.assertEqual(code, 200)
        self.assertEqual(result["choices"][0]["finish_reason"], "length")

    def test_original_sized_png_and_jpeg_decode_to_rgb_and_keep_conversation_roles(self):
        for fmt, mode in (("PNG", "L"), ("JPEG", "RGB")):
            with self.subTest(fmt=fmt):
                messages = [{"role": "system", "content": "Use the current image."},
                            image_message(image_url(fmt, mode)),
                            {"role": "assistant", "content": "Previous fixture response."},
                            {"role": "user", "content": "Describe it again."}]
                normalized, images = prepare_messages(messages)
                self.assertEqual([m["role"] for m in normalized], ["system", "user", "assistant", "user"])
                self.assertEqual(normalized[1]["content"][0], {"type": "image"})
                self.assertEqual(len(images), 1)
                self.assertEqual(images[0].size, (13, 7))
                self.assertEqual(images[0].mode, "RGB")
                self.assertNotIn("base64", json.dumps(normalized))

    def test_one_image_across_history_is_required_before_inference(self):
        for messages in ([{"role": "user", "content": "No image."}],
                         [image_message(), image_message()],
                         [{"role": "user", "content": [
                             {"type": "image_url", "image_url": {"url": image_url()}},
                             {"type": "image_url", "image_url": {"url": image_url()}},
                         ]}]):
            with self.subTest(images=len(messages)):
                payload = dict(self.payload, messages=messages)
                self.assert_rejected_without_backend(payload)

    def test_invalid_messages_roles_and_content_blocks_fail_before_inference(self):
        for messages in (None, "not-a-list", [], [None],
                         [{"role": "tool", "content": "untrusted"}],
                         [{"role": "assistant", "content": image_message()["content"]}],
                         [{"role": "system", "content": image_message()["content"]}],
                         [{"role": "user", "content": {"text": "wrong shape"}}],
                         [{"role": "user", "content": [None]}],
                         [{"role": "user", "content": [{"type": "video"}]}],
                         [{"role": "user", "content": [{"type": "text", "text": 7}]}]):
            with self.subTest(messages=messages):
                self.assert_rejected_without_backend(dict(self.payload, messages=messages))

    def test_message_count_and_text_length_limits_are_enforced(self):
        accepted = [{"role": "system", "content": "context"}] * 23 + [image_message()]
        normalized, _ = prepare_messages(accepted)
        self.assertEqual(len(normalized), 24)
        long_block = image_message()
        long_block["content"][1]["text"] = "x" * 32001
        for messages in (accepted + [{"role": "user", "content": "extra"}],
                         [{"role": "system", "content": "x" * 32001}, image_message()],
                         [long_block]):
            self.assert_rejected_without_backend(dict(self.payload, messages=messages))

    def test_invalid_base64_remote_urls_and_invalid_image_bytes_are_client_errors(self):
        for url in ("https://example.invalid/image.png", "file:///test.png",
                    "data:image/gif;base64,R0lGODlh", "data:image/png;base64,%%%",
                    "data:image/png;base64," + base64.b64encode(b"not an image").decode("ascii")):
            with self.subTest(url=url[:45]):
                self.assert_rejected_without_backend(dict(self.payload, messages=[image_message(url)]))

    def test_malformed_image_url_objects_are_client_errors(self):
        for value in (None, "not-a-mapping", ["url"], {"url": 7}, {}):
            with self.subTest(image_url=value):
                message = image_message()
                message["content"][0]["image_url"] = value
                self.assert_rejected_without_backend(dict(self.payload, messages=[message]))

    def test_actual_format_and_image_pixel_budget_are_validated_before_decode_or_inference(self):
        # Alter only a valid PNG's IHDR dimensions and CRC. Pillow reads its
        # header, and the service must reject the size before decoding pixels.
        raw = bytearray(base64.b64decode(image_url().split(",", 1)[1]))
        raw[16:24] = struct.pack(">II", 4001, 4000)
        raw[29:33] = struct.pack(">I", zlib.crc32(raw[12:29]) & 0xFFFFFFFF)
        oversized_url = "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
        gif_payload = image_url("GIF").split(",", 1)[1]
        masquerading_url = "data:image/png;base64," + gif_payload
        for url in (oversized_url, masquerading_url):
            with self.subTest(url=url[:45]):
                self.assert_rejected_without_backend(dict(self.payload, messages=[image_message(url)]))

    def test_model_alias_stream_and_output_temperature_bounds_fail_before_inference(self):
        variants = [{"model": "RemoteAgent"}, {"model": None}, {"stream": True}]
        variants += [{"max_tokens": value} for value in (0, -1, 65, True, 1.5, "1", None)]
        variants += [{"temperature": value} for value in (-0.01, 2.01, True, "0", None, math.nan, math.inf)]
        for changes in variants:
            with self.subTest(changes=changes):
                self.assert_rejected_without_backend(dict(self.payload, **changes))
        for value in (0, 2):
            code, result = self.request(payload=dict(self.payload, max_tokens=64, temperature=value))
            self.assertEqual(code, 200, result)

    def test_malformed_json_and_request_size_headers_do_not_invoke_backend(self):
        for raw in (b"{", b"\xff", b"[]", b"null", b"1", b'"text"'):
            with self.subTest(raw=raw):
                code, result = self.request(raw=raw)
                self.assertEqual(code, 400, result)
        for length in ("0", "-1", "not-an-integer", str(MAX_BODY + 1)):
            with self.subTest(length=length):
                # No body bytes are needed to test a rejected size declaration;
                # this also avoids Windows resetting a closed socket mid-send.
                code, result = self.request(raw=b"", headers={"Content-Length": length})
                self.assertEqual(code, 400, result)
        self.assertEqual(self.backend.calls, [])

    def test_missing_request_length_is_rejected_without_waiting_for_body(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.putrequest("POST", "/v1/chat/completions")
            connection.putheader("Content-Type", "application/json")
            connection.endheaders()
            response = connection.getresponse()
            self.assertEqual(response.status, 400)
            self.assertIn("error", json.loads(response.read()))
        finally:
            connection.close()
        self.assertEqual(self.backend.calls, [])

    def test_non_json_chunked_and_incomplete_request_bodies_fail_before_inference(self):
        for headers in ({"Content-Type": "text/plain"}, {"Transfer-Encoding": "chunked"}):
            code, result = self.request(payload=self.payload, headers=headers)
            self.assertEqual(code, 400, result)
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.putrequest("POST", "/v1/chat/completions")
            connection.putheader("Content-Type", "application/json")
            connection.putheader("Content-Length", "20")
            connection.endheaders()
            connection.send(b"{}")
            # Finish the body without closing the response side of the socket.
            # This checks incomplete-body handling without a 30-second wait.
            connection.sock.shutdown(socket.SHUT_WR)
            response = connection.getresponse()
            self.assertEqual(response.status, 400)
            self.assertIn("error", json.loads(response.read()))
        finally:
            connection.close()
        self.assertEqual(self.backend.calls, [])

    def test_loading_and_failed_model_have_health_but_no_ready_models_or_answers(self):
        self.application.backend = None
        for error in (None, "Explicit fake fixture loading failure"):
            with self.subTest(error=error):
                self.application.error = error
                code, health = self.request("/health")
                self.assertEqual(code, 200)
                self.assertFalse(health["ready"])
                self.assertEqual(health["error"], error)
                self.assertIsNone(health["metadata"])
                for path in ("/ready", "/model-info", "/v1/models"):
                    code, result = self.request(path)
                    self.assertEqual(code, 503, result)
                self.assert_rejected_without_backend(self.payload, status=503)

    def test_concurrent_request_is_busy_while_health_remains_responsive(self):
        self.backend.release = threading.Event()
        results = []
        thread = threading.Thread(target=lambda: results.append(self.request(payload=self.payload)))
        thread.start()
        try:
            self.assertTrue(self.backend.entered.wait(timeout=2))
            self.assert_rejected_without_backend(self.payload, status=429)
            code, ready = self.request("/ready")
            self.assertEqual(code, 200)
            self.assertTrue(ready["ready"])
        finally:
            self.backend.release.set()
            thread.join(timeout=5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], 200)
        self.assertEqual(len(self.backend.calls), 1)

    def test_inference_failure_releases_lock_and_has_no_fabricated_answer(self):
        self.backend.failure = OSError("Private fixture detail must stay out of response")
        code, result = self.request(payload=self.payload)
        self.assertEqual(code, 500)
        self.assertEqual(result["error"], "OSError")
        self.assertNotIn("choices", result)
        self.assertNotIn("Private fixture detail", json.dumps(result))
        self.backend.failure = None
        code, result = self.request(payload=self.payload)
        self.assertEqual(code, 200, result)

    def test_unknown_http_routes_return_404(self):
        for path, payload in (("/unknown", None), ("/unknown", self.payload),
                              ("/v1/chat/completions?ignored=1", self.payload)):
            code, result = self.request(path, payload=payload)
            self.assertEqual(code, 404)
            self.assertIn("error", result)
        self.assertEqual(self.backend.calls, [])


class OptionalAgentLightweightCLITests(unittest.TestCase):
    def test_import_and_cli_help_never_import_heavy_model_dependencies(self):
        root = Path(__file__).resolve().parents[1]
        code = """
import builtins, runpy, sys
original_import = builtins.__import__
blocked = {'torch', 'transformers', 'accelerate', 'safetensors', 'vllm', 'openai'}
def guard(name, *args, **kwargs):
    if name.split('.')[0] in blocked:
        raise AssertionError('Unexpected heavy dependency import: ' + name)
    return original_import(name, *args, **kwargs)
builtins.__import__ = guard
import model_services.agent_service
assert not blocked.intersection(sys.modules)
sys.argv = ['agent_service', '--help']
runpy.run_module('model_services.agent_service', run_name='__main__')
"""
        result = subprocess.run([sys.executable, "-B", "-c", code], cwd=root,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--model-dir", result.stdout)
        self.assertIn("--device", result.stdout)
        self.assertNotIn("RemoteAgent loading", result.stdout)

    def test_invalid_cli_context_port_and_pixel_budgets_exit_before_model_loading(self):
        root = Path(__file__).resolve().parents[1]
        for option, value in (("--max-context", "255"), ("--max-context", "32769"),
                              ("--port", "0"), ("--port", "65536"),
                              ("--max-pixels", "3135"), ("--max-pixels", "1048577")):
            with self.subTest(option=option, value=value):
                result = subprocess.run([sys.executable, "-B", "-m", "model_services.agent_service",
                                         "--model-dir", "deliberately-nonexistent-test-model", option, value],
                                        cwd=root, capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("Invalid port, image-pixel budget or context length", result.stderr)
                self.assertNotIn("RemoteAgent loading", result.stdout)


if __name__ == "__main__":
    unittest.main()
