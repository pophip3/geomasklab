# External masks and reference evaluation

## Bring an existing prediction

Upload the RGB image first, then select **Import prediction PNG**. The mask must
use the displayed image's exact dimensions and orientation. Specify its target,
tool/model or annotation origin and settings, then confirm pixel alignment.

Accepted masks are single-frame PNGs with values 0/1 or 0/255. Identical-channel
RGB and fully opaque grayscale/RGB alpha images are accepted losslessly.
Palette, colored, multiclass, probabilistic, transparent and differently sized
masks are rejected. Convert those explicitly in the source tool; GeoMaskLab
does not guess a class mapping, apply a threshold, resize or rotate labels.

The uploaded mask is retained as `source_mask.png`. The full binary prediction
is normalized to 0/255 without changing positive pixels. A new result version
records `mode=external`, `execution_kind=external_mask_import` and
`inference_performed=false`. Source provenance is user-supplied and is not
authenticated. Review starts pending; prior results remain available.

Imported predictions support ordinary measurements, review, evidence handoff,
version comparison and offline region recalculation. There is no assumption
that the source tool was GeoMaskLab or that the mask is accurate.

## Evaluate a reference

Select a saved mask and click **Evaluate reference**. Upload an aligned binary
reference where foreground denotes the positive semantic target. State the
label source/version and annotation procedure. Confirm alignment and explicitly
state whether the reference was prepared independently of this prediction.
The reference target must match the saved result target.

Evaluation uses only the saved spatial domain, not an unsaved rectangle drawn
on the canvas. To assess another region, first create a saved region-analysis
version. For complement results, the positive-target reference is complemented
inside that same domain. No geospatial registration is performed.

For pixel counts TP, FP, FN and TN within that domain:

| Metric | Formula | Undefined condition |
| --- | --- | --- |
| IoU | TP / (TP + FP + FN) | Empty union |
| Dice | 2 TP / (2 TP + FP + FN) | Empty foreground in both masks |
| Precision | TP / (TP + FP) | No predicted foreground |
| Recall | TP / (TP + FN) | No reference foreground |
| Specificity | TN / (TN + FP) | No reference background |
| Pixel accuracy | (TP + TN) / evaluated pixels | Empty selected domain |

JSON stores undefined values as `null`; the UI displays **Undefined** and CSV
leaves those fields blank. Metrics are fractions from 0 to 1. All-negative
masks can have pixel accuracy 1 while IoU/Dice are undefined. Pixel accuracy
alone can be misleading when background dominates.

The error image overlays mint true positives, amber false positives and magenta
false negatives. Pixels outside the selected domain remain the original image.
Evaluation does not change the prediction, version history or review decision.

## Reproduce and share

The assessment packet contains:

- `prediction.zip`: exact verified evidence used for evaluation;
- `reference.png`: exact user-uploaded reference bytes;
- `evaluation.json`: scores, counts, scope, timestamps, hashes and provenance;
- `metrics.csv`: numeric measurements, with undefined ratios blank;
- `difference.png`: pixel error map;
- `report.md`: interpretation and recomputation instructions;
- `manifest.json`: file membership, byte sizes and SHA-256 hashes.

Extract this packet into its own directory and recompute:

You can first verify its hashes, recorded scores, numeric CSV and error-map
pixels directly, without extracting:

```sh
geomasklab verify-assessment path/to/evaluation.zip
```

This also rejects a forged metric record even if its file hashes were updated.
The result remains a consistency check, not an authentication of reference origin.
For a separate recomputed packet:

```sh
geomasklab evaluate prediction.zip reference.png --aligned --source "Dataset/version and label procedure" --target building --independent --output recomputed.zip
```

Use `--independent` only when the stated label preparation supports that claim.
The command assumes that the user has checked alignment. A new run timestamp
will differ; pixel counts, metrics and input identities should match.

The complete offline example is:

```sh
python examples/reference_workflow.py
```

It generates a diagram, an imperfect prediction and exact procedural rectangle
labels. The expected confusion is TP=15,000, FP=2,500, FN=6,100 and TN=130,000
over 153,600 pixels. IoU is 15,000/23,600 (about 63.56%). These are hand-counted
software checks, not real satellite observations or neural accuracy results.

## HTTP interface

- `POST /api/import-mask`: `session_id`, `mask` (base64 PNG), `target`, `source`,
  `aligned=true` and optional `parent_run_id`.
- `POST /api/evaluate-reference`: `session_id`, `run_id`, `reference` (base64
  PNG), `target`, `source`, `aligned=true`, and Boolean `independent`.

Both operations run locally without model-service calls. The evaluation
response includes the metric record, a base64 error PNG and a local ZIP download
URL. Completed assessment packets are saved under the experiment's `assessments`
directory separately from prediction history; downloads remain available after
the dialog closes. These packets contain the supplied reference labels.
PNG upload limits are 12 MB and 16 million pixels. An evidence packet can contain
the source image/reference, so share it only where those inputs may be shared.

## Interpretation limits

Scores describe agreement against the supplied reference. The software does
not establish that the reference is correct, independent, licensed, aligned or
representative. Self-reported provenance and integrity hashes do not authenticate
its author. A held-out real-image dataset and suitable aggregation are required
for a general semantic-performance statement; one image is an illustrative
case. Binary foreground metrics are not instance-detection precision or recall.
