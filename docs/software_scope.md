# Software scope and application context

GeoMaskLab adds replayable, region-aware measurement evidence to an existing
segmentation mask. Its main workflow is:

**mask -> explicit spatial scope and denominators -> deterministic measurement
-> portable evidence -> independent offline replay**.

## Users and practical task

A researcher receives a mask and a coverage number from a colleague. To reuse
that result, they need its exact image, selected region, denominator and source
mask. GeoMaskLab retains these together, rejects inconsistent records and permits
a new region to be measured without rebuilding the model environment.

Masks may be supplied by GIS/annotation software, a model or a local baseline.
Provider execution is an adapter; the scientific scope is measurement and replay.
Text segmentation, experiment history, annotation exports and manual review already
exist in other tools and are not treated as GeoMaskLab's contribution. Global
uniqueness, industrial adoption and reduced human labor require separate evidence.

## Core version 1.0 boundary

| Task | Implemented contract |
| --- | --- |
| Install | Headless src package and wheel, Python 3.10+, Pillow |
| Supply a mask | Exact-grid binary PNG; explicit source/target/alignment assertions |
| Define a domain | Whole image, one pixel half, rectangle; exclusive upper bounds |
| Measure | Foreground pixels; both whole-image and selected-region denominators; candidate components |
| Preserve evidence | Exact source bytes, full and scoped masks, metadata, logs and SHA-256 manifest |
| Verify | Replay the scope and measurements; compare records and source identities |
| Derive | Recalculate from the verified full mask; preserve provenance and reset review |
| Inspect | Verified standalone English HTML report; optional existing browser workbench |
| Assess labels | Separate reference-assessment packet with exact scoped confusion counts |
| Adapt a source | Model-free RGB color baseline or local executable argument-array hook |

The core currently supports the six task labels retained by the workbench. Labels
and review decisions do not establish semantic accuracy. The real NASA example
uses green-color candidates and explicitly documents their unvalidated semantics.

Version comparison, experiment management, batch controls, animation, model-service
questions and Label Studio conversion remain supporting source-workbench features.
They are frozen rather than expanded or presented as independent scientific claims.

## Measurement definitions and limitations

For `A` positive pixels in an image of `W*H` pixels and a region of `R` pixels,
`area_ratio=A/(W*H)` and `scope_area_ratio=A/R`. Empty-region ratios are null.
Halves split at floor(width/2) or floor(height/2); the remainder belongs to the
right or bottom. A rectangle cannot be combined with a half in the public offline
operation. Legacy bundles may omit within-region fields, and remain readable.

Measurements use pixels. GeoTIFF/CRS processing, physical area, polygon zones,
temporal change and signing remain separate extensions pending validated designs.
Internal replay is distinct from semantic accuracy and authenticity. A completely
self-consistent replacement bundle can pass without identifying its creator.
Historical real-image metrics retain their original code and dataset identities.

See [core API and format](core_package.md), [architecture](architecture.md),
[reference scoring](reference_evaluation.md) and [workflow evidence](workflow_study.md).
