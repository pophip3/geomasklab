# Published SoftwareX repository reference

Inspected on 5 October 2026. This is an observation of published software
repositories, not a replacement for the current journal author guide.

## Primary example: GeoRocket

[GeoRocket: A scalable and cloud-based data store for big geospatial files](https://doi.org/10.1016/j.softx.2020.100409)
is an Original Software Publication in SoftwareX 11 (2020), article 100409.
Its publisher-linked [repository](https://github.com/ElsevierSoftwareX/SOFTX_2018_173)
contains server, client and shared-code modules, `docs`, `scripts`, README,
Apache-2.0 LICENSE, CHANGELOG, Gradle build files, platform launch wrappers and
a Dockerfile. The README explains building and running a server and CLI.

The recursive GitHub tree was inspected at commit
`af1f82efaf01a85d8a81abc70422989ed8a8830f`. Both actual tests and test resources
are present, including GeoJSON fixtures. The
[CI workflow](https://github.com/ElsevierSoftwareX/SOFTX_2018_173/blob/af1f82efaf01a85d8a81abc70422989ed8a8830f/.github/workflows/gradle.yml)
invokes Gradle checks, builds a Docker image and runs server integration tests.
The [GeoJsonSplitter test](https://github.com/ElsevierSoftwareX/SOFTX_2018_173/blob/af1f82efaf01a85d8a81abc70422989ed8a8830f/georocket-server/src/test/java/io/georocket/input/geojson/GeoJsonSplitterTest.java)
loads fixtures and asserts parsed content and chunk metadata.

These are source observations. GeoRocket was not installed or benchmarked here,
and its current fork head must not be assumed to be the immutable 2020 paper
version without checking the publication tag.

## Additional browser-interface example: Open Sensing

[Open sensing: An interactive online tool for environmental data collection, monitoring, analysis, and modelling for custom environmental sensor devices](https://doi.org/10.1016/j.softx.2025.102439)
describes an online tool. Its publisher-indexed code metadata links the
[frontend source repository](https://github.com/scalable-design-participation-lab/open-sensing-frontend).
The repository uses Nuxt/Vue and provides API routes, `package.json`, dependency
lock files, `.env.example`, browser assets, a README and a BSD-2-Clause license.
It documents dependency installation, environment setup and development commands.
The tree inspected at `e60087eb7a0cd2e1a705dda60dfba50411051940` includes
`vitest.config.mjs`; the existence of a configuration file does not establish
test coverage or passing tests. No application execution was performed.

The live publisher page returned an access error; the indexed publisher record
was available. The inspected current branch may have changed since publication.
This example supports browser-based distribution as an established form of
research software; it does not define journal requirements for every submission.

## Additional maintenance example: Numba-MPI

[Numba-MPI v1.0](https://doi.org/10.1016/j.softx.2024.101897), SoftwareX 28
(2024), article 101897, links a publisher archive at
[SOFTX-D-24-00357](https://github.com/ElsevierSoftwareX/SOFTX-D-24-00357).
The complete nine-page author-hosted paper was inspected, together with the
[upstream repository](https://github.com/numba-mpi/numba-mpi) at
`1542d7410ae16daf5083e9ad10afc1d710d857db`.

Its source includes focused API modules, API and paper-listing tests, GPL-3.0
licensing, a README, `CITATION.cff`, `.zenodo.json`, a code of conduct and
`pyproject.toml`. The inspected workflow checks lint/formatting and generated
documentation, builds and installs distribution artifacts, and executes README
examples as well as a Python/platform/MPI test matrix. Those are observed
workflow instructions, not test results reproduced here. The current upstream
commit is not automatically the immutable version 1.0 paper artifact.

Useful practices are exact version identity, runnable documentation, tests of
distributed source and accurate citation metadata. MPI dependencies, its license
and its author list are specific to that project and are not copied.

## Mapping to GeoMaskLab

| Repository component | GeoMaskLab status / action |
| --- | --- |
| Purpose and scientific use | Defined in `software_scope.md`; clarify these tasks at the beginning of the final README. |
| Source modules | Present for planning, transport, geometry, evidence, review and offline analysis; improve the remaining large server/UI modules during release preparation. |
| License | Standard MIT text is installed in both `LICENSE` and `Licence.txt`; third-party model/data conditions are separate. |
| Installation and dependencies | English installation instructions, `requirements.txt`, pinned reviewer dependencies, `quickstart.py` and an empty credential example are provided. Independent live-service installation remains unclaimed. |
| Small examples | `fixtures.py`, `reviewer_demo.py` and example scripts exist. Generated images are explicitly synthetic. |
| Automated checks | Unit/integration tests, a geometry matrix and six OS/Python CI jobs exist; a new code version needs its own CI result. |
| Build/release artifact | Source distribution is primary; the functional scope is frozen as `1.0.0-rc.1`. Distributed-source checks and fixed-version publication are recorded separately. |
| Executable / container | Optional convenience; neither replaces source, dependency documentation or model configuration. No `.exe` or Docker release is claimed at present. |
| Stable citation | A public, fixed version and accurate contributor citation remain pending; do not invent author metadata. |

Follow the documented practices that make the software usable and inspectable.
Do not copy another project's license, author information, dependency stack,
historical CI versions or source code without a justified need and compatible rights.
