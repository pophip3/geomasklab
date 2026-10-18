# GeoMaskLab

**Measure, compare and verify segmentation masks from remote sensing imagery.**

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776ab)](https://www.python.org/)
[![MIT license](https://img.shields.io/badge/license-MIT-24836b)](LICENSE)
[![Release 1.0.0](https://img.shields.io/badge/release-1.0.0-2563eb)](https://github.com/pophip3/geomasklab/releases/tag/v1.0.0-repro.20261016)
[![Research software checks](https://github.com/pophip3/geomasklab/actions/workflows/research-checks.yml/badge.svg)](https://github.com/pophip3/geomasklab/actions/workflows/research-checks.yml)

## Description

GeoMaskLab brings regional measurement, segmentation assessment and result
comparison into one open-source workbench. Work interactively in the browser or
run repeatable analyses from the command line. Saved masks, analysis settings and
results travel together in portable evidence packets. Applications include urban
land-cover measurement, vegetation monitoring and surface-water assessment.

[Installation](#installation) · [Demo](#quick-start--demo) ·
[Reproduce paper results](#reproduce-paper-results) ·
[Browser workbench](#open-the-browser-workbench) ·
[Documentation](https://pophip3.github.io/geomasklab/) · [Example data](#example-data)

## Features

| Feature | What you can do |
| :--- | :--- |
| 📐 **Regional measurement** | Measure mask coverage across an image or selected region using valid pixels. |
| 🎯 **Segmentation assessment** | Compare predictions with reference masks using IoU, Dice and error overlays. |
| 🔄 **Version comparison** | Inspect shared, added and removed foreground over the same valid area. |
| 🔎 **Component inspection** | Examine individual regions, their sizes and their contact with boundaries. |
| 📂 **Batch processing** | Apply a shared workflow to multiple inputs and collect the results. |
| 📦 **Export and verification** | Share saved inputs and results, then recompute measurements offline. |

**Try it first:** [install the package](#installation), then [run the bundled example](#quick-start--demo) to generate a local results page.

## Source layout

| Directory | Contents |
| --- | --- |
| `src/geomasklab/` | Shared analysis library, command-line interface, schemas and packet verification |
| `workbench/` | Browser workbench package and web assets |
| `model_services/` | Optional model adapters, service launcher and fixed environment files |
| `examples/` | Runnable demonstrations and bundled example inputs |
| `evaluation/` | Paper measurements, validation scripts and model reproduction guides |
| `tests/` | Automated software checks |

`pyproject.toml` declares the installable packages and command-line entry points.
Root-level launch scripts provide convenient source-checkout commands.

## System Requirements

- Operating system: Windows, Linux or macOS.
- Python: 3.10 or later; the submission reproduction was checked with Python 3.12.14 on Windows.
- Offline demo and measurement reproduction: CPU only; no CUDA or model downloads.
- Browser workbench: a current browser and a free local port (4180 by default).
- Fresh model inference: separate model environments and GPU setup described in [Local-model setup](docs/local_model_modules.md), including PyTorch 2.6.0 / CUDA 12.4.

## Dependencies

The offline workflow uses **Pillow 12.3.0**, fixed in [requirements.txt](requirements.txt).
[requirements-build.txt](requirements-build.txt) fixes setuptools 80.9.0 and wheel 0.45.1 for source installation.
The commands below install both files, then build the package with those tools.
Evaluation, plotting, export integrations, RemoteAgent, RemoteSAM and water V5 each
have complete dependency locks, including indirect and platform-specific packages.
Use the separate environments and commands in [Reproduction environments](docs/reproduction_environments.md).

## Installation

Clone the public repository and keep the terminal in its root directory:

```sh
git clone --branch v1.0.0-submission.20261018.1 https://github.com/pophip3/geomasklab.git
cd geomasklab
```

The SoftwareX submission uses the fixed review tag [v1.0.0-submission.20261018.1](https://github.com/pophip3/geomasklab/tree/v1.0.0-submission.20261018.1).
The project repository is [https://github.com/pophip3/geomasklab](https://github.com/pophip3/geomasklab); the tag is a version inside this same repository.
The [research-data release](https://github.com/pophip3/geomasklab/releases/tag/v1.0.0-repro.20261016) retains the original water V5 checkpoint,
experiment records and the updated `GeoMaskLab_Supplementary_Reproducibility_Evidence_Final_20261018.zip`.
Use `GeoMaskLab-1.0.0-submission-20261018-final-source.zip` for a downloadable copy of this review source.
The older tags and dated archives remain historical records. The 18 October update
corrects documentation and review entry points; executable code and dependency locks
are unchanged from `v1.0.0-dependencies.20261017`.
All project links above belong to `pophip3/geomasklab` and require no login.
Existing Zenodo DOIs identify historical packages, not this submission archive.
See [submission identities and verification scope](docs/submission_20261018.md).

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt -r requirements.txt
.\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps .
.\.venv\Scripts\geomasklab.exe --version
```

### Linux and macOS

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-build.txt -r requirements.txt
.venv/bin/python -m pip install --no-build-isolation --no-deps .
.venv/bin/geomasklab --version
```

The version command prints `1.0.0`.

## Quick Start / Demo

Keep the terminal in the project directory. The example measures a saved mask,
selects a region, compares mask versions, inspects connected components and
processes a batch. It writes its results to `five-step-output/`.

Run the complete demo with one command after installation:

### Windows PowerShell

```powershell
.\.venv\Scripts\python.exe examples/five_step_workflow.py
```

Then verify its five exported packet types:

```powershell
.\.venv\Scripts\geomasklab.exe verify five-step-output/baseline.zip
.\.venv\Scripts\geomasklab.exe verify-comparison five-step-output/comparison.zip
.\.venv\Scripts\geomasklab.exe verify-components five-step-output/components.zip
.\.venv\Scripts\geomasklab.exe verify-assessment five-step-output/assessment.zip
.\.venv\Scripts\geomasklab.exe verify-batch five-step-output/batch.zip
```

### Linux and macOS

```sh
.venv/bin/python examples/five_step_workflow.py
```

Then verify the exports:

```sh
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

Expected demo measurements: **105,232 foreground pixels / 196,608 valid pixels**.
Its batch completes three samples and records one deliberately missing input;
the empty valid domain has undefined coverage. `five-step-output/summary.json`
reports `"passed": true` when all checks succeed.

<a id="how-to-reproduce-results"></a>
<a id="reproduce-paper-results"></a>

## Reproduce paper results (How to reproduce results)

After installation, run the paper measurement helper from the repository root:

```powershell
.\.venv\Scripts\python.exe examples/reproduce_paper_results.py
```

On Linux/macOS:

```sh
.venv/bin/python examples/reproduce_paper_results.py
```

The bundled NAIP image and mask need no additional download. The command checks
the four conditions in **Section 3.1 / Figure 4**, exports verified packets and
writes `output/paper-results/figure4_metrics.csv`, `figure4_measurements.png`,
`comparison.json` and `summary.json`.

| Condition | Foreground / valid pixels | Expected coverage |
| :--- | ---: | ---: |
| Whole image | 142,629 / 262,144 | 54.41% |
| Right half | 63,028 / 131,072 | 48.09% |
| Exclude left quarter | 105,232 / 196,608 | 53.52% |
| Empty valid domain | 0 / 0 | Undefined |

The whole/right comparison has **0 changed pixels** in the common domain;
the saved foreground difference is **-79,601 pixels**, entirely outside that domain.
The PNG reconstructs the measurement panels; publication artwork is supplied
with the article's LaTeX source.

For **Table 4, Supplementary Figure S1 and Section 3.4**, download
`GeoMaskLab_Supplementary_Experiment_Records.zip` from the
[reproduction release](https://github.com/pophip3/geomasklab/releases/tag/v1.0.0-repro.20261016), place it in the
repository root and run:

```powershell
.\.venv\Scripts\python.exe examples/reproduce_paper_results.py --records GeoMaskLab_Supplementary_Experiment_Records.zip --output output/paper-results-with-records
```

Use `.venv/bin/python` on Linux/macOS. This recalculates all six table rows and
the twelve S1 coverage values from recorded counts, plus the 65-scene water
totals: **IoU 82.27%, Dice 90.27%, precision 97.43%, recall 84.09%**.
Results are saved as `table4_metrics.csv` and `water_metrics.json`.

For new inference on the six selected WHU/iSAID images and the Figure 5 aircraft
case, obtain the official inputs and model assets and follow the reconstruction
guides in the reproducibility supplement. The water V5 checkpoint is supplied as
`GeoMaskLab_Water_V5_Checkpoint.zip` in the same deposit and in the
[reproduction release](https://github.com/pophip3/geomasklab/releases/tag/v1.0.0-repro.20261016).
Follow the [65-scene inference guide](evaluation/water_v5/README.md) to regenerate
the water masks and check every scene against the manuscript counts.
See the [result-by-result reproduction guide](docs/reproduce_paper_results.md)
for commands, data locations and the complete figure/metric mapping.

### Check the software

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -q
.\.venv\Scripts\python.exe reviewer_demo.py
```

On Linux/macOS, replace the Python path with `.venv/bin/python`.
Optional geospatial, schema and signing checks run when their extras are installed.

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

## Documentation

| Guide | Use it to |
| :--- | :--- |
| [Browser workbench](docs/presentation_workbench.md) | Explore the interactive tools and workflows. |
| [API and evidence format](docs/core_package.md) | Integrate the measurement core and understand exported records. |
| [Local-model setup](docs/local_model_modules.md) | Configure optional model adapters. |

## Source layout

- [`src/geomasklab/`](src/geomasklab/): measurement core and command-line interface.
- [`workbench/`](workbench/): browser interface and local server.
- [`model_services/`](model_services/): optional local model adapters.
- [`examples/`](examples/): runnable examples and bundled data.
- [`tests/`](tests/): software tests.

Report bugs or suggest improvements through [GitHub Issues](https://github.com/pophip3/geomasklab/issues).
For development setup and checks, see [Contributing](CONTRIBUTING.md).

## License

GeoMaskLab is distributed under the [MIT License](LICENSE).
Bundled imagery and third-party components retain the terms recorded in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Citation

Use [CITATION.cff](CITATION.cff) for the software author, version and fixed release.
The manuscript is **GeoMaskLab: Replayable measurements for segmentation masks**,
by Yun Xing, submitted to SoftwareX. Its article DOI will be added after publication.
The [versioned reproduction release](https://github.com/pophip3/geomasklab/releases/tag/v1.0.0-repro.20261016) supplies the
reproduction materials and experiment records.

## Contact

[2416010301@hhu.edu.cn](mailto:2416010301@hhu.edu.cn)
