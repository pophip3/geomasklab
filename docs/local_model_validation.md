# Local-model and reviewer delivery validation

Software version remains **1.0.0**. Revised snapshots have an exact Git commit
and dated build/checksum records; the original release tag and artifacts are
preserved. The manuscript was not edited during this code delivery.

## Reviewer installation and replay

GitHub Actions checks source installation and the bundled reviewer commands
on Windows, Linux and macOS. The extended matrix covers Python 3.10 and 3.13,
optional geo/schema/interoperability/signing dependencies, wheel installation,
extracted-source startup and the connected workbench examples. See
[research checks](https://github.com/pophip3/geomasklab/actions/workflows/research-checks.yml)
and [reviewer/coverage checks](https://github.com/pophip3/geomasklab/actions/workflows/ci.yml).

Core line coverage was 86.47% on Windows and about 86.51% in the Linux CI run:
2,484 executable lines, with no excluded lines. The coverage badge rounds to
86.5%; it describes `src/geomasklab`, not GPU model code or all workbench code.
CI requires at least 80%. One local test originally skipped the optional Label
Studio SDK; the extended CI environment installs that dependency.

The source archive checker runs examples in a separate extracted directory,
verifies every manifest hash and starts its browser server. The wheel checker
uses a fresh Pillow-only environment outside the development checkout and
exercises the installed CLI, writable workbench storage and browser resources.

## Actual model execution on 7 October 2026

The full [saved acceptance report](validation/local-model-acceptance-20261007.json)
records genuine local RemoteAgent and RemoteSAM requests on the supplied
512 x 512 NAIP chip. It reports `passed: true` for scene answering, fresh
segmentation, Agent feedback, four exports, independent pixel counts and source
preservation. Original BF16 Agent weights and the fixed official SAM architecture
were used; no quantization or injected model responses were used.

The tested laptop had an RTX 4060 Laptop GPU with 8 GB VRAM and 16 GB system RAM.
Agent placement used a 3 GiB GPU budget, 2 GiB CPU budget and disk offload;
vision input was limited to 65,536 pixels, context to 4,096 tokens, output to
128 tokens and chat timeout to 3,600 seconds. These are placement/input budgets,
not whole-process memory limits. The core used Python 3.12.14; the separately
prepared model environments used Python 3.9 and inherited existing packages.
This is not a clean model-environment installation claim for every OS.

Scene generation took 572.595 seconds. Segmentation planning, SAM execution and
Agent feedback together took 1,561.756 seconds. The complete run took about
35.6 minutes. An 8 GB GPU can execute this tested configuration with disk offload,
but it is unsuitable for a promised short live demonstration.

The class prompt `building in the image` produced an **empty mask**. The workbench
kept the evidence, marked the result `needs_review`, and warned that an empty
prediction does not prove target absence. Four exported bundles verified; this
demonstrates software execution and arithmetic, not accurate building detection.

A separate request with referring prompt `all buildings` on the same image,
source and checkpoint produced 6,543 foreground pixels. Its retained mask and
model/input identities are in [the bundled data](../examples/data/local-model-mask/).
Run:

```sh
python examples/replay_model_mask.py
```

Expected foreground counts are whole 6,543, left 0, right 6,543 and rectangle
713. The script checks hashes, independently counts pixels, preserves full-mask
pixels and exports four bundles. It performs no new inference. These different
prompt outcomes illustrate sensitivity to wording; target boundaries and scene
answers still need semantic review.

The unified launcher was also exercised with both real services, explicit
readiness, generated local settings, fresh SAM requests and owned-process
shutdown. Both ports closed after stop. Full checkpoint SHA-256 verification
matched the retained Agent shards/index and SAM checkpoint. Startup failures
produce an explicit error and clean up owned processes; health alone is not
treated as readiness.

## What this verification establishes

The tested installation, request/response integration, pixel accounting and
evidence replay work without an author-hosted server. It does not guarantee
model access/download availability, arbitrary hardware compatibility, response
latency or semantic accuracy. Models require separately obtained assets and
adequate resources; the lightweight and retained-mask examples remain available
without them. Use [the local setup guide](local_model_modules.md) for fresh inference.
