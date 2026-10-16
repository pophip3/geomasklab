# Reviewer quick start

Follow the [README installation](../README.md#installation) in a new virtual
environment. It pins Pillow and the source-build tools and provides commands
for Windows, Linux and macOS.

## Run the demo

```sh
python examples/five_step_workflow.py
```

Use the installed virtual environment Python. Expected result:
five-step-output/summary.json contains passed: true. The example checks
measurement, common-domain comparison, component inspection, reference
assessment and batch replay. The README lists the five CLI verification commands.
The sample with a missing input is a deliberate batch check; three other samples
complete, including one with an empty valid domain.

## Reproduce the manuscript measurements

```sh
python examples/reproduce_paper_results.py
```

The bundled NAIP image reproduces Section 3.1 / Figure 4: 54.41%, 48.09%, 53.52%
and undefined coverage. Outputs are in output/paper-results/.
For Table 4, Supplementary Figure S1, the 65-scene numerical records and model
reconstruction, see [Reproduce paper results](reproduce_paper_results.md).

## Explore the browser workbench

```sh
geomasklab-ui --port 4180
```

Open http://127.0.0.1:4180, select **Enter workbench** and open the bundled demo.
Keep the terminal running; press Ctrl+C to stop it. For new image questions and
model-generated masks, follow [Local-model setup](local_model_modules.md).

## Additional bundled checks

| Command | Expected result |
| --- | --- |
| python examples/reproduce_table.py | 54.41%, 48.09%, 53.52%; spread 6.32 percentage points |
| python examples/run_replay_demo.py | Original PASS; altered valid-mask pixel produces the expected rejection; exit code 0 |
| python examples/replay_model_mask.py | Whole 6,543, left 0, right 6,543, rectangle 713 foreground pixels; four replay passes |
| python reviewer_demo.py | passed: true; five procedural examples match expected counts |

These commands use supplied inputs and run without model downloads.
