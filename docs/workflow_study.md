# Existing-tool interoperability and workflow evidence

GeoMaskLab lets a recipient reconstruct a saved segmentation measurement from
its image, target, mask, scope and review state without rebuilding the model
environment. The following checks test artifact exchange and offline region
analysis.

## SDK round-trip checks

`examples/compare_handoff.py` executes the official Label Studio SDK 2.1.2 brush
converter, not a reimplementation. For five procedural examples it compares:

1. Binary PNG → official brush RLE → decoded pixels.
2. A verified GeoMaskLab bundle → brush prediction → decoded pixels.
3. GeoMaskLab evidence import → session reload → re-export, preserving image,
   full-mask, selected-mask and recorded-statistics bytes.

All five examples passed these component-level round trips. Four controlled
metadata inconsistencies (whole-image denominator, ROI intent, review/mask
binding and candidate count) were rejected after checksums were regenerated.
See [the numerical record](../evaluation/workflow/summary.json).

The adapter exports **predictions**, preserving image dimensions and local image
assets with an English labeling configuration. Confidence scores are omitted;
annotation acceptance is a separate review step. This test covers the SDK brush
converter, not the full Label Studio GUI. QGIS and SAMGeo provide context through
their official papers and documentation. Timings measure different operations
and are reported separately rather than ranked.

## Offline region investigation

`examples/recalculate_region.py` imports a verified bundle, forbids model calls,
derives whole/left/right/rectangle results, and compares masks against direct
Pillow crops. Source image/full-mask bytes and semantic target/complement are
preserved. Both coverage denominators are checked; each derived result starts
pending review. [The numerical record](../evaluation/workflow/region_analysis.json)
is separate from model accuracy.

For ROI `[80,50,280,250]`, the procedural building mask has 12,850 foreground
pixels, 40,000 selected-region pixels and 480,000 whole-image pixels. Whole-image
coverage is 2.6771%; within-region coverage is 32.125%. The explicit denominator
prevents those different questions from being silently conflated.

## Interpretation

These checks establish artifact/mask round trips, independent pixel replay,
rejection of the selected inconsistent records and saved-mask region analysis.
They evaluate component interoperability and numerical preservation. Human
completion times and usability require the separate
[handoff-study protocol](handoff_study.md).
