# Workbench API

GeoMaskLab serves these routes on the local loopback HTTP server. Requests use
JSON objects; responses are JSON unless an image, Markdown report, CSV or ZIP is
explicitly requested. Session and run IDs are 12 lowercase hexadecimal characters.
This interface is intended for a trusted local researcher, without multi-user
authentication. Start it with `python quickstart.py`.

## Routes

| Method and route | Inputs | Output |
| --- | --- | --- |
| `GET /api/status` | None | Version, capabilities, example descriptions and configuration status; no credentials |
| `GET /api/sessions` | None | Up to 100 saved image sessions, newest first |
| `POST /api/session` | `sample` (`urban` or `airport`), or base64/data-URL `image`; optional `name` | New session with normalized RGB image and empty result history |
| `GET /api/session/{id}` | Saved session ID | Session, results and selected task context |
| `POST /api/run` | `session_id`, `query`, `mode` (`demo` or `live`); optional parent, scope, ROI, quality mode | One run result; inspect its `status` before assuming a mask exists |
| `POST /api/review` | `session_id`, `run_id`, `decision`, `reviewer`, `note` | Updated self-reported review history for the exact image/mask |
| `POST /api/import` | Base64/data-URL `bundle`; optional file `name` | A verified single-result evidence bundle in a new session |
| `POST /api/recalculate-region` | `session_id`, `run_id`, `scope`; optional typed `roi` | Separate derived result without agent or segmentation calls |
| `GET /api/export/{session}/{run}` | Valid mask run | Portable evidence ZIP with manifest |
| `GET /api/report/{session}/{run}` | Valid mask run | English Markdown report; historical/user-supplied text is preserved |
| `POST /api/batch` | 2–5 distinct `session_ids`, shared `query` and execution options | Synchronous sequential batch with per-item results/failures |
| `POST /api/batch/start` | Same batch fields | Asynchronous batch ID; poll the route below |
| `GET /api/batch/{id}` | Batch ID | Batch progress/results |
| `GET /api/batch-export/{id}` | Completed saved batch ID | UTF-8 CSV with per-item measurements and failure reasons |
| `POST /api/check-services` | Empty object | Availability/readiness declarations; no images sent or accuracy measured |

## Task options and numerical frame

- `parent_run_id`: a result from the same session; supplies the selected version's
  target/scope/complement context. A failed request does not replace valid masks.
- `scope`: `all`, `left`, `right`, `top` or `bottom`, in image coordinates.
- `roi`: `{"xyxy":[80,50,280,250],"source":"drawn","image_size":[800,600]}`.
  Coordinates are integers with exclusive upper bounds. ROI and half-image
  selection are mutually exclusive. An empty object explicitly clears a parent ROI
  for a new task; the offline region route instead rejects an invalid empty ROI.
- `quality_mode`: `auto`, `fast` or `accurate`. The interface calls `accurate`
  **Tiled refinement**. This is a service option, not an accuracy guarantee.
- `force_perception`: requests new inference rather than compatible cached-mask
  reuse. Matching identity includes image, target, prompt, revision and request.
- `simulate_failure`: explicit procedural failure demonstration; produces no mask
  or measurements. It is never represented as a real model-service failure.

For foreground `A`, image pixels `I` and region pixels `R`, `area_ratio=A/I`,
`scope_area_pixels=R`, and `scope_area_ratio=A/R` (null if `R=0`). Candidate
components use eight-connectivity; their count is not a verified object count.
No CRS, metric distance or geographic area is inferred.

## Run states

`completed` means a nonempty mask and measurements were produced, not semantic
acceptance. `needs_review` includes empty masks. `answered` is a scene response
without segmentation. `needs_clarification` has no executed segmentation;
`failed` has no valid output for that run; `export_ready` refers to a previous
valid result. New segmentation/derived results start with `semantic_review.state`
set to `pending`, irrespective of a parent's acceptance.

Offline derivatives explicitly record `execution_kind=saved_mask_region_analysis`
and `inference_performed=false`. Their local duration and original prediction
provenance are separate; changing scope does not improve a model prediction.

## Input limits and errors

Images and evidence bundles are limited to 12 MB; images to 16 million pixels.
Task text is limited to 1,800 characters, reviewer labels to 100 characters and
review rationales to 2,000 characters. POST bodies have an 18 MB upper limit to
allow base64 overhead. Binary masks must contain only 0/1 or 0/255, with the exact
image dimensions; probability maps are not silently thresholded or resized.

HTTP 400 indicates invalid application input; 404 identifies unavailable routes
or resources. A run can return HTTP 200 with `status=failed` because failed
attempts are recorded research events. Read the run state and error message.
The verifier detects inconsistent artifacts, not a malicious author's identity;
hashes can be regenerated. Imported ZIP entries are read without extraction.
