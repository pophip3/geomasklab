# Distribution layout and release reference

The supplied GeoRocket 1.3.0 CLI and server ZIPs were inspected as release-package
references. Their top-level `bin/`, `lib/`, `conf/` and `docs/` directories make
entry points, Java dependencies, connection configuration and offline documentation
easy to locate. The server package also includes an embedded Elasticsearch tree;
the CLI package contains a client configuration. Their HTML manual documents the
architecture, commands, HTTP routes, query language, configuration and errors.
These are runtime distributions, distinct from their source repository. See the
[GeoRocket website](https://georocket.io/) for its own downloads and documentation.
No third-party launch scripts, binaries, illustrations or interface code were
copied into GeoMaskLab.

GeoMaskLab applies these delivery principles to its smaller Python application:

| Location | Purpose |
| --- | --- |
| `pyproject.toml`, `src/geomasklab/` | Installable Pillow-only core and console command |
| `src/geomasklab/schemas/` | Packaged, versioned JSON Schemas for optional metadata validation |
| `release/check_wheel.py` | Installed-wheel acceptance outside the checkout |
| `bin/geomasklab.cmd`, `bin/geomasklab.sh` | Windows/POSIX entry points; prefer a root virtual environment and forward command-line arguments |
| `quickstart.py` | Local server entry point with port diagnostics |
| `requirements.txt`, `requirements-reviewer.txt` | Minimal dependency range and pinned reviewer environment |
| `.env.example`, `docs/model_services.md` | Placeholder-only configuration and service contracts; credentials/weights excluded |
| `workbench/web/help.html` | Complete local English user guide, independent of network assets |
| `docs/api.md`, `docs/architecture.md` | API and implementation documentation |
| `workbench/fixtures.py`, `reviewer_demo.py`, `examples/` | Procedural fixtures, exact checks and executable examples |
| `tests/`, `.github/workflows/` | Contract/HTTP checks and cross-platform CI |
| `LICENSE`, `Licence.txt`, `THIRD_PARTY_NOTICES.md` | MIT source license, origin and external dependency boundaries |
| `release/build_source.py`, `release/check_distribution.py` | Fixed-commit archive, file hashes and extracted-package acceptance |

The software is distributed as a headless Python wheel and a separate full source
archive. Both require Python and Pillow; the source includes browser assets and
examples. A Python runtime is installed separately. The lightweight offline workflow
and external live-model installation are documented separately. A versioned source
archive is produced from committed files only, with a `SOURCE-MANIFEST.json`
containing the exact Git commit and per-file checksums. Development archives are
not final releases or DOI deposits.
