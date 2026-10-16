# Reproduction environments

Use one environment per row. The installation files fix direct and indirect
dependencies, including Python-version branches and Linux CUDA libraries.

| Workflow | Python | Platform | Installation files |
| --- | --- | --- | --- |
| Core demo and paper measurement replay | 3.10 or newer; fresh check with 3.12 | Windows, Linux, macOS | `requirements.txt`, `requirements-build.txt` |
| Evaluation, plots, Label Studio brush conversion, schema/geo/provenance/signing | 3.10-3.12 | Windows AMD64, Linux x86_64 (glibc 2.28+) | `evaluation/requirements-*.txt`, `requirements-extras.txt` |
| RemoteAgent | 3.10 | Windows AMD64, Linux x86_64, NVIDIA CUDA 12.4 | `model_services/requirements-agent.txt` |
| RemoteSAM | 3.10 | Windows AMD64, Linux x86_64, NVIDIA CUDA 12.4 | `model_services/requirements-sam.txt` |
| Water V5, 65-scene assessment | 3.9 | Windows AMD64, Linux x86_64, NVIDIA CUDA 12.4 | `evaluation/water_v5/requirements.txt`, `requirements-build.txt` in that directory |

## Core demo

Follow the [README installation](../README.md#installation), then run
`python examples/five_step_workflow.py` with that environment's interpreter.

## Evaluation and integrations

Create and activate a Python 3.10-3.12 environment. From the repository root:

```sh
python -m pip install -r requirements-build.txt
python -m pip install -r evaluation/requirements-report.txt -r evaluation/requirements-workflow.txt -r requirements-extras.txt
python -m pip install --no-build-isolation --no-deps .
python -m pip check
python examples/reproduce_paper_results.py
python -m unittest discover -s tests -p "test_*.py" -q
```

Each requirements entry point applies the shared
[complete constraints](../evaluation/locks/constraints-python310-312.txt).
For basic numerical evaluation alone, use `evaluation/requirements-evaluation.txt`.
The [lock guide](../evaluation/locks/README.md) explains the version branches and
contains the validation record.

## RemoteAgent and RemoteSAM

Follow [Local model setup](local_model_modules.md) to create separate Python 3.10
environments. Each model's complete requirements file selects the CUDA 12.4
PyTorch wheels and pins the Linux runtime packages when applicable. Install
`pip==26.0.1`, then apply `model_services/requirements-build-constraints.txt`
through pip's `--build-constraint` option. This fixes build tools for the
source-only architecture packages as well as the runtime dependencies.

The model guide supplies the fixed upstream architecture, checkpoint hashes,
service configuration and startup commands.

## Water V5

The [water V5 guide](../evaluation/water_v5/README.md) supplies the original
checkpoint, 65 source-scene hashes, complete dependencies and inference command.
The requirements retain the recorded PyTorch, NumPy, Pillow and architecture
versions. Four rotation predictions per tile and SAM boundary refinement remain
part of the procedure. Expected totals are TP 1,356,978, FP 35,782 and FN 256,701.

## Source and historical results

The dependency supplement includes a source archive containing
`dependency-closure-20261016` in its name. Its manifest identifies the exact
Git commit and file hashes. The [public reproduction release](https://github.com/pophip3/geomasklab/releases/tag/v1.0.0-repro.20261016)
provides the fixed manuscript source, original experiment records and V5 checkpoint.
Dependency updates preserve the inference implementation, checkpoint identities
and recorded measurements.

## Verification record

The evaluation and extension environment was installed from scratch on Windows
with Python 3.10.19 and 3.12.14. Both installations passed dependency consistency,
numerical, plotting and integration checks. The complete software suite passed
380 tests; one Windows symlink test was skipped because the account could not
create file symlinks.

The Agent, SAM and V5 locks were resolved for Windows and Linux and checked for
exact versions throughout each dependency graph. Those model environments were
not reinstalled completely during this check. The original 65-scene V5 inference
record remains separately available and matches every recorded scene count.

Machine-readable records: [evaluation](../evaluation/locks/validation.json),
[model services](../model_services/locks/validation.json), and
[water V5](../evaluation/water_v5/environment_validation.json).
