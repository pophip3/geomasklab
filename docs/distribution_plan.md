# GeoMaskLab distribution decision

Decision date: 5 October 2026.

GeoMaskLab will be distributed primarily as Python source with a local browser
interface. This is a research software application: the local backend executes
tasks, performs measurements and persists evidence; the browser provides its UI.
The interface does not require a separately hosted public website.

## Journal requirement versus project decision

The previously downloaded official SoftwareX Original Software Publication
LaTeX template, retained outside this repository under `audit/literature`,
requires public code/software sharing, a GitHub repository, a documented README,
a license file, and mandatory code metadata describing the version, source link,
license, languages/tools/services, environment/dependencies, documentation and
support contact. It does not prescribe a Windows `.exe` distribution.

The [current official author guide](https://www.sciencedirect.com/journal/softwarex/publish/guide-for-authors)
returned HTTP 403 during this check. The
[publisher's Research Elements page](https://www.elsevier.com/researcher/author/tools-and-resources/research-elements-journals)
links that guide and the SoftwareX template. Final requirements must be rechecked
before submission; an older template or another published repository is not
proof that every current upload requirement has been verified.

The published GeoRocket and Open Sensing projects provide concrete source/server
and browser-interface examples; see [the repository inspection](softwarex_repository_reference.md).
There is no identified basis for making `.exe` packaging a prerequisite for
GeoMaskLab development or submission preparation.

## Planned software release contents

1. A public, versioned GitHub source repository with an approved open-source license.
2. English purpose, installation, usage, troubleshooting and developer documentation.
3. Dependency declarations, supported operating systems, an empty credential
   configuration example and local startup instructions.
4. Small procedural examples, masks and executable reproduction scripts with
   explicit distinctions between demonstration data and real model results.
5. Offline evidence verification, import/review/region-analysis/export examples.
6. External-agent/segmentation service specifications, versions, parameters and
   model/weight acquisition instructions subject to their licenses.
7. Unit/integration checks and CI evidence tied to the released source version.
8. A source archive, release notes and permanent version link; citation information
   containing confirmed contributors only.

These are software release deliverables. The manuscript, metadata, figures,
cover letter and applicable declarations are separate submission materials.
This document does not claim to enumerate every current EM upload field.

## Optional convenience artifacts

A Windows launcher or `.exe` may be added after the source workflow passes
acceptance. If provided, test it on a clean Windows installation, retain the
matching source/version, and document its dependencies. Bundling the workbench
does not remove the need for external model endpoints or legally obtained
weights. A Docker image is another possible convenience, not an implemented
feature or a claimed journal mandate.

Current status: version 1.0 scope frozen as `1.0.0-rc.1`; standard MIT license installed; English generated-output acceptance implemented. Final fixed-release publication and creator/DOI metadata require their own recorded checks. Independent live-service installation acceptance remains pending and is not claimed.
