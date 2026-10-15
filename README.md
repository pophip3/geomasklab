# GeoMaskLab

Remote sensing interpretation and quantitative mask analysis.

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776ab)](https://www.python.org/)
[![MIT license](https://img.shields.io/badge/license-MIT-24836b)](LICENSE)
[![Release 1.0.0](https://img.shields.io/badge/release-1.0.0-2563eb)](https://github.com/pophip3/geomasklab/releases/tag/v1.0.0-build.20261015)
[![Research software checks](https://github.com/pophip3/geomasklab/actions/workflows/research-checks.yml/badge.svg)](https://github.com/pophip3/geomasklab/actions/workflows/research-checks.yml)

GeoMaskLab is an open-source workbench for remote sensing image interpretation
and quantitative mask analysis. Use model-generated or imported masks to measure
selected regions, assess predictions and compare saved results. Portable exports
keep the inputs and settings together so that measurements can be verified and
reused.

[Install](#install) · [Offline example](#run-the-offline-example) ·
[Browser workbench](#open-the-browser-workbench) ·
[Documentation](https://pophip3.github.io/geomasklab/)

## Features

| Feature | What you can do |
| :--- | :--- |
| 📐 Regional measurement | Measure coverage for a whole image or selected region, with explicit valid-pixel domains. |
| 🎯 Reference assessment | Inspect IoU, Dice and other metrics alongside spatial error overlays. |
| 🔄 Version comparison | Compare shared, added and removed foreground within a common valid domain. |
| 🔎 Component inspection | Review component sizes, locations and contact with analysis boundaries. |
| 📂 Batch processing | Run a shared workflow across multiple inputs and collect their results. |
| 📦 Export and verification | Share evidence packets and recompute recorded measurements offline. |

## Install

Requirements: Python 3.10 or later. The installation command installs Pillow
automatically. The example below uses the image and mask included in the source
package and runs without a GPU, RemoteAgent or RemoteSAM.

Download and extract the [fixed source package](https://github.com/pophip3/geomasklab/releases/download/v1.0.0-build.20261015/GeoMaskLab-1.0.0-build-20261015-source.zip), then open a
terminal in the extracted project directory containing this README and
`pyproject.toml`.

This package is GeoMaskLab 1.0.0, submission build 15 October 2026.

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\geomasklab.exe --version
```

### Linux and macOS

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/geomasklab --version
```

The version command prints `1.0.0`.

## Run the offline example

Keep the terminal in the project directory. The example measures a saved mask,
selects a region, compares mask versions, inspects connected components and
processes a batch. It writes its results to `five-step-output/`.

### Windows PowerShell

```powershell
.\.venv\Scripts\python.exe examples/five_step_workflow.py
.\.venv\Scripts\geomasklab.exe verify five-step-output/baseline.zip
.\.venv\Scripts\geomasklab.exe verify-comparison five-step-output/comparison.zip
.\.venv\Scripts\geomasklab.exe verify-components five-step-output/components.zip
.\.venv\Scripts\geomasklab.exe verify-assessment five-step-output/assessment.zip
.\.venv\Scripts\geomasklab.exe verify-batch five-step-output/batch.zip
```

### Linux and macOS

```sh
.venv/bin/python examples/five_step_workflow.py
.venv/bin/geomasklab verify five-step-output/baseline.zip
.venv/bin/geomasklab verify-comparison five-step-output/comparison.zip
.venv/bin/geomasklab verify-components five-step-output/components.zip
.venv/bin/geomasklab verify-assessment five-step-output/assessment.zip
.venv/bin/geomasklab verify-batch five-step-output/batch.zip
```

Open `five-step-output/index.html` in a browser to view the image, measurements
and comparison results. The verification commands print `"verified": true`.
To repeat the example, use a new output directory:

```powershell
.\.venv\Scripts\python.exe examples/five_step_workflow.py --output five-step-output-2
```

On Linux/macOS, use `.venv/bin/python` in place of the Windows Python path.

## Open the browser workbench

Windows PowerShell:

```powershell
.\.venv\Scripts\geomasklab-ui.exe --port 4180
```

Linux/macOS:

```sh
.venv/bin/geomasklab-ui --port 4180
```

Open `http://127.0.0.1:4180` and select **Enter workbench**. Use **Import mask**
with your own aligned image and binary mask, or open the bundled demo. Keep the
terminal running while using the workbench; press `Ctrl+C` to stop it.

## Example data

The source package includes a 512 × 512 aerial image of Denver City Park and a
binary colour-baseline mask in `examples/data/naip-denver/`. No separate data
download is needed for the offline example.

- Image: 2019 USDA NAIP, distributed by USGS The National Map; public domain.
- Credit: USDA-FSA-APFO / USGS The National Map.
- Mask: supplied colour-baseline mask for the measurement example.
- [Data source, processing details and attribution](examples/data/naip-denver/README.md).
- [USGS NAIP collection](https://www.usgs.gov/centers/eros/science/usgs-eros-archive-aerial-photography-national-agriculture-imagery-program-naip).

## Source and documentation

- `src/geomasklab/`: shared measurement core and command-line interface.
- `workbench/`: browser interface and local server.
- `model_services/`: optional local model adapters.
- `examples/`: runnable examples and bundled data.
- `tests/`: software tests.
- [API and evidence format](docs/core_package.md).
- [Browser workbench guide](docs/presentation_workbench.md).
- [Optional local-model setup](docs/local_model_modules.md).

## License and contact

GeoMaskLab is distributed under the [MIT License](LICENSE).
Bundled imagery and third-party components retain the terms recorded in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Contact: [2416010301@hhu.edu.cn](mailto:2416010301@hhu.edu.cn).
