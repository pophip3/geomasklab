"""Editable experiment metadata and a complete measurement ledger export."""
import csv
import io


def metadata_changes(payload):
    """Validate only editable labels; image identity and results stay immutable."""
    if set(payload) - {'session_id', 'name', 'notes', 'pinned'}:
        raise ValueError('Only experiment name, notes and pinned status may be edited.')
    changes = {}
    for field, maximum in (('name', 120), ('notes', 4000)):
        if field in payload:
            value = payload[field]
            if not isinstance(value, str) or len(value) > maximum or '\x00' in value:
                raise ValueError(f'{field} must be text of at most {maximum} characters.')
            if field == 'name' and not value.strip():
                raise ValueError('Experiment name cannot be empty.')
            changes[field] = value.strip()
    if 'pinned' in payload:
        if type(payload['pinned']) is not bool:
            raise ValueError('Pinned status must be a boolean.')
        changes['pinned'] = payload['pinned']
    if not changes:
        raise ValueError('Provide at least one editable metadata field.')
    return changes


def safe_cell(value):
    """Keep user text literal when opened by spreadsheet software."""
    if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
        return "'" + value
    return value


def ledger_csv(session):
    """Include failed and non-mask runs with blank, not fabricated, measurements."""
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    fields = ['session_id', 'experiment_name', 'run_id', 'version', 'parent_run_id',
              'query', 'status', 'review_state', 'created_at', 'mode', 'execution_kind', 'target',
              'complement', 'scope', 'roi_xyxy', 'foreground_pixels', 'whole_image_pixels',
              'whole_image_coverage', 'selected_region_pixels', 'within_region_coverage',
              'candidate_components', 'duration_ms', 'message', 'validity_policy', 'validity_source',
              'valid_image_pixels','valid_region_pixels','excluded_region_pixels',
              'coverage_of_valid_image','coverage_of_valid_region']
    writer.writerow(fields)
    for run in session['runs']:
        m, t = run.get('metrics') or {}, run.get('task') or {}
        row = [session['id'], session['name'], run['id'], run['version'], run.get('parent_run_id'),
               run['query'], run['status'], (run.get('semantic_review') or {}).get('state'),
               run.get('created_at'), run.get('mode'), run.get('execution_kind'), t.get('target'), t.get('invert'),
               t.get('side'), ','.join(map(str, t['roi']['xyxy'])) if t.get('roi') else '',
               m.get('pixel_area'), m.get('total_pixels'), m.get('area_ratio'),
               m.get('scope_area_pixels'), m.get('scope_area_ratio'),
               (m.get('candidate_stats') or {}).get('candidate_count'), run.get('duration_ms'), run.get('message')]
        declaration=(run.get('analysis_config') or {}).get('validity') or {}
        v=m.get('validity_measurements') or {}
        row.extend([declaration.get('policy','all_pixels_declared_valid' if m else None),declaration.get('source'),
                    v.get('valid_image_pixels',m.get('total_pixels')),v.get('valid_region_pixels',m.get('scope_area_pixels')),
                    v.get('excluded_region_pixels',0 if m else None),
                    v.get('coverage_of_valid_image',m.get('area_ratio')),v.get('coverage_of_valid_region',m.get('scope_area_ratio'))])
        writer.writerow([safe_cell(v) for v in row])
    return '\ufeff' + output.getvalue()
