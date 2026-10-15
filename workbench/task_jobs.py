"""Saved single-image jobs; losing an HTTP response must not repeat inference."""
import json
import re
import threading
import uuid
from datetime import datetime, timezone

JOBS = {}
LOCK = threading.RLock()
IDENTIFIER = re.compile(r'^[a-f0-9]{12}$')


def _save(data, job):
    folder = data / 'tasks'
    folder.mkdir(exist_ok=True)
    target = folder / (job['id'] + '.json')
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(job, ensure_ascii=False), encoding='utf-8')
    temporary.replace(target)


def publish(data, job, **changes):
    with LOCK:
        job.update(changes, updated_at=datetime.now(timezone.utc).isoformat())
        _save(data, job)


def get_job(data, identifier):
    if not isinstance(identifier, str) or not IDENTIFIER.fullmatch(identifier):
        raise ValueError('Invalid task ID.')
    with LOCK:
        job = JOBS.get((str(data), identifier))
        if job is None:
            target = data / 'tasks' / (identifier + '.json')
            if not target.is_file():
                raise ValueError('Task not found.')
            job = json.loads(target.read_text(encoding='utf-8'))
            if job['status'] == 'running':
                # A restart cannot resume an in-flight model call safely.
                publish(data, job, status='interrupted', phase='Server restarted',
                        error='The server stopped during execution. Inspect saved experiment files before retrying. No inference was automatically repeated.')
        return dict(job)


def active_job(data, session_id):
    if not isinstance(session_id, str) or not IDENTIFIER.fullmatch(session_id):
        raise ValueError('Invalid session ID.')
    with LOCK:
        candidates = [dict(job) for (root, _), job in JOBS.items()
                      if root == str(data) and job['session_id'] == session_id and job['status'] == 'running']
    return candidates[-1] if candidates else None


def start_job(data, session, payload, execute):
    if payload.get('batch_id'):
        raise ValueError('Only the batch executor may assign batch_id.')
    query = payload.get('query')
    if not isinstance(query, str) or not query.strip() or len(query) > 1800:
        raise ValueError('Enter a task of no more than 1,800 characters.')
    if payload.get('mode', 'demo') not in ('demo', 'live'):
        raise ValueError('Unknown runtime mode.')
    if not session['lock'].acquire(blocking=False):
        raise ValueError('This experiment is busy. Wait for the current task to finish.')
    job = {'id': uuid.uuid4().hex[:12], 'session_id': session['id'],
           'query': query, 'status': 'running', 'phase': 'Task accepted'}
    try:
        with LOCK:
            if sum(item['status'] == 'running' for item in JOBS.values()) >= 32:
                raise ValueError('Too many active tasks. Wait before submitting another task.')
            publish(data, job)
            JOBS[(str(data), job['id'])] = job
    except Exception:
        session['lock'].release()
        raise

    def worker():
        try:
            result = execute(session, dict(payload), job=job)
            publish(data, job, status='completed', phase='Result saved', result=result)
        except Exception as exc:
            publish(data, job, status='failed', phase='Execution failed',
                    error=str(exc) if isinstance(exc, ValueError) else type(exc).__name__)
        finally:
            session['lock'].release()

    threading.Thread(target=worker, daemon=True, name='geomasklab-task-' + job['id']).start()
    return dict(job)
