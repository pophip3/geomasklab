# Literature review and prior-publication search

Checked 2026-10-04. This is a focused evidence log, not a systematic review.
Depth labels distinguish read methods/results from abstract or project-documentation
checks. Failed full-text downloads are not counted as complete readings. Source
papers remain in a separate local reading directory and are not redistributed here.

## Software publication and closely related systems

| Source | Reading depth | What constrains this paper |
|---|---|---|
| [SoftwareX OSP template](https://legacyfileshare.elsevier.com/promis_misc/softwarex-osp-template.tex), downloaded official source | Full template | Five main sections, code metadata, public GitHub code, README and Licence.txt. Its current text specifies 4000 words and at most six figures. A private repository with pending licensing is not submission-ready. |
| [Elsevier LaTeX instructions](https://www.elsevier.com/researcher/author/policies-and-guidelines/latex-instructions) | Official instructions | Prepare editable sources and complete source files; use the target journal requirements to choose the article structure. The generic elsarticle class is not itself a SoftwareX research strategy. |
| Wu and Osco, [SamGeo](https://doi.org/10.21105/joss.05663), JOSS 8(89), 5663 (2023) | Complete two-page paper; current official documentation | Segmentation interfaces already include automatic, interactive and text-prompt methods, with raster/vector outputs. GeoScope cannot claim text segmentation or a GUI as novel. Current documentation has evolved beyond the 2023 paper; distinguish publication capabilities from today's implementation. |
| Wu, [Leafmap](https://doi.org/10.21105/joss.03414), JOSS 6(63), 3414 (2021) | Paper's need statement, architecture and backend discussion | Minimal-code geospatial analysis and interactive tools precede GeoScope. The workbench needs a more specific contribution around experiments and checkable numerical processing. |
| Wu, [geemap](https://doi.org/10.21105/joss.02305), JOSS 5(51), 2305 (2020) | Journal metadata and abstract/project context | Interactive Earth Engine mapping is established. Do not portray this RGB workbench as a replacement for a full geospatial analysis platform. |
| Michels et al., [CyberGIS-Compute](https://doi.org/10.1016/j.softx.2024.101691), SoftwareX 26, 101691 (2024) | Publisher abstract and authors' architecture documentation | Integration middleware can be a SoftwareX contribution. The scientific use and accessible interfaces matter; an integration paper still needs runnable software and evidence. Full publisher text was intermittently inaccessible. |
| Liu et al., [Geospatial Analytics Extension for KNIME](https://doi.org/10.1016/j.softx.2023.101627), SoftwareX 25, 101627 (2024) | Publisher/indexed manuscript excerpts and official repository | Visual programming plus GIS is a relevant publication precedent. GeoScope has a smaller task scope; cannot claim equivalent spatial functionality. Full NSF PDF download failed, so no complete reading is claimed. |
| Krämer, [GeoRocket](https://doi.org/10.1016/j.softx.2020.100409), SoftwareX 11, 100409 (2020) | Full six-page author-hosted PDF, especially architecture, example and impact | The software paper supplies a licensed, concrete use case and exact deployment description. It illustrates how reproducible application detail can substantiate impact beyond listing features. GeoScope needs a real EO case in addition to synthetic checks. |
| [AutoImageSeg](https://doi.org/10.1016/j.softx.2025.102491) | Author-maintained repository/README and publisher abstract; full text unavailable | A zero-code train/infer/evaluate/annotation loop already exists. GeoScope's bounded remote-service workflow differs, but broad “closed-loop segmentation platform” novelty would overlap. Verify final journal year and author details before adding this reference to the manuscript. |

## External methods and evidence integrity

| Source | Reading depth | Consequence |
|---|---|---|
| Yao et al., [RemoteSAM](https://arxiv.org/abs/2505.18022), arXiv:2505.18022 (2025) | HTML methods, dataset construction and evaluation sections; current metadata | Referring segmentation, task unification and RemoteSAM-270K belong to the original model authors. Its data integration includes iSAID; using iSAID for a workbench test does not prove the foundation model never saw related data. The model includes absent-target examples, reinforcing the need for negative test images. |
| Yao et al., [RemoteAgent](https://arxiv.org/abs/2604.07765), arXiv:2604.07765 (2026) | HTML task formulation, RL training, tool inference and evaluation; current metadata | Intrinsic/extrinsic task separation and VagueEO are prior work. GeoScope's potential contribution is enforceable runtime context and inspectable artifacts, not that general agent principle. The workbench's restricted HTTP protocol must not be described as implementing the paper's entire MCP toolkit. |
| Padovani, Anantharaj and Fiore, [yProv4ML](https://doi.org/10.1016/j.softx.2025.102298), SoftwareX 31, 102298 (2025) | Full author arXiv HTML including functions, example and impact | Tracks artifacts, parameters and metrics using PROV-JSON. Existing provenance logging makes a simple run log insufficient novelty. The relevant difference to establish is reconstructable pixel operations in an interactive segmentation export. Do not claim GeoScope implements PROV compliance. |
| Barker et al., [FAIR4RS](https://doi.org/10.1038/s41597-022-01710-x), Scientific Data 9, 622 (2022) | Publication metadata, available summary and authors' alliance guidance; full publisher access failed | Identifiable versions, metadata and reuse conditions belong in the release plan. A FAIR claim requires evidence and an assessment, not just GitHub hosting. |
| [W3C PROV-Overview](https://www.w3.org/TR/prov-overview/) (2013) | Official introduction and document roadmap | Provenance describes entities, activities and people and supports interchange. The GeoScope manifest currently establishes internal identity and consistency, without a standard provenance serialization. |
| [RO-Crate 1.1 specification](https://www.researchobject.org/ro-crate/specification/1.1/) | Version/status and metadata overview | Useful future packaging reference; the checked site also advertises newer releases. No RO-Crate-compliance claim is made for this custom ZIP schema. |

## GeoScope name disambiguation and article type

| Record | Reading depth | Decision |
|---|---|---|
| Zhang et al., [GeoScope: Full 3D geospatial information system case study](https://doi.org/10.1007/s11806-011-0478-z), Geo-spatial Information Science 14(2), 150–156 (2011; online 2012) | Publisher title, authors and abstract | Full 3D GIS, different authors/system and different journal. It is not evidence of an earlier SoftwareX article for this repository. |
| Albrecht et al., [PAIRS (RE)LOADED](https://doi.org/10.5194/isprs-archives-XLII-3-W12-2020-255-2020), ISPRS Archives (2020) | Full six-page conference paper, architecture and benchmarks | IBM PAIRS Geoscope is a large-scale spatiotemporal data platform. It is a homonym, not this RGB segmentation workbench. |

Search queries included `"GeoScope" "SoftwareX"`, `"GeoScope" "Sitian"`,
`"GeoScope" "RemoteAgent"`, `"GeoScope" "RemoteSAM"`, and a SoftwareX-site
restriction. No matching SoftwareX article for the private competition project was
identified in accessible results. This is a search finding, not proof of global
absence. Author identities beyond the account name and a complete publication list
were unavailable; that limits author-based disambiguation.

Draft as an **Original Software Publication** provisionally. If the authors have
already published the same software in SoftwareX, use the official update template.
The name alone does not determine article type. Avoid “first-ever GeoScope” and use
the qualified name **GeoScope Workbench**.

## Synthesis

The strongest direction is an inspectable, versioned workflow connecting external
segmentation to deterministic pixel measurements, with portable reconstruction.
The literature narrows the novelty claim and makes clear that interface design,
text prompting, tool dispatch and provenance logging individually have substantial
prior art. Demonstrate the complete combination with a specific scientific case,
licensed release and independent application validation. A broad “new AI model for
remote sensing” framing is unsupported by this code and evidence.
