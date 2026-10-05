# GeoMaskLab software scope and use context

Decision date: 5 October 2026. This document describes the intended version 1.0
functional scope. The version 1.0 feature boundary was consolidated in 1.0.0-dev.5 after
comparison, experiment management and reference-assessment development. The implementation remains a development build; this decision
does not certify publication readiness or establish novelty.

## Product definition

GeoMaskLab is a model-assisted workbench for traceable remote-sensing segmentation
and region-specific pixel measurements. A locally running Python backend serves
a browser interface. External model services provide scene responses and masks;
GeoMaskLab validates task fields, applies spatial constraints, records measurements
and result versions, and supports evidence handoff and review.

The primary users are remote-sensing researchers and students investigating RGB
image chips. A typical task is to segment buildings or aircraft, inspect the
returned mask, compare selected image regions, and send a result to a colleague
who needs to check the measurement without recreating the model environment.

## Scientific problem and proposed value

A coverage number is interpretable only when the image, semantic target, mask,
selected region, denominator and prediction origin are known. Changing a region
or passing a screenshot between collaborators can obscure these relationships.
GeoMaskLab keeps the relevant artifacts together and replays deterministic pixel
operations before imported results are displayed or reused.

The proposed contribution is a connected experiment and handoff workflow. It
does not introduce a segmentation model. Text-guided segmentation, history and
manual review already exist in other software:
[SAMGeo](https://samgeo.gishub.org/usage/),
[QGIS processing history](https://docs.qgis.org/3.44/en/docs/user_manual/processing/history.html),
and [Label Studio predictions](https://labelstud.io/guide/predictions.html).
The present evidence supports exact artifact round trips, consistency checks and
offline investigation of saved masks. It does not establish global uniqueness,
reduced human labor, superior model accuracy or industrial adoption.

## Intended application scenarios

1. **Building-mask inspection:** compare pixel coverage across an urban image
   chip or selected rectangle, inspect omissions and false positives, and retain
   each region analysis as a separate result version.
2. **Aircraft-mask inspection:** inspect candidate connected components and
   their boundaries in an airport image chip. Components are review candidates,
   not validated aircraft counts.
3. **Independent result review:** import an evidence ZIP, verify the image/mask
   identities and measurements, change its analysis region without calling
   models, and record a separate review decision.
4. **Annotation-tool handoff:** convert a verified mask into Label Studio brush
   predictions for further editing. The bridge produces predictions, not manual
   annotations or ground truth. Only the SDK converter has been tested so far.

These scenarios support exploratory research and quality inspection. Pixel
coverage is not a land-use inventory, geographic area estimate or validated
operational detection result.

## Version 1.0 feature boundary

| Feature | Decision and present implementation |
| --- | --- |
| RGB image input | Retain uploads and clearly labeled procedural fixtures; current upload limits are 12 MB and 16 million pixels. |
| Scene responses | Retain external-agent image questions; distinguish text answers from mask results. |
| Single-category segmentation | Retain bounded agent/tool execution and external RemoteSAM masks. Buildings and aircraft are the primary application categories. |
| Other categories | Retain road, water, vegetation and ship as experimental; no frozen semantic evaluation is claimed for them. |
| Spatial analysis | Retain whole image, one pixel half, or a rectangle ROI in original image coordinates. Upper coordinate bounds are exclusive. |
| Complement | Retain explicitly requested mask complement; offline region analysis preserves the source setting and target. |
| Measurements | Report foreground pixels, whole-image coverage, within-region coverage, and eight-connected candidate components. |
| Result versions | Preserve the selected parent, derived versions and earlier valid results after a failed request. |
| Review | Record self-reported pending/accepted/rejected decisions bound to image and mask hashes; new derived results start pending. |
| Evidence handoff | Export/import a single result with hashes, source mask, output mask, statistics and execution records; verify before reuse. |
| External mask import | Accept aligned binary PNG predictions with declared target/source; preserve input bytes, record no inference and begin a new pending-review version. |
| Reference assessment | Compare against supplied positive-target labels in the saved region, report TP/FP/FN/TN and six ratios, show errors and export all inputs for offline recomputation. |
| Version comparison | Compare saved predictions in their common region; mask agreement is distinct from reference assessment. |
| Experiment management | Search, name, annotate and pin investigations; export complete measurement ledgers including failures. |
| Offline investigation | Recalculate a selected region from the verified full-image mask without agent or segmentation calls; retain historical prediction provenance. |
| Small batches | Retain explicit batches of 2–5 image sessions and aggregate exports. |
| Label Studio bridge | Retain optional official-SDK brush predictions; complete annotation GUI acceptance is pending. |
| Review examples | Retain model-free procedural examples and scripts; they test software behavior rather than neural accuracy. |
| Distribution | Source release plus documented local startup; a Windows executable is an optional future convenience. |

Version 1.0 does not include georeferenced measurement, CRS transformation,
square meters/hectares, model training, manual boundary editing, multi-user
authentication, or unrestricted agent actions. Those would require separate
design and validation. The original competition repository is preserved.

## Statistical definitions

For a final foreground mask with `A` positive pixels, image size `W × H`, and
selected-region size `R` pixels:

- `area_ratio = A / (W × H)`: whole-image coverage; its existing definition is unchanged.
- `scope_area_pixels = R`: size of the selected rectangle or pixel half.
- `scope_area_ratio = A / R`: within-region coverage; null when an empty half has zero pixels.

Odd image sizes split at `floor(W/2)` or `floor(H/2)`. The remainder belongs to
the right or bottom half. A rectangle is not combined with a half-image in the
public offline operation. Legacy evidence without within-region fields remains
readable; its missing coverage is not silently inferred as recorded evidence.

The procedural example ROI `[80, 50, 280, 250]` has 12,850 foreground pixels,
40,000 region pixels and 480,000 image pixels. Its within-region coverage is
32.125%, while its whole-image coverage is approximately 2.6771%. These are
different descriptions of the same saved mask, not competing accuracy results.

## Implementation and acceptance

`POST /api/recalculate-region` accepts `session_id`, `run_id`, `scope` and optional
`roi`. It verifies the persisted source bundle, retains the full-mask bytes,
creates a new result version, resets review to pending and records
`execution_kind=saved_mask_region_analysis` and `inference_performed=false`.
It cannot change the semantic target, repair a prediction, or regenerate a
missing full-image mask. Source model timing is reported as historical timing.

```sh
python reviewer_demo.py
python examples/recalculate_region.py reviewer-output/right.zip
python -m unittest discover -s tests -p "test_*.py" -q
```

The offline example compares four derived masks against direct Pillow crops,
checks both denominators, preserves input/full-mask bytes and verifies exported
bundles. Integrity tests also cover legacy bundles, re-signed metadata faults,
complement retention, busy sessions, reload and HTTP handoff. This is not a
benchmark against a complete competing application.

## Acceptance and release status

The version 1.0 functional contract is now defined in
[the acceptance contract](version_1_functional_contract.md). Development build
1.0.0-dev.5 implements that scope; acceptance must refer to its exact commit.
A stable release is still subject to GUI checks, clean-environment reproduction
and external-service integration checks. Creator metadata, archive DOI and
journal files belong to publication preparation and do not change software
functionality. They remain pending separately. A real-user study and independent
external-service installation have not been performed and are not claimed.
The frozen prior-version semantic evaluation retains its original limitations;
the new spatial operation does not improve those measured predictions.
See [English release standard](english_release_standard.md),
[repository reference](softwarex_repository_reference.md), and
[submission sequence](submission_requirements.md).
