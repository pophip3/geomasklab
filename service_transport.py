"""HTTP calls to configured model services, separate from download proxies."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request


def request_json(url, payload=None, timeout=120, headers=None):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('模型地址须为 HTTP/HTTPS 地址；凭据应通过专用密钥配置')
    mode = os.environ.get('GEO_SERVICE_PROXY_MODE', 'direct')
    if mode not in ('direct', 'environment'):
        raise ValueError('GEO_SERVICE_PROXY_MODE 只能为 direct 或 environment')
    handler = urllib.request.ProxyHandler({}) if mode == 'direct' else urllib.request.ProxyHandler()
    opener = urllib.request.build_opener(handler)
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json', **(headers or {})})
    try:
        with opener.open(req, timeout=timeout) as response:
            raw = response.read(48 * 1024 * 1024 + 1)
        if len(raw) > 48 * 1024 * 1024:
            raise ValueError('模型响应过大')
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError('模型接口应返回 JSON 对象')
        return result
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        raise ValueError(f'模型接口返回 HTTP {code}，请核对地址、权限和服务日志') from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ValueError('模型服务连接失败或超时，请检查服务、端口及代理配置') from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError('模型接口没有返回有效 JSON') from None


def inspect_services():
    """Read-only probes: sends no image and never runs an inference request."""
    base = os.environ.get('GEO_AGENT_BASE_URL', '').rstrip('/')
    model = os.environ.get('GEO_AGENT_MODEL', '')
    sam = os.environ.get('GEO_REMOTESAM_URL', '')
    report = {'inference_verified': False,
              'note': '仅检查服务与就绪声明，不代表真实推理或语义精度通过验收。'}
    if not base or not model:
        report['agent'] = {'status': 'not_configured', 'message': '请填写认知服务地址和实际模型名称'}
    else:
        try:
            data = request_json(base + '/models', timeout=5,
                                headers={'Authorization': 'Bearer ' + os.environ.get('GEO_AGENT_API_KEY', 'EMPTY')})
            ids = [item['id'] for item in data.get('data', []) if isinstance(item, dict) and isinstance(item.get('id'), str)]
            report['agent'] = {'status': 'ready' if model in ids else 'model_missing', 'models': ids,
                               'message': '找到配置的模型，推理待验证' if model in ids else '服务返回的模型列表中没有配置的名称'}
        except Exception as exc:
            report['agent'] = {'status': 'unreachable', 'message': str(exc) if isinstance(exc, ValueError) else '模型列表响应格式不符合约定'}
    if not sam:
        report['sam'] = {'status': 'not_configured', 'message': '请填写 RemoteSAM /predict 地址'}
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
                             'message': '服务声明已就绪，真实分割待验证' if declared else '尚未收到明确的 ready=true 或 status=ready'}
        except Exception as exc:
            report['sam'] = {'status': 'unknown', 'message': (str(exc) if isinstance(exc, ValueError) else '就绪响应格式异常') + '；未提供 /ready 的服务需单独验收 /predict'}
    report['services_ready'] = all(report[key]['status'] == 'ready' for key in ('agent', 'sam'))
    return report
