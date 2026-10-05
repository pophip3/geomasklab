"""Expose the local src package only for legacy source-checkout entry points."""
from pathlib import Path
import sys


def use_local_core():
    """Prefer this checkout's core; installed wheels never depend on this shim."""
    source=str(Path(__file__).resolve().parent/'src')
    if source not in sys.path:sys.path.insert(0,source)
