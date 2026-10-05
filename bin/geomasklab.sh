#!/bin/sh
# Start from the software root, regardless of the caller's working directory.
set -eu
GEOMASKLAB_ROOT=$(CDPATH= cd -P "$(dirname "$0")/.." && pwd)
cd "$GEOMASKLAB_ROOT"
if [ -x "$GEOMASKLAB_ROOT/.venv/bin/python" ]; then
  exec "$GEOMASKLAB_ROOT/.venv/bin/python" quickstart.py "$@"
fi
if command -v python3 >/dev/null 2>&1; then
  exec python3 quickstart.py "$@"
fi
if command -v python >/dev/null 2>&1; then
  exec python quickstart.py "$@"
fi
printf '%s\n' 'Python 3.10 or newer is required. See README.md for installation steps.' >&2
exit 1
