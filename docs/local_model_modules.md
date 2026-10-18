# Optional local model services

This guide configures RemoteAgent and RemoteSAM for **new model-generated scene
answers or masks** in GeoMaskLab 1.0.0. The [reviewer quickstart](reviewer_quickstart.md)
covers core installation, examples and evidence replay with Python and Pillow.

Obtain the current repository:

```powershell
git clone https://github.com/pophip3/geomasklab.git
cd geomasklab
```

The services run on the computer configured in this guide. Network access is
needed to obtain dependencies and model assets; subsequent inference uses local
files and local endpoints.

## Select a workflow

| Task | Required processes |
| --- | --- |
| Open synthetic procedural examples, import masks, measure, compare and export/replay evidence | GeoMaskLab core only; Python and Pillow |
| Inspect the bundled RemoteSAM image and prediction with `python examples/replay_model_mask.py` | Core only; replay of a saved prediction |
| Ask a new scene question about an uploaded image | Core + RemoteAgent; select `--only agent` below |
| Generate a new segmentation mask from text | Core + RemoteAgent + RemoteSAM |

Replay checks retained pixels, settings, counts and denominators. Fresh inference
runs the configured models on a new request. The built-in procedural examples use
synthetic masks and preset scene text.

After the one-time setup and configuration, daily use is two commands in two
terminals (keep both open):

```powershell
.\model-envs\core\Scripts\python.exe -m model_services.launcher start --config model_services/profile.local.json
.\model-envs\core\Scripts\python.exe quickstart.py --port 4180
```

Open `http://127.0.0.1:4180` and select live mode. For questions without new
segmentation, append `--only agent` to the first command. The initial setup below
includes copying the generated endpoints to `.env`; it is not repeated on each
launch. This is a local model interface, with task context rather than complete
multi-turn conversational memory. Original replies are currently requested in
English. Loading and answering can be slow on constrained hardware.

The [reproduction release](https://github.com/pophip3/geomasklab/releases/tag/v1.0.0-repro.20261016)
contains the current dependency supplement and source archive. Use the files
whose names include `dependency-closure-20261016` for this installation route.

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
Linux and macOS. A macOS CPU deployment of the live models has not been verified;
the CUDA setup below applies to Windows and Linux with an NVIDIA GPU.

The complete Python 3.10 dependency locks cover Windows AMD64 and Linux x86_64.
Build tools and Linux CUDA runtime libraries are fixed as well. See
[environment checks](reproduction_environments.md) for the verification record.
Run setup from the repository root:

```powershell
py -3.10 -m venv model-envs/core
py -3.10 -m venv model-envs/agent
py -3.10 -m venv model-envs/sam
.\model-envs\core\Scripts\python.exe -m pip install -r requirements-build.txt -r requirements.txt
.\model-envs\core\Scripts\python.exe -m pip install --no-build-isolation --no-deps .
.\model-envs\agent\Scripts\python.exe -m pip install pip==26.0.1
.\model-envs\agent\Scripts\python.exe -m pip install --build-constraint model_services/requirements-build-constraints.txt -r model_services/requirements-agent.txt
.\model-envs\agent\Scripts\python.exe -m pip install --no-build-isolation --no-deps .
.\model-envs\agent\Scripts\python.exe -m pip check
.\model-envs\sam\Scripts\python.exe -m pip install pip==26.0.1
.\model-envs\sam\Scripts\python.exe -m pip install --build-constraint model_services/requirements-build-constraints.txt -r model_services/requirements-sam.txt
.\model-envs\sam\Scripts\python.exe -m pip install --no-build-isolation --no-deps .
.\model-envs\sam\Scripts\python.exe -m pip check
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

For original BF16 disk offload, generated `workbench.env` includes a 3600-second
planning budget and a separate 1800-second feedback budget. These are request
limits, not expected runtimes; retain actual elapsed times in the run records.

The SAM adapter provides two recorded sampling paths. **Fast** retains 896 x
896 whole-image inference, FP16 CUDA autocast, bilinear foreground-probability
restoration, threshold 0.5 and no EPOC refinement. **Tiled** (`accurate` in the
interface contract) divides the original image into non-overlapping 512-pixel
cores with up to 64 pixels of context on each side. It runs the same backend on
each crop, restores its binary mask to crop coordinates and copies only that
crop's core into the output. Every output pixel belongs to exactly one core.
The response records all core/read windows and the actual tile count; more than
256 tiles are rejected before inference. This optional path changes sampling
and has not been shown to improve semantic accuracy. Existing Fast scientific
reproduction results are not replaced by tiled predictions. On images no larger
than 512 x 512, Tiled uses one crop and matches Fast.

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
GEO_AGENT_FEEDBACK_TIMEOUT_SECONDS=900
GEO_PORT=4180
```

The default chat timeout is 120 seconds. Slow disk-offload requests may need
1800 or 3600 seconds per Agent call; 3600 is the supported maximum. The explicit
128-token budget can truncate answers, so increase it if necessary and record
the setting. A timeout increase permits slow execution; it does not accelerate
inference. Shell `GEO_` variables override `.env`; clear or update stale values.

The feedback timeout is separate (default 60 seconds) and cannot exceed the
planning timeout. Original-weight disk offload may require an explicitly recorded
larger budget, as above. A feedback timeout preserves computed masks and
measurements and records a warning; it does not count as a successful full
Agent–SAM–Agent chain. Browser tasks now use saved IDs and progress polling, so
refreshing the page reconnects to the same task without repeating inference.
The local Agent checks generation deadlines cooperatively between token steps;
an individual slow CPU/GPU operation may finish after its deadline.

Start the core in a separate terminal:

```powershell
.\model-envs\core\Scripts\python.exe quickstart.py --port 4180
```

Open `http://127.0.0.1:4180`, choose live mode, upload your image and use
**Runtime settings -> Check connections**. A scene question creates a qualitative
answer; `Extract all planes` requests aircraft segmentation. Inspect the returned
SAM response and grid-aligned mask. Ask for the left
half next: the Harness applies a deterministic pixel-half domain to the full
prediction, so an object crossing the center line can be clipped. All displayed
areas, denominators and ratios are computed by the core.

There is no preset expected sentence or foreground count for an arbitrary new
image. A successful service request can produce an empty mask or a semantically
incorrect response. Readiness verifies loading, and the acceptance script
verifies execution and exported-evidence consistency; neither establishes model
accuracy. The saved real run and its nonempty separate SAM prompt result are
documented in [local validation](local_model_validation.md), including the
observed prompt sensitivity. Use the bundled saved mask to reproduce fixed
counts, rather than expecting fresh inference to reproduce those counts.

`127.0.0.1` identifies processes on the computer running the services. Keep the
local supervisor terminal open while using the module.

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
the same way. Replay checks saved pixel arithmetic and internal consistency.
Semantic assessment and source authentication require separate evidence.

The [saved validation record](local_model_validation.md) reports a completed
real two-model NAIP run, separate nonempty SAM prediction and supervised
start/status/stop checks. The laptop's disk-offload end-to-end run took about
35.6 minutes. Use the retained-model-mask replay for a short walkthrough without
model weights.

## Stop the local models

```powershell
.\model-envs\core\Scripts\python.exe -m model_services.launcher stop --config model_services/profile.local.json
```

Alternatively press Ctrl+C in the original supervisor terminal. Shutdown cleans
up only its own model children. Stop the separate workbench terminal with Ctrl+C
when finished.
