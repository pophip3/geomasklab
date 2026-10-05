# SoftwareX preparation and submission sequence

Checked 5 October 2026. No Editorial Manager submission, author declaration,
payment, article acceptance or archive DOI is claimed by this preparation.
Each requirement is distinguished from a project decision and an unverified
journal-specific detail. Follow the current journal guide and system fields
before the final submission action.

## Primary guidance and access limits

- [SoftwareX Guide for Authors](https://www.sciencedirect.com/journal/softwarex/publish/guide-for-authors):
  direct automated access returned HTTP 403. Its current full requirements could
  not be certified. Do not replace it with an unverified third-party summary.
- [Elsevier Research Elements](https://www.elsevier.com/researcher/author/tools-and-resources/research-elements-journals):
  provides the journal/template links. The downloaded official SoftwareX OSP
  LaTeX template specifies five main sections, code metadata, public GitHub code,
  README and `Licence.txt`, with a 4,000-word/six-figure limit in that downloaded
  version. Current-guide confirmation is still necessary; conflicting secondary
  limits must not be promoted as official current rules.
- [Elsevier LaTeX instructions](https://www.elsevier.com/researcher/author/policies-and-guidelines/latex-instructions):
  supports `elsarticle`, journal-specific bibliography styles and editable source
  submission. EM source files must be at one folder level; source ZIP contents
  must include bibliography and required classes/styles/figures. Do not submit
  LaTeX source under supplementary-material item types.
- [Elsevier artwork guidance](https://www.elsevier.com/about/policies-and-standards/author/artwork-and-media-instructions/artwork-types):
  vector fonts should be embedded; raster line art 1,000 dpi, halftones 300 dpi,
  and combination artwork 500 dpi. Evaluate readability at final size rather
  than changing DPI metadata without real image detail.

## 1. Complete and freeze the software

Prepare the public source repository with standard MIT `LICENSE` and matching
`Licence.txt`, source attribution, README, dependency/setup guidance, English UI,
English comments/output, small procedural dataset generator, runnable example
scripts, API/architecture docs, behavioral tests, CI and change log. Keep model
weights, credentials, private infrastructure and restricted raw datasets out of
the release. Preserve the original competition repository.

Retain test logs, exact commit/version, environment details, generated example
outputs and observed website/browser acceptance evidence. Freeze a candidate
version and verify its archived source can run independently. A browser-based
local workbench is the selected distribution; no `.exe` requirement was found
in the inspected official template. An executable is optional convenience,
not a substitute for source and model dependencies.

## 2. Publish the fixed version and software archive

Confirm actual creator names/identifiers for software attribution. Freeze the
tagged release and source checksum; create citation/Zenodo metadata from those
verified facts. Enable the actual repository in the authenticated Zenodo GitHub
integration, then archive the fixed release. Verify archive contents, version,
license, creators and DOI resolution before inserting a DOI badge or paper link.
See [the archive plan](archive_plan.md).

The user requires an archive DOI as a project submission gate. The currently
inaccessible journal guide has not independently established that every
SoftwareX submission must obtain a Zenodo/Figshare DOI. A GitHub branch URL is
mutable; record the exact source commit and release even when a DOI exists.

## 3. Complete the article using the dedicated template

Use the OSP structure: Motivation and significance; Software description
(architecture/functions); Illustrative examples; Impact; Conclusions. Explain
scientific use, input/output, dependencies, constraints and reproducible steps.
Separate procedural integrity tests, component interoperability and the limited
prior-version real-image study. Attribute RemoteAgent/RemoteSAM methods and
preserve missed-target/false-positive results. Do not invent uniqueness, user
adoption, geographic area, model accuracy or time savings.

Complete code metadata C1–C8: version; permanent code link; legal license;
version control; languages/tools/services; environments/dependencies; developer
documentation; verified support contact. Confirm the actual article type and
absence of an earlier SoftwareX publication for this same software, independently
of naming homonyms. An Original Software Publication is provisional.

## 4. Prepare all submission files and metadata

| Item | Preparation / verification |
| --- | --- |
| Main manuscript PDF | Complete English text, tables, figures and numbered references; compile without errors and inspect every page |
| Editable LaTeX source ZIP | Flat folder with `.tex`, bibliography/`.bbl`, required `.bst`/`.cls`/`.sty`, figures and any necessary sources; no credentials or runtime data |
| Title/author metadata | Verified full names, order, affiliations, corresponding author/contact and ORCIDs where applicable |
| Separate title page / anonymous manuscript | Prepare only if the current journal review model requires it; do not assume double-anonymized review |
| Cover letter | One concise page describing software, scope, contribution and fit; originality/all-author approval declarations require actual confirmation |
| Highlights | Prepare a concise English draft; verify exact count/character limits and whether required in current guide/EM |
| Graphical abstract | Prepare an original vector workflow graphic if required/appropriate; verify current guide, dimensions and allowed types |
| Figures/tables | English labels/captions, numbering, permissions, sufficient genuine resolution and embedded vector fonts |
| Supplementary material | Reproduction instructions, evidence-method supplement, numerical tables and licensed assets only; accurately label procedural versus real data |
| Code/data availability statement | Actual fixed source/archive links, license, raw-data access restrictions and model dependency requirements |
| CRediT contributions | Assign actual human author roles after confirmation; do not infer roles from a GitHub username |
| Funding | Exact funder/grant identifiers or verified no-funding statement |
| Competing interests | Actual declaration from the authors; no automatic no-conflict assertion |
| Ethics/consent/permissions | State applicable approvals and permissions accurately; verify image/data rights; do not invent approval numbers |
| AI-assistance disclosure | Follow current Elsevier policy and describe actual assistance; humans verify results and take responsibility; AI is not an author |
| Other EM fields | Complete any required keywords, article classification, suggested/excluded reviewers and declarations shown by the actual system; do not infer universal requirements |

## 5. Final preflight and submission

Verify the current guide/template and actual EM required-file list, article type,
word/figure limits, language, author metadata, all declarations, archive DOI and
public access in a signed-out browser. Check references against primary sources,
numbers against committed evidence, figures at publication size and source
compilation in the supported EM environment. All authors must approve the actual
final manuscript and submission. Submission itself requires the author's final
action/authorization; this preparation does not send it.

## 6. After submission and acceptance

Record manuscript ID/status. Address reviewer comments point by point with exact
changes and new validation when needed; keep release/paper versions consistent.
After acceptance, the authors handle the publishing agreement, actual open-access
license/APC/funder obligations, proofs and corrections. No payment or agreement
is preapproved here. Review proof figures, authors, references, links and archive
version carefully before publication.
