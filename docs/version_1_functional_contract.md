# Version 1.0 functional contract

Core decision date: 5 October 2026. The five-operation contract was implemented
in `1.0.0rc4` and retained in stable version `1.0.0`.

The software freeze target consists of five connected operations: declared pixel
validity and realized configuration, fair result comparison, reliable manifest-based
batch execution, candidate-component inspection and one shared-core browser workflow.
All five operations are implemented in the core, CLI and source workbench.
Automated acceptance uses the exact versioned artifacts. Current source/archive
identities are listed in [submission identities](submission_20261018.md).

## Five connected operations

| Operation | Implemented contract |
| --- | --- |
| Valid pixels/configuration | Source-bound image, region and explicit validity; complement excludes invalid pixels; null empty-domain ratios |
| Fair comparison | Intersection or identical-domain policy; source/geometry/validity explanations; shared/excluded accounting and replay packet |
| Manifest batch | Explicit pairs; atomic samples; isolated failures; cooperative cancel, crash-safe locks and verified identity-bound resume; macro/micro means |
| Candidate inspection | Stable 8-connected IDs, bounding boxes, pixel-center centroids and independent boundary flags; source-preserving filters |
| Browser workflow | The same core creates, compares, inspects, batches and replays packets; completed batch samples reopen as normal evidence |

The real NAIP `examples/five_step_workflow.py` exercises the connected operations
and checks independent pixel sets. Its perturbed baseline/reference is a protocol
fixture, not an independent segmentation-accuracy result.

## Core contribution

Segmentation mask -> explicit spatial domain and coverage denominators ->
deterministic pixel measurements -> portable evidence -> offline replay.

The wheel includes the reusable core and complete browser workbench; the core
can run without starting the browser server.
It requires Pillow and runs without model services. Target accuracy, authenticated
origin and human workflow value require separate evidence.

## Fixed acceptance boundary

1. Create evidence from an exactly aligned external binary PNG; preserve source
   bytes, declared provenance and pending review.
2. Verify source identities, lossless mask normalization, deterministic spatial
   replay, recorded statistics and review bindings before reuse.
3. Recalculate a whole image, half or rectangle from the full saved mask without
   inference; retain historical provenance and reset review.
4. Print versioned JSON Schemas and optionally validate metadata shapes offline.
5. Produce an English standalone report only from successfully replayed evidence.
6. Support a reproducible local RGB baseline and a fresh-output command adapter;
   retain explicit candidate semantics and caller-asserted origin.
7. Run a credited real-photo handoff example, without presenting its baseline as
   ground truth or an independent accuracy experiment.
8. Install and run the wheel outside the checkout with Pillow-only dependencies.
9. Build a source archive at a fixed commit and check its hashes, examples,
   browser startup and launchers after extraction.

Reference-assessment packets support validation. Experiment management, annotation
conversion, model questions and animation are available in the workbench and are
optional for headless installation.

## Validation and extensions

Automated acceptance belongs to the exact tested commit. Cross-platform CI,
source/wheel identity and package metadata are checked for the release under
review. [Local-model validation](local_model_validation.md) records live-model
execution, and the [handoff-study protocol](handoff_study.md) describes the
planned human evaluation.

Optional extensions add a replayed PROV-JSON mapping and matched-GeoTIFF area
assessment, with declared units, CRS, pixel equality, area assumptions and exported
mask-grid checks. Polygon/MultiPolygon domains and optional trusted-key signatures are implemented. They retain the Pillow-only base dependency; temporal change remains deferred. The supplied MEP 2.0 prototype was evaluated separately;
it does not define the new validity format. Legacy geoscope-evidence/1.0 remains
readable, and validity-aware results use geomasklab-evidence/2.0.

See [software scope](software_scope.md), [core package](core_package.md) and
[architecture](architecture.md) for definitions and extension boundaries.
