# Independent application evaluation: protocol v2.1

Locked before any test prediction on 2026-10-04. This executable version replaces
the earlier **planned** WHU/iSAID sampling proposal. Many WHU and OEM samples have
since appeared in other local experiments, so buildings are evaluated on unused
LoveDA validation tiles instead. Data acquisition plans and their hashes are
retained locally; a draft that incorrectly treated all archive inventory IDs as
used model inputs was corrected before prediction and retained as superseded.

## Data and annotations

60 native-resolution images: 30 buildings and 30 aircraft; each class has 20
positive and 10 empty-target images. Buildings use [LoveDA](https://zenodo.org/records/5706578)
validation images and released human labels (building=2; no-data=0 ignored).
Positive tiles are balanced 10 Urban/10 Rural. At most one LoveDA tile per domain
and 32-consecutive-ID block is selected, as a spacing proxy. Geographic scene
metadata are unavailable in filenames; this does **not** establish independent
acquisitions or city separation.

Aircraft use official [iSAID](https://captain-whu.github.io/iSAID/dataset.html)
validation pixel annotations and matching [DOTA-v1.0](https://captain-whu.github.io/DOTA/dataset.html)
RGB imagery. Plane pixels are exactly RGB (0,127,255). This is a **binary
one-vs-rest application evaluation** over all pixels of the released class mask,
including black unlabeled background as non-plane; it is not the official
instance-AP or multiclass ignore-background evaluation. Missing annotations would
affect apparent false positives. DOTA detection boxes are never used as pixel GT.

Selection uses SHA-256 ordering with the recorded salt, annotation presence only,
and interface constraints of <=16,000,000 pixels and <=12 MiB source image file.
No target-size minimum beyond one pixel, model-score filtering, resizing, cropping,
or replacement after inference. Frozen local manifests and scored execution CSVs
exclude 43 prior iSAID source IDs plus all known prior file hashes. Source archive
inventories are distinguished from model-execution records. Each selected source
ID appears once. There is no proof that the external pretrained models never saw
these public datasets, or that unidentified source scenes never overlap.

Raw images, source labels, derived binary GT and valid masks stay outside Git.
The [LoveDA license](https://github.com/Junjue-Wang/LoveDA#license) and iSAID/DOTA
terms allow academic use and restrict commercial use. Download recipes, metadata,
CRC checks and file SHA-256 values are supplied without redistributing raw imagery.
The agent does not claim to have performed human annotation. A separate audit sheet
can record later human review; no reviewer approval is fabricated.

## Frozen models and requests

Fixed primary direct prompts: `all buildings`, `all planes`; `referring_seg`,
`quality_mode=fast`, service-produced binary mask, no threshold search. RemoteSAM
checkpoint SHA-256 is frozen along with endpoint version, FP16/EPOC settings,
workbench source hashes, evaluator source hashes and the Git commit. RemoteAgent
weights are identified by the verified shard hashes; temperature=0 is used by the
existing adapter. No model retraining or parameter adjustment occurs in this run.

Each image also receives three new live workbench queries: whole image, right
half and central ROI `[floor(W/4),floor(H/4),floor(3W/4),floor(3H/4)]`. All requests
force new perception, avoiding cached predictions. The request text and expected
category/scope are assigned before prediction by the protocol, rather than by a
blinded human rater. ROI and half-image tasks are mutually exclusive.

The workbench planner can select `semantic_seg` rather than `referring_seg`.
Consequently the fixed-prompt direct result and the workbench result are separately
reported application paths, **not** a claim of workbench model improvement.
Preservation is tested by an additional direct call reproducing the actual
planner-selected task, text/classes and quality mode. This matched call is compared
pixel-by-pixel with the full pre-scope workbench mask. A separate NumPy computation
checks the saved scoped output, and the evidence ZIP is verified offline. Any
matched mismatch triggers two additional direct repeats; the first result is kept.

Fixed-direct / whole-workbench order is randomized deterministically per image.
Matched calls necessarily follow planning. Requests are sequential and use warm
services. Wall times, service-reported inference times and export verification time
are retained; concurrency, GPU setup and these timing boundaries must be reported.
Raw timing is observational and may include unrelated shared-host load.

## Scores and denominators

IoU = TP/(TP+FP+FN); Dice = 2TP/(2TP+FP+FN). Only valid pixels within the declared
scope count. Report per-class positive-image mean scores and pooled TP/FP/FN.
Whole-image positive denominators are fixed at 20 per class. Conditional success
scores and all-positive-request utility with failed requests scored zero are both
reported. No execution failure, empty mask or negative case is silently removed.

Empty-GT/empty-prediction has undefined IoU/Dice (recorded null), rather than an
arbitrary perfect score. Empty-GT cases have separate FP pixel counts, FP fraction
and any-foreground image rate. Scoped empty-GT cases are separated even when their
full image contains a target. Failed negative requests are separately reported.

180 supported workbench requests and 60 primary fixed direct calls are planned;
matched direct calls are additional. Report correct category/scope, mask acceptance,
completed exports, independent pixel-scope reconstruction and exact matched mask
preservation with their own denominators. Any separate unsupported-query suite is
a contract/system check, not a new segmentation or human-judged agent benchmark.

Nominal image/source-ID bootstrap intervals (2,000 resamples, fixed seed) may be
shown as exploratory uncertainty. Images from one airport or adjacent source tiles
may remain correlated, so these intervals do not prove independent-scene precision
and do not support a significance claim. No new segmentation algorithm superiority
or generalization claim follows from this small stratified application set.

## Reproduction

Install `evaluation/requirements-evaluation.txt` in addition to workbench requirements.
Run `prepare_independent.py --help` for explicit source and output arguments. The
preparation script freezes the selection and rejects resampling after a manifest
exists. `run_independent.py --root LOCAL_DATA_ROOT` freezes the run protocol and
retains per-request receipts; rerunning resumes completed requests without changing
parameters. `summarize_independent.py --root LOCAL_DATA_ROOT` recomputes scores and
denominators from the saved receipts.

`annotation_packet.py --root LOCAL_DATA_ROOT` produces label-only review sheets
and a blank human-review record. `verify_independent_scores.py --root
LOCAL_DATA_ROOT` separately rederives all binary ground truths from the released
source labels, checks exact RGB pixel duplicates, and audits confusion tables and
IoU/Dice with Pillow boolean arithmetic, independently of the NumPy scorer. This
checks conversion and arithmetic, not the annotators' semantic accuracy.

Install `evaluation/requirements-report.txt` for the optional publication figure
and HTML report; run `report_independent.py --root LOCAL_DATA_ROOT` after summary
generation. No restricted source imagery is needed in the numerical Git artifacts.
