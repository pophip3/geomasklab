# Fixed software version and DOI archive

An archive DOI remains pending. No DOI has been fabricated, reserved or published
for GeoMaskLab in this preparation. Creator names, individual attribution and
archive access must be verified before creating the final archival record.

## Ordered release procedure

1. Pass the source release checks, English reviewer examples and current CI.
   Record version, exact source commit, tests, dependencies and artifact checksums.
2. Confirm software creators and their verified names/ORCIDs/affiliations; distinguish
   software contributors from the manuscript author list. Update citation metadata.
3. Freeze the final tag. Publish its source archive and release notes, preserving
   an immutable commit link and checksum manifest. Do not overwrite an already
   cited release with different code; use a new version for changes.
4. Sign in to the intended archive account. For Zenodo, connect GitHub and enable
   this repository, following the [official integration instructions](https://help.zenodo.org/docs/github/enable-repository/).
   New releases are ingested automatically once the repository is connected.
   Do not assume existing releases have already been archived.
5. Inspect the resulting deposit: title, version, resource type Software, creators,
   MIT license, source files, README, examples, citation and model/data boundaries.
   Use the actual version DOI when citing the evaluated release; describe a concept
   DOI separately if one is supplied by the archive.
6. Verify public download and DOI resolution, compare the archive contents/checksum
   against the intended source version and run the reviewer workflow from it.
7. Insert the verified DOI into citation metadata, README, documentation and
   manuscript code/data availability fields. Do not insert the article's eventual
   DOI as the software archive DOI.

Zenodo [registers DOIs when uploads are published](https://help.zenodo.org/docs/deposit/describe-records/reserve-doi/).
A draft DOI can be reserved in advance, but a reserved draft is not evidence of
a published, downloadable archive. Record that distinction explicitly.

## Metadata prepared now

The software title, purpose, languages, version, license, source repository,
documentation URL, keywords and distribution boundaries are known. The
`release/metadata-draft.json` file records these and explicitly leaves unverified
creator/contact/DOI fields empty. It is a preparation record, not a valid
`.zenodo.json` upload or confirmed citation author list.

The user requires a DOI before submission. Actual account authorization and
creator metadata are unavailable during this preparation; continue software and
paper-material work without pretending this gate has passed.
