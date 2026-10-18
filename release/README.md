# Release and archival preparation

This directory contains metadata preparation, source packaging and distribution
checks. The version `1.0.0` submission source is fixed at
[`v1.0.0-submission.20261018.1`](https://github.com/pophip3/geomasklab/tree/v1.0.0-submission.20261018.1)
and archived at [10.5281/zenodo.23447736](https://doi.org/10.5281/zenodo.23447736).
The following procedure applies to future releases.

1. Run the full and Pillow-only tests, the real NAIP comparison, installed-wheel
   checks and extracted-source checks at the exact release commit. Inspect the
   cross-platform workflow results, not only the status of an earlier commit.
2. Supply confirmed software creators, their order, optional affiliations/ORCIDs
   and the actual release date using `creator-metadata.template.json`. The
   generator rejects unconfirmed or placeholder metadata:

   ```sh
   python release/prepare_metadata.py confirmed-creators.json --version 1.0.0 --output staged-metadata
   ```

3. Validate the staged `CITATION.cff` with the official CFF schema and review
   `.zenodo.json`. Put reviewed files in the repository root. Software creators
   and manuscript authors may differ; attribution is not inferred from an account.
4. Set the new release version, rerun affected checks, commit and build the
   artifacts. Publish a new version tag and release with the source commit and
   SHA-256 checksums. Preserve existing version tags and published artifacts.
5. Connect the confirmed public repository to Zenodo or upload the exact version
   archive there. Inspect creators, licenses, third-party dataset terms, version,
   title and source URL before publishing the deposit. Store its actual version DOI
   in citation/archive metadata after the deposit is publicly available.

`prepare_metadata.py` generates `CITATION.cff` and `.zenodo.json` from the supplied
creator metadata. The root `CITATION.cff` records Yun Xing, Hohai University,
ORCID 0009-0009-1746-5019, and the published version DOI. The template is reusable
input for future releases; it does not replace the current citation metadata.

The compatible core format remains `geoscope-evidence/1.0`; this is a legacy
format identifier, not a competing software name. All new assessment/signature
formats use `geomasklab-*`. The wheel packages `workbench/` and its complete local assets alongside
`src/geomasklab/`. Both wheel and fixed source ZIP ship the same presentation.

References: [CFF specification](https://github.com/citation-file-format/citation-file-format),
[Zenodo metadata documentation](https://developers.zenodo.org/#deposit-metadata).
