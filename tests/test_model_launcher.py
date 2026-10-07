"""Supervisor tests use fake children and local fake services, never model loads."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from model_services.launcher import (SCHEMA, Supervisor, build_command, check_configuration,
    child_workdir, load_profile, main, readiness_report, request_local_json, stop_supervisor, workbench_settings)


class FakeProcess:
    counter = 100000

    def __init__(self, command, **kwargs):
        type(self).counter += 1
        self.pid = type(self).counter
        self.command = command
        self.terminated = self.killed = False
        self.returncode = None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def kill(self):
        self.killed = True
        self.returncode = -1

    def wait(self, timeout=None):
        if self.returncode is None:
            raise subprocess.TimeoutExpired(self.command, timeout)
        return self.returncode


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        # Resolve macOS /var symlinks and Windows runner short-path aliases,
        # matching the canonical paths produced by load_profile.
        self.root = Path(self.temp.name).resolve()
        self.servers = []
        self.threads = []
        self.supervisors = []
        self.ready = True
        owner = self
        class FakeService(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                body = json.dumps({"ready": owner.ready, "checkpoint_sha256": "fake-checkpoint",
                                   "source_tree_sha256": "fake-source"}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        ports = []
        for _ in range(2):
            server = ThreadingHTTPServer(("127.0.0.1", 0), FakeService)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.servers.append(server)
            self.threads.append(thread)
            ports.append(server.server_port)
        data = {"schema": SCHEMA, "runtime_dir": "runtime", "readiness_timeout_seconds": 5,
            "agent": {"python": sys.executable, "model_dir": "agent", "offload_dir": "offload", "port": ports[0]},
            "sam": {"python": sys.executable, "source_root": "sam-source", "checkpoint": "sam.pth",
                    "tokenizer": "tokenizer", "port": ports[1]}}
        self.profile = self.root / "profile.json"
        self.profile.write_text(json.dumps(data), encoding="utf-8")
        self.config = load_profile(self.profile)

    def tearDown(self):
        for supervisor, thread in self.supervisors:
            supervisor.stop_event.set()
            thread.join(timeout=5)
        for server in self.servers:
            server.shutdown()
            server.server_close()
        for thread in self.threads:
            thread.join(timeout=5)
        self.temp.cleanup()

    def test_portable_paths_and_independent_environment_commands(self):
        self.assertEqual(self.config["runtime_dir"], self.root / "runtime")
        agent = build_command(self.config, "agent")
        sam = build_command(self.config, "sam")
        self.assertEqual(agent[3], "model_services.agent_service")
        self.assertEqual(sam[3], "model_services.sam_service")
        self.assertIn("3GiB", agent)
        self.assertIn("512MiB", agent)
        self.assertIn("--source-root", sam)

    def test_generated_offload_settings_allow_measured_slow_requests_without_changing_cuda_defaults(self):
        settings = workbench_settings(self.config)
        self.assertIn("GEO_AGENT_MAX_TOKENS=128", settings)
        self.assertIn("GEO_AGENT_TIMEOUT_SECONDS=3600", settings)
        self.config["agent"]["device"] = "cuda"
        settings = workbench_settings(self.config)
        self.assertNotIn("GEO_AGENT_MAX_TOKENS=", settings)
        self.assertNotIn("GEO_AGENT_TIMEOUT_SECONDS=", settings)

    def test_sam_revision_changes_with_precision_and_adapter_parameters(self):
        metadata = {"checkpoint_sha256": "same-weight", "source_tree_sha256": "same-source",
                    "fp16": True, "precision": "FP16 CUDA autocast", "service_version": "fixture",
                    "adapter_parameters": {"probability_threshold": 0.5}, "epoc": False,
                    "packages": {"torch": "fixture-version"}}
        report = {"services": {"sam": {"ready_declaration": metadata}}}
        original = workbench_settings(self.config, "sam", report)
        metadata["fp16"], metadata["precision"] = False, "float32"
        float32 = workbench_settings(self.config, "sam", report)
        self.assertNotEqual(original, float32)
        metadata["adapter_parameters"]["probability_threshold"] = 0.7
        changed_parameters = workbench_settings(self.config, "sam", report)
        self.assertNotEqual(float32, changed_parameters)
        self.assertIn(":weights=same-weight:source=same-source:pipeline=", original)

    def test_installed_children_avoid_another_environment_site_packages(self):
        installed_root = self.root / "core-environment/site-packages"
        installed_root.mkdir(parents=True)
        with patch("model_services.launcher.REPO_ROOT", installed_root):
            self.assertEqual(child_workdir(self.config), self.config["runtime_dir"])
        source_root = self.root / "source-checkout"
        (source_root / "src/geomasklab").mkdir(parents=True)
        with patch("model_services.launcher.REPO_ROOT", source_root):
            self.assertEqual(child_workdir(self.config), source_root)

    def test_check_is_read_only_and_reports_missing_assets_without_heavy_imports(self):
        with patch("subprocess.Popen", side_effect=AssertionError("check must not launch")):
            result = check_configuration(self.config)
        self.assertFalse(result["ok"])
        self.assertTrue(any("RemoteSAM" in item for item in result["errors"]))
        self.assertFalse(self.config["runtime_dir"].exists())
        self.assertFalse(result["full_weight_hashes_computed"])

    def test_http_reachability_does_not_imply_model_readiness(self):
        self.ready = False
        report = readiness_report(self.config)
        self.assertFalse(report["all_ready"])
        self.assertEqual(report["services"]["sam"]["ready_http_status"], 200)

    def agent_assets(self):
        root = self.config["agent"]["model_dir"]
        root.mkdir()
        for filename in ("config.json", "preprocessor_config.json", "tokenizer_config.json", "tokenizer.json"):
            (root / filename).write_text("{}", encoding="utf-8")
        (root / "fixture.safetensors").write_bytes(b"good-bf16-weight")
        index = {"metadata": {"total_size": 15}, "weight_map": {"test.weight": "fixture.safetensors"}}
        (root / "model.safetensors.index.json").write_text(json.dumps(index), encoding="utf-8")
        files = []
        for filename in ("model.safetensors.index.json", "fixture.safetensors"):
            raw = (root / filename).read_bytes()
            files.append({"name": filename, "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
        return {"schema": "geomasklab-model-lock/1.0", "agent": {"files": files}}

    def test_complete_hashes_verify_index_and_shards_while_lightweight_never_claims_identity(self):
        lock = self.agent_assets()
        light = check_configuration(self.config, "agent", model_lock=lock)
        full = check_configuration(self.config, "agent", hashes=True, model_lock=lock)
        self.assertTrue(light["ok"] and full["ok"])
        self.assertFalse(light["checkpoint_identity_verified"]["agent"])
        self.assertFalse(light["full_weight_hashes_computed"])
        self.assertTrue(full["checkpoint_identity_verified"]["agent"])
        self.assertTrue(full["full_weight_hashes_computed"])
        self.assertEqual(len([row for row in full["observations"] if "sha256" in row]), 2)

    def test_same_size_shard_mutation_requires_hashes_and_returns_nonzero_cli_status(self):
        lock = self.agent_assets()
        (self.config["agent"]["model_dir"] / "fixture.safetensors").write_bytes(b"evil-bf16-weight")
        light = check_configuration(self.config, "agent", model_lock=lock)
        full = check_configuration(self.config, "agent", hashes=True, model_lock=lock)
        self.assertTrue(light["ok"])
        self.assertFalse(light["checkpoint_identity_verified"]["agent"])
        self.assertFalse(full["ok"])
        self.assertFalse(full["checkpoint_identity_verified"]["agent"])
        self.assertTrue(any("SHA-256 mismatch" in error for error in full["errors"]))
        lock_path = self.root / "fixture-model-lock.json"
        lock_path.write_text(json.dumps(lock), encoding="utf-8")
        with patch("model_services.launcher.MODEL_LOCK_PATH", lock_path), patch("builtins.print"):
            status = main(["check", "--config", str(self.profile), "--only", "agent", "--hashes"])
        self.assertEqual(status, 1)

    def test_lightweight_check_rejects_truncated_shards_and_lfs_pointer_files(self):
        lock = self.agent_assets()
        shard = self.config["agent"]["model_dir"] / "fixture.safetensors"
        for raw, message in ((b"short", "file size mismatch"),
                             (b"version https://git-lfs.github.com/spec/v1\noid sha256:placeholder\nsize 15\n", "Git LFS pointer")):
            shard.write_bytes(raw)
            result = check_configuration(self.config, "agent", model_lock=lock)
            self.assertFalse(result["ok"])
            self.assertFalse(result["checkpoint_identity_verified"]["agent"])
            self.assertTrue(any(message in error for error in result["errors"]))

    def test_agent_context_budget_minimum_matches_service(self):
        profile = json.loads(self.profile.read_text())
        profile["agent"]["max_context"] = 255
        self.profile.write_text(json.dumps(profile))
        with self.assertRaises(ValueError):
            load_profile(self.profile)
        profile["agent"]["max_context"] = 256
        self.profile.write_text(json.dumps(profile))
        self.assertEqual(load_profile(self.profile)["agent"]["max_context"], 256)

    def run_supervisor(self, only="both"):
        supervisor = Supervisor(self.config, only)
        failure = []
        def run():
            try:
                supervisor.run()
            except Exception as exc:
                failure.append(exc)
        thread = threading.Thread(target=run, daemon=True)
        self.supervisors.append((supervisor, thread))
        thread.start()
        self.assertTrue(supervisor.ready_event.wait(5), "Fake services did not become ready.")
        return supervisor, thread, failure

    def test_nonce_owned_stop_cleans_only_created_child_handles(self):
        created = []
        def spawn(command, **kwargs):
            child = FakeProcess(command, **kwargs)
            created.append(child)
            return child
        unrelated = FakeProcess(["unrelated-process"])
        with patch("model_services.launcher.subprocess.Popen", side_effect=spawn):
            supervisor, thread, failure = self.run_supervisor()
            record = json.loads((self.root / "runtime/supervisor.json").read_text())
            code, _ = request_local_json(record["control_url"] + "/stop", nonce="wrong-owner", stop=True)
            self.assertEqual(code, 403)
            self.assertFalse(supervisor.stop_event.is_set())
            result = stop_supervisor(self.config)
            self.assertEqual(result["status"], "stopping")
            thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertFalse(failure)
        self.assertEqual(len(created), 2)
        self.assertTrue(all(child.terminated for child in created))
        self.assertFalse(unrelated.terminated or unrelated.killed)
        self.assertEqual(record["children"]["agent"]["command"], created[0].command)
        self.assertFalse((self.root / "runtime/supervisor.lock").exists())
        self.assertIn("GEO_REMOTESAM_REVISION", (self.root / "runtime/workbench.env").read_text())

    def test_only_sam_is_started_and_stale_pid_record_is_never_killed(self):
        with patch("model_services.launcher.subprocess.Popen", side_effect=FakeProcess):
            supervisor, thread, failure = self.run_supervisor("sam")
            self.assertEqual(set(supervisor.children), {"sam"})
            stop_supervisor(self.config)
            thread.join(timeout=5)
        self.assertFalse(failure)
        record = json.loads((self.root / "runtime/supervisor.json").read_text())
        record["supervisor_pid"] = 123
        record["children"]["sam"]["pid"] = 456
        (self.root / "runtime/supervisor.json").write_text(json.dumps(record))
        with patch("os.kill", side_effect=AssertionError("Never kill a recorded PID")):
            with self.assertRaises(RuntimeError):
                stop_supervisor(self.config)


if __name__ == "__main__":
    unittest.main()
