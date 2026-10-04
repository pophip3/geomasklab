# Frozen application evaluation artifacts

This directory publishes metadata and derived numerical results only. Original
academic-use images and human annotations stay in local storage. The manifest
contains dataset IDs, dimensions, class strata, filenames and SHA-256 identities;
it is not an image dataset distribution. See `docs/application_protocol_v2.md`.

`manifest.csv` is retained byte-for-byte, including its CSV line endings, to match
the SHA-256 recorded in `data-lock.json`. `.gitattributes` disables automatic
newline conversion only for this frozen file. `run-protocol.json` records the
source hashes, model settings and software commit executed in this run. Later
documentation commits do not change the measured software version.

Published source data:

- [LoveDA validation](https://zenodo.org/records/5706578): building=2, no-data=0 ignored.
- [iSAID validation annotations](https://captain-whu.github.io/iSAID/dataset.html),
  paired with [DOTA-v1.0 validation images](https://captain-whu.github.io/DOTA/dataset.html):
  plane RGB (0,127,255), binary one-vs-rest evaluation.

The data selection was frozen locally before predictions; the executable protocol
and seed were committed to the research repository before predictions. This is
independent of the observed workbench/other-local-experiment tuning selections,
not a guarantee of unseen external-model pretraining or nonoverlapping geography.
No new human review or user study is claimed.

Completed numerical artifacts:

- `summary.json`: every class/path, denominator, empty-target false positives,
  pooled confusion counts, nominal bootstrap intervals and pipeline checks.
- `per_request_metrics.csv`: all 240 planned primary/workbench outcomes;
  matched direct scores are separately audited in the original local receipts.
- `independent-score-audit.json`: independent Pillow audit of 420 score tables,
  240 input hashes, 60 label conversions and exact RGB-pixel uniqueness.
- `fixed_model_accuracy.png` and `.svg`: numerical figure with exploratory
  image-bootstrap intervals; these files contain no source dataset imagery.

Whole-workbench positive-image mean IoU/Dice: buildings 22.75%/29.12%, aircraft
35.23%/47.61%. Corresponding empty-target false-positive image counts are 1/10
and 4/10. All 180 workbench requests, exports, matched masks and independent
scope reconstructions passed. Preserving outputs is not proof of high accuracy.
Full [interpretation and limitations](../../docs/application_results_zh.md).
