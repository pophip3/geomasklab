# External model services

The standard offline workflow requires only Python and Pillow. Live scene
responses and segmentation additionally require compatible deployed model
services. GeoMaskLab does not distribute RemoteAgent/RemoteSAM source trees or
checkpoints. Service deployment and model licensing are separate from the
workbench installation.

The revised 1.0.0 source includes a [local two-model launcher](local_model_modules.md),
with separate environments and fixed asset checks. Reviewers can run it on their
own computer; no author-hosted endpoint is required.

## Configuration

Copy `.env.example` to `.env` in the project root. Fill in actual, reachable
endpoints and the deployed model identifier, then restart `quickstart.py`.
Environment variables set in the shell take precedence over `.env`, including
an intentionally empty value. The loader accepts plain `GEO_` assignments and
does not evaluate shell syntax. Keep `.env` out of Git and source archives.

| Setting | Purpose |
| --- | --- |
| `GEO_AGENT_BASE_URL` | OpenAI-compatible API base, normally ending in `/v1` |
| `GEO_AGENT_MODEL` | Exact multimodal model identifier available on the service |
| `GEO_AGENT_TIMEOUT_SECONDS` | Chat timeout from 5 to 3600 seconds; default 120 |
| `GEO_AGENT_MAX_TOKENS` | Optional 16–1024 output-token budget; truncated replies are rejected |
| `GEO_AGENT_FEEDBACK_TIMEOUT_SECONDS` | Separate feedback budget, 5–3600 seconds; default 60, capped by the planning timeout. Completed masks and measurements survive feedback failure. Explicitly record larger budgets used for slow disk offload |
| `GEO_AGENT_FEEDBACK_MAX_TOKENS` | Optional reporting output budget, 16–1024 tokens, independent of the planning output budget. Without this setting, reporting retains the existing cap of 96 tokens. A reply cut off at the token limit is rejected and retained as a diagnostic, never presented as a completed answer |
| `GEO_AGENT_API_KEY` | Planner credential, if required; retained on the Python server |
| `GEO_REMOTESAM_URL` | Compatible mask service `/predict` URL |
| `GEO_REMOTESAM_REVISION` | Verified checkpoint/deployment revision; unknown revisions disable safe live reuse |
| `GEO_REMOTESAM_QUALITY_MODES` | Optional comma-separated `fast`/`accurate` declaration, generated from the loaded service's readiness metadata. The current local adapter supports both; explicitly unsupported modes are rejected before planning |
| `GEO_SERVICE_PROXY_MODE` | `direct` by default; `environment` only if the service requires the configured HTTP proxy |

`.env.example` addresses are examples, not public inference services. The browser
never receives the configured credentials. Live mode sends the uploaded image
to the configured services. Use images that may be processed there.

## Planner protocol

The planner uses `/chat/completions` with a multimodal image and explicit task
context. For dense tasks it must return exactly one restricted literal call:

```text
T_call(referring_expression_segmentation, "image_path", "all buildings")
T_call(semantic_segmentation, "image_path", ["aircraft"])
```

These are alternative calls, not two calls for one task. The parser accepts
literal strings/a flat list and a turn-specific tool allowlist; it never evaluates
model-generated Python. The executor binds the actual session image and owns
target alignment, ROI, scope, complement, execution mode and batch membership.
Scene-response turns expose no segmentation tool and use one `<answer>` block.
Tool feedback may report the recorded result but cannot trigger another action.
Prompts request English; original returned text is preserved as source evidence.

The browser submits a single-image task to `POST /api/run/start` and follows the
returned task ID through `GET /api/task/<id>`. Progress names describe actual
execution stages; they are not estimates of model completion or quality.
Task status and final results are saved under the experiment directory. Refreshing
the browser reconnects to the same task instead of submitting inference again.
A failed polling connection is retried. If reconnection fails, inspect the saved
task and experiment before retrying. A server restart interrupts active inference;
the software never claims that an interrupted task completed or automatically
repeats the model request. The synchronous `/api/run` remains available for
existing API clients.

The local Agent adapter accepts the `X-Geo-Request-Budget-Seconds` header and
checks its deadline during token generation. Expired output is rejected, and the
generation lock is released when inference exits. This stop is cooperative: it
cannot interrupt an individual CPU/GPU operation already in progress. A slow
offloaded forward pass can therefore finish after the declared deadline. Other
OpenAI-compatible services may ignore this header and require their own server
timeouts. Availability checks and synthetic contract tests do not establish
successful real-model inference.

## Mask contract

The service receives base64 PNG `image` and either `task=referring_seg` with
English `text`, or `task=semantic_seg` with one `classes` entry. It also receives
the resolved `quality_mode` (`fast` or `accurate`). A referring response contains
`status=success` and base64 `mask`; a semantic response uses `masks` keyed by the
class. The binary mask must be restored to the original image dimensions.
Return the confirmed `quality_mode` and preferably model revision/checkpoint
hash, service version, parameters and timing. Explicit mode requests cannot be
mislabelled when the service does not confirm them.

Supported targets are buildings, aircraft, roads, water, vegetation and ships.
In the 14 October 2026 build of 1.0.0, building-class requests and canonical `all buildings` referring
prompts use the supervised OpenEarthMap UNet-EfficientNet-B4 SCSE building
channel (class 8). All uploaded images follow the same inference path: native
resolution, 512-pixel tiles, 256-pixel stride, four rotations, Hann-weighted
probability fusion, then threshold 0.5. Accurate mode additionally averages
mirrored views. This is not an image-name lookup or saved-mask replacement.

Supply `sam.building_model_dir` in the local model profile (or pass
`--building-model-dir` to `geomasklab-sam`). The directory contains
`model.safetensors` and `training-manifest.json`; the manifest's weight checksum
is verified before readiness is reported. The launcher writes
`GEO_BUILDING_MODEL_REVISION` from the loaded checkpoint and inference identity.
Copy the generated settings to the workbench as usual. An unknown building
revision disables cache reuse; historical RemoteSAM masks are never reused for
the new building route. The workbench and model service both need this update.
The model files are separate from the Python wheel. Prior-version application
study metrics do not describe this model; multi-image diagnostic results must
state possible overlap with official model pretraining.

Water requests use a supervised OpenEarthMap UNet-EfficientNet-B4 model with
park, land and walkway correction training, followed by automatic SAM image-edge
refinement in an eight-pixel boundary band. Both semantic `water` requests and
canonical water referring prompts use this route. RGB tiles retain their original
resolution and overlap by 256 pixels. Water interiors come from the supervised
classifier; the edge model adjusts shoreline, pier and boat boundaries while
preserving every non-water pixel from the classifier. This
prevents edge refinement from refilling correctly excluded narrow walkways.
Four rotation directions are averaged before thresholding; the refined mode
also averages mirrored views. Continuous-angle augmentation and hard negative
mining cover park crops and aligned water/land labels during correction training.
The launcher records a separate water pipeline revision for cache reuse.
HTTP inference uses one persistent model thread; request handlers share that
worker instead of creating a new CUDA inference context for every request.
Explicit water tasks bypass text-model planning. An empty prediction is a normal
completed water task with zero coverage. Model assets remain outside the wheel.
Buildings and aircraft have a limited prior-version application study; roads,
vegetation and ships remain experimental. Whole-image masks are requested before deterministic
scope/complement operations. A service must not apply an unrecorded ROI or return
a probability map as a ready-to-measure binary mask.

## Acceptance sequence

1. Check the service model list and explicit mask readiness declaration from
   **Runtime settings → Check connections**. This sends no image and establishes
   availability only.
2. Use a separate development image for a live scene-response turn; confirm that
   no mask or numerical measurements were produced for that route.
3. Request one supported mask; inspect recorded request, mode confirmation,
   original/output dimensions, revision and execution state.
4. Inspect the overlay for semantic problems; export the evidence and verify it
   offline. Verify a region-derived result without a new model call.
5. Record hardware, service versions and model/checkpoint identity separately
   from the workbench version. New semantic-performance claims require a new,
   prospectively frozen evaluation rather than reusing old numbers.

The author's earlier local deployment passed real inference on 4 October 2026
and a frozen prior-version application study. That observation does not prove
installation on an unrelated reviewer's hardware. RemoteAgent used an existing
laboratory service; RemoteSAM used a local NVIDIA GPU deployment. Private
infrastructure, tunnels and checkpoints are excluded from the distributable
workbench. The reviewer can run the complete procedural workflow and inspect
portable evidence independently without those services.
