# Explicit offline mask batches

GeoMaskLab processes paired image and binary-mask files without a model or server. A JSON manifest lists each sample and its analysis settings. No files are paired by filename similarity, directory order or an inferred target.

The core requires Pillow. References and declared valid pixels use the same saved analysis domain as individual measurements. An optional reference is a supplied label image; its independence and quality remain user assertions.

## Manifest and commands

Save this as `manifest.json` next to the named input files:

```json
{
  "schema": "geomasklab-batch-manifest/1.0",
  "samples": [
    {
      "id": "site_a",
      "image": "site_a.png",
      "mask": "site_a-mask.png",
      "target": "vegetation",
      "source": "Externally prepared vegetation candidate mask",
      "aligned": true,
      "scope": "all",
      "invert": false,
      "image_source": "Image source and redistribution permission",
      "valid_mask": "site_a-valid.png",
      "valid_source": "Manually declared analysis exclusions",
      "reference": {
        "path": "site_a-reference.png",
        "source": "Reference preparation method and provenance",
        "independent": true,
        "target": "vegetation"
      }
    },
    {
      "id": "site_b",
      "image": "site_b.png",
      "mask": "site_b-mask.png",
      "target": "vegetation",
      "source": "Externally prepared vegetation candidate mask",
      "aligned": true,
      "scope": "right"
    }
  ]
}
```

Remove both `valid_mask` and `valid_source` when no explicit validity mask is supplied. Omit `reference` when no reference is available. White validity pixels include the pixel and black pixels exclude it; image colors do not declare validity. Source masks always denote the positive semantic target, including for complemented measurements.

```bash
geomasklab batch manifest.json --output batch-results
geomasklab verify-batch batch-results
geomasklab export-batch batch-results --output batch-results.zip
geomasklab verify-batch batch-results.zip
```

Relative input paths default to the manifest directory. Set another root explicitly:

```bash
geomasklab batch manifest.json --base-dir input-data --output batch-results
```

Use `--resume` only with the same normalized manifest, input bytes and software version:

```bash
geomasklab batch manifest.json --output batch-results --resume
```

Already completed samples are replayed and retained byte for byte. A changed file, setting, provenance description or software version rejects resume before modifying successful outputs. Missing input files also have a pinned state: supplying a previously missing file creates a different batch identity and requires a new output directory.

Get the formal schema with `geomasklab schema batch`. Runtime checks supplement the schema with resolved-path containment, case-insensitive unique IDs and binary-mask validation.

## Analysis settings

Required sample fields are `id`, `image`, `mask`, `target`, `source` and `aligned: true`. Optional fields are `scope`, `roi`, `invert`, `image_source`, `valid_mask`, `valid_source` and `reference`. Unknown fields are rejected.

`scope` accepts `all`, `left`, `right`, `top` and `bottom`; omitted scope defaults to `all`. An optional rectangle uses the normalized displayed image's pixel coordinates, with exclusive upper bounds:

```json
"roi": {
  "xyxy": [20, 10, 400, 250],
  "source": "imported",
  "image_size": [512, 512]
}
```

The ROI must be valid for the actual image and used with `scope: "all"`. Half-image scopes split at the integer midpoint. The retained output is the positive mask, or its complement, intersected with the selected geometric region and declared valid pixels. Complements never include excluded pixels.

Reference objects require `path`, `source` and a boolean `independent`; their optional `target` defaults to the sample target. Prediction and reference dimensions must match the normalized image exactly. GeoMaskLab does not resize or register labels. A reference error fails the entire sample; no partial successful evidence directory is published.

## Output and replay

The output directory contains:

- `batch_manifest.json`: the normalized explicit pairing and settings.
- `batch_identity.json`: input SHA-256 hashes, byte counts, software version and a canonical batch fingerprint.
- `batch_summary.json` and `batch_summary.csv`: sample states and arithmetic aggregates.
- One directory per completed sample containing `evidence.zip`, `image-input.bin` and `receipt.json`; `reference.zip` is included when requested.
- `debug.log` when a sample fails. This local traceback log is excluded from exported packets.

`image-input.bin` preserves the original image upload bytes, including JPEG or other supported source formats. `evidence.zip` retains normalized image pixels and the original binary-mask bytes. Each receipt binds those artifacts to the pinned input hashes and declared settings. Offline verification needs the output artifacts, without access to the original input directory.

Batch ZIP export contains verified public metadata and completed artifacts, plus a checksum manifest. It excludes local traceback logs, locks and temporary directories. Export holds the same operating-system advisory lock throughout its snapshot and verifies the assembled packet before returning it; concurrent resume cannot produce a mixed snapshot. ZIP verification checks allowed paths, unique members, size limits, checksums, retained input identities, deterministic sample measurements, optional reference calculations and aggregate arithmetic. A completed sample with corrupted or conflicting artifacts prevents resume and export.

Internal verification establishes consistency and replayability. An internally consistent replacement of the entire unsigned dataset and identity can still verify; hashes do not authenticate authorship, original acquisition, semantic accuracy or reference independence. Recorded failures identify processing outcomes, while their causes cannot be independently proven from the exported packet.

## Failure isolation, cancellation and recovery

Each sample runs in its own `TemporaryDirectory`. GeoMaskLab validates its complete staged evidence and optional reference before atomically publishing the sample directory. An exception records a concise English error in the public summary and a traceback in the local log, cleans staging files and proceeds to later samples. Failed samples have unavailable measurements, represented by `null` in JSON and blank fields in CSV.

In the CLI, Ctrl+C requests cooperative cancellation. The core checks cancellation before each sample and before publishing its artifacts. It does not interrupt a decoding or measurement operation midway. Completed results remain usable; cancelled samples have no successful artifacts and can be retried with verified resume. The browser routes its cancellation control to this same core predicate.

Metadata files are replaced atomically. If interruption occurs after a valid sample directory is published but before its summary is updated, resume validates the receipt and recovers that completed sample without rerunning it. A concurrent writer is rejected by a nonblocking operating-system advisory lock (`fcntl.flock` on Unix and `msvcrt.locking` on Windows). The operating system releases that lock when its process exits, including abrupt termination. The harmless `.batch.lock` file remains in the output directory and is excluded from exported packets.

After acquiring the exclusive lock, resume validates the unchanged input identity and removes an abandoned `.sample-*` staging directory only when its ownership marker identifies this batch, its paths remain inside the output directory and its contents are recognized regular artifacts. Empty staging directories are safe to remove. Atomic metadata temporary filenames include the complete pinned batch fingerprint and a permitted target filename; only matching regular files inside this output directory can be removed after an interrupted write. Foreign markers, symbolic links and unexpected files are rejected and preserved. Published sample directories are verified and retained. A missing or stale derived summary CSV can be regenerated only after its JSON, pinned identity and completed evidence replay correctly; ordinary verification still rejects a mismatching CSV. This recovery does not use PID liveness guesses or terminate another process. Graceful cancellation releases the lock and cleans temporary directories. Damaged ownership markers, unfinished initial metadata setup before a valid identity and summary exist, or unrelated files require explicit recovery; they are not automatically deleted. No completed sample has been published at that initial setup stage.

## Aggregate interpretation

For completed sample `i`, let `A_i` be retained foreground pixels and `R_i` its selected valid-region pixels. Coverage is `p_i = A_i / R_i` when `R_i > 0`; otherwise it is `null`.

- `macro_mean_coverage`: the arithmetic mean of defined per-sample coverages.
- `micro_weighted_coverage`: `sum(A_i) / sum(R_i)` over completed samples with a nonempty valid domain.
- `undefined_coverage_samples`: completed samples whose valid-region denominator is zero.

Successful zero-foreground measurements with a nonempty domain contribute zero to both aggregates. Empty domains are omitted from both aggregates and counted explicitly. Failed, cancelled and pending samples contribute no measurements. If every denominator is unavailable or zero, both aggregate coverages are `null`.

For example, two completed measurements of `4/16` and `2/2` yield macro coverage `0.625` and micro coverage `6/18 = 0.333333...`. Averaging percentages and pooling pixels answer different questions. All ratios use values from zero to one.

## Resource and portability limits

The CLI core accepts 1–128 explicit samples and a manifest no larger than 1 MB. Images are limited to 48 MB and 64 million pixels; individual binary-mask uploads to 32 MB. Inputs are single-frame images and exactly aligned lossless binary PNG masks. Image orientation is normalized; masks are never silently rotated, resized or thresholded. Existing browser upload and HTTP limits can be smaller than these core limits.

Exported batch packets are limited to 256 MB in both compressed and expanded size. Divide larger collections into explicitly named manifests. This workflow is sequential and does not claim distributed or unbounded raster processing.

Input paths are relative to the declared base directory, use forward slashes and cannot contain traversal or drive prefixes. Resolved symlink escapes are rejected. Sample IDs contain 1–64 ASCII letters, digits, underscores or hyphens, begin with a letter or digit and are unique even on case-insensitive filesystems. Reserved Windows device names are rejected. The output directory must be distinct from the input root and cannot contain a declared input file.

## Python API

```python
from geomasklab.batch import run_batch, verify_batch, batch_packet, verify_batch_packet

summary = run_batch(
    manifest,
    base_dir="input-data",
    output_dir="batch-results",
    resume=False,
    cancel=lambda: False,
    progress=lambda snapshot: print(snapshot["completed_count"]),
)
facts = verify_batch("batch-results")
packet = batch_packet("batch-results")
facts_from_packet = verify_batch_packet(packet)
```

The optional progress callback receives a copied summary snapshot. Core calculation, evidence creation, reference evaluation, verification and aggregate rules are shared by the CLI and browser adapters.
