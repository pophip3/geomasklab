# Headless core and evidence contract

GeoMaskLab's reusable core is `src/geomasklab`. It requires Python 3.10+ and
Pillow; it imports no browser server, network client, GPU runtime or model.
The source browser workbench calls the same measurement and external-mask
creation functions. Root modules remain compatibility entry points for older
scripts and examples.

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

Verification detects corruption and inconsistent records, including changed
numbers with regenerated hashes. A completely self-consistent replacement bundle
can still pass. SHA-256 does not establish authorship, authenticity or semantic
accuracy. Signed evidence and the incompatible supplied MEP 2.0 format have not
been adopted into this release.

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
