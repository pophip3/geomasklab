"""Self-reported semantic review of one immutable result, not authenticated truth."""
import hashlib

SCHEMA = 'geoscope-semantic-review/1.0'
STATES = {'pending', 'accepted', 'rejected'}


def initial_review():
    return {'schema': SCHEMA, 'state': 'pending', 'events': [],
            'notice': '人工自报复核，未经身份认证；不等同真值、精度评测或边界修正。'}


def append_review(current, payload, *, at, run_id, image_bytes, mask_bytes):
    decision = payload.get('decision')
    if not isinstance(decision, str) or decision not in STATES:
        raise ValueError('复核状态须为 pending、accepted 或 rejected')
    reviewer, note = payload.get('reviewer'), payload.get('note')
    if not isinstance(reviewer, str) or not reviewer.strip() or len(reviewer) > 100:
        raise ValueError('请填写不超过100字的复核人标识')
    if not isinstance(note, str) or not note.strip() or len(note) > 2000:
        raise ValueError('请填写不超过2000字的复核依据或退回原因')
    review = {**initial_review(), **(current or {})}
    event = {'decision': decision, 'reviewer': reviewer.strip(), 'note': note.strip(),
             'at': at, 'run_id': run_id,
             'image_sha256': hashlib.sha256(image_bytes).hexdigest(),
             'mask_sha256': hashlib.sha256(mask_bytes).hexdigest()}
    review.update(state=decision, events=[*review['events'], event])
    return review


def verify_review(review, *, run_id, image_sha256, mask_sha256):
    if not isinstance(review, dict):
        raise ValueError('Semantic review record must be an object.')
    if review.get('schema') != SCHEMA or review.get('state') not in STATES:
        raise ValueError('Unsupported semantic review record.')
    events = review.get('events')
    if not isinstance(events, list) or (not events and review['state'] != 'pending'):
        raise ValueError('Semantic review history is missing.')
    for event in events:
        if not isinstance(event, dict):
            raise ValueError('Semantic review event must be an object.')
        if (event.get('decision') not in STATES or event.get('run_id') != run_id
                or event.get('image_sha256') != image_sha256 or event.get('mask_sha256') != mask_sha256):
            raise ValueError('Semantic review result identity mismatch.')
        if any(not isinstance(event.get(key), str) or not event[key].strip() for key in ('reviewer', 'note', 'at')):
            raise ValueError('Semantic review evidence is incomplete.')
    if events and events[-1]['decision'] != review['state']:
        raise ValueError('Semantic review state disagrees with history.')
