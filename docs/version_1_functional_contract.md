# GeoMaskLab version 1.0 functional contract

Decision date: 5 October 2026. The feature scope below is fixed for version 1.0.
The implementation is 1.0.0-dev.5; a fixed scope is not a claim that release
acceptance or scientific validation has been completed.

## Problem and intended users

An RGB-chip segmentation experiment is difficult to reuse when its image,
prediction, target, selected region, measurement denominator, model origin and
reference labels are stored separately. A new crop can change coverage without
changing prediction quality, and similarity between two predictions does not
measure accuracy against a reference.

GeoMaskLab connects these artifacts in a local inspection and handoff workflow.
Researchers and students can use configured model services or bring an existing
binary prediction, inspect and branch results, measure regions, assess supplied
reference labels, and hand over exact inputs for deterministic recomputation.

This positioning is an inference about workflow value, not established global
novelty. SAMGeo already provides text-prompt batch segmentation; Label Studio
provides annotation exports; CVAT provides review workflows. These capabilities
are not claimed as inventions of GeoMaskLab. Superiority requires a defined
task, competing versions, comparable inputs and measured user effort or output
quality; no superiority claim is made from documentation comparisons alone.

## Fixed functional boundary

| User task | Version 1.0 behavior | Completion criterion |
| --- | --- | --- |
| Start locally | Python backend and English browser workbench; Pillow-only offline path | Extracted source starts and documented examples run without model accounts |
| Select an image | RGB chip upload or clearly labeled procedural fixture | File/pixel limits and displayed coordinates are explicit |
| Obtain a mask | Bounded RemoteAgent/RemoteSAM execution, or import aligned binary PNG | Imported results cannot be mislabeled as live inference; invalid inputs cannot overwrite valid masks |
| Choose a domain | Whole image, one pixel half, rectangle, explicit complement | Pixel coordinates replay exactly; each denominator is shown |
| Inspect results | Original/mask/overlay views, opacity and comparison slider | Views refer to the selected saved version |
| Preserve versions | Selected parent, derived versions and failure records | Prior valid masks survive failed requests and reload |
| Investigate spatial changes | Offline region recalculation from full prediction | No model calls; full prediction/source bytes retained; new review pending |
| Compare predictions | Common-domain agreement and colored differences | Same exact image and target/complement; empty union/domain undefined |
| Assess references | Scoped TP/FP/FN/TN and IoU/Dice/precision/recall/specificity/pixel accuracy | Hand-counted cases, odd sizes, ROI, complement and empty masks agree with explicit definitions |
| Review semantics | Hash-bound, self-reported pending/accepted/rejected decisions | Reference scores cannot silently accept a result or authenticate a reviewer |
| Manage experiments | Names, notes, pins, search, measurement CSV | Metadata changes preserve evidence; failed rows retain blank unavailable metrics |
| Hand off evidence | Verified single-result ZIP and reproducible reference-assessment ZIP | Exact inputs retained and deterministic checks precede reuse |
| Process small batches | Explicit 2–5-session batches, progress and aggregate export | Failure in one image does not erase other results |
| Continue annotation | Optional Label Studio brush-prediction converter | Official SDK round trip verified; full GUI integration remains a separate check |
| Learn and troubleshoot | English offline guide, procedural examples, launchers and error messages | No remote assets required for the local guide; commands forward arguments correctly |

## Acceptance gates

1. **Arithmetic and state:** meaningful automated tests, legacy evidence replay,
   immutable inputs, invalid-input rejection, persistence and model-free examples.
2. **User interface:** import a PNG through the file chooser, select its version,
   assess a reference, inspect displayed metrics and download/recompute its packet.
   Check modal errors, English labels and absence of page-wide horizontal overflow.
3. **Distribution:** exact-commit source archive, file hash verification, extracted
   launch and examples with the minimal dependency set. Cross-platform CI must
   refer to this commit, rather than an earlier passing commit.
4. **External services:** configured-service checks and a real-image inference
   with recorded model/version metadata. A prior implementation's integration
   result is historical evidence, not acceptance of this build. Independent
   external-service installation and a real-user study remain unperformed.
5. **Release identity:** clean source, license, dependency notices and consistent
   version identifiers. Stable tagging follows software acceptance. Creator
   approval, archival DOI and manuscript files remain publication work.

The recorded status for each gate belongs in the exact build's acceptance
record; an unchecked gate must not be reported as passed. No new major features
are planned before closing these gates. Fixes and clearer UI wording are allowed.

## Deferred scope

Version 1.0 does not provide geographic-area measurement, CRS transformation,
large raster tiling, model training, a manual polygon/brush editor, unrestricted
agent actions, multi-user authentication or an executable that bundles all model
weights. Existing annotation and GIS applications remain appropriate for those
tasks. The original competition repository remains unchanged.

Buildings and aircraft are the primary application categories. Other supported
categories remain experimental. Prior real-image semantic results retain their
original limitations; no new independent accuracy or adoption claim is created
by this feature consolidation.

## Primary references consulted

- [SAMGeo text-prompt batch example](https://samgeo.gishub.org/examples/text_prompts_batch/)
- [Label Studio annotation exports](https://labelstud.io/guide/export.html)
- [CVAT manual QA and review](https://docs.cvat.ai/docs/qa-analytics/manual-qa/)

These are product documentation references, not a complete literature survey or
a benchmark of whole competing applications. GeoRocket's release packages also
informed documentation and launcher organization; no third-party binaries or
illustrations were copied.
