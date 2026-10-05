# English-language release standard

Recorded: 5 October 2026. Applies to the eventual SoftwareX submission and
the accompanying research software. This is a release requirement, not a
statement that the current development build has completed language review.

## Language and editorial quality

The user requires English throughout all submitted materials. Use consistent
American English, clear scientific prose, accurate terminology and natural
phrasing. Review meaning, grammar, spelling, punctuation and consistency;
literal translation alone is insufficient. Do not claim that a native-speaking
editor has reviewed the work unless that review actually took place.

The requirement covers:

- Manuscript, cover letter, highlights, captions, tables and supplementary text.
- Software interface, accessible labels, help text, confirmation and error messages.
- Code comments, docstrings and public API documentation.
- Console output, application logs, exception messages and service-status text.
- Generated reports, human-readable JSON/CSV values and example task descriptions.
- Text rendered in test images, overlays, screenshots and scientific figures.
- README, installation instructions, reviewer walkthrough and comparison protocol.

Use English example requests and verify them through the complete workflow.
Changing button labels without checking generated artifacts does not satisfy
this requirement. Keep technical identifiers consistent across the interface,
code, figures and manuscript. Preserve original observations and historical
evidence; prepare English explanations instead of silently altering source data.
Machine-specific paths and quoted source records must not be rewritten as if
they were translated observations. Compatibility input patterns are distinct
from generated messages and documentation.

## Publisher guidance checked

The following primary sources were checked on 5 October 2026:

1. [Elsevier artwork overview](https://www.elsevier.com/about/policies-and-standards/author/artwork-and-media-instructions/artwork-overview):
   recommends Arial/Helvetica, Courier, Symbol and Times/Times New Roman for artwork.
2. [Elsevier artwork types](https://www.elsevier.com/about/policies-and-standards/author/artwork-and-media-instructions/artwork-types):
   requires embedded fonts for vector artwork; raster line art needs at least
   1000 dpi, grayscale/color halftones at least 300 dpi, and combination art 500 dpi.
3. [Elsevier LaTeX instructions](https://www.elsevier.com/researcher/author/policies-and-guidelines/latex-instructions):
   supports `elsarticle` and directs authors to the journal's specific requirements.
4. [Research Elements journal page](https://www.elsevier.com/researcher/author/tools-and-resources/research-elements-journals):
   links to the SoftwareX guide and its Original Software Publication template.

Access to the dedicated SoftwareX guide returned HTTP 403. The linked Word
template was identified, but its download also returned HTTP 403; its current
font-size settings have not been inspected. General Elsevier recommendations
must not be described as an independently verified SoftwareX-specific mandate.

## Project typography decisions

Use Arial for figure labels and the English interface, with Helvetica and a
standard sans-serif fallback for the interface. Use a consistent monospace face
for code. These are project decisions, not claimed journal rules for software UI.
Do not redistribute proprietary font files without appropriate rights.

For the manuscript, retain the dedicated journal template's typography and
verify it before submission; do not impose a supposed universal Times New Roman
12-point requirement. Review figure text at its final publication size, embed
fonts in PDF/EPS figures and verify the effective raster resolution. Changing
the DPI tag or enlarging an old screenshot does not create additional detail.
Raw evaluation images remain at their original pixel dimensions.

## Release gates

1. Inventory and revise comments, docstrings, interface strings and generated text.
2. Run English examples, service-error cases, import/review/export and CLI paths.
3. Inspect generated JSON, CSV, logs, reports and screenshots for untranslated text.
4. Review all reader-facing English for meaning and idiomatic usage.
5. Verify fonts, vector embedding, image resolution and readability at final size.
6. Assemble the English submission package, then check the specific current
   SoftwareX template and author guide again.

The existing Chinese development interface and internal planning documents have
not passed these gates. Prior functional tests and interoperability measurements
do not establish completion of English-language or typography review.
