# GeoMaskLab independent release handoff

Ask a colleague who did not develop GeoMaskLab to follow this path using the
public rc4 release and its documentation. Record failures and any author help.
Successful independent completion is a separate result from automated testing.

## Obtain and install the release

Use Python 3.10 or newer. Download the source ZIP, wheel and `SHA256SUMS.txt`
from [v1.0.0rc4](https://github.com/pophip3/geomasklab/releases/tag/v1.0.0rc4).
Compare their digests using `Get-FileHash -Algorithm SHA256` on PowerShell,
`sha256sum` on Linux or `shasum -a 256` on macOS. Extract the source ZIP.

Create a new environment beside the downloaded files. On Windows PowerShell:

```powershell
python -m venv ui-env
.\ui-env\Scripts\python.exe -m pip install .\geomasklab-1.0.0rc4-py3-none-any.whl
.\ui-env\Scripts\geomasklab.exe --version
.\ui-env\Scripts\geomasklab-ui.exe --port 4180
```

On Linux or macOS:

```sh
python3 -m venv ui-env
./ui-env/bin/python -m pip install ./geomasklab-1.0.0rc4-py3-none-any.whl
./ui-env/bin/geomasklab --version
./ui-env/bin/geomasklab-ui --port 4180
```

Open the local URL printed by the server. If the port is occupied, choose another
port with `--port`. Keep the terminal running while using the browser. The wheel
supplies the complete interface, assets and scientific core. The source ZIP
supplies the matching real-image inputs and batch examples. No model service
is needed for this walkthrough. The first screen is the introduction; choose
**Enter workbench**. **Overview** returns to the introduction without changing
the selected experiment. This is the interface intended for submission figures.

## Complete the browser path

1. Choose the real image `examples/data/naip-denver/image.png` from the extracted
   source. It is a 512 × 512 USDA NAIP Denver image supplied through USGS.
2. Use **Import mask** with the matching `mask.png`. Select **Vegetation** and record
   the source as "repository excess-green/Otsu baseline; not independently
   validated vegetation labels". Confirm pixel alignment. Keep this first version.
3. Expand **Measurement details** and use **Region & validity**.
   Derive a **Right half** version without replacing the prediction. Record the
   selected version, foreground count, whole-image denominator and region denominator.
4. Compare the two saved versions using **Restrict to shared valid pixels**.
   Record the common denominator and the explanation of the foreground-total
   difference. Identical prediction pixels can have different totals because
   the selected regions differ.
5. Export the selected region's evidence ZIP and the comparison packet. Record
   the filenames the browser actually saved; an experiment-specific filename is normal.
6. Close and reopen the workbench. Check that the session and saved versions
   remain available. Record any ambiguity about which version is selected.

The baseline is not vegetation ground truth. Review acceptance is a user's
recorded decision; it does not turn integrity checks into accuracy measurements.

## Replay in a second environment

Stop the UI server with Ctrl+C when finished. From the directory containing the
downloaded wheel, create a second environment. Create a `replay` directory beside
it, outside the extracted source tree. Copy the selected region's evidence ZIP
and comparison ZIP there, naming them `selected-region-evidence.zip` and
`comparison.zip`. Renaming a ZIP does not change its contents. Keep the original
download names in the handoff record.

On Windows PowerShell:

```powershell
python -m venv cli-env
.\cli-env\Scripts\python.exe -m pip install .\geomasklab-1.0.0rc4-py3-none-any.whl
.\cli-env\Scripts\python.exe -I -m geomasklab --version
.\cli-env\Scripts\python.exe -I -m geomasklab verify .\replay\selected-region-evidence.zip
.\cli-env\Scripts\python.exe -I -m geomasklab verify-comparison .\replay\comparison.zip
```

On Linux or macOS, use `python3 -m venv cli-env` and replace
`.\cli-env\Scripts\python.exe` with `./cli-env/bin/python`; use forward slashes
for the wheel and packet paths. The `-I` option prevents the local source and
`PYTHONPATH` from supplying the imported core. Verification must exit successfully
and agree with the saved counts and denominators. The core replay starts no
browser or model service.

## Exercise failure isolation and recovery

The published source provides an automated real-image batch example:

```sh
python examples/five_step_workflow.py
```

From the extracted source, use the first environment's Python. It writes
`five-step-output/index.html`, a batch manifest and its named inputs, and exercises
one deliberately missing input plus one empty valid domain. It also checks
verified resume. Record the resulting summary rather than counting an empty
denominator as zero coverage.

For another attempt, choose a new output directory, for example
`python examples/five_step_workflow.py --output five-step-retry`, and adjust the
paths below to that directory. Retain the earlier outputs and failed record.

For a browser cancellation attempt, expand **More**, use **Offline batch**, upload
`five-step-output/batch-manifest.json` and all available files named by that
   manifest. They are in `five-step-output/inputs`. Do not supply the deliberately
missing file. While the batch is running, request cancellation. It is cooperative:
a sample may finish computing before cancellation takes effect. If the batch
finishes too quickly to cancel, record "cancellation not observed"; do not claim
a successful cancellation. After an observed cancellation, use **Verify & resume**,
export the batch and replay it with `geomasklab verify-batch batch.zip`.

## Record and return the result

Use a copy of [handoff_record.csv](handoff_record.csv). For each step, record
the exact command or browser action, environment, actual output, status, elapsed
time, unclear wording and author intervention. Keep the failed attempt when
retrying; add another row for the retry. Remove personal paths and credentials
before sharing logs publicly.

Return the filled record, relevant error messages and exported evidence to the
author. Do not rely on the author's development directory or existing virtual
environment. One successful handoff establishes that participant's completion;
it does not estimate a general productivity or usability improvement. The
[separate observed study protocol](handoff_study.md) remains available if a
matched comparison study is later conducted.
