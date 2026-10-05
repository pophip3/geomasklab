# Headless core and evidence contract

GeoMaskLab's reusable core is `src/geomasklab`. It requires Python 3.10+ and
Pillow; it imports no browser server, network client, GPU runtime or model.
The source browser workbench calls the same measurement and external-mask
creation functions. Browser routes and legacy adapters live under `workbench/`; the source root
retains only launch/demo entry points and the local-package bootstrap.

## Install and use

Install from this checkout with `python -m pip install .`, or install a built
wheel with `python -m pip install /path/to/geomasklab-VERSION-py3-none-any.whl`.
The project has not yet been published on PyPI. The wheel contains the headless
core and its schemas. Start the optional browser application from the source
distribution with `python quickstart.py`.

```sh
geomasklab create --image image.png --mask mask.png --target building --source "My exported mask" --aligned --output evidence.zip
geomasklab verify evidence.zip
geomasklab recalc evidence.zip --roi 10 10 80 80 --output roi.zip
geomasklab report roi.zip --output report.html
```

`--aligned` is an explicit caller assertion of exact pixel alignment with the
EXIF-normalized displayed RGB image. Input masks must be binary PNG with exact
dimensions. Positive pixels may be encoded as 0/1 or 0/255, with lossless
normalization; probabilities, multiclass images and transparent masks are rejected.
User-entered target/source claims are retained without authenticating their origin.

## Metadata and compatibility

The identifier `geoscope-evidence/1.0` is retained for previously exported evidence.
It denotes the evidence format, independently of the software version or repository
name. Current software version is recorded separately in each new result.

Packaged JSON Schemas use **Draft 2020-12**:

- [Manifest](../src/geomasklab/schemas/manifest-1.0.schema.json)
- [Result](../src/geomasklab/schemas/result-1.0.schema.json)
- [Statistics](../src/geomasklab/schemas/statistics-1.0.schema.json)

`geomasklab schema result` prints the packaged result schema. For optional shape
validation, install from the checkout with `python -m pip install ".[schema]"`,
then run `geomasklab verify evidence.zip --schema`. Schema references resolve
locally; no remote schema request is made. Shape validation complements mandatory
file integrity, source-mask normalization, spatial replay and measurement checks.

### Declared valid pixels

Use an aligned binary PNG with white (1 or 255) for included pixels and black (0)
for excluded pixels. A validity mask has a separate role from the positive-target
prediction. Source and exclusion rationale are required; colors in the image do
not automatically define NoData, clouds or black-border exclusions.

```sh
geomasklab create --image image.png --mask mask.png --target building --source "External prediction" --aligned --valid-mask valid.png --valid-source "Explicit exclusion rationale" --output valid-evidence.zip
geomasklab recalc valid-evidence.zip --scope right --output right.zip
geomasklab recalc valid-evidence.zip --all-valid --output reset.zip
geomasklab verify valid-evidence.zip --schema
python examples/validity_workflow.py
```

Validity-aware evidence uses `geomasklab-evidence/2.0`. It includes `analysis.json`,
the normalized single-channel `valid_mask.png` and the original
`source_valid_mask.png` when supplied. The manifest binds the configuration,
validity identity and valid-pixel counts. Configurations record realized pixel
coordinates, image identity, dimensions, target, complement and connectivity.
They describe one exact input grid; copying pixel ROIs between different-sized
images is not an automatic operation.

For selected region S, declared validity V and positive/complement target E,
the saved output is E intersect S intersect V. `area_ratio` retains the geometric
whole-image denominator; `scope_area_ratio` retains the geometric selected-region
denominator. New `validity_measurements` fields separately record valid denominators,
excluded pixels, `coverage_of_valid_image` and `coverage_of_valid_region`.
Zero valid denominators produce null. Complements exclude invalid pixels.

Recalculation retains validity by default. `--valid-mask` plus `--valid-source`
replaces it; `--all-valid` explicitly resets it. Every change creates a separate
pending-review version and preserves source prediction bytes. The browser exposes
the same operations under **Set region & validity (offline)**. Reference evaluation,
polygon statistics and result comparison use the saved valid domain; comparison
uses the intersection of both domains. No shared valid domain returns
`No_Common_Valid_Domain` with null agreement and no difference image.

Optional GeoTIFF assessment adds separately named valid-area quantities and an
internal validity mask in the exported GeoTIFF. Source GeoTIFF NoData is still
rejected; automatic NoData extraction is not implemented. A user-supplied validity
mask is not proof that its included pixels are scientifically suitable.

Legacy `geoscope-evidence/1.0` inputs remain readable using their original rules.
Evidence without a validity extension declares all image pixels valid. A bundle
cannot place validity files or metadata under the legacy format and have them
silently ignored. Packaged schemas are available with `geomasklab schema analysis`,
`geomasklab schema validity` and `geomasklab schema manifest-v2`.

Verification detects corruption and inconsistent records, including changed
numbers with regenerated hashes. A completely self-consistent replacement bundle
can still pass. SHA-256 does not establish authorship, authenticity or semantic
accuracy. Optional detached Ed25519 signatures bind exact artifact bytes to a separately
trusted key. See [the trust contract](signatures.md). The incompatible MEP 2.0
prototype does not replace the retained core evidence format.

## Local provider adapters

`MaskProvider.produce(image_bytes)` returns a binary PNG and metadata.
`ExcessGreenProvider` is a reproducible, model-free color baseline; its candidates
have no established vegetation or tree accuracy. It uses unnormalized 8-bit RGB
`2*G-R-B`, an integer histogram and the lowest maximizing Otsu threshold.

```sh
geomasklab segment image.png --provider exg --output mask.png
geomasklab create --image image.png --mask mask.png --target tree --source "Green-color candidates; unvalidated" --provider-info mask.png.provider.json --aligned --output evidence.zip
```

The optional sidecar is included in evidence only when its output SHA-256 matches
the supplied mask. It remains caller-supplied provenance. It is retained by region
recalculation and independently checked for mask identity.

The command adapter reads an argument array rather than a shell string. For example,
`command.json` may contain `["python", "my_segmentation.py", "{image}", "{output}"]`:

```sh
geomasklab segment image.png --provider command --argv-json command.json --output mask.png
```

The executable receives a normalized RGB PNG and a fresh output path. It must
produce a binary PNG on the exact input grid within the configured timeout. Exit
code, output identity and executable name are recorded; process output and arguments
are omitted from exported metadata. Model provenance is not authenticated. Command
execution is a local CLI/Python operation; it is not exposed as a browser-server route.

## Reports and reference assessment

Standalone HTML reports require successful replay first, escape metadata values,
embed the verified-mask overlay, and display both denominators. Invalid evidence
is rejected rather than rendered as a reusable report.

Reference scoring is a separate operation described in
[reference evaluation](reference_evaluation.md). It preserves supplied labels,
source assertions and scoped confusion counts in a replayable assessment packet.
It never silently changes review decisions or treats a baseline mask as reference truth.

## Optional standard and geographic extensions

[PROV-JSON mapping](provenance_mapping.md) needs no added runtime dependency.
`.[interop]` installs an independent parser for interoperability tests.
[GeoTIFF area assessment](geospatial_assessment.md) uses the optional `.[geo]`
extra (Rasterio and pyproj). Both work from verified evidence; neither changes
the core's pixel measurements or its evidence-format identifier.

[Polygon/MultiPolygon zones](zonal_statistics.md) work in pixel coordinates with
Pillow alone, or in WGS84 coordinates with a matching projected GeoTIFF and the
geo extra. The separate packet preserves source scope, geometry, domains and
both denominators. `geomasklab schema zonal` exports its record contract.
[Detached signatures](signatures.md) require the optional signing extra and a
separately trusted public key. Export their shape with `geomasklab schema signature`.
[Raster preparation](raster_inputs.md) records explicit bands, window and scaling
before geospatial measurement. Headless targets are explicit ASCII labels;
the browser retains its six category selectors.

## Connected comparison, inspection and batches

The installed commands `compare`, `inspect`, `batch`, `export-batch` and their
verification counterparts call the same core operations as the source workbench.
Comparison packets retain two exact evidence sources and the chosen domain policy.
Inspection filters generate a separate candidate layer and preserve all source pixels.
Batch manifests pair inputs explicitly and pin byte identities, settings and software
version before processing. Cancellation is cooperative; resume replays completed
artifacts before reuse. Macro and micro coverage retain distinct definitions.

See [fair comparison](fair_comparison.md), [candidate inspection](component_inspection.md)
and [manifest batch](manifest_batch.md). Run `examples/five_step_workflow.py` for the
real NAIP integration case and independent arithmetic checks.

Fragmented masks exceeding 100,000 8-connected components are refused before
materializing an unbounded statistics list. Pixel/file limits are admission bounds,
not a claim that every pattern up to 64 million pixels is supported.
