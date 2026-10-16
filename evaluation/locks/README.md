# Optional evaluation and extension environments

The shared constraints file fixes the complete dependency closure for the
evaluation scripts, report generation, Label Studio SDK 2.1.2 converter, and
the `schema`, `geo`, `interop`, and `signing` extras. It covers CPython
3.10-3.12 on Windows x86-64 and Linux x86-64. The Linux binary check targets
glibc 2.28 or newer. Other Python versions and architectures are outside this
lock's scope. Use a separate environment from the optional model services.

After creating and activating a clean environment with a supported Python,
run from the repository root:

```sh
python -m pip install -r requirements-build.txt
python -m pip install -r evaluation/requirements-report.txt -r evaluation/requirements-workflow.txt -r requirements-extras.txt
python -m pip install --no-build-isolation --no-deps .
python -m pip check
```

For only the basic evaluation scripts, install
`evaluation/requirements-evaluation.txt`. For only the software extras,
install `requirements-extras.txt`. Each entry point automatically applies the
same complete transitive constraints; it installs only the dependencies that
its selected features require.

The resolver selects NumPy 2.2.6 so that Python 3.10 and the SDK's OpenCV 4.12
requirement agree. Rasterio, pyproj, and a few other dependencies have explicit
Python-version branches. These are environment fixes; archived scientific
observations retain their originally recorded versions and results.

The full SDK metadata dependencies are installed and checked. The actual
workflow exercise uses its official brush converter; this does not certify
the Label Studio web application or its API client.

## Regenerating the lock

`pyproject.toml` in this directory contains the resolver inputs and exact
platform/Python scope. The lock was generated with uv 0.13.1:

```sh
uv --directory evaluation/locks pip compile pyproject.toml --universal --python-version 3.10 --only-binary :all: --no-annotate --no-header --output-file constraints-python310-312.txt
```

Regeneration can select newer transitive releases and is a maintenance step,
not part of reproduction. Reproduction installs the committed constraints.
Validation details and platform limits are recorded in `validation.json`.
