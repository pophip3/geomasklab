# Independent application validation protocol — planned, not executed

This file preserves the original v1 proposal. The executable sampling and scoring
protocol has been revised before test inference: see
[protocol v2.1](application_protocol_v2.md), which uses unused LoveDA building
images and held-out iSAID source IDs after auditing other local experiments.

Protocol `geoscope-application-v1`. Freeze the repository commit, data manifest,
checkpoint SHA-256, model revision, endpoint software, prompt and thresholds
**before** inspecting test predictions. Protocol version changes must be dated.

## Questions and primary outcomes

1. Does the workbench preserve the same service prediction when applying a
   declared scope? Compare pixel-by-pixel with a separately implemented script.
2. Does each exported result allow offline reconstruction of its declared pixel
   operations and statistics? Report verified/total exports, including failures.
3. How often do supported queries produce an executable, category-aligned plan?
   Report accepted correct plans / all supported requests, plus explicit rejection
   and clarification correctness on a separate unsupported-request set.
4. What segmentation quality does the frozen external model provide on the new
   image set? Report per-class image-mean IoU and Dice, pooled TP/FP/FN, empty-target
   false positive pixels and false-positive-image rate. Do not label workbench
   contract tests as model accuracy.

## Images and leakage controls

Use at least 30 new building images and 30 new aircraft images from accessible
licensed sources: 20 positive and 10 absent-target images for each class. Do not
reuse the historical 20 diagnostic images or the ten aircraft tuning images.
Keep source scenes/cities separated where source metadata allows; do not treat
multiple crops from a scene as independent observations. Select IDs by a recorded
seeded sampling procedure, publish the candidate list and inclusion criteria.
An image being new to this workbench's tuning is not proof that an external
foundation model never saw its source dataset. Explicitly record that limitation.

Use pixel masks, not detection boxes, for segmentation IoU. For iSAID, decode the
documented class color and exclude void labels consistently. For WHU, record the
exact subset and mask convention. Use local downloads or download scripts with
verified hashes when licenses prohibit redistribution; never ship raw restricted
datasets as a convenient manuscript attachment.

## Fixed paired runs

Freeze one prompt per class (`all buildings`, `all planes`) and one service quality
mode. `fast` is a reasonable primary candidate; high-quality tiled settings can be
a separately prespecified secondary condition. Do not select the best test score.

For each of the 60 images run the direct service baseline and the workbench on the
same endpoint, revision and parameters. Store full masks and compare their hashes
or pixels. For nondeterministic services run at least three repeats, preserve all
outputs, and compare distributions rather than pretending identical predictions.
The workbench should not be expected to improve an unchanged model's whole-image
IoU. Its evaluated benefit is validated execution and reconstructable processing.

Evaluate all-image, right-half and one fixed normalized ROI on each image.
Apply exactly the same pixel scope to prediction and ground truth before computing
ROI-specific IoU. Coverage shown in the interface always uses full-image area as
the denominator; it must not be confused with ROI-normalized coverage.

Use two supported queries per image and a fixed 30-request unsupported/ambiguous
set. Record human-labelled expected action, category and scope before running.
Grade internal scene descriptions separately; do not infer accuracy from a fluent
answer. Batches must report every member, including skipped or failed members.

## Denominators, failures and timing

Report transport success, mask-contract acceptance, completed processing and
semantic scores separately. Timeouts and malformed predictions remain in the
system failure denominator. For successful predictions report conditional IoU;
also provide an explicitly labelled all-request utility score with failures set
to zero. Do not silently exclude empty masks or zero-target images.

For negative images, report FP pixels and whether any foreground was predicted.
Empty-ground-truth/empty-prediction images are excluded from positive-image mean
IoU and reported separately; this avoids an arbitrary 0/0 convention dominating
the score. Define all conventions in the released evaluation script.

Log wall time for the complete request, planner time, service inference time,
postprocessing and export verification. Report medians, interquartile ranges,
hardware, concurrency and cold/warm runs separately. Randomize paired run order.
Bootstrap confidence intervals at independent source-scene level where feasible;
otherwise state the limited unit of analysis. Use no significance claim from ten
tuning images.

## Impact evidence

One reproducible realistic case can establish a concrete scientific use: compare
coverage for two ROIs, branch from the earlier result, inspect the full prediction,
and independently reconstruct both exports. A blinded small usability comparison
can subsequently compare time/error rates for equivalent tasks, with participants,
consent and any applicable institutional requirements documented. This protocol
does not assert that a user study has already occurred.

## Required artifacts and current status

Publish a pre-run manifest, protocol, exact environment, all request outcomes,
evaluation scripts, summaries and licensed predictions or a permitted retrieval
path. Supply timestamps and immutable version links. Historical aggregate CSVs
and the simulated integrity matrix are available in this preparation; the 60-image
independent real-model evaluation remains **not executed**.
