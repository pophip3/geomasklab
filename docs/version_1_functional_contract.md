# Version 1.0 functional contract

Decision date: 5 October 2026. Current implementation: 1.0.0.dev7.

## Core contribution

Segmentation mask -> explicit spatial domain and coverage denominators ->
deterministic pixel measurements -> portable evidence -> offline replay.

The reusable core installs independently of the source-only browser workbench.
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

The existing reference-assessment packet is a supporting validation operation.
Version comparison, experiment management, annotation conversion, model questions
and animation are frozen auxiliary features. They are not separate contribution
claims and do not block the headless core's installation.

## Release gates

Automated acceptance belongs to the exact tested commit. Cross-platform CI,
source/wheel identity and package metadata must be checked before stable tagging.
Current-version live-model inference and an actual human handoff study are separate
scientific checks, not inferred from core tests or historical model results.

Optional extensions add a replayed PROV-JSON mapping and matched-GeoTIFF area
assessment, with declared units, CRS, pixel equality, area assumptions and exported
mask-grid checks. They do not widen the Pillow-only core requirement. Polygon zones,
temporal change and signatures remain deferred. The supplied MEP 2.0 prototype was evaluated separately;
it does not replace the compatible geoscope-evidence/1.0 format in this build.

See [software scope](software_scope.md), [core package](core_package.md) and
[architecture](architecture.md) for definitions and extension boundaries.
