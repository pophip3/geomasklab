# Distribution layout and release reference

GeoMaskLab separates its reusable analysis core, local browser workbench,
optional model adapters and release tools. Entry points, dependencies and
offline documentation are organized as follows:

| Location | Purpose |
| --- | --- |
| `pyproject.toml`, `src/geomasklab/` | Installable Pillow-only core and console command |
| `src/geomasklab/schemas/` | Packaged, versioned JSON Schemas for optional metadata validation |
| `release/check_wheel.py` | Installed-wheel acceptance outside the checkout |
| `bin/geomasklab.cmd`, `bin/geomasklab.sh` | Windows/POSIX entry points; prefer a root virtual environment and forward command-line arguments |
| `quickstart.py` | Local server entry point with port diagnostics |
| `requirements.txt`, `requirements-reviewer.txt` | Pinned core and reviewer dependencies |
| `.env.example`, `docs/model_services.md` | Placeholder-only configuration and service contracts; credentials/weights excluded |
| `workbench/web/help.html` | Complete local English user guide, independent of network assets |
| `docs/api.md`, `docs/architecture.md` | API and implementation documentation |
| `workbench/fixtures.py`, `reviewer_demo.py`, `examples/` | Procedural fixtures, exact checks and executable examples |
| `tests/`, `.github/workflows/` | Contract/HTTP checks and cross-platform CI |
| `LICENSE`, `Licence.txt`, `THIRD_PARTY_NOTICES.md` | MIT source license, origin and external dependency boundaries |
| `release/build_source.py`, `release/check_distribution.py` | Fixed-commit archive, file hashes and extracted-package acceptance |

The wheel contains the core, workbench modules and browser assets; run
`geomasklab-ui` after installation. A source checkout also supplies executable
examples and handoff materials; `python quickstart.py` opens the same interface.
Both require a separately installed Python runtime and Pillow. The lightweight
offline workflow and external model installation have separate setup instructions.

`release/build_source.py` builds an archive from committed files and adds
`SOURCE-MANIFEST.json` with the exact Git commit and per-file checksums. The fixed
SoftwareX submission archive instead carries `SOURCE_SNAPSHOT.json`; its version
and published DOI are listed in [submission identities](submission_20261018.md).

The distinction between runtime and source distributions follows common release
practice; [GeoRocket](https://georocket.io/) was a packaging reference.
