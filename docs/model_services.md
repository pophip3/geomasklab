# External model services

The standard offline workflow requires only Python and Pillow. Live scene
responses and segmentation additionally require compatible deployed model
services. GeoMaskLab does not distribute RemoteAgent/RemoteSAM source trees or
checkpoints. Service deployment and model licensing are separate from the
workbench installation.

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
| `GEO_AGENT_API_KEY` | Planner credential, if required; retained on the Python server |
| `GEO_REMOTESAM_URL` | Compatible mask service `/predict` URL |
| `GEO_REMOTESAM_REVISION` | Verified checkpoint/deployment revision; unknown revisions disable safe live reuse |
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
Buildings and aircraft have a limited prior-version application study; the
others are experimental. Whole-image masks are requested before deterministic
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
