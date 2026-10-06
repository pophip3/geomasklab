# GeoMaskLab reviewer reproduction

This procedure reproduces the principal pixel-analysis example from a fixed
release. The browser, CLI and source archive use the same calculation core.
The interface shown in manuscript figures must come from the submitted version.

## Download and installation

Download the wheel, source ZIP and `SHA256SUMS.txt` from the fixed release linked
in the manuscript. Record the release version and verify the downloaded hashes.
Extract the source ZIP to obtain the public example inputs; install the wheel
in a new environment beside, rather than inside, the extracted source directory.
Python 3.10 or newer is required. Installation downloads Pillow; the following
example requires no model service, account or GPU.

Windows PowerShell:

```powershell
python -m venv ui-env
.\ui-env\Scripts\python.exe -m pip install .\geomasklab-1.0.0rc6-py3-none-any.whl
.\ui-env\Scripts\geomasklab.exe --version
.\ui-env\Scripts\geomasklab-ui.exe --port 4180
```

macOS/Linux:

```sh
python3 -m venv ui-env
./ui-env/bin/python -m pip install ./geomasklab-1.0.0rc6-py3-none-any.whl
./ui-env/bin/geomasklab --version
./ui-env/bin/geomasklab-ui --port 4180
```

Open the URL printed by the server and keep the terminal running. If the port
is occupied, use `--port 4182`. Use the same working directory when restarting;
saved experiments are written to its `experiments` directory. A local URL refers
to the reviewer's computer after startup.

## Principal example

1. On the introduction, choose **Import image + mask**. Select the extracted
   `examples/data/naip-denver/image.png` as the source image and `mask.png` as
   the target mask. The form should show matching 512 × 512 dimensions.
2. Choose **Vegetation**, enter
   `repository excess-green/Otsu baseline; not independently validated`,
   confirm alignment and choose **Import and view results**. Record V1.
3. Expand **Measurement details → Region & validity**. Choose **Right half**,
   retain **Keep saved validity**, and create V2.
4. Choose **Compare versions**, compare V1 and V2 using
   **Restrict to shared valid pixels**, and export the comparison packet.
5. Select V2 and use **Export evidence**. Keep the ZIP unchanged; record its
   original download name. For the commands below, name a copy
   `selected-region-evidence.zip`, and name the comparison copy `comparison.zip`.
6. Export the same saved V2 using **Export figure** if inspecting presentation
   outputs. PNG, PDF, SVG and `config.json` are available. Reload and reopen
   the experiment to check saved-result persistence.

| Measurement | Whole image V1 | Right half V2 |
| --- | ---: | ---: |
| Foreground pixels | 142,629 | 63,028 |
| Whole-image denominator | 262,144 | 262,144 |
| Whole-image coverage | 54.41% | 24.04% |
| Selected-region denominator | 262,144 | 131,072 |
| Selected-region coverage | 54.41% | 48.09% |

The comparison has 131,072 common valid pixels and zero changed prediction
pixels. The selected region changed; the original prediction did not. Coverage
is a proportion of pixels, not a segmentation-accuracy score. The real NAIP
RGB image is credited to USDA-FSA-APFO / USGS The National Map; its accompanying
mask is an unvalidated color baseline. Source details are in
`examples/data/naip-denver/provenance.json`.

## Independent command-line replay

Stop the UI with Ctrl+C. Create another environment in the download directory,
outside the source tree. Store your two exported ZIP copies in `replay`.

```powershell
python -m venv cli-env
.\cli-env\Scripts\python.exe -m pip install .\geomasklab-1.0.0rc6-py3-none-any.whl
.\cli-env\Scripts\python.exe -I -m geomasklab verify .\replay\selected-region-evidence.zip
.\cli-env\Scripts\python.exe -I -m geomasklab verify-comparison .\replay\comparison.zip
```

On macOS/Linux, use `python3 -m venv cli-env` and replace the executable path
with `./cli-env/bin/python` and the packet paths with forward slashes.
Both commands should exit with code 0 and report `verified: true`. The evidence
replay reports `pixel_area: 63028`, `scope: right` and
`area_ratio: 0.2404327392578125`, consistent with the saved V2.

## Extended checks and other data

The [full handoff procedure](independent_handoff.md) and
[Chinese procedure](independent_handoff_zh.md) cover valid pixels, empty
denominators, candidate location, isolated batch failures, cancellation and
verified resume. The published `examples/five_step_workflow.py` generates
explicit batch inputs and a deliberately missing-input sample. Record this
sample as an expected failure and confirm successful samples remain available.

Reviewers may replace the supplied pair with their own image and aligned binary
mask. Dimensions are preserved; matching dimensions alone do not establish
alignment. The browser supports image files up to 12 MB and 16 million pixels.
Neither the procedure nor the program assumes a universal 512 × 512 image size.

Record environment details, commands, actual outputs, exceptions and any author
assistance. Preserve the first failure and its retry rather than replacing the
record with the final result. The same release and public instructions are used
for pre-submission independent verification and reviewer reproduction.

Software support: Yun Xing, Hohai University — 2416010301@hhu.edu.cn.
