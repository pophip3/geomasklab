# GeoMaskLab

> Replayable measurements and portable evidence for segmentation masks.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Software checks](https://github.com/pophip3/geomasklab/actions/workflows/research-checks.yml/badge.svg)](https://github.com/pophip3/geomasklab/actions/workflows/research-checks.yml)
[![Reviewer quickstart and core coverage gate](https://github.com/pophip3/geomasklab/actions/workflows/ci.yml/badge.svg)](https://github.com/pophip3/geomasklab/actions/workflows/ci.yml)

## Reviewer quickstart — bundled data, no models required

Use Python 3.10+ and this **1.0.0 revised snapshot**. The fixed source archive
records its exact commit and checksums. The commands below use only bundled
NAIP imagery and a retained color-baseline mask; they perform no model download.

1. Clone and install in a virtual environment:

   ```sh
   git clone --branch softwarex-v1.0.0-revised https://github.com/pophip3/geomasklab.git
   cd geomasklab
   python -m venv .venv
   ```

   Activate `.venv` with `.\.venv\Scripts\Activate.ps1` on Windows or
   `source .venv/bin/activate` on Linux/macOS, then run `python -m pip install .`.

2. Recompute the manuscript's saved-domain example:

   ```sh
   python examples/reproduce_table.py
   ```

   Expected coverages: **54.41%, 48.09%, 53.52%**; spread **6.32 pp**. Each
   line identifies its manuscript section/figure. These use different analysis
   supports and retain the same source prediction. Output ZIPs and counts are
   saved under `reviewer-output/denominators/`.

3. Verify retained bytes and numerical replay, then reject one changed pixel:

   ```sh
   python examples/run_replay_demo.py
   ```

   The original reports PASS. The intentional mutation reports the expected
   `manifest.checksums.valid_mask.png.sha256` failure; this successful rejection
   leaves the script's exit code zero. Artifacts are saved under
   `reviewer-output/replay-demo/`. Unsigned replay proves internal consistency.

Run `geomasklab-ui` to open the complete local workbench. Fresh scene questions
and text segmentation have a separate [local-model setup](docs/local_model_modules.md)
and real-inference acceptance command; their original weights need about 19.2 GB
and suitable memory. The lightweight quickstart above does not rerun those models.

GeoMaskLab binds a binary mask to its image, target, spatial scope, declared valid
pixels and coverage denominators. Compare results under explicit conditions,
inspect clipping boundaries, process paired samples reliably and let a colleague
replay the measurement offline. The headless core requires
only **Python 3.10+ and Pillow**. The complete browser workbench is included in the same package and uses the same core.

## Official website

Visit the [GeoMaskLab documentation website](https://pophip3.github.io/geomasklab/)
for the workbench guide, examples and service setup.

## Optional local model modules

Scene questions use **RemoteAgent**; text-driven extraction uses **RemoteAgent +
RemoteSAM**. The source includes independent local HTTP adapters, separate model
environment requirements, a supervised launcher and a portable configuration
example. See [local setup and reviewer use](docs/local_model_modules.md) and
[fixed upstream identities](docs/model_source_provenance.md).

Reviewers run these services on their own computer after obtaining the external
weights and architecture. After installation, inference uses local files only.
The author's computer does not need to stay online. Original BF16 RemoteAgent
weights require substantial memory; disk offload is slower and has separate
image/token budgets. Saved evidence and the normal workbench remain usable
offline without either model. Replay does not generate a new scene answer or mask.

## Install

```sh
git clone --branch softwarex-v1.0.0-revised https://github.com/pophip3/geomasklab.git
cd geomasklab
python -m venv .venv
```

Activate with `.\.venv\Scripts\Activate.ps1` on Windows PowerShell, or
`source .venv/bin/activate` on Linux/macOS. Then:

```sh
python -m pip install .
geomasklab --version
```

For independent testing, use the **1.0.0 revised snapshot** source branch above.
The [original 1.0.0 release](https://github.com/pophip3/geomasklab/releases/tag/v1.0.0)
is retained with its original tag and assets. It predates the local model package
and the two new reviewer scripts; use matching revised artifacts when available.
The wheel includes the complete browser interface, images, CLI and JSON Schemas;
the source ZIP supplies the matching examples and handoff instructions. After
installing the wheel, run `geomasklab-ui` and open the local URL it prints.
The root URL shows the introduction; **Enter workbench** opens the working view.
The interface matches this release's [presentation guide](docs/presentation_workbench.md).
Core calculations and all five browser workflows use the same source in both
artifacts. Optional geo, interoperability and signing dependencies are installed
with the corresponding extras; model-service mode uses explicitly configured
external endpoints. No private development configuration or model weights ship.
PyPI publication and archival DOI remain pending. Confirmed citation metadata for
Yun Xing, Hohai University ([ORCID](https://orcid.org/0009-0009-1746-5019)), is in [CITATION.cff](CITATION.cff).

## One connected offline workflow

```sh
python examples/five_step_workflow.py
geomasklab verify-comparison five-step-output/comparison.zip
geomasklab verify-components five-step-output/components.zip
geomasklab verify-batch five-step-output/batch.zip
```

This real NAIP example declares valid pixels, compares a controlled mask
perturbation, inspects clipped components, processes explicitly paired inputs
and replays each exported operation. Independent pixel sets check the arithmetic.
One deliberate missing-input failure and one empty valid domain demonstrate
failure isolation and undefined coverage; the perturbed mask is a software fixture.
The English report is `five-step-output/index.html`. Add `--geo` after installing
the geo extra to check matching nominal square-metre measurements.

The mask workflow and source preservation are reproducible. Semantic accuracy
and actual human handoff value require separate studies.

## A real geospatial example

The source includes a credited, public-domain 2019 USDA NAIP chip from USGS,
a reproducible color-baseline mask and four WGS84 study polygons. Install the
optional geo extra to reproduce nominal square-metre areas:

```sh
python -m pip install ".[geo]"
python examples/naip_zonal_workflow.py
geomasklab verify-zonal workflow-output/naip-zonal/zonal.zip
```

All four polygon domains, foreground counts and nominal areas agree with an
independent Rasterio/GDAL and NumPy calculation. The script writes a consistency
table. The regions include holes, MultiPolygon overlap and a slanted boundary.
The full-image color mask contains **142,629 foreground pixels**, or
**51,346.44 m2 of nominal projected area** on the exported 0.6 m grid.
Its vegetation semantics have not been assessed; projection distortion and
terrain are omitted. See [data provenance](examples/data/naip-denver/README.md)
and [the comparison record](evaluation/geospatial/README.md).

For a Pillow-only workflow without optional dependencies:

```sh
python examples/real_image_handoff.py
geomasklab verify workflow-output/real-image/right.zip
geomasklab report workflow-output/real-image/right.zip --output report.html
```

That NASA photograph example illustrates the two coverage denominators, with
35,751 foreground pixels, 20.7199% of the image and 41.3173% of the selected half.

## Bring your own mask

```sh
geomasklab create --image image.png --mask mask.png --target building --source "My exported binary mask" --aligned --output evidence.zip
geomasklab verify evidence.zip
geomasklab recalc evidence.zip --roi 10 10 80 80 --output roi.zip
geomasklab report roi.zip --output roi.html
geomasklab compare evidence.zip roi.zip --domain-policy intersection --output comparison.zip
geomasklab inspect roi.zip --min-area-pixels 10 --output components.zip
```

Inputs are a single image and an exactly aligned binary PNG, with explicit
target/source assertions. The PNG may encode positives as 1 or 255. Probabilities,
multiclass masks, transparent pixels and dimension mismatches are rejected.
Coordinates refer to the EXIF-normalized displayed RGB image. Outputs retain
source bytes, full/scoped masks, metrics, review state, provenance and a manifest.

[Core API, providers and JSON Schemas](docs/core_package.md) describe the Python
interface, format compatibility, local RGB baseline and external-command adapter.
[PROV-JSON mapping](docs/provenance_mapping.md) exports standard provenance metadata.
[Optional GeoTIFF assessment](docs/geospatial_assessment.md) binds a matching raster
to declared square-metre area models and a georeferenced mask export.
[Polygon zones](docs/zonal_statistics.md) measure explicit domains and replay their packets.
[Detached signatures](docs/signatures.md) bind bytes to a separately trusted key.
[Raster windows and scaling](docs/raster_inputs.md) prepare explicit multiband/high-bit-depth inputs.
[Reference assessment](docs/reference_evaluation.md) adds supplied reference masks,
scoped confusion counts and a separately replayable assessment packet.
[Fair comparison](docs/fair_comparison.md) distinguishes source-mask changes from
analysis-condition changes and accounts for foreground outside the shared domain.
[Candidate inspection](docs/component_inspection.md) exposes stable component IDs,
bounding boxes and independent image/region/invalid-boundary flags.
[Explicit manifest batches](docs/manifest_batch.md) provide isolated failures,
cooperative cancellation, verified resume and separate macro/micro coverage.

## Optional browser workbench

```sh
python quickstart.py
```

Open `http://127.0.0.1:4180`, or select another port with `--port 4182`.
Import images, external masks and verified evidence; inspect overlays; recalculate
regions and valid pixels; compare versions under a chosen domain policy; inspect
candidate boundaries; run an **Offline mask batch**; replay review packets; and
download evidence. Completed batch samples reopen directly in the same workbench.
Procedural demonstration fixtures
are labeled explicitly. Configured external model services are optional:
[setup and contract](docs/model_services.md). Stop the server with Ctrl+C.

## Validation and maintenance

```sh
python -m pip install ".[schema,geo,interop,signing]" -r evaluation/requirements-evaluation.txt
python -m unittest discover -s tests -p "test_*.py" -q
python reviewer_demo.py
python examples/reference_workflow.py
python examples/real_image_handoff.py
python examples/five_step_workflow.py --geo
```

The CI matrix covers Windows, Linux and macOS with Python 3.10 and 3.13; inspect
the linked workflow for the result at your exact commit. Distribution checks
also run the installed wheel outside the checkout and verify a committed source
archive. Tests check arithmetic, provenance, state, malformed inputs and evidence
replay; they do not replace independent semantic evaluation.

The earlier fixed rc3 source rerun passed 271 of 272 tests. One native file-symlink
test was skipped because the Windows account could not create file symlinks.
The [release validation summary](docs/release_validation.md) distinguishes the
current rc4 handoff candidate from the historical rc3 baseline. The 1.0.0 release
provides its own artifact hashes and current-commit technical acceptance. An
[independent handoff walkthrough](docs/independent_handoff.md) and empty
record sheet are ready for a colleague; a [Chinese handoff guide](docs/independent_handoff_zh.md)
is also included. No human completion is claimed yet.

- [Architecture](docs/architecture.md) and [software scope](docs/software_scope.md)
- [Existing-tool workflow study](docs/workflow_study.md)
- [Historical real-image results and limitations](docs/application_results.md)
- [Changes](CHANGELOG.md), [contributing](CONTRIBUTING.md) and [local security](SECURITY.md)

## Limitations

Core measurements are in pixels. The headless limit is 64 million pixels and 100,000 connected components, with bounded file/archive sizes; the browser keeps smaller upload limits. Optional geospatial assessment requires matching
8-bit GeoTIFF pixels, valid domains and declared coordinate units. Nominal area
omits projection distortion; the geodesic corner model omits terrain and edge
curvature. Polygon domains and separately trusted Ed25519 signatures are supported. Temporal change remains outside this release. Source/alignment assertions and semantic
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
Confirmed creator metadata is in CITATION.cff; an archival DOI remains pending.
Use the [issue tracker](https://github.com/pophip3/geomasklab/issues) for support.
