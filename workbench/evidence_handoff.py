"""Restore verified single-run evidence without inference or trusting cache hints."""
import hashlib
import json
import math
import re
from copy import deepcopy
from workbench.export_bundle import load_verified_bundle

MAX_IMPORT_BYTES = 12 * 1024 * 1024


def prepare_import(payload):
    """Validate operational metadata before creating any session directory."""
    if len(payload) > MAX_IMPORT_BYTES:
        raise ValueError('Evidence bundles must be 12 MB or smaller.')
    try:
        facts, files = load_verified_bundle(payload)
        result = json.loads(files['result.json'])
        if not re.fullmatch(r'[a-f0-9]{12}', result['id']):
            raise ValueError('Invalid run ID.')
        if result['status'] not in ('completed', 'needs_review') or result['mode'] not in ('demo', 'live', 'external'):
            raise ValueError('Only bundles with a valid segmentation result are supported.')
        if result['task']['target'] not in ('building', 'aircraft', 'road', 'water', 'tree', 'ship'):
            raise ValueError('Unsupported target in the evidence bundle.')
        for key in ('query', 'message', 'created_at'):
            if not isinstance(result[key], str) or len(result[key]) > 20000:
                raise ValueError('Invalid text field in the evidence bundle.')
        if type(result['duration_ms']) not in (int, float) or not math.isfinite(result['duration_ms']) or result['duration_ms'] < 0:
            raise ValueError('Invalid recorded duration.')
        for key in ('planner', 'source', 'perception'):
            if not isinstance(result['provenance'][key], str):
                raise ValueError('Invalid provenance field.')
        for key in ('task_options', 'service_metadata', 'agent_decision'):
            if result.get(key) is not None and not isinstance(result[key], dict):
                raise ValueError('Invalid metadata field.')
        trace = json.loads(files['run_log.json'])
        if not isinstance(trace, list) or len(trace) > 1000 or any(not isinstance(e, dict) for e in trace):
            raise ValueError('Invalid execution log.')
        imported = deepcopy(result)
        imported.pop('mask_cache_key', None)
        imported['parent_run_id'] = None
        imported['version'] = 1
        imported['trace'] = trace
        imported['imported_evidence'] = {
            'bundle_sha256': hashlib.sha256(payload).hexdigest(),
            'source_session_id': result.get('session_id'), 'source_run_id': result['id'],
            'source_version': result.get('version'), 'source_parent_run_id': result.get('parent_run_id'),
            'verification': facts, 'inference_performed_on_import': False,
            'complete_branch_history_restored': False,
        }
        return imported, files, facts
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError('Unsupported or incomplete evidence-bundle structure.') from error
