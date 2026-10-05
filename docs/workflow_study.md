# Existing-tool interoperability and workflow evidence

The practical question is whether a recipient can reconstruct a saved
segmentation measurement without rebuilding the model environment, while
retaining the image, target, mask, scope and review state. GeoMaskLab addresses
this handoff; it does not introduce text-guided segmentation or replace GIS and
annotation applications.

## Actual comparison performed

`examples/compare_handoff.py` executes the official Label Studio SDK 2.1.2 brush
converter, not a reimplementation. For five procedural examples it compares:

1. Binary PNG → official brush RLE → decoded pixels.
2. A verified GeoMaskLab bundle → brush prediction → decoded pixels.
3. GeoMaskLab evidence import → session reload → re-export, preserving image,
   full-mask, selected-mask and recorded-statistics bytes.

All five examples passed these component-level round trips. Four controlled
metadata inconsistencies (whole-image denominator, ROI intent, review/mask
binding and candidate count) were rejected after checksums were regenerated.
This demonstrates additional application-specific verification, not a defect in
the SDK or superior segmentation. See [the numerical record](../evaluation/workflow/summary.json).

The adapter creates **predictions**, with no accepted manual annotation, ground
truth designation or invented confidence. It preserves image dimensions and
exports local image assets plus an English labeling configuration. The full
Label Studio GUI was not installed or benchmarked. QGIS and SAMGeo were examined
through their official papers/documentation; their complete applications were
not benchmarked here. Observed timings compare different work and therefore are
not a speed ranking or user-efficiency study.

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

## Claims supported and still unmeasured

| Supported by executed checks | Not established |
| --- | --- |
| Exact artifact/mask round trips | Superiority over a complete competing application |
| Independent pixel-operation replay | Higher segmentation accuracy |
| Rejection of selected internally inconsistent metadata | Cryptographic author authentication or universal tamper prevention |
| Saved-mask region analysis without inference | Quantified human labor or time savings |
| Explicit distinction between verification and review | Industrial adoption or independently verified user acceptance |

For a later user study, prospectively specify tasks, participants, comparison
workflow, error categories and outcome definitions. Do not fill in hypothetical
user-study values as results. Current publication claims should remain at the
executed component/workflow level with a separate, limited real-image application
example.
