# GeoMaskLab

> Replayable measurements and portable evidence for segmentation masks.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Software checks](https://github.com/pophip3/geoscope-softwarex/actions/workflows/research-checks.yml/badge.svg)](https://github.com/pophip3/geoscope-softwarex/actions/workflows/research-checks.yml)

GeoMaskLab binds a binary mask to its image, target, spatial scope and coverage
denominators. Create an evidence ZIP, change its region without model inference,
and let a colleague replay the measurement offline. The headless core requires
only **Python 3.10+ and Pillow**. The optional browser workbench uses the same core.

## Official website

Visit the [GeoMaskLab documentation website](https://pophip3.github.io/remote-sensing-workbench-docs/)
for the workbench guide, examples and service setup.

## Install

```sh
git clone https://github.com/pophip3/geoscope-softwarex.git
cd geoscope-softwarex
python -m venv .venv
```

Activate with `.\.venv\Scripts\Activate.ps1` on Windows PowerShell, or
`source .venv/bin/activate` on Linux/macOS. Then:

```sh
python -m pip install .
geomasklab --version
```

You can also install the distributed wheel directly. It contains the headless
core and JSON Schemas; source-only browser assets and examples are supplied in
the source archive. This development version is **1.0.0.dev6**. PyPI publication
and a stable release tag remain pending.

## A complete example

The source includes a credited real NASA photograph and a precomputed, locally
reproducible RGB color baseline. No account, network, GPU or model weights are needed:

```sh
python examples/real_image_handoff.py
geomasklab verify workflow-output/real-image/right.zip
geomasklab report workflow-output/real-image/right.zip --output report.html
```

Open `report.html`. The right-half result contains **35,751 foreground pixels**,
covering **20.7199% of the whole image** or **41.3173% of the selected half**.
Both denominators are recorded and independently replayed. The example mask is
a green-color candidate baseline, not human reference labels or validated tree
ground truth. See [image attribution and processing](examples/data/san-francisco-bay/README.md).

## Bring your own mask

```sh
geomasklab create --image image.png --mask mask.png --target building --source "My exported binary mask" --aligned --output evidence.zip
geomasklab verify evidence.zip
geomasklab recalc evidence.zip --roi 10 10 80 80 --output roi.zip
geomasklab report roi.zip --output roi.html
```

Inputs are a single image and an exactly aligned binary PNG, with explicit
target/source assertions. The PNG may encode positives as 1 or 255. Probabilities,
multiclass masks, transparent pixels and dimension mismatches are rejected.
Coordinates refer to the EXIF-normalized displayed RGB image. Outputs retain
source bytes, full/scoped masks, metrics, review state, provenance and a manifest.

[Core API, providers and JSON Schemas](docs/core_package.md) describe the Python
interface, format compatibility, local RGB baseline and external-command adapter.
[Reference assessment](docs/reference_evaluation.md) adds supplied reference masks,
scoped confusion counts and a separately replayable assessment packet.

## Optional browser workbench

```sh
python quickstart.py
```

Open `http://127.0.0.1:4180`, or select another port with `--port 4182`.
Import images, external masks and verified evidence; inspect overlays; recalculate
regions; review results; and download evidence. Procedural demonstration fixtures
are labeled explicitly. Configured external model services are optional:
[setup and contract](docs/model_services.md). Stop the server with Ctrl+C.

## Validation and maintenance

```sh
python -m pip install ".[schema]" -r evaluation/requirements-evaluation.txt
python -m unittest discover -s tests -p "test_*.py" -q
python reviewer_demo.py
python examples/reference_workflow.py
python examples/real_image_handoff.py
```

The CI matrix covers Windows, Linux and macOS with Python 3.10 and 3.13; inspect
the linked workflow for the result at your exact commit. Distribution checks
also run the installed wheel outside the checkout and verify a committed source
archive. Tests check arithmetic, provenance, state, malformed inputs and evidence
replay; they do not replace independent semantic evaluation.

- [Architecture](docs/architecture.md) and [software scope](docs/software_scope.md)
- [Existing-tool workflow study](docs/workflow_study.md)
- [Historical real-image results and limitations](docs/application_results.md)
- [Changes](CHANGELOG.md), [contributing](CONTRIBUTING.md) and [local security](SECURITY.md)

## Limitations

Measurements are in pixels. CRS transformations, georeferenced area and temporal
change are not implemented in this build. Source/alignment assertions and semantic
review are self-reported. SHA-256 and replay establish internal consistency, not
authenticity or target accuracy; a self-consistent replacement bundle can pass.
Candidate components are not validated object counts. The 60-image model study
belongs to its explicitly recorded earlier commit; its metrics are historical.
External model inference and a real-user handoff study have not been validated
for this build. The browser server is intended for trusted local use.

## License and citation

Project code is [MIT licensed](LICENSE). [Third-party notices](THIRD_PARTY_NOTICES.md)
record source attribution and separate image, dataset and dependency terms.
For reproducible citation, record the software version and exact commit. Confirmed
creator metadata and an archival DOI will accompany the stable release.
Use the [issue tracker](https://github.com/pophip3/geoscope-softwarex/issues) for support.
