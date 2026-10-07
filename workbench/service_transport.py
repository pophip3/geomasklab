"""HTTP calls to configured model services, separate from download proxies."""
import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request


def agent_request_settings(default_tokens):
    """Validate optional chat budgets without changing health/SAM timeouts."""
    tokens = default_tokens
    raw_tokens = os.environ.get('GEO_AGENT_MAX_TOKENS')
    if raw_tokens is not None:
        raw_tokens = raw_tokens.strip()
        if not raw_tokens.isascii() or not raw_tokens.isdigit():
            raise ValueError('GEO_AGENT_MAX_TOKENS must be an integer between 16 and 1024.')
        tokens = int(raw_tokens)
        if not 16 <= tokens <= 1024:
            raise ValueError('GEO_AGENT_MAX_TOKENS must be an integer between 16 and 1024.')
    timeout = 120
    raw_timeout = os.environ.get('GEO_AGENT_TIMEOUT_SECONDS')
    if raw_timeout is not None:
        try:
            timeout = float(raw_timeout)
        except (TypeError, ValueError):
            raise ValueError('GEO_AGENT_TIMEOUT_SECONDS must be finite and between 5 and 3600 seconds.') from None
        if not math.isfinite(timeout) or not 5 <= timeout <= 3600:
            raise ValueError('GEO_AGENT_TIMEOUT_SECONDS must be finite and between 5 and 3600 seconds.')
    return tokens, timeout


def request_json(url, payload=None, timeout=120, headers=None):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Model endpoints must use HTTP or HTTPS. Configure credentials in the dedicated key setting.')
    mode = os.environ.get('GEO_SERVICE_PROXY_MODE', 'direct')
    if mode not in ('direct', 'environment'):
        raise ValueError('GEO_SERVICE_PROXY_MODE must be direct or environment.')
    handler = urllib.request.ProxyHandler({}) if mode == 'direct' else urllib.request.ProxyHandler()
    opener = urllib.request.build_opener(handler)
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json', **(headers or {})})
    try:
        with opener.open(req, timeout=timeout) as response:
            raw = response.read(48 * 1024 * 1024 + 1)
        if len(raw) > 48 * 1024 * 1024:
            raise ValueError('The model response is too large.')
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError('The model endpoint must return a JSON object.')
        return result
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        raise ValueError(f'Model endpoint returned HTTP {code}. Check the URL, permissions and service logs.') from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ValueError('Model connection failed or timed out. Check the service, port and proxy settings.') from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError('The model endpoint returned invalid JSON.') from None


def inspect_services():
    """Read-only probes: sends no image and never runs an inference request."""
    base = os.environ.get('GEO_AGENT_BASE_URL', '').rstrip('/')
    model = os.environ.get('GEO_AGENT_MODEL', '')
    sam = os.environ.get('GEO_REMOTESAM_URL', '')
    report = {'inference_verified': False,
              'note': 'Checks service availability and readiness declarations only; does not establish inference success or semantic accuracy.'}
    if not base or not model:
        report['agent'] = {'status': 'not_configured', 'message': 'Configure the planner URL and actual model name.'}
    else:
        try:
            data = request_json(base + '/models', timeout=5,
                                headers={'Authorization': 'Bearer ' + os.environ.get('GEO_AGENT_API_KEY', 'EMPTY')})
            ids = [item['id'] for item in data.get('data', []) if isinstance(item, dict) and isinstance(item.get('id'), str)]
            report['agent'] = {'status': 'ready' if model in ids else 'model_missing', 'models': ids,
                               'message': 'Configured model found; inference remains unverified.' if model in ids else 'The configured model name is absent from the service model list.'}
        except Exception as exc:
            report['agent'] = {'status': 'unreachable', 'message': str(exc) if isinstance(exc, ValueError) else 'The model-list response violates the expected format.'}
    if not sam:
        report['sam'] = {'status': 'not_configured', 'message': 'Configure the RemoteSAM /predict URL.'}
    else:
        # /ready is a proposed integration contract; a 404 does not prove /predict is broken.
        parts = urllib.parse.urlsplit(sam)
        path = parts.path.rstrip('/')
        ready_path = path.rsplit('/', 1)[0] + '/ready'
        ready_url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, ready_path, '', ''))
        try:
            data = request_json(ready_url, timeout=5)
            declared = data.get('ready') is True or data.get('status') == 'ready'
            report['sam'] = {'status': 'ready' if declared else 'not_ready',
                             'message': 'Service declares readiness; real segmentation remains unverified.' if declared else 'No explicit ready=true or status=ready declaration was received.'}
        except Exception as exc:
            report['sam'] = {'status': 'unknown', 'message': (str(exc) if isinstance(exc, ValueError) else 'Invalid readiness-response format.') + '; services without /ready require separate /predict acceptance.'}
    report['services_ready'] = all(report[key]['status'] == 'ready' for key in ('agent', 'sam'))
    return report
