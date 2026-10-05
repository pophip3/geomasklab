# Fair comparison and difference explanation

GeoMaskLab compares two verified result bundles on an explicitly chosen pixel domain. It reports prediction changes separately from changes in the selected region and declared validity. Both exact source bundles travel with the exported comparison, so a recipient can replay the result offline.

## Run a comparison

Install the core package, then compare two saved results:

```console
python -m pip install .
geomasklab compare baseline.zip alternate.zip --domain-policy intersection --output comparison.zip
geomasklab verify-comparison comparison.zip
```

The workbench offers the same two domain policies in **Compare versions**. Its backend calls the installed core implementation. A comparison uses saved masks and does not invoke a model.

| Policy | Comparison domain | Admission rule |
| --- | --- | --- |
| `intersection` | `C = S_A ∩ V_A ∩ S_B ∩ V_B` | Both results must use the same exact input image, target and complement setting. |
| `identical` | The shared effective domain | The realized selected valid pixels must additionally match exactly. |

`S` denotes the selected geometric region and `V` denotes explicitly included pixels. Equal effective domains can result from different validity masks outside the selected region. Such results satisfy `identical`, while the report still records the differing conditions.

Different exact input-image hashes, semantic targets or complement settings are rejected. Identical dimensions alone do not establish alignment. GeoMaskLab performs no image registration, resampling or coordinate transformation during this comparison.

## Interpret the differences

The direction is **A → B**. Every common-domain pixel belongs to one of four foreground/background categories; pixels outside that domain form a fifth category.

| Value in `difference-classes.png` | Meaning | Overlay color |
| --- | --- | --- |
| `0` | Outside the common valid domain | Original image |
| `1` | Common background | Original image |
| `2` | Common foreground | Mint green |
| `3` | Removed foreground: A foreground, B background | Blue |
| `4` | Added foreground: A background, B foreground | Amber |

`difference-classes.png` is an L-mode categorical PNG. Its values are class codes rather than binary mask values. `difference.png` is an RGB illustration of the same categories over the source image.

The record classifies realized changes as:

| `change_kind` | Interpretation |
| --- | --- |
| `Identical_Realized_Analysis` | Prediction pixels, geometric region and validity pixels match. |
| `Analysis_Conditions_Only` | Source prediction pixels match; region or validity pixels differ. |
| `Prediction_Only` | Source prediction pixels differ; realized region and validity pixels match. |
| `Prediction_And_Analysis_Conditions` | Both source prediction pixels and analysis conditions differ. |

Equality uses decoded binary pixels. Different upload encodings or source descriptions can therefore represent equal prediction pixels. A whole-image rectangle and a whole-image scope can represent the same realized geometric region. Source metadata and original task declarations remain available in the embedded evidence.

Changes outside the common domain do not appear in its pixel difference. `full_prediction_pixels_equal` records whether the complete source predictions match, while `changed_pixels` counts changes only in the common valid domain. Both fields are necessary to interpret a comparison correctly.

## Account for changes in saved totals

Let `F_A` and `F_B` be each saved result's foreground pixels after its own region and validity clipping. The record checks this set identity:

```text
saved_total_delta = common_domain_delta + excluded_domain_delta

saved_total_delta    = |F_B| − |F_A|
common_domain_delta  = added_in_C − removed_in_C
excluded_domain_delta = |F_B outside C| − |F_A outside C|
```

The source summaries report each saved numerator, geometric region, valid region, valid-region coverage and foreground excluded from comparison. This prevents a cropped result from being compared directly with a whole-image total as though both used the same denominator.

The identity is arithmetic accounting rather than causal attribution. When predictions and conditions both change, foreground outside the shared domain depends on both inputs; the software does not assign that difference exclusively to cropping or to the model.

For example, the shipped NAIP workflow deliberately changes 1,024 pixels inside a 25,600-pixel ROI: 944 removed and 80 added. Its saved-total foreground difference is −87,205 pixels, comprising −864 in the common domain and −86,341 outside it. The much larger saved-total difference reflects the different analysis domains as well as the controlled prediction changes.

## Empty domains and undefined agreement

An empty common domain produces `No_Common_Valid_Domain`, `pixel_diff_available: false`, null agreement scores and no difference images. The workbench shows the pixel comparison as unavailable. Retained zero count fields describe the empty set; they do not establish agreement or an absence of changes elsewhere.

A nonempty domain with no foreground in either mask has undefined IoU and Dice, represented by JSON `null`. A normal comparison reports:

```text
IoU  = shared / (shared + removed + added)
Dice = 2 × shared / (foreground_A_in_C + foreground_B_in_C)
```

These are mask-agreement scores. Semantic accuracy requires suitable independent reference labels and a separate evaluation design.

## Replay the exported packet

`comparison.zip` contains:

- `source-a.zip` and `source-b.zip`: both exact verified evidence sources;
- `comparison.json`: versioned conditions, identities, counts, agreement and accounting;
- `report.html`: a self-contained English report;
- `difference.png` and `difference-classes.png`: included together when the common domain is nonempty;
- `manifest.json`: exact member sizes and SHA-256 digests.

The comparison record uses `geomasklab-result-comparison/2.0`; the packet manifest uses `geomasklab-comparison-packet/1.0`. Packaged Draft 2020-12 schemas describe their typed fields and availability rules. The core verifier checks exact bounded membership, replays both source bundles, recomputes every measurement and compares decoded difference pixels. Updating hashes after changing a number, region, class image or report does not bypass replay.

The recorded comparison operation version is separate from each source's software version. A newer verifier retains the recorded operation version while checking the versioned calculation.

Internal consistency does not authenticate the person, model or image source. A completely reconstructed, internally consistent unsigned packet can pass. For an authenticity workflow, sign the exact packet and distribute its trusted public key separately using the existing signing commands.

## Complete real-image example

```console
python examples/five_step_workflow.py --output five-step-output
geomasklab verify-comparison five-step-output/comparison.zip
geomasklab verify-components five-step-output/components.zip
geomasklab verify-batch five-step-output/batch.zip
```

The example uses credited 2019 NAIP imagery, a packaged color-baseline mask, an explicit demonstration exclusion and declared XOR perturbations. Independent pixel-index sets check the measurements and accounting. The reference is deliberately identified as non-independent. This example validates workflow behavior and replay; human handoff validation and semantic accuracy assessment remain separate tasks.
