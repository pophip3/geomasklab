# Reviewer quick start

Version 1.0.0.dev7 provides an installable Pillow-only replay core and optional source workbench.

## Independent core and real-image example

```sh
python -m pip install .
python examples/real_image_handoff.py
geomasklab verify workflow-output/real-image/right.zip
geomasklab report workflow-output/real-image/right.zip --output report.html
```

This example includes a credited real NASA photograph and a reproducible color
baseline. It checks explicit denominators and source identities; it makes no
ground-truth or semantic-accuracy claim. The installed wheel provides the core,
CLI and schemas without starting a server. See [core package](core_package.md).

## Requirements and commands

Use Python 3.10 or newer. From the extracted software directory:

```sh
python -m pip install -r requirements.txt
python reviewer_demo.py
python quickstart.py
```

Only Pillow is required. The terminal prints a local URL. Open it in a browser;
use `--port 4182` if port 4180 is occupied. For this walkthrough keep **Demo mode**
(demo mode). A new browser starts in demo mode; an existing browser can remember a
previous live-mode choice. The mode button explains and selects the mode.

The standalone reviewer script neither needs nor invokes model services. After
installation it works offline. The UI and its assets are local, without CDN fonts
or JavaScript dependencies. Model-service mode is an additional path requiring
compatible deployed models, not a condition for the procedural walkthrough.

## Expected automated result

The script exits successfully and writes `reviewer-output/summary.json` plus five
ZIP exports. Failure produces a nonzero exit code. No screenshot comparison or
manual transcription is needed.

| Example | Foreground pixels | Whole-image denominator | Review state |
|---|---:|---:|---|
| Whole buildings | 75,350 | 480,000 | pending |
| Right buildings | 37,350 | 480,000 | accepted by an explicitly labelled automated fixture check |
| Left branch | 38,000 | 480,000 | pending; earlier acceptance not inherited |
| Rectangle `[80,50,280,250]` | 12,850 | 480,000 | pending |
| Whole aircraft | 22,532 | 640,000 | pending |

The generated right/left/ROI examples descend from the whole-image result. The
right example tests saving and reloading review metadata. Each ZIP contains the
source image, full pre-scope mask, final mask, overlay, numerical statistics, run
result, execution log, readable report and checksum manifest. Its final mask and
coverage are reconstructed from the recorded full mask and spatial operation.

To verify any ZIP independently:

```sh
python export_bundle.py reviewer-output/right.zip
```

`verified: true` means file integrity and deterministic pixel reconstruction
passed. `semantic_accuracy_verified: false` remains false even after an accepted
review. These samples are procedural diagrams and fixture masks, not satellite
observations, real model predictions or real-image segmentation ground truth.

## Interactive walkthrough

1. Click **Extract right-half buildings**, then **Extract buildings in the left half.**. The displayed values are
   37,350 and 38,000 pixels respectively; coverage uses the full image denominator.
2. Click the earlier result version to restore it. The next query uses that
   selected version as its parent rather than silently mixing result contexts.
3. Inspect the image and overlay. **Record review** records acceptance, rejection,
   or return to pending; enter an identifier and a reason. This self-reported
   decision changes no mask or numerical statistic.
4. Download **Export evidence** and verify it with the command above. Decisions and
   their complete history are included; rejected results remain exportable for audit.
5. Use **Import evidence** to reopen that ZIP in a new local experiment. The image,
   scope, statistics and prior review records are restored without any inference.
   You may add a review record and export again. Missing ancestor results are not
   reconstructed; new segmentation on an imported image requires model mode.

Optional Label Studio converter interoperability and controlled handoff tests are
documented in [the workflow study](workflow_study.md). They use an official
third-party converter and require NumPy; this does not add dependencies to the
Pillow-only reviewer demonstration.

## Measured execution and installation

On 2026-10-04, a newly created Windows Python 3.13.9 virtual environment contained
only pip 25.2 and Pillow 12.3.0. The five-example script completed in 0.784 seconds.
The main development environment with Pillow 12.0 also passed.

The initial 7.2 MB Pillow wheel download ran at about 57.9 kB/s and took 3 minutes
32 seconds on this connection. A universal two-minute installation claim is not
supported. There is no fixed execution or installation time requirement; the
priority is straightforward and successful reproduction. Package downloading and Python setup
are reported separately. Cross-platform CI runs this entry before installing
the optional evaluation dependencies; check the actual run result for this commit.

## Real model results

For genuine live inference configure `.env` as described in the full repository's
model-service documentation. The earlier 60-image application experiment is
documented separately; it exposes substantial misses and false positives. The
quick walkthrough does not claim to reproduce that model experiment or its
semantic performance. Changes to model behavior require development images and
a new frozen evaluation before making new performance claims.
## Offline investigation of a saved mask

After selecting a mask result, click **Recalculate region (offline)**. Choose
the whole image, one image half, or the current rectangle ROI. To use another
rectangle, draw it on the image before opening the dialog. The target and
complement remain fixed; this operation creates a separate result version with
pending review and does not call model services. It works on imported evidence.

The main coverage value uses the whole image as its denominator. The separate
**Within-region coverage** value uses the selected region. Older records without
these fields show that the value was not recorded; they remain importable.

For a model-free CLI check, run `python reviewer_demo.py`, followed by
`python examples/recalculate_region.py reviewer-output/right.zip`. The script
checks four saved-mask analyses against direct Pillow crops. It does not
measure neural prediction accuracy. See [software scope](software_scope.md).
