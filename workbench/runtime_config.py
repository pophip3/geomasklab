"""Small explicit configuration loader; never executes dotenv values."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_settings(path=None):
    path = Path(path) if path else (ROOT if (ROOT / 'src/geomasklab').is_dir() else Path.cwd()) / '.env'
    if not path.is_file():
        return
    for number, raw in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            raise ValueError(f'.env line {number}: missing equals sign.')
        key, value = (part.strip() for part in line.split('=', 1))
        if not key.startswith('GEO_') or not key.replace('_', '').isalnum():
            raise ValueError(f'.env line {number}: expected a valid GEO_ setting.')
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
        'note': 'RemoteAgent planning and tool feedback are integrated. Configuration does not establish successful model inference.',
    }
