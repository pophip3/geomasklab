# GeoMaskLab release validation

The current handoff candidate is **1.0.0rc4**, which combines the complete browser
presentation and CLI in the wheel and fixed source ZIP. Its exact artifact
hashes, technical acceptance and current-commit CI link are supplied on the
[rc4 release](https://github.com/pophip3/geomasklab/releases/tag/v1.0.0rc4).
Use [independent_handoff.md](independent_handoff.md) for the matching interface.
Independent human completion is still pending; no semantic-accuracy or DOI claim
is implied by automated acceptance.

## Historical rc3 baseline

The fixed **1.0.0rc3** source ZIP and wheel passed automated installation,
measurement and replay checks. These checks establish reproducible software
behavior; independent human handoff and semantic accuracy require separate evidence.

## Version and artifacts

Release: [v1.0.0rc3](https://github.com/pophip3/geomasklab/releases/tag/v1.0.0rc3).
Source commit: `ab7494726637b8b9f34229f41db88c5a900fc227`.

| Artifact | SHA-256 |
| --- | --- |
| `GeoMaskLab-1.0.0rc3-source.zip` | `f31df0f35696c22375112458d3bc8a13046140730ed52846c1a0e641fdc00f32` |
| `geomasklab-1.0.0rc3-py3-none-any.whl` | `655da08682a5beaa1d327abfe4a158093c7e86fcc686483eda21fc98f26d44c8` |

The wheel contains the headless core, CLI and schemas. The source ZIP contains
the browser workbench, static assets, examples and documentation. This ZIP is
a committed-source distribution, not a Python packaging `sdist`. The 227 source
files matched both the archive manifest and the tagged Git blobs. The parallel
presentation changes are outside these rc3 artifacts.

## Checks and their scope

The automated recheck on 2026-10-06 used an extracted copy of the source ZIP
and a separate Windows Python 3.13.9 virtual environment. The new environment
contained pip 25.2, Pillow 12.3.0 and GeoMaskLab 1.0.0rc3, without inherited
system packages. This is a fresh virtual environment on an existing host;
it is not a new operating-system installation or a human usability result.

| Check | Result | What it establishes |
| --- | --- | --- |
| Full source tests with optional dependencies | 272 run; 271 passed; 1 skipped; 0 failed | Arithmetic, source preservation, malformed-input rejection, domain rules, batch recovery and HTTP adapters |
| Source and wheel identity | SHA-256 matched release metadata; 227 source files matched the commit | These checks apply to the named fixed artifacts |
| Installed CLI replay outside the checkout | Five saved browser packets passed in the new environment | Conditions-only comparison, prediction-and-condition comparison, component inspection, resumed batch and reference assessment replay |
| Real Denver NAIP workflow | Passed, including optional nominal projected area | Explicit valid domains, pixel-set arithmetic, comparison accounting, candidate inspection, failure isolation and aggregation |
| Independent human handoff | Pending; zero observed participants | Automated replay does not establish usability without author assistance |

The skipped test is `test_symlink_escape_rejected_when_supported`: the current
Windows account could not create a native file symlink. This platform-dependent
test records a skip; it is not counted as a pass. See the CI results for other
environments and the broader path-validation tests for their distinct checks.

The [CI run for this commit](https://github.com/pophip3/geomasklab/actions/runs/37327185301)
completed nine jobs successfully: minimal installs on Windows, Linux and macOS,
plus full contracts on each platform with Python 3.10 and 3.13.

## Reproduce the checks

Run from the extracted source directory in the appropriate environment:

```sh
python -m pip install ".[schema,geo,interop,signing]" -r evaluation/requirements-evaluation.txt
python -m unittest discover -s tests -p "test_*.py" -q
python examples/five_step_workflow.py --geo
```

Install the published wheel in another environment. From outside the source
checkout, supply the exported packet paths:

```sh
geomasklab --version
geomasklab verify evidence.zip
geomasklab verify-comparison comparison.zip
geomasklab verify-components inspection.zip
geomasklab verify-batch batch.zip
geomasklab verify-assessment assessment.zip
```

The concrete commands, artifact identities and scope are also recorded in the
[machine-readable summary](../evaluation/releases/rc3-validation.json).

## Scientific interpretation

The synthetic 800 × 600 urban example has 75,350 foreground pixels out of
480,000 image pixels: **15.70% whole-image coverage**. It is a procedural software
demonstration, not a remote-sensing semantic accuracy result.

The real 512 × 512 Denver NAIP example is credited to USDA-FSA-APFO / USGS The
National Map. In the connected validity example, 105,232 foreground pixels
lie in 196,608 declared valid pixels: **53.52% valid-region coverage**. The
excess-green baseline, exclusions and controlled perturbations are protocol
fixtures, not independently validated vegetation labels or observed change.
The deliberately incomplete batch completes three samples and fails one;
one completed sample has undefined coverage. The macro mean is 50.872294%,
and the pixel-weighted coverage is 51.402588%; failure and empty domains are
reported separately.

An earlier recorded compatibility check replayed 180 bundles from 60 historical
images and made 120 derived region checks. Its predictions belong to commit
`46ffbbb1898a4b5e8f2ac5974f0bdabace3a94bd`. Those counts are retained as the
existing compatibility receipt; the 2026-10-06 recheck did not repeat that entire
historical run. No new model calls or human observations are claimed.

Integrity replay, self-reported review acceptance and semantic validation have
different meanings. Ordinary RGB inputs provide pixel coordinates and a pixel
scale. Geographic area requires the optional geospatial path and its declared
assumptions. No stable release or archival DOI is asserted here.
