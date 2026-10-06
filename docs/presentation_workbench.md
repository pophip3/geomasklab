# Workbench presentation and publication figures

The browser presentation layer is in `workbench/web/presentation.css` and
`presentation.js`. It preserves the existing workbench operations and shared
Python calculations. No framework, remote font, icon service or model download
is needed.

## Start and inspect

Start the browser workbench as described in the reviewer quickstart. First-time
visitors see a project introduction at the root URL, including when an experiment
has already been saved. **Overview** returns to it. The explicit `#workbench` URL
opens the workbench directly; `#home` opens the introduction. Switching pages
preserves the current investigation. **Run an offline example** creates a separate
synthetic urban investigation and calculates its procedural building mask in
demo mode. It does not call model services or establish EO accuracy.

The introduction animates the repository's real 2019 Denver NAIP RGB image and
its actual excess-green/Otsu baseline mask. This preview is separate from the
procedural example. It is credited to USDA-FSA-APFO / USGS The National Map,
and labeled as unvalidated vegetation candidates. The assets are byte-identical
copies of `examples/data/naip-denver/image.png`, `mask.png` and `provenance.json`.
The animation can be paused; it stops in the workbench and respects reduced motion.

The main coverage card shows the saved whole-image percentage, a proportional
blue ring and the foreground/total-image pixel fraction. Geometric-region and
valid-pixel denominators remain available in **Measurement details**. The amber
**Demo mode** label identifies the current runtime setting separately from each
result's recorded provenance.

Use the labeled toolbar icons for **Hide assistant**, **Hide results** and **Focus
canvas** to give the image more space. Escape exits canvas focus. Original, overlay, binary mask and the
existing comparison slider continue to use the selected saved result. The scale
bar follows displayed zoom and measures **pixels**. The arrow indicates **Y−**,
not geographic north. Geographic annotations require recorded georeferencing.

Review status and integrity status are distinct. An accepted review is a
self-reported decision; passing integrity checks is not a semantic-accuracy score.
Error dialogs display the actual error message, rather than invented validation
codes or successful checks.

The default working view shows the image, target, whole-image coverage,
foreground pixels, candidate components and primary actions. **Measurement
details** expands the saved scope, validity denominators, method, timings,
integrity checks and review guidance. Successful mask messages have a short
summary and expandable full response; errors and clarification remain visible.
**Task settings & info**, **More** and **Result history** retain the advanced
controls and complete records without repeating them throughout the working view.
At widths of 980 px and above, the image and results remain side by side.

## Export a paper figure

Select a saved mask version, then choose **Export figure** below **Export evidence**.
The available layouts are a single overlay, original/overlay pair,
and original/overlay/binary-mask triptych. Choose 300 or 600 DPI and optionally
include a legend, pixel scale, subfigure labels and measurement caption.

- Print width is 180 mm. PNG stores a corresponding `pHYs` density chunk.
- PDF embeds a JPEG raster at the same physical page size; it is not a vector PDF.
- SVG embeds a PNG raster at the declared physical size; mask boundaries are
  not vectorized.
- Higher DPI improves figure annotations and output sampling; it does not add
  detail to the source observation.

The export captures the **selected saved version**, not a new ROI being drawn,
the currently displayed zoom or an unsaved analysis setting. Its caption uses
the saved measurements and distinguishes whole-image, geometric-region and
valid-region coverage. An empty valid domain remains undefined. Geographic
scale, CRS and north are not inferred from RGB browser uploads.

Download the companion **config.json** separately. It includes SHA-256 hashes
of the stored normalized image and mask bytes, software version, figure settings,
task, analysis configuration, measurements, provenance, execution trace and
review record. Model or weight versions and seeds absent from the saved record
are null, with an explicit explanation. The normalized image hash need not equal
the original uploaded-file hash. Retain the normal evidence ZIP for independent
measurement replay: the figure configuration does not replace that packet.

## Verify

`tests/presentation_browser.cjs` checks the first-run path, real-image mask import,
saved-metric equality, layout controls, split view, scale under zoom, downloads,
mobile overflow, session restoration and reduced motion. It needs an installed
Playwright package and Edge. Set `PLAYWRIGHT_PATH`, `GEOMASKLAB_UI_URL` and
`GEOMASKLAB_UI_AUDIT` for your local installation and isolated audit output.
Run it against a server with a separate experiment directory when other work is
in progress. Generated audit images and downloads are not release source files.

`tests/unified_handoff_browser.cjs` walks the installed browser through all five
workflow operations and replays its actual downloads in a second installed
environment. Set `GEOMASKLAB_REPLAY_PYTHON` to that environment's interpreter,
`GEOMASKLAB_HANDOFF_AUDIT` to an output directory and `GEOMASKLAB_UI_URL` to the
isolated installed server. These are automated checks, not participant observations.
