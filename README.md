# GeoMaskLab

> Replayable measurements and portable evidence for segmentation masks.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Software checks](https://github.com/pophip3/geomasklab/actions/workflows/research-checks.yml/badge.svg)](https://github.com/pophip3/geomasklab/actions/workflows/research-checks.yml)

GeoMaskLab binds a binary mask to its image, target, spatial scope and coverage
denominators. Create an evidence ZIP, change its region without model inference,
and let a colleague replay the measurement offline. The headless core requires
only **Python 3.10+ and Pillow**. The optional browser workbench uses the same core.

## Official website

Visit the [GeoMaskLab documentation website](https://pophip3.github.io/geomasklab/)
for the workbench guide, examples and service setup.

## Install

```sh
git clone https://github.com/pophip3/geomasklab.git
cd geomasklab
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
the source archive. This release candidate is **1.0.0rc2**. PyPI publication,
confirmed creator metadata, stable tagging and archival DOI remain pending.

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
python -m pip install ".[schema,geo,interop,signing]" -r evaluation/requirements-evaluation.txt
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

Core measurements are in pixels. The headless limit is 64 million pixels with bounded file/archive sizes; the browser keeps smaller upload limits. Optional geospatial assessment requires matching
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
creator metadata and an archival DOI will accompany the stable release.
Use the [issue tracker](https://github.com/pophip3/geomasklab/issues) for support.
