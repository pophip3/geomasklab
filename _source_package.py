"""Expose the local src package only for legacy source-checkout entry points."""
from pathlib import Path
import sys


def use_local_core():
    """Prefer a source checkout's core; leave isolated wheel imports unchanged."""
    source=str(Path(__file__).resolve().parent/'src')
    if Path(source).is_dir() and source not in sys.path:sys.path.insert(0,source)
