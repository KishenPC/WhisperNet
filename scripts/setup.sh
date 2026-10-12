#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if ! command -v tcpdump >/dev/null || ! python3 -m venv --help >/dev/null; then
    echo "Install Linux dependencies first: sudo apt-get update; sudo apt-get install python3-venv tcpdump iproute2"
    exit 1
fi
environment="$HOME/.local/share/whispernet/venv"
python3 -m venv "$environment"
"$environment/bin/python" -m pip install --upgrade pip
if [ -f requirements.lock.txt ]; then
    "$environment/bin/python" -m pip install -c requirements.lock.txt -e '.[dev]'
else
    "$environment/bin/python" -m pip install -e '.[dev]'
fi
"$environment/bin/python" -m pip freeze --exclude-editable > requirements.lock.txt
"$environment/bin/python" -m whispernet doctor

