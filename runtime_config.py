"""Small explicit configuration loader; never executes dotenv values."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_settings(path=None):
    path = Path(path) if path else ROOT / '.env'
    if not path.is_file():
        return
    for number, raw in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            raise ValueError(f'.env 第 {number} 行缺少等号')
        key, value = (part.strip() for part in line.split('=', 1))
        if not key.startswith('GEO_') or not key.replace('_', '').isalnum():
            raise ValueError(f'.env 第 {number} 行不是有效的 GEO_ 配置项')
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        # A real shell setting wins over the file, including an intentionally empty value.
        os.environ.setdefault(key, value)


def settings_status():
    return {
        'agent_configured': bool(os.environ.get('GEO_AGENT_BASE_URL') and os.environ.get('GEO_AGENT_MODEL')),
        'sam_configured': bool(os.environ.get('GEO_REMOTESAM_URL')),
        'agent_model': os.environ.get('GEO_AGENT_MODEL', ''),
        'agent_protocol': 'remoteagent',
        'service_proxy_mode': os.environ.get('GEO_SERVICE_PROXY_MODE', 'direct'),
        'note': '工作台已接入 RemoteAgent 规划和工具反馈接口；配置不等于真实模型已验收。',
    }
