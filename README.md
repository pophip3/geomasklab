# GeoMaskLab

> A traceable workbench for remote-sensing segmentation and region-specific pixel measurements.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Software checks](https://github.com/pophip3/geoscope-softwarex/actions/workflows/research-checks.yml/badge.svg)](https://github.com/pophip3/geoscope-softwarex/actions/workflows/research-checks.yml)

## Official website

For the user guide, coverage definitions, examples and model-service setup, visit
the [GeoMaskLab documentation website](https://pophip3.github.io/remote-sensing-workbench-docs/).

## Purpose and status

GeoMaskLab helps researchers inspecting RGB remote-sensing image chips retain the
connection between an image, semantic target, prediction, spatial scope,
measurement and review decision. External models supply masks; a deterministic
executor validates requests, measures pixels, preserves result versions and
exports evidence that another researcher can check without model services.

**Version 1.0.0-rc.1** freezes the version 1.0 feature scope for release acceptance.
It is a release candidate, not a submitted or accepted SoftwareX publication.
Final creator metadata, archive DOI and current journal-guide verification remain
pending. The original competition repository is preserved.

Buildings and aircraft are the primary use cases. Road, water, vegetation and
ship support is experimental. Candidate components are not verified object
counts. Measurements use pixels, not geographic area. The contribution is a
traceable workflow; GeoMaskLab does not introduce the external segmentation models.

## Install and run

Use Python 3.10 or newer on Windows, Linux or macOS. Clone this repository or
extract its source archive, then work from the software root. A virtual
environment is recommended:

```sh
git clone https://github.com/pophip3/geoscope-softwarex.git
cd geoscope-softwarex
python -m venv .venv
```

Activate it on Windows PowerShell with `.\.venv\Scripts\Activate.ps1`, or on
Linux/macOS with `source .venv/bin/activate`. If your system names the interpreter
`python3`, use that command. Activation is optional: you can invoke the environment's
Python executable directly.

```sh
python -m pip install -r requirements.txt
python reviewer_demo.py
python quickstart.py
```

Open `http://127.0.0.1:4180`. If the port is occupied, run
`python quickstart.py --port 4182` and open the printed address. Stop the server
with Ctrl+C. The interface, accessible labels, generated reports, errors and new
examples are English. Original user-entered/historical source text is preserved.

Only Pillow is required for the offline workflow. No GPU, account, model weights,
NumPy, requests or inference endpoint is needed. A reproducible reviewer dependency
pin is provided in `requirements-reviewer.txt`. Procedural assets are generated
by `fixtures.py`; they are diagrams with exact fixture masks, **not satellite
observations, real-image ground truth or neural predictions**.

## Reviewer example and expected output

`reviewer_demo.py` executes five offline examples, checks exact pixel counts,
tests branch/review persistence, and verifies five portable ZIPs. It exits
nonzero on failure and writes `reviewer-output/summary.json` and the bundles.

| Example | Foreground pixels | Whole-image pixels |
| --- | ---: | ---: |
| Whole buildings | 75,350 | 480,000 |
| Right-half buildings | 37,350 | 480,000 |
| Left-half branch | 38,000 | 480,000 |
| Rectangle `[80,50,280,250]` | 12,850 | 480,000 |
| Whole aircraft | 22,532 | 640,000 |

The right-half review is accepted by a clearly labeled **automated procedural
software check**, not by a human EO reviewer. New results start pending.
See [the complete reviewer walkthrough](docs/reviewer_quickstart.md).

```sh
python export_bundle.py reviewer-output/right.zip
python examples/recalculate_region.py reviewer-output/right.zip
```

`verified: true` establishes internal file/pixel consistency, not semantic
accuracy or author identity. The region example verifies whole/left/right/ROI
analyses using direct Pillow crops without model calls, retaining source image
and full-mask bytes.

## Main workflow

1. Choose a procedural image or upload an RGB image for configured live services.
2. Request one category and a whole image, one pixel half or a rectangle ROI.
3. Inspect original, overlay and mask views; examine pixel measurements/components.
4. Record a self-reported semantic review with a label and rationale.
5. Export an evidence ZIP; import it into a new session for independent inspection.
6. Use **Recalculate region (offline)** to derive another spatial analysis from
   a verified full mask, with separate pending review and no new inference.

Changing scope preserves the semantic target/complement and cannot correct an
inaccurate prediction. Whole-image coverage is `A / (W × H)`; within-region
coverage is `A / R`, where `R` is the selected region's pixel count. For the
procedural ROI, these are **2.6771%** and **32.125%**, respectively. They answer
different questions and are not accuracy scores.

Results retain parent IDs, execution origin, source identities, deterministic
statistics and review history. Imported single-result bundles cannot restore
ancestors absent from the export. The verifier replays mask complement, scope,
coverage, distribution and candidate measurements before reuse. SHA-256 checks
do not authenticate an author; a manifest can be regenerated.

## Live model services

Copy `.env.example` to `.env`, configure actual compatible endpoints, the model
identifier and verified revision, then restart. The planner uses OpenAI-compatible
multimodal chat with one bounded `T_call` or `<answer>` block. The mask service
uses the documented JSON contract and original-size binary masks. Scene responses
and masks are separate execution routes. Tiled refinement is a service option,
not a guarantee of greater accuracy.

[Model-service setup and acceptance](docs/model_services.md) documents the
settings, request/response expectations and limitations. Model implementations,
weights and licenses are external. The recorded local deployment and prior
application study do not establish installation on unrelated reviewer hardware.
Uploaded images are sent to configured services in live mode; credentials stay
on the Python server. The server is for trusted local use without multi-user
authentication.

## Tests and existing-tool evidence

The current suite contains 96 behavioral tests. Six OS/Python CI combinations
cover Windows/Linux/macOS with Python 3.10/3.13; use the Actions badge to inspect
the exact commit's result. Full tests add optional evaluation dependencies:

```sh
python -m pip install -r evaluation/requirements-evaluation.txt
python -m unittest discover -s tests -p "test_*.py" -q
python evaluation/run_integrity_matrix.py
python evaluation/recompute_historical.py
python examples/reproduce_example.py
```

The 60-case geometry matrix uses simulated planner/mask transport. It tests
software behavior, not model accuracy. Frozen historical diagnostics remain
attributed to their original code/data identities.

Optional interoperability runs the **actual official Label Studio SDK 2.1.2 brush
converter** on five examples and four controlled inconsistent-metadata cases:

```sh
python -m pip install --no-deps label-studio-sdk==2.1.2
python examples/compare_handoff.py
python label_studio_export.py reviewer-output/right.zip --output workflow-output/label-studio
```

The bridge exports predictions, not accepted annotations, ground truth or
invented confidence. The full Label Studio GUI, QGIS and SAMGeo were not
benchmarked. Different workflow operations are not a speed ranking. See the
[workflow study and claim boundaries](docs/workflow_study.md).

## Prior-version real-image application study

A frozen study at commit `46ffbbb1898a4b5e8f2ac5974f0bdabace3a94bd` used 30
LoveDA building and 30 iSAID/DOTA aircraft images, each class containing 20
positive and 10 empty-target cases. Dataset-provided human pixel labels supplied
ground truth. Whole-workbench positive-image mean IoU/Dice was
**22.75%/29.12% for buildings** and **35.23%/47.61% for aircraft**. Empty-target
false positives occurred in 1/10 and 4/10 images. Nine positive building images
and one positive aircraft image yielded empty masks. These limitations require
human inspection and preclude a high-accuracy claim.

All 180 workbench requests/exports completed and matched service masks and
independent scope reconstruction agreed exactly. Integrity success is separate
from recognition accuracy. Unknown pretraining exposure/geographic overlap and
the binary aircraft scoring convention limit generalization claims. See
[results and limitations](docs/application_results.md),
[the frozen protocol](docs/application_protocol_v2.md) and
[metadata/numerical artifacts](evaluation/independent/README.md).
Raw restricted images/labels are not redistributed.

## Documentation and maintenance

- [Feature scope and application context](docs/software_scope.md)
- [Architecture and module responsibilities](docs/architecture.md)
- [Workbench API, inputs/outputs and numerical definitions](docs/api.md)
- [Published SoftwareX repository inspection](docs/softwarex_repository_reference.md)
- [Ordered submission requirements](docs/submission_requirements.md)
- [Fixed-release and DOI archive plan](docs/archive_plan.md)
- [Change log](CHANGELOG.md), [contributing](CONTRIBUTING.md), [local security](SECURITY.md)

## License, provenance and citation

The modified workbench is licensed under the [MIT License](LICENSE); `Licence.txt`
contains the same standard text for the journal template convention. Selected
competition-source provenance, dependencies and data/model boundaries are
documented in [third-party notices](THIRD_PARTY_NOTICES.md) and `docs/origin.json`.
The original competition repository remains unchanged. Existing schema and
repository identifiers are retained for compatibility under the GeoMaskLab name.

For now, reference the exact code commit and version. Creator/contact metadata
and a final software archive DOI are pending in `release/metadata-draft.json`;
no DOI badge, confirmed citation author list or article acceptance is implied.
Use the repository issue tracker for ordinary support and reproducible bug
reports, without posting private images or credentials.

## Source distribution

From a Git checkout, build an exact committed version and check the extracted
archive outside the checkout:

```text
python release/build_source.py --revision HEAD --output GeoMaskLab-source.zip
python release/check_distribution.py GeoMaskLab-source.zip
```

The builder includes committed regular files only and rejects local credentials,
experiments and model weights. `SOURCE-MANIFEST.json` binds every file to a SHA-256
and the full source commit. The distribution check runs five reviewer cases,
saved-mask region examples and an isolated local server. It verifies new English
evidence text; it does not install or evaluate external models.
