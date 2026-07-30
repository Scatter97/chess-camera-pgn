#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

pause_on_error() {
    exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        echo
        echo "Chess Camera could not start. Review the error above."
        read -r -p "Press Return to close this window..." _
    fi
}
trap pause_on_error EXIT

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "This launcher is for macOS. Use run_windows.bat or run_ubuntu.sh instead."
    exit 1
fi

PYTHON_BIN=""
for candidate in python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c \
            'import sys; raise SystemExit(sys.version_info[:2] not in {(3, 11), (3, 12)})'
        then
            PYTHON_BIN="$candidate"
            break
        fi
    fi
done

if [[ -z "$PYTHON_BIN" ]]; then
    echo "Python 3.11 or 3.12 is required."
    echo "Install it from https://www.python.org/downloads/macos/"
    exit 1
fi

if [[ ! -x ".venv/bin/python" ]]; then
    echo "Preparing Chess Camera for the first launch..."
    "$PYTHON_BIN" -m venv .venv
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install -r requirements.txt
fi

echo "Starting Chess Camera..."
.venv/bin/python app.py "$@"
