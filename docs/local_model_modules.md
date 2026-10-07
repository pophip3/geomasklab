# Run the optional models on your own computer

These instructions target the `1.0.0 revised snapshot` development branch. The fixed
`v1.0.0` release is unchanged and does not contain this deployment package.
Until the branch is merged, obtain it explicitly:

```powershell
git clone --branch softwarex-v1.0.0-revised https://github.com/pophip3/geomasklab.git
cd geomasklab
```

GeoMaskLab can use local model processes for scene questions and natural-language
segmentation. A reviewer starts them on their own machine when needed. No
connection to the author's computer or continuously hosted inference server is
required. Downloads and environment setup need network access once; inference
uses local files and local endpoints afterward.

| Task | Required processes |
| --- | --- |
| Open procedural examples, import a saved mask, measure, compare and export/replay evidence | GeoMaskLab core only; Python and Pillow |
| Ask about the uploaded image's scene | Core + RemoteAgent |
| Request a fresh mask with text, for example `Extract all planes` | Core + RemoteAgent + RemoteSAM |
| Derive another half-image region from retained mask evidence | Core; no new inference is needed |

**Fresh inference and evidence replay are different.** Fresh inference runs a
model on an image and request. Replay verifies retained pixels, settings,
counts and denominators without rerunning that model. Procedural examples are
explicitly labeled synthetic; they are not offline substitutes for model scene
answers or segmentation of arbitrary new images.

## Hardware and environments

The original RemoteAgent checkpoint alone occupies about 16.58 GB on disk.
An 8 GB GPU cannot hold all of its BF16 weights. The adapter provides optional
CPU/disk offload, retaining the original weights rather than quantizing them.
On an 8 GB GPU with 16 GB system RAM, limited available memory can force heavy
disk movement. Loading and each generation can be slow; this configuration is
an experimental resource-constrained route, without a low-latency guarantee.
Use a local SSD and record actual readiness and inference timings.

The author's earlier RemoteAgent deployment used a 24 GB RTX 3090; the
RemoteSAM example used an 8 GB RTX 4060 Laptop. Those are separately recorded
deployments, not a guarantee that both models fit or respond promptly on one
8 GB device. For simultaneous GPU-resident services, plan memory for both
models and runtime activations; separate GPUs/processes can also be used.
Weights alone need approximately 19.2 GB of storage combined, with extra space
for environments, download caches and any offload files.

Use separate Python 3.10 environments for the core, Agent and SAM. Agent uses
Transformers 4.57.6 / Accelerate 1.10.1; the fixed RemoteSAM architecture uses
Transformers 4.30.2. Combining these requirements in one environment causes
version conflicts. The pinned official SAM architecture imports MMCV 1 checkpoint
helpers; its separate requirements include `mmcv==1.7.2`. The commands below use Windows PowerShell; on Linux replace
`model-envs/*/Scripts/python.exe` with `model-envs/*/bin/python` and use ordinary shell
environment assignments.

The CUDA installation commands are for Windows/Linux with an NVIDIA GPU.
The Pillow-only quickstart and model HTTP contracts are checked on Windows,
Linux and macOS. macOS has no CUDA support; its live models need a separate CPU
setup with sufficient system memory, which this delivery does not claim to
have verified.

The commands are a pinned setup route, not a clean-install claim for every OS.
The author's existing model environments used Python 3.9 separately from the
Python >=3.10 core. Run setup from the repository root:

```powershell
py -3.10 -m venv model-envs/core
py -3.10 -m venv model-envs/agent
py -3.10 -m venv model-envs/sam
.\model-envs\core\Scripts\python.exe -m pip install .
.\model-envs\agent\Scripts\python.exe -m pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
.\model-envs\agent\Scripts\python.exe -m pip install -r model_services/requirements-agent.txt
.\model-envs\agent\Scripts\python.exe -m pip install . --no-deps
.\model-envs\sam\Scripts\python.exe -m pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
.\model-envs\sam\Scripts\python.exe -m pip install -r model_services/requirements-sam.txt
.\model-envs\sam\Scripts\python.exe -m pip install . --no-deps
```

The CUDA wheel must work with your installed NVIDIA driver. Check each model
environment before starting it:

```powershell
.\model-envs\agent\Scripts\python.exe -c "import torch; print(torch.__version__, torch.cuda.is_available())"
.\model-envs\sam\Scripts\python.exe -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

## Obtain fixed external assets

Source provenance and hashes are in [model_source_provenance.md](model_source_provenance.md).
Keep model files and the external architecture outside distributed source
archives. The path names below are examples inside an ignored local runtime
directory.

Obtain the external SAM architecture and pin its verified official commit:

```powershell
git clone https://github.com/1e12Leon/RemoteSAM.git model-runtime/RemoteSAM-src
git -C model-runtime/RemoteSAM-src checkout --detach ebb7bc278c7343c29c8c16b035289f78f40f0f72
```

Download the fixed SAM checkpoint and the tokenizer/config assets only:

```powershell
.\model-envs\sam\Scripts\python.exe -c "from huggingface_hub import hf_hub_download; hf_hub_download(repo_id='1e12Leon/RemoteSAM', filename='RemoteSAMv1.pth', revision='a6d09f44bac5b64be7f74980b15afb2a749b5e92', local_dir='model-runtime/RemoteSAM')"
.\model-envs\sam\Scripts\python.exe -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='google-bert/bert-base-uncased', revision='86b5e0934494bd15c9632b12f734a8a67f723594', allow_patterns=['vocab.txt','tokenizer.json','tokenizer_config.json','special_tokens_map.json','config.json','LICENSE'], local_dir='model-runtime/bert-base-uncased')"
Get-FileHash -Algorithm SHA256 model-runtime/RemoteSAM/RemoteSAMv1.pth
```

The expected checkpoint SHA-256 is
`f85dfa044a527f096b9e41eacfe298040d52e77fca642f46dfe1226745e137e7`.

Obtain the complete RemoteAgent snapshot using the
[official ModelScope distribution](https://modelscope.cn/models/AIMGroup/RemoteAgent)
and its download/access instructions. With Git LFS installed, the model
provider's published download route is:

```powershell
git lfs install
git clone https://www.modelscope.cn/AIMGroup/RemoteAgent.git model-runtime/RemoteAgent
```

Check that four actual Safetensors shard files, their index, model config,
tokenizer files, preprocessor config and chat template are present. Git LFS
pointer files are not usable weights. Compare the downloaded shards with the
retained [RemoteAgent file-hash record](../evaluation/supplementary/remote-model/remoteagent-weight-lock.json)
when reproducing the same historical snapshot. Its original ModelScope commit
was not recorded; newly downloaded revisions must not be silently relabeled
as that fixed snapshot.

## Check and start the local supervisor

Copy `model_services/profile.example.json` to `model_services/profile.local.json`.
Paths are relative to that profile file. To match the setup above, update:

| Profile field | Value |
| --- | --- |
| `runtime_dir` | `../model-runtime` |
| `agent.python` | `../model-envs/agent` |
| `agent.model_dir` | `../model-runtime/RemoteAgent` |
| `agent.offload_dir` | `../model-runtime/agent-offload` |
| `sam.python` | `../model-envs/sam` |
| `sam.source_root` | `../model-runtime/RemoteSAM-src` |
| `sam.checkpoint` | `../model-runtime/RemoteSAM/RemoteSAMv1.pth` |
| `sam.tokenizer` | `../model-runtime/bert-base-uncased` |

Keep ports 8000/6657, `readiness_timeout_seconds: 1800`, and the example's
`agent.device: offload` for the constrained-memory route. Its GPU model-placement
budget is `3GiB`, with `512MiB` of CPU model placement. These are not whole-process
memory limits. Reserve additional memory for activations, SAM and the OS. Allow
at least 20 GB of additional free SSD space for Agent offload. On a GPU with
sufficient available memory, select `agent.device: cuda` instead. Use absolute
paths for external assets stored elsewhere.

The example limits Agent vision input to 65,536 pixels; SAM still receives
the original uploaded image. This reduces the Agent's resource use and may
reduce visible scene detail. Record this budget when testing your own imagery.

Check all assets and full checkpoint hashes, then start both services:

```powershell
.\model-envs\core\Scripts\python.exe -m model_services.launcher check --config model_services/profile.local.json --hashes
.\model-envs\core\Scripts\python.exe -m model_services.launcher start --config model_services/profile.local.json
```

The hash check reads approximately 19 GB; a mismatch exits nonzero. It does not
load models or prove GPU compatibility. `start` launches the two adapters with
their separate interpreters and waits for explicit readiness. Logs are written
to `model-runtime/agent.log` and `model-runtime/sam.log`. Keep its foreground
terminal open. In another terminal, inspect readiness:

```powershell
.\model-envs\core\Scripts\python.exe -m model_services.launcher status --config model_services/profile.local.json
```

`status` exits nonzero unless the selected models declare readiness. `--only
agent` or `--only sam` permits individual component check/start/status. An HTTP
health response alone is insufficient for readiness or inference acceptance.

The SAM adapter implements **Fast** only: 896 x 896 whole-image inference, FP16
CUDA autocast, foreground softmax probabilities restored bilinearly to the
original grid, threshold 0.5 and no EPOC refinement. Explicit accurate/tiled
requests are rejected; they cannot pass under a misleading mode label.

## Connect the workbench and tune slow requests

After both models are ready, the supervisor writes `model-runtime/workbench.env`
with local endpoints and the loaded SAM source/checkpoint identity. Copy these
settings into the repository `.env`:

```powershell
Copy-Item model-runtime/workbench.env .env
```

Add the following explicit generation/time settings to `.env`:

```dotenv
GEO_AGENT_MAX_TOKENS=128
GEO_AGENT_TIMEOUT_SECONDS=1800
GEO_PORT=4180
```

The default chat timeout is 120 seconds. Slow disk-offload requests may need
1800 or 3600 seconds per Agent call; 3600 is the supported maximum. The explicit
128-token budget can truncate answers, so increase it if necessary and record
the setting. A timeout increase permits slow execution; it does not accelerate
inference. Shell `GEO_` variables override `.env`; clear or update stale values.

Start the core in a separate terminal:

```powershell
.\model-envs\core\Scripts\python.exe quickstart.py --port 4180
```

Open `http://127.0.0.1:4180`, choose live mode, upload your image and use
**Runtime settings -> Check connections**. A scene question should create a
qualitative answer without segmentation measurements. `Extract all planes`
should create a validated SAM request and a grid-aligned mask. Ask for the left
half next: the Harness applies a deterministic pixel-half domain to the full
prediction, so an object crossing the center line can be clipped. All displayed
areas, denominators and ratios are computed by the core.

The two endpoints are on the machine running these services. On a reviewer's
computer, `127.0.0.1` refers to that reviewer's own processes. When all assets
have been obtained, the adapters load local files without requesting external
model downloads during inference. Keep this local launch running while using
the module; the author need not be online.

## Run real acceptance and replay independently

With both services configured, run the actual workbench acceptance script:

```powershell
.\model-envs\core\Scripts\python.exe examples/live_model_acceptance.py --timeout 3600 --output outputs/model-acceptance
```

The default is the supplied public NAIP image with target `building`. For your
own image, add `--image path/to/image.png --target aircraft`. Supported targets
are building, aircraft, road, water, tree and ship. The script performs a fresh
scene request, a fresh whole-image extraction and Agent tool feedback. Left,
right and rectangle cases then use deterministic saved-mask replay, with no
new model requests. A complete passing attempt produces four files:

- `whole-image-live.zip`
- `left-saved-mask.zip`
- `right-saved-mask.zip`
- `rectangle-saved-mask.zip`

Every attempt has its own folder and `summary.json`. A required scene,
segmentation, feedback, export or replay failure produces `passed: false` and a
nonzero exit status. Record hardware, source/model hashes, package versions,
prompts, generation settings and timing. Health checks and injected-backend
contract tests are separate from real-model acceptance.

The installed core replays the exported bundles without model services:

```powershell
.\model-envs\core\Scripts\python.exe -m geomasklab verify outputs/model-acceptance/run-.../whole-image-live.zip
```

Replace `run-...` with the actual attempt directory and verify the other ZIPs in
the same way. Replay proves saved pixel arithmetic and internal consistency,
not scene-answer accuracy, segmentation accuracy or authenticated model origin.
The overlay still requires separate semantic review.

The [saved validation record](local_model_validation.md) reports a completed
real two-model NAIP run, separate nonempty SAM prediction and supervised
start/status/stop checks. The laptop's disk-offload end-to-end run took about
35.6 minutes. These are execution checks; segmentation and scene-answer accuracy
were not established. Use the retained-model-mask replay for a short,
weights-free walkthrough.

## Stop the local models

```powershell
.\model-envs\core\Scripts\python.exe -m model_services.launcher stop --config model_services/profile.local.json
```

Alternatively press Ctrl+C in the original supervisor terminal. Shutdown cleans
up only its own model children. Stop the separate workbench terminal with Ctrl+C
when finished.
