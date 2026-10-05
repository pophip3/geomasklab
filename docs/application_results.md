# Frozen prior-version application study

Completed on 4 October 2026 using software commit
`46ffbbb1898a4b5e8f2ac5974f0bdabace3a94bd`. This is a limited application
evaluation of the earlier workbench/model configuration, not new-version
semantic-performance evidence. The version 1.0 candidate adds language, evidence
and offline-analysis work; it does not claim to improve these predictions.

## Data and score definitions

The prospectively frozen set contains 60 native-resolution images: 30 buildings
from LoveDA validation and 30 aircraft from iSAID validation human pixel labels
paired with DOTA-v1.0 imagery. Each class includes 20 positive and 10 empty-target
images. Dataset-provided human annotations are used; no new human reviewer or
user study is claimed. Data, models, prompts, fast mode and scoring were fixed
before prediction without outcome-based replacement, threshold tuning or label
editing. See [the executable protocol](application_protocol_v2.md).

The table reports the mean of per-image IoU/Dice over 20 positive images per
class. Empty-target false positives are reported separately. These percentages
are overlap scores, not object-detection correctness rates.

| Category and path | Positive-image mean IoU | Positive-image mean Dice | Empty-target images with false positives |
| --- | ---: | ---: | ---: |
| Buildings: fixed direct referring request | 33.40% | 45.44% | 8/10 |
| Buildings: whole-image workbench path | 22.75% | 29.12% | 1/10 |
| Aircraft: fixed direct referring request | 35.23% | 47.61% | 4/10 |
| Aircraft: whole-image workbench path | 35.23% | 47.61% | 4/10 |

Fixed direct prompts are `all buildings` and `all planes`. The workbench planner
can select semantic or referring segmentation; most building requests used the
semantic route. This is not a same-parameter algorithm comparison. Differences
must not be attributed to an improvement or degradation of the underlying
model's intrinsic capability. Nine of 20 positive building images and one of 20
positive aircraft images produced empty masks in the whole-image workbench path;
these missed targets remain scored as zero. Lower false-positive counts must not
be promoted independently of these omissions.

The frozen service's fast path internally resizes to 896 × 896, normalizes
channels, applies argmax and restores masks with nearest-neighbor interpolation.
Native-dimension scoring does not mean native-resolution neural inference.
Pooled scores across all successful images, including empty-target cases, use
different denominators: building direct IoU/Dice 17.74%/30.14%, building workbench
32.68%/49.26%, and aircraft 19.45%/32.57% for both paths. Do not mix pooled values
with positive-image means. Half-image/ROI strata can also have different positive
image denominators; inspect the complete numerical record.

## Evidence preservation results

- 180/180 supported workbench requests completed with the specified target/scope.
- 180/180 exported bundles passed offline verification and independent scope replay.
- 180/180 matched-parameter direct service masks agreed pixel-for-pixel with the
  workbench's full masks.
- 240/240 frozen inputs passed file-hash checks, 60/60 annotation conversions were
  independently checked, and the 60 RGB-pixel hashes were distinct.
- 420/420 confusion-count and IoU/Dice tables passed independent Pillow Boolean
  reconstruction, covering 60 fixed-direct, 180 workbench and 180 matched-direct cases.

Execution success, numerical preservation and semantic recognition are separate
outcomes. The findings support traceable preservation for the recorded models and
scopes; they do not support high-accuracy general segmentation, novel model
superiority, measured labor savings or official full-dataset leaderboard scores.

## Limits and reproducibility

Known local experiments contributed 43 excluded iSAID source IDs and known input
hashes. The LoveDA one-image-per-domain/32-consecutive-ID-block rule is a spacing
proxy, not evidence of distinct cities or acquisitions. Unknown pretraining
exposure and geographic overlap remain possible. Aircraft scoring is binary
one-vs-rest, treating black unlabeled background as non-aircraft; it differs from
official multiclass ignore-background evaluation and instance AP. Missing source
annotations may affect apparent false-positive counts. Image bootstrap intervals
are exploratory descriptions, not proof of unseen-scene generalization.

[Frozen metadata and numerical artifacts](../evaluation/independent/README.md)
contain the manifest, model/data locks, request metrics, summary, independent
score audit and English numerical figures. Raw images, labels, response receipts,
masks and evidence ZIPs remain in local validation storage; their redistribution
is governed by dataset/model rights. Retrieve the recorded source commit and
frozen protocol for reproduction rather than replacing it with current code.
