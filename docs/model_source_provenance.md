# Model and adapter provenance

Checked on 7 October 2026 for the `1.0.0 revised snapshot` branch
`softwarex-v1.0.0-revised`. The fixed `v1.0.0` release is unchanged.
GeoMaskLab distributes its own HTTP adapters and
measurement integration. Model checkpoints and the RemoteSAM architecture
remain separately obtained dependencies. The workbench's MIT license does not
relicense those external assets.

## Fixed source identities

| Asset | Authoritative source | Fixed identity |
| --- | --- | --- |
| RemoteSAM architecture | [Official RemoteSAM repository](https://github.com/1e12Leon/RemoteSAM) | [`ebb7bc278c7343c29c8c16b035289f78f40f0f72`](https://github.com/1e12Leon/RemoteSAM/commit/ebb7bc278c7343c29c8c16b035289f78f40f0f72), default branch `master` |
| RemoteAgent upstream orchestration reference | [Official RemoteAgent repository](https://github.com/1e12Leon/RemoteAgent) | [`74dc734540a600eeb8ece9c371b0ca2b945856a0`](https://github.com/1e12Leon/RemoteAgent/commit/74dc734540a600eeb8ece9c371b0ca2b945856a0), default branch `main` |
| RemoteSAMv1 checkpoint | [Official Hugging Face files](https://huggingface.co/1e12Leon/RemoteSAM/tree/a6d09f44bac5b64be7f74980b15afb2a749b5e92) | Repository revision `a6d09f44bac5b64be7f74980b15afb2a749b5e92` |
| BERT tokenizer files | [Official BERT files](https://huggingface.co/google-bert/bert-base-uncased/tree/86b5e0934494bd15c9632b12f734a8a67f723594) | Revision `86b5e0934494bd15c9632b12f734a8a67f723594`; tokenizer/config assets only |
| RemoteAgent checkpoint | [Official ModelScope distribution](https://modelscope.cn/models/AIMGroup/RemoteAgent) | Downloaded snapshot identified by the retained file hashes; the historical download did not record a ModelScope commit |

The source commits were verified through the GitHub repository API. The
RemoteSAM checkpoint revision, exact size and LFS content hash were verified
through [the official Hugging Face model API](https://huggingface.co/api/models/1e12Leon/RemoteSAM?blobs=true).
Pin the commit when obtaining architecture code; a mutable branch name is not
a frozen experimental dependency.

For external startup validation, 14 architecture Python files were obtained
from this exact SAM commit through the GitHub API in base64 form. Decoded bytes
were verified against each API Git blob SHA-1, with SHA-256/size records retained
separately. These unmodified official files include `args.py`, the `lib` model
files, `lib/mmcv_custom` checkpoint helpers and `arc` modules. This verifies
source-byte identity, not completed real inference on the official-source
model. The checkpoint helper imports MMCV 1 APIs, supplied by `mmcv==1.7.2`
in the separate SAM requirements; the architecture import chain does not
require CuPy.

## Checkpoint identity

`RemoteSAMv1.pth` is 2,566,704,235 bytes (about 2.57 GB decimal). Its SHA-256 is:

```text
f85dfa044a527f096b9e41eacfe298040d52e77fca642f46dfe1226745e137e7
```

The adapter requires this fixed checkpoint and records source-file hashes,
tokenizer hashes, package versions and restoration parameters in its model
metadata. It checks all trained state keys, permitting only the generated BERT
position-id buffer to be absent. This is a compatibility check, not a claim of
segmentation accuracy.

The retained RemoteAgent snapshot contains four BF16 Safetensors shards. Its
index declares 8,292,166,656 parameters and 16,584,333,312 tensor bytes; the
four shard files total 16,584,414,544 bytes (about 16.58 GB decimal). The fixed
historical hashes are in
[`remoteagent-weight-lock.json`](../evaluation/supplementary/remote-model/remoteagent-weight-lock.json).
That file explicitly records `repository_revision: null`. A current ModelScope
download must be compared with those hashes before it can be described as the
same snapshot; a newly issued snapshot is a different inference dependency.

The local supervisor's [model lock](../model_services/model-lock.json) records
Agent index/shard hashes and sizes, SAM checkpoint identity, the official SAM
source revision and the BERT tokenizer revision. `check --hashes` compares the
complete checkpoint bytes with the recorded hashes. Source-byte validation,
model readiness, real inference and measurement replay are separate checks.

## What is implemented here

- `model_services/agent_service.py` loads the official local RemoteAgent weights
  with Transformers' `Qwen2_5_VLForConditionalGeneration` architecture and serves
  the non-streaming model-list/chat endpoints consumed by GeoMaskLab. It does
  not import or redistribute the upstream general RemoteAgent tool executor.
- `model_services/sam_backend.py` imports the separately obtained RemoteSAM
  architecture, loads the fixed checkpoint, performs 896 x 896 inference,
  restores foreground softmax probabilities bilinearly and thresholds at 0.5.
  This follows the six-image SoftwareX mask-handoff protocol. It is different
  from the competition service's argmax/nearest-neighbor restoration, so masks
  need not match a competition video pixel for pixel.
- `model_services/sam_service.py` returns a checked binary mask on the original
  image grid and confirms the implemented `fast` mode. It does not silently
  claim the workbench's optional accurate/tiled mode.
- The workbench owns validated task routing, image binding, pixel scopes,
  statistics, versions and evidence export. Its restricted single-call planner
  protocol does not expose the full upstream RemoteAgent tool collection.

The competition repository supplied the existing deployment context and
transport requirements: [SitianGao/geoscope](https://github.com/SitianGao/geoscope).
The paper software and these independently maintained adapters are delivered
through [pophip3/geomasklab](https://github.com/pophip3/geomasklab).

## Third-party terms and attribution

At the checked RemoteSAM source commit, GitHub reports no detected license and
the repository tree has no top-level license file. The checked checkpoint
repository API likewise supplies no license declaration. Therefore its source
and weights are obtained from their official providers and are not vendored or
declared MIT in this distribution. Follow the providers' stated terms and access
process for the intended use.

The locally retained RemoteAgent model README declares Apache License 2.0 for
that weight snapshot. This declaration is separate from the upstream
orchestration source; its checked repository does not provide a top-level
license for that code. The original adapter here uses the installed Transformers
architecture and independently downloaded checkpoint.

The BERT tokenizer repository declares Apache 2.0. Its standalone pretrained
weight files are unnecessary: RemoteSAMv1 already contains its trained BERT
tensors, and the adapter constructs the standard BERT structure locally before
loading those tensors.

Use the model authors' references when describing their models:

- Yao et al., [RemoteAgent: Bridging Vague Human Intents and Earth Observation
  with RL-based Agentic MLLMs](https://arxiv.org/abs/2604.07765), 2026.
- Yao et al., [RemoteSAM: Towards Segment Anything for Earth Observation](https://arxiv.org/abs/2505.18022), 2025.

## Reproduction boundary

Checkpoint hashes and source commits identify inputs; they do not establish
new semantic performance. The existing six-image case evaluates a fixed
RemoteSAM mask handoff and arithmetic replay. It does not evaluate RemoteAgent
scene-answer accuracy or independently validate this newly packaged complete
local chain. Report actual deployment and fresh-inference acceptance separately
from CPU-only contract tests or successful evidence replay.
