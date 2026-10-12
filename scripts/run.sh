#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
environment="${WHISPERNET_VENV:-$HOME/.local/share/whispernet/venv}"
if [ ! -x "$environment/bin/python" ]; then
    echo "Run setup first; or set WHISPERNET_VENV to your Linux environment path." >&2
    exit 1
fi
command="${1:-doctor}"
shift || true
case "$command" in
    test) exec "$environment/bin/python" -m pytest -q "$@" ;;
    build) exec "$environment/bin/python" -m build "$@" ;;
    doctor|demo|experiment|report|inspect|send|receive) exec "$environment/bin/python" -m whispernet "$command" "$@" ;;
    *) echo "Unknown command: $command" >&2; exit 2 ;;
esac

