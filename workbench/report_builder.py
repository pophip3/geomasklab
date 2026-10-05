"""Readable English reports built from persisted results, without model calls."""
import json
from workbench.semantic_review import initial_review


def build_report(session, result, target_labels, scope_labels, capabilities):
    """Describe recorded artifacts and distinguish integrity from semantic accuracy.

    Historical/user-supplied text is quoted unchanged. No missing service version,
    inference request, review decision or geographic measurement is inferred.
    """
    if result.get('execution_kind') == 'saved_mask_region_analysis':
        from workbench.region_analysis import region_report
        return region_report(session, result)
    metrics, task = result['metrics'], result['task']
    candidates = metrics['candidate_stats']
    options = result.get('task_options', {})
    service = result.get('service_metadata') or {}
    model = service.get('model') or {}
    if not isinstance(model, dict):
        model = {}
    request = task.get('service_request') or {}
    request = {key: request[key] for key in ('task', 'text', 'classes', 'quality_mode') if key in request}
    actual_request = json.dumps(request, ensure_ascii=False, sort_keys=True) if request else (
        'No model call in the procedural demonstration.' if result['mode'] == 'demo'
        else 'No model call during external mask import.' if result['mode'] == 'external'
        else 'Not recorded in this older result; cannot be inferred.')
    call = (result.get('agent_decision') or {}).get('tool_call') or {}
    roi = options.get('roi')
    review = result.get('semantic_review') or initial_review()
    recorded = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True)
    region_ratio = metrics.get('scope_area_ratio')
    region_coverage = f'{region_ratio * 100:.4f}%' if region_ratio is not None else 'Not recorded or empty scope'
    origin = {'demo': 'Procedural synthetic image and mask; not neural inference',
              'external': 'User-supplied binary mask; imported without model inference'}.get(result['mode'], 'Live model-service response')
    category = 'Primary application category; human review required' if capabilities[task['target']]['level'] == 'primary' else 'Experimental category; no frozen semantic evaluation'
    scope = scope_labels[task['side']] + (f'; rectangle ROI {roi["xyxy"]}' if roi else '')
    lines = [f'# GeoMaskLab experiment report: {session["name"]}', '',
        '## Task and prediction provenance', '',
        f'- Run ID: {result["id"]}', f'- Software version: {result.get("software_version", "Not recorded")}',
        f'- Status: {result["status"]}; semantic and boundary review is separate.',
        f'- Image dimensions: {session["width"]} × {session["height"]} pixels',
        f'- Recorded data source: {session["source"]}', f'- Recorded user task: {result["query"]}',
        f'- Execution origin: {origin}', f'- Planner: {result["provenance"]["planner"]}',
        f'- External mask provenance (user supplied): {recorded(result.get("external_mask"))}',
        f'- Segmentation source: {result["provenance"]["perception"]}',
        f'- Semantic target: {target_labels.get(task["target"], task["target"])}',
        f'- Mask complement: {bool(task.get("invert"))}', f'- Spatial scope: {scope}',
        f'- Requested execution mode: {options.get("quality_mode", "Not recorded")}',
        f'- Service-confirmed mode: {options.get("effective_quality_mode") or "Unconfirmed"}',
        f'- Bounded tool call: {call.get("name", "No model tool call recorded")}',
        '- Executor checks: target, image identity, ROI, mode, binary mask dimensions and spatial scope.',
        f'- Actual recorded service request: {actual_request}',
        f'- Service version: {service.get("service_version") or model.get("service_version", "Not recorded")}',
        f'- Checkpoint SHA-256: {model.get("checkpoint_sha256", "Not recorded")}',
        f'- Category status: {category}', f'- Mode parameters: {recorded(service.get("mode_parameters", {}))}',
        f'- Recorded service timing (ms): {recorded(service.get("timing_ms", {}))}',
        f'- Run duration: {result["duration_ms"]} ms', '', '## Pixel measurements', '',
        f'- Foreground pixels: {metrics["pixel_area"]:,}', f'- Total image pixels: {metrics["total_pixels"]:,}',
        f'- Whole-image coverage: {metrics["area_ratio"] * 100:.4f}% (denominator: all image pixels)',
        f'- Selected-region pixels: {metrics.get("scope_area_pixels", "Not recorded")}',
        f'- Within-region coverage: {region_coverage} (denominator: selected-region pixels)',
        f'- Candidate components: {candidates["candidate_count"]}; candidates are not verified object counts.',
        f'- Connectivity: {candidates["connectivity"]}; minimum component area: {candidates["min_area_pixels"]} pixels',
        f'- Components before/after filtering: {candidates["raw_candidate_count"]} / {candidates["candidate_count"]}',
        f'- Mean candidate area: {candidates["mean_area"]} pixels',
        f'- Full-mask foreground in left/right halves: {metrics["distribution"]["left_pixels"]:,} / {metrics["distribution"]["right_pixels"]:,} pixels',
    ]
    if roi:
        lines.append(f'- Full-mask foreground inside/outside the ROI: {metrics["distribution"]["roi_inside_pixels"]:,} / {metrics["distribution"]["roi_outside_pixels"]:,} pixels')
    if 'validity_measurements' in metrics:
        lines.extend(['', '## Declared validity', '',
                      recorded(result['analysis_config']),recorded(metrics['validity_measurements']),
                      'Validity is a user-declared analysis condition, not an accuracy assessment.'])
    lines += ['', '## Review and reproduction', '',
        f'- Semantic review state: {review["state"]}; decisions are self-reported, not authenticated.',
        f'- Recorded review events: {recorded(review["events"])}',
        f'- Image SHA-256: {result["provenance"]["image_sha256"]}',
        f'- Segmentation revision: {result["provenance"].get("perception_revision", "Not recorded")}',
        f'- Image/mask dimensions match: {metrics["width"] == session["width"] and metrics["height"] == session["height"]}',
        f'- Spatial check: {metrics["spatial_check"]}',
        '- Bundle files: original.png, full_mask.png, mask.png, overlay.png, statistics.json, result.json, run_log.json, report.md and manifest.json.',
        '- Offline verification: `geomasklab verify path/to/evidence.zip`.',
        '- Verification replays scope, complement and pixel measurements. It does not authenticate authors or establish semantic accuracy.',
        '- Measurements use image pixels, not square meters, hectares or geographic coordinates.',
        '- Review target identity, omissions, false positives and component boundaries separately.',
        '- User-supplied and historical source text is preserved verbatim.', '']
    if result.get('imported_evidence'):
        origin = result['imported_evidence']
        lines += ['## Evidence handoff', '',
            '- Import did not run model inference; image and mask bytes were retained.',
            f'- Source bundle SHA-256: {origin["bundle_sha256"]}',
            f'- Source run ID: {origin["source_run_id"]}; source version: {origin["source_version"]}',
            '- A single-result import cannot restore ancestors absent from the bundle.', '']
    return '\n'.join(lines)
