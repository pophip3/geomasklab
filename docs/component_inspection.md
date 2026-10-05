# Candidate component inspection

GeoMaskLab measures eight-connected foreground components in a verified, saved analysis result. Each component has a location, area, pixel-center centroid and explicit boundary flags. These attributes help a reviewer find candidates that may have been affected by image, region or validity clipping.

```console
geomasklab inspect evidence.zip --min-area-pixels 16 --boundary-filter touching --output components.zip
geomasklab verify-components components.zip
```

The core uses Pillow and the Python standard library. Inspection preserves the source evidence and creates a separate selection layer. The workbench uses the same implementation for its component table and exported packet.

## Component attributes

Components are labeled after geometric-region and validity clipping. Diagonally touching foreground pixels belong to the same component.

```json
{
  "component_id": 1,
  "area_pixels": 450,
  "bbox": [10, 20, 50, 60],
  "centroid": {"x": 29.5, "y": 39.5},
  "touches_image_boundary": false,
  "touches_roi_boundary": true,
  "touches_invalid_boundary": false,
  "selected": true,
  "exclusion_reasons": []
}
```

This illustrative record is a format example, not a measured object. Bounding boxes use zero-based `[x1, y1, x2, y2]` coordinates with exclusive upper bounds. The centroid is the mean of pixel centers `(column + 0.5, row + 0.5)`, rounded to six decimal places. Areas count pixels rather than physical square meters.

IDs follow the first foreground pixel encountered in row-major order. Changing selection filters does not renumber the same saved mask's components. Changing a source mask or clipping region can split, merge or relabel components; IDs are not persistent object identities across different results.

## Boundary rules

Boundary flags inspect the eight neighboring pixel positions, including diagonal adjacency.

| Attribute | Exact condition |
| --- | --- |
| `touches_image_boundary` | At least one component pixel lies on an outer image row or column. |
| `touches_roi_boundary` | At least one component pixel has an in-image neighbor outside the selected geometric region. The rule also applies to half-image scopes. |
| `touches_invalid_boundary` | At least one component pixel has an in-image neighbor whose declared validity is zero. |

The flags are independent and can overlap. An out-of-image neighbor affects the image flag only; it is not an invalid pixel or an ROI neighbor. The whole-image geometric region therefore creates no ROI-boundary contact on its own.

Boundary contact is a review hint, not proof that a semantic object has been truncated. A naturally ending foreground region can touch a boundary. Validity exclusions can also split a single source component into several analyzed candidates. Component counts consequently do not establish building, tree or other semantic object counts.

## Select candidates without changing measurements

`--min-area-pixels` accepts a positive integer. The default is `1`.

| `--boundary-filter` | Candidates selected |
| --- | --- |
| `all` | Every component meeting the minimum area. |
| `touching` | Components meeting the minimum area with at least one boundary flag. |
| `interior` | Components meeting the minimum area with no boundary flags. |

All components remain in the inspection JSON and CSV, including unselected candidates and their exclusion reasons. `selection.png` is a separate binary layer containing selected candidates. The saved source mask, evidence numerator and semantic review are unchanged. The selection is not an automatically corrected prediction or a new semantic annotation.

The record checks area conservation: the sum of all component areas equals the analyzed foreground count. Selected area and selected component count are reported separately.

## Packet contents and replay

`components.zip` contains:

- `evidence.zip`: the exact verified source evidence;
- `inspection.json`: every candidate, selection setting and boundary rule;
- `components.csv`: all candidate attributes with English column names;
- `selection.png`: selected candidate pixels in a separate L-mode binary image;
- `report.md`: English interpretation, rules and replay commands;
- `manifest.json`: exact member sizes and SHA-256 digests.

The inspection record uses `geomasklab-component-inspection/1.0`; its manifest uses `geomasklab-component-packet/1.0`. Verification checks bounded unique membership, source evidence, typed canonical records, component labeling, boundary flags, candidate selection and decoded selection pixels. Rehashing a changed area, flag, CSV or selection image does not make it replay correctly.

Inspection admits at most 100,000 components. Exceeding that limit produces an explicit error; choose a smaller analysis region rather than expecting a silently truncated table. The existing evidence image and packet size limits also apply. The algorithm is an offline pixel inspection tool rather than a semantic object detector.

## Real-image workflow

```console
python examples/five_step_workflow.py --output five-step-output
geomasklab verify-components five-step-output/components.zip
```

The frozen NAIP example selects candidates of at least 16 pixels touching a clipping boundary. It checks component-area conservation against independently counted source pixels and preserves the exact validity source during ROI derivation. The alternative mask is a declared protocol perturbation, and the example makes no segmentation-accuracy or human-study claim.
