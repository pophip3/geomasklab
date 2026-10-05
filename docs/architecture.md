# Architecture and maintainability

GeoMaskLab has a headless, Pillow-only core and an optional browser workbench. Python owns file identity,
execution constraints, pixel processing and storage; JavaScript manages the
interactive display. External model services provide predictions. The default
offline demonstration substitutes explicit procedural fixtures rather than
pretending to perform neural inference.

| Module | Responsibility |
| --- | --- |
| `src/geomasklab/api.py`, `measurements.py`, `geometry.py` | Pure evidence creation, explicit domains and deterministic pixel measurements |
| `src/geomasklab/evidence.py`, `regions.py`, `review.py` | Bundle replay, saved-mask derivation and hash-bound review |
| `src/geomasklab/provenance.py`, `geospatial.py` | Standard provenance mapping and optional matched-grid physical-area assessment |
| `src/geomasklab/providers.py` | Local RGB baseline and fresh-output executable adapter |
| `src/geomasklab/report.py`, `cli.py`, `schemas/` | Verified standalone reports, installed commands and versioned metadata schemas |
| `quickstart.py`, `runtime_config.py` | Startup, local settings and dependency guidance |
| `server.py` | HTTP routing, session locks, bounded task orchestration and persistence |
| `planner_protocol.py`, `agent_bridge.py` | Literal planner parsing, target alignment, service adapter and bounded tool feedback |
| `task_grammar.py`, `v07_contract.py` | Explicit task intent, ROI, quality mode and batch constraints |
| `service_transport.py` | JSON HTTP transport, proxy handling and service inspection |
| `pixel_geometry.py` | Region denominators and eight-connected candidate measurements |
| `region_analysis.py` | Verified saved-mask spatial analysis without inference |
| `semantic_review.py` | Self-reported decisions bound to exact image/mask hashes |
| `export_bundle.py`, `evidence_handoff.py` | Evidence packaging, independent validation and import |
| `report_builder.py` | English reports from recorded fields without model-generated statistics |
| `label_studio_export.py` | Optional official-SDK brush-prediction conversion |
| `fixtures.py`, `reviewer_demo.py` | Procedural inputs and runnable reviewer workflow |
| `web/` | Browser interaction, canvas display and local styles/assets |

## Execution and persistence

A task binds one image and one category. A planner proposes one allowed action;
the executor checks intent and options before requesting a full mask. Binary
values and original dimensions are checked before complement/scope processing.
Metrics and provenance are persisted with a run ID, parent ID and software
version. Failed requests remain visible without overwriting valid earlier masks.
Per-session locks prevent conflicting mutation. New results always start pending
semantic review; a parent's acceptance is not inherited.

Each single-result bundle holds the original image, full pre-scope mask, final
mask, overlay, statistics, result, log, report and manifest. The offline verifier
reconstructs the recorded operations and checks numerical consistency before
import or saved-mask analysis. Checksums are integrity aids, not proof of identity.

Saved-mask analysis records its immediate source bundle/mask identities and
original prediction provenance, preserves target/complement and full-mask bytes,
and separates local analysis duration from historical inference time. No model
call or new semantic prediction is implied.

## Compatibility and extension

Existing `geoscope-*` schema/local-storage identifiers are retained for
compatibility despite the GeoMaskLab name. Legacy evidence can omit newly added
within-region fields; missing recorded values are not presented as original
observations. Raw historical/user text is preserved. Generated interface,
reports, errors and new examples use English.

Legacy root modules delegate to the src package. The server's external-mask
creation and all measurements use that same core, preventing a separate GUI
arithmetic implementation. The wheel excludes source-only browser assets.

Source modules have explicit boundaries, but `server.py` and `web/app.js` still
coordinate multiple operations. Changes should be small and verified through
behavioral tests and public API examples rather than an extensive unvalidated
rewrite. New scientific quantities need specified units, denominators and an
independent verification path. Optional geospatial operations are isolated from the core and use declared area
models. Model training, manual boundary editing and multi-user hosting remain outside
scope.
