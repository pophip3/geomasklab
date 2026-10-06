# Release and archival preparation

The current software is a release candidate, `1.0.0rc4`. Automated software
checks and real-data arithmetic are distinct from confirmed creator attribution
and observed human-study results.

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
4. Set the stable source version, rerun affected checks, commit, build exact
   artifacts and publish the `v1.0.0` tag/release. Record SHA-256 and source commit.
   Never reuse a stable tag for changed contents.
5. Connect the confirmed public repository to Zenodo or upload the exact version
   archive there. Inspect creators, licenses, third-party dataset terms, version,
   title and source URL before publishing the deposit. Store its actual version DOI
   in citation/archive metadata. A fabricated DOI or an unpublished local template
   is not an archive.

`prepare_metadata.py` writes both complete files from real confirmed facts;
the root CITATION.cff now records the author-confirmed Yun Xing, Hohai University
and ORCID 0009-0009-1746-5019. A stable tag and archival DOI remain pending.
The creator template remains an input example, not an observed human result.

The compatible core format remains `geoscope-evidence/1.0`; this is a legacy
format identifier, not a competing software name. All new assessment/signature
formats use `geomasklab-*`. The wheel packages `workbench/` and its complete local assets alongside
`src/geomasklab/`. Both wheel and fixed source ZIP ship the same presentation.

References: [CFF specification](https://github.com/citation-file-format/citation-file-format),
[Zenodo metadata documentation](https://developers.zenodo.org/#deposit-metadata).
