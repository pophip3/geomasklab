"""Run local model services in separate Python environments, without downloads.

The start command stays in the foreground. Stop requests a nonce-owned local
supervisor to clean up its own Popen handles; recorded PIDs are never killed.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

SCHEMA = "geomasklab-local-model-profile/1.0"
REPO_ROOT = Path(__file__).resolve().parents[1]
SAM_SHA256 = "f85dfa044a527f096b9e41eacfe298040d52e77fca642f46dfe1226745e137e7"
DEFAULT_TIMEOUT = 1800
MODEL_LOCK_PATH = Path(__file__).with_name("model-lock.json")


def _path(base: Path, value, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + " must be a nonempty path string.")
    path = Path(value).expanduser()
    return (path if path.is_absolute() else base / path).resolve()


def _python(base: Path, value, label: str) -> Path:
    path = _path(base, value, label)
    if path.is_dir():
        for candidate in (path / "Scripts/python.exe", path / "bin/python", path / "python.exe"):
            if candidate.is_file():
                return candidate
        # Preserve the unresolved environment directory for useful check output.
    return path


def load_profile(path) -> dict:
    source = Path(path).expanduser().resolve(strict=True)
    data = json.loads(source.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise ValueError("Use a profile with schema " + SCHEMA)
    base = source.parent
    config = {"config_path": str(source), "runtime_dir": _path(base, data.get("runtime_dir"), "runtime_dir")}
    timeout = data.get("readiness_timeout_seconds", DEFAULT_TIMEOUT)
    if type(timeout) not in (int, float) or not 1 <= timeout <= 86400:
        raise ValueError("readiness_timeout_seconds must be between 1 and 86400.")
    config["readiness_timeout_seconds"] = timeout
    for name in ("agent", "sam"):
        item = data.get(name)
        if not isinstance(item, dict):
            raise ValueError("Both agent and sam profile sections are required.")
        port = item.get("port", 8000 if name == "agent" else 6657)
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError(name + ".port must be between 1 and 65535.")
        section = {"python": _python(base, item.get("python"), name + ".python"), "port": port}
        if name == "agent":
            section.update(model_dir=_path(base, item.get("model_dir"), "agent.model_dir"),
                           model_name=item.get("model_name", "RemoteAgent"), device=item.get("device", "offload"),
                           gpu_memory=item.get("gpu_memory", "3GiB"), cpu_memory=item.get("cpu_memory", "512MiB"),
                           offload_dir=_path(base, item.get("offload_dir", "../model-runtime/agent-offload"), "agent.offload_dir"),
                           max_pixels=item.get("max_pixels", 262144), max_context=item.get("max_context", 4096))
            if section["device"] not in ("cuda", "offload", "cpu"):
                raise ValueError("agent.device must be cuda, offload or cpu.")
            for key in ("model_name", "gpu_memory", "cpu_memory"):
                if not isinstance(section[key], str) or not section[key].strip():
                    raise ValueError("agent." + key + " must be a nonempty string.")
            if not re.fullmatch(r"[A-Za-z0-9._/-]+", section["model_name"]):
                raise ValueError("agent.model_name must be a single printable model identifier.")
            for key in ("gpu_memory", "cpu_memory"):
                if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?(?:GiB|MiB|GB|MB)", section[key]):
                    raise ValueError("agent." + key + " must be a memory quantity such as 3GiB or 512MiB.")
            if (type(section["max_pixels"]) is not int or not 3136 <= section["max_pixels"] <= 1048576 or
                    type(section["max_context"]) is not int or not 256 <= section["max_context"] <= 32768):
                raise ValueError("Invalid agent image-pixel or context budget.")
        else:
            section.update(source_root=_path(base, item.get("source_root"), "sam.source_root"),
                           checkpoint=_path(base, item.get("checkpoint"), "sam.checkpoint"),
                           tokenizer=_path(base, item.get("tokenizer"), "sam.tokenizer"),
                           device=item.get("device", "cuda:0"), fp16=item.get("fp16", True))
            if not isinstance(section["device"], str) or (section["device"] != "cpu" and not
                    (section["device"].startswith("cuda:") and section["device"][5:].isdigit())):
                raise ValueError("sam.device must be cpu or an explicit CUDA device.")
            if type(section["fp16"]) is not bool:
                raise ValueError("sam.fp16 must be true or false.")
        config[name] = section
    if config["agent"]["port"] == config["sam"]["port"]:
        raise ValueError("Agent and SAM must use different local ports.")
    return config


def selected_services(only: str) -> tuple[str, ...]:
    return ("agent", "sam") if only == "both" else (only,)


def build_command(config: dict, name: str) -> list[str]:
    item = config[name]
    command = [str(item["python"]), "-u", "-m", "model_services." + name + "_service"]
    if name == "agent":
        for key, option in (("model_dir", "--model-dir"), ("model_name", "--model-name"),
                            ("device", "--device"), ("gpu_memory", "--gpu-memory"),
                            ("cpu_memory", "--cpu-memory"), ("offload_dir", "--offload-dir"),
                            ("max_pixels", "--max-pixels"), ("max_context", "--max-context"), ("port", "--port")):
            command.extend([option, str(item[key])])
    else:
        for key, option in (("source_root", "--source-root"), ("checkpoint", "--checkpoint"),
                            ("tokenizer", "--tokenizer"), ("device", "--device"), ("port", "--port")):
            command.extend([option, str(item[key])])
        command.extend(["--host", "127.0.0.1"])
        if not item["fp16"]:
            command.append("--no-fp16")
    return command


def child_workdir(config: dict) -> Path:
    """Source checkouts supply modules locally; installed environments stay isolated."""
    return REPO_ROOT if (REPO_ROOT / "src/geomasklab").is_dir() else config["runtime_dir"]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _model_lock(value=None) -> dict:
    value = json.loads(MODEL_LOCK_PATH.read_text(encoding="utf-8")) if value is None else value
    if not isinstance(value, dict) or value.get("schema") != "geomasklab-model-lock/1.0":
        raise ValueError("The fixed model lock is missing or has an unsupported schema.")
    return value


def _agent_file_lock(lock: dict) -> dict:
    entries = lock.get("agent", {}).get("files")
    if not isinstance(entries, list) or not entries:
        raise ValueError("The fixed model lock contains no RemoteAgent file records.")
    files = {}
    for row in entries:
        if not isinstance(row, dict):
            raise ValueError("Invalid RemoteAgent file record in model lock.")
        name, size, digest = row.get("name"), row.get("size_bytes"), row.get("sha256")
        if (not isinstance(name, str) or Path(name).name != name or name in files or
                any(character in name for character in ("/", "\\", ":")) or
                (name != "model.safetensors.index.json" and not name.endswith(".safetensors")) or
                type(size) is not int or size <= 0 or not isinstance(digest, str) or
                not re.fullmatch(r"[0-9a-fA-F]{64}", digest)):
            raise ValueError("Unsafe or incomplete RemoteAgent file record in model lock.")
        files[name] = {"size_bytes": size, "sha256": digest.lower()}
    if "model.safetensors.index.json" not in files or len(files) < 2:
        raise ValueError("The RemoteAgent lock must include the index and all checkpoint shards.")
    return files


def _lfs_pointer(path: Path) -> bool:
    with path.open("rb") as stream:
        return stream.read(128).startswith(b"version https://git-lfs.github.com/spec/v1")


def check_configuration(config: dict, only="both", *, hashes=False, model_lock=None) -> dict:
    """Check local assets without importing torch, executing Python, or downloading."""
    errors, observations = [], []
    identity_verified = {name: False for name in selected_services(only)}
    hashes_completed = {name: False for name in selected_services(only)}
    try:
        lock = _model_lock(model_lock)
    except (ValueError, TypeError, OSError) as exc:
        errors.append("Cannot read the fixed model lock: " + str(exc))
        lock = {}
    for name in selected_services(only):
        item = config[name]
        if not item["python"].is_file():
            errors.append(name + " Python executable was not found: " + str(item["python"]))
        if name == "agent":
            checkpoint_error_start = len(errors)
            root = item["model_dir"]
            for filename in ("config.json", "model.safetensors.index.json", "preprocessor_config.json",
                             "tokenizer_config.json", "tokenizer.json"):
                if not (root / filename).is_file():
                    errors.append("Missing RemoteAgent asset: " + str(root / filename))
            index_path = root / "model.safetensors.index.json"
            expected = {}
            try:
                expected = _agent_file_lock(lock)
            except (ValueError, TypeError, AttributeError) as exc:
                errors.append("Invalid RemoteAgent model lock: " + str(exc))
            hashed_names = set()
            for filename, fixed in expected.items():
                path = root / filename
                if not path.is_file():
                    errors.append("Missing locked RemoteAgent file: " + str(path))
                    continue
                actual_size = path.stat().st_size
                if actual_size != fixed["size_bytes"]:
                    errors.append("RemoteAgent file size mismatch for " + filename + ": expected " +
                                  str(fixed["size_bytes"]) + ", found " + str(actual_size))
                try:
                    if _lfs_pointer(path):
                        errors.append("RemoteAgent file is a Git LFS pointer, not checkpoint data: " + filename)
                    if hashes:
                        digest = _sha256(path)
                        matched = digest == fixed["sha256"]
                        hashed_names.add(filename)
                        observations.append({"asset": "RemoteAgent/" + filename, "sha256": digest,
                                             "expected_sha256": fixed["sha256"], "sha256_matches_lock": matched})
                        if not matched:
                            errors.append("RemoteAgent SHA-256 mismatch for " + filename + "; checkpoint identity is unverified.")
                except OSError as exc:
                    errors.append("Cannot read locked RemoteAgent file " + filename + ": " + str(exc))
            if index_path.is_file():
                try:
                    index = json.loads(index_path.read_text(encoding="utf-8"))
                    if not isinstance(index, dict):
                        raise ValueError("Checkpoint index must be a JSON object.")
                    mapping = index.get("weight_map")
                    if not isinstance(mapping, dict) or not mapping:
                        raise ValueError("No weight_map in checkpoint index.")
                    shards = sorted(set(mapping.values()))
                    if any(not isinstance(shard, str) or Path(shard).name != shard or
                           any(character in shard for character in ("/", "\\", ":")) for shard in shards):
                        raise ValueError("Unsafe checkpoint shard filename.")
                    for shard in shards:
                        path = root / shard
                        if not path.is_file() or not path.stat().st_size:
                            errors.append("Missing or empty RemoteAgent shard: " + str(path))
                    if expected and set(shards) != set(expected) - {"model.safetensors.index.json"}:
                        errors.append("RemoteAgent index shard set differs from the fixed model lock.")
                    metadata = index.get("metadata", {})
                    if not isinstance(metadata, dict):
                        raise ValueError("Checkpoint index metadata must be an object.")
                    observations.append({"agent_shards": len(shards), "agent_tensor_bytes": metadata.get("total_size")})
                except (ValueError, TypeError, OSError) as exc:
                    errors.append("Invalid RemoteAgent checkpoint index: " + str(exc))
            hashes_completed["agent"] = bool(hashes and expected and hashed_names == set(expected))
            identity_verified["agent"] = hashes_completed["agent"] and len(errors) == checkpoint_error_start
        else:
            for filename in ("args.py", "lib/segmentation.py", "lib/_utils.py", "lib/backbone.py",
                             "lib/mask_predictor.py", "lib/cross_scale_interaction.py", "lib/various_receptive.py",
                             "arc/__init__.py", "arc/adaptive_rotated_conv.py", "arc/routing_function.py", "arc/weight_init.py"):
                if not (item["source_root"] / filename).is_file():
                    errors.append("Missing external RemoteSAM source: " + str(item["source_root"] / filename))
            checkpoint = item["checkpoint"]
            if not checkpoint.is_file() or not checkpoint.stat().st_size:
                errors.append("Missing or empty RemoteSAM checkpoint: " + str(checkpoint))
            elif hashes:
                digest = _sha256(checkpoint)
                matched = digest == SAM_SHA256
                hashes_completed["sam"] = True
                identity_verified["sam"] = matched
                observations.append({"asset": "RemoteSAMv1", "sha256": digest,
                                     "expected_sha256": SAM_SHA256, "sha256_matches_lock": matched})
                if digest != SAM_SHA256:
                    errors.append("RemoteSAM checkpoint SHA-256 differs from the official fixed snapshot.")
            if not (item["tokenizer"] / "vocab.txt").is_file():
                errors.append("Missing local BERT tokenizer vocab.txt: " + str(item["tokenizer"]))
    notes = [
        "This check does not load models or prove GPU compatibility; readiness and real-image acceptance are separate.",
        "The lightweight check compares locked file sizes and shard names and rejects Git LFS pointers; it does not verify checkpoint identity. Use check --hashes for complete index/shard SHA-256 comparison.",
        "The original RemoteAgent uses BF16 weights, approximately 16.6 GB. Disk offload retains the original weights and may be slow.",
        "The default Agent GPU budget is 3 GiB and CPU model budget is 512 MiB; these are placement budgets, not total runtime memory limits.",
        "Allow at least 20 GB free disk for Agent offload plus weights, dependencies, logs and saved results; prefer an SSD.",
        "SAM uses an additional CUDA allocation. The 8 GB laptop path requires measured joint acceptance; it is not a general hardware guarantee.",
        "Python environments, external source, weights and tokenizer assets must be obtained separately. No files are downloaded here.",
    ]
    return {"ok": not errors, "selected": list(selected_services(only)), "errors": errors,
            "observations": observations, "notes": notes, "hashes_requested": hashes,
            "full_weight_hashes_computed": all(hashes_completed.values()),
            "checkpoint_identity_verified": identity_verified,
            "commands": {name: build_command(config, name) for name in selected_services(only)}}


def request_local_json(url: str, *, nonce=None, stop=False, timeout=2) -> tuple[int | None, dict]:
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    headers = {"Content-Type": "application/json"}
    if nonce is not None:
        headers["X-GeoMaskLab-Nonce"] = nonce
    request = Request(url, data=b"{}" if stop else None, headers=headers)
    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        response = opener.open(request, timeout=timeout)
    except HTTPError as exc:
        response = exc
    except (OSError, URLError, TimeoutError) as exc:
        return None, {"error": type(exc).__name__}
    with response:
        try:
            data = json.loads(response.read(1024 * 1024).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return response.status, {"error": "Invalid JSON response"}
        return response.status, data if isinstance(data, dict) else {"error": "Expected JSON object"}


def readiness_report(config: dict, only="both") -> dict:
    reports = {}
    for name in selected_services(only):
        base = "http://127.0.0.1:" + str(config[name]["port"])
        code, declaration = request_local_json(base + "/ready")
        ready = (code == 200 and declaration.get("ready") is not False and
                 declaration.get("model_ready") is not False and
                 (declaration.get("ready") is True or declaration.get("model_ready") is True or
                  declaration.get("status") == "ready"))
        health_code, health = request_local_json(base + "/health")
        reports[name] = {"ready": ready, "ready_http_status": code, "ready_declaration": declaration,
                         "health_http_status": health_code, "health_declaration": health}
    return {"all_ready": all(item["ready"] for item in reports.values()), "services": reports}


def workbench_settings(config: dict, only="both", readiness=None) -> str:
    lines = ["# Local endpoints; the corresponding model services must be running.", "GEO_SERVICE_PROXY_MODE=direct"]
    if "agent" in selected_services(only):
        lines.extend(["GEO_AGENT_BASE_URL=http://127.0.0.1:" + str(config["agent"]["port"]) + "/v1",
                      "GEO_AGENT_MODEL=" + config["agent"]["model_name"], "GEO_AGENT_API_KEY=EMPTY"])
        if config["agent"]["device"] == "offload":
            lines.extend(["# Original BF16 disk offload can take several minutes per model response.",
                          "GEO_AGENT_MAX_TOKENS=128", "GEO_AGENT_TIMEOUT_SECONDS=3600"])
    if "sam" in selected_services(only):
        lines.append("GEO_REMOTESAM_URL=http://127.0.0.1:" + str(config["sam"]["port"]) + "/predict")
        metadata = (readiness or {}).get("services", {}).get("sam", {}).get("ready_declaration", {})
        checkpoint, source = metadata.get("checkpoint_sha256"), metadata.get("source_tree_sha256")
        if checkpoint and source:
            pipeline = {key: metadata.get(key) for key in
                        ("service_version", "adapter_parameters", "precision", "fp16", "epoc", "packages")}
            fingerprint = hashlib.sha256(json.dumps(
                pipeline, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
            lines.append("GEO_REMOTESAM_REVISION=geomasklab-probability-adapter:weights=" + checkpoint +
                         ":source=" + source + ":pipeline=" + fingerprint)
        else:
            lines.append("# Add GEO_REMOTESAM_REVISION only after identifying the loaded checkpoint and source.")
    return "\n".join(lines) + "\n"


def _atomic_json(path: Path, value):
    temporary = path.with_name(path.name + ".writing")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _read_record(config: dict):
    path = config["runtime_dir"] / "supervisor.json"
    if not path.is_file():
        raise ValueError("No recorded supervisor. Start the launcher first.")
    record = json.loads(path.read_text(encoding="utf-8"))
    control = record.get("control_url", "")
    nonce = record.get("nonce")
    from urllib.parse import urlparse
    parsed = urlparse(control)
    if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.path or parsed.query or
            not parsed.port or not isinstance(nonce, str) or len(nonce) < 32):
        raise ValueError("Invalid local supervisor identity record.")
    return record


def stop_supervisor(config: dict) -> dict:
    record = _read_record(config)
    code, reply = request_local_json(record["control_url"] + "/stop", nonce=record["nonce"], stop=True)
    if code != 200 or reply.get("nonce") != record["nonce"] or reply.get("status") != "stopping":
        raise RuntimeError("No matching supervisor accepted the stop request. No PID was killed. Use its original terminal if it is still open.")
    return {"status": "stopping", "supervisor_pid": record.get("supervisor_pid"),
            "note": "The owning supervisor will stop only its own child processes."}


class Supervisor:
    def __init__(self, config: dict, only="both"):
        self.config, self.only = config, only
        self.stop_event = threading.Event()
        self.ready_event = threading.Event()
        self.nonce = secrets.token_urlsafe(32)
        self.children, self.logs = {}, []
        self.record = {"supervisor_pid": os.getpid(), "nonce": self.nonce,
                       "config_path": config["config_path"], "selected": list(selected_services(only)),
                       "children": {}, "state": "starting"}

    def _control_server(self):
        owner = self
        class Control(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, code, value):
                raw = json.dumps(value).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def authorized(self):
                supplied = self.headers.get("X-GeoMaskLab-Nonce", "")
                return hmac.compare_digest(supplied, owner.nonce)

            def do_GET(self):
                if self.path != "/status" or not self.authorized():
                    return self.reply(403, {"error": "Supervisor ownership not verified."})
                self.reply(200, {"nonce": owner.nonce, "state": owner.record["state"]})

            def do_POST(self):
                # Consume the tiny control body before an early response. Leaving
                # received bytes unread can reset the connection on Windows.
                length = self.headers.get("Content-Length", "")
                if not length.isdigit() or not 0 <= int(length) <= 4096 or self.headers.get("Transfer-Encoding"):
                    return self.reply(400, {"error": "Use a bounded control request with Content-Length."})
                self.connection.settimeout(2)
                if len(self.rfile.read(int(length))) != int(length):
                    return self.reply(400, {"error": "Incomplete control body."})
                if self.path != "/stop" or not self.authorized():
                    return self.reply(403, {"error": "Supervisor ownership not verified."})
                self.reply(200, {"nonce": owner.nonce, "status": "stopping"})
                owner.stop_event.set()
        return ThreadingHTTPServer(("127.0.0.1", 0), Control)

    def _cleanup_children(self):
        # Only Popen objects obtained by this instance are touched. Recorded PIDs
        # are informational and are never supplied to an OS kill operation.
        for child in self.children.values():
            if child.poll() is None:
                try:
                    child.terminate()
                except ProcessLookupError:
                    pass
        for child in self.children.values():
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=10)

    def run(self):
        runtime = self.config["runtime_dir"]
        runtime.mkdir(parents=True, exist_ok=True)
        lock_path = runtime / "supervisor.lock"
        try:
            lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise RuntimeError("This runtime directory is already reserved. Use status/stop or the original terminal. After a crash, remove the stale lock only after checking that no launcher is running.") from None
        os.close(lock_fd)
        control = None
        control_thread = None
        record_path = runtime / "supervisor.json"
        try:
            control = self._control_server()
            self.record["control_url"] = "http://127.0.0.1:" + str(control.server_port)
            _atomic_json(record_path, self.record)
            control_thread = threading.Thread(target=control.serve_forever, daemon=True)
            control_thread.start()
            env = dict(os.environ)
            env.update(PYTHONNOUSERSITE="1", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", TOKENIZERS_PARALLELISM="false")
            env.pop("PYTHONPATH", None)
            for name in selected_services(self.only):
                command = build_command(self.config, name)
                log_path = runtime / (name + ".log")
                stream = log_path.open("ab")
                self.logs.append(stream)
                child = subprocess.Popen(command, cwd=child_workdir(self.config), env=env, stdout=stream,
                                         stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, shell=False)
                self.children[name] = child
                self.record["children"][name] = {"pid": child.pid, "command": command, "log": str(log_path)}
                _atomic_json(record_path, self.record)
                print(name + " started; log: " + str(log_path), flush=True)
            deadline = time.monotonic() + self.config["readiness_timeout_seconds"]
            last_update = 0
            report = None
            while not self.stop_event.is_set():
                for name, child in self.children.items():
                    if child.poll() is not None:
                        raise RuntimeError(name + " exited before shutdown; inspect " + str(runtime / (name + ".log")))
                report = readiness_report(self.config, self.only)
                if report["all_ready"]:
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError("Model readiness timed out. Inspect the logs; no inference acceptance is claimed.")
                if time.monotonic() - last_update >= 10:
                    print("Waiting for models: " + ", ".join(name + "=" + ("ready" if item["ready"] else "loading/unavailable")
                          for name, item in report["services"].items()), flush=True)
                    last_update = time.monotonic()
                self.stop_event.wait(1)
            if not self.stop_event.is_set():
                self.record["state"] = "ready"
                _atomic_json(record_path, self.record)
                (runtime / "workbench.env").write_text(workbench_settings(self.config, self.only, report), encoding="utf-8")
                print("Models ready. Copy settings from " + str(runtime / "workbench.env") +
                      " to the workbench .env, then run geomasklab-ui (or python -m workbench.launcher) in a separate terminal.", flush=True)
                print("Keep this terminal open. Ctrl+C or launcher stop cleans up these model processes.", flush=True)
                self.ready_event.set()
                while not self.stop_event.wait(1):
                    for name, child in self.children.items():
                        if child.poll() is not None:
                            raise RuntimeError(name + " exited; both owned services will be stopped.")
        except KeyboardInterrupt:
            self.stop_event.set()
        finally:
            self.record["state"] = "stopping"
            self._cleanup_children()
            if control:
                if control_thread and control_thread.is_alive():
                    control.shutdown()
                control.server_close()
            if control_thread:
                control_thread.join(timeout=5)
            for stream in self.logs:
                stream.close()
            self.record["state"] = "stopped"
            _atomic_json(record_path, self.record)
            lock_path.unlink(missing_ok=True)
            print("Owned model processes stopped.", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("start", "status", "stop", "check"))
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--only", choices=("agent", "sam", "both"), default="both")
    parser.add_argument("--hashes", action="store_true", help="check: compute all checkpoint hashes (reads approximately 19 GB)")
    args = parser.parse_args(argv)
    try:
        config = load_profile(args.config)
        if args.command == "check":
            report = check_configuration(config, args.only, hashes=args.hashes)
            print(json.dumps(report, indent=2))
            return 0 if report["ok"] else 1
        if args.command == "status":
            report = readiness_report(config, args.only)
            print(json.dumps(report, indent=2))
            return 0 if report["all_ready"] else 1
        if args.command == "stop":
            print(json.dumps(stop_supervisor(config), indent=2))
            return 0
        report = check_configuration(config, args.only)
        if not report["ok"]:
            print(json.dumps(report, indent=2))
            return 1
        for note in report["notes"]:
            print(note, flush=True)
        # Never start on ports already occupied, including unrelated services.
        import socket
        for name in selected_services(args.only):
            with socket.socket() as probe:
                try:
                    probe.bind(("127.0.0.1", config[name]["port"]))
                except OSError:
                    raise RuntimeError(name + " port is occupied. Inspect status and use another port; no existing process was stopped.") from None
        Supervisor(config, args.only).run()
        return 0
    except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
