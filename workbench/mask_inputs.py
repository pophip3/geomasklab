"""Compatibility imports for source-checkout users; core lives in geomasklab."""
from _source_package import use_local_core
use_local_core()
from geomasklab.masks import *  # noqa: F401,F403
