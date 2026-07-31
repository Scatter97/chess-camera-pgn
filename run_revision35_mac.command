#!/usr/bin/env bash
cd "$(dirname "$0")"
if [ -x .venv/bin/python ]; then .venv/bin/python revision35_patch2.py "$@"; else python3 revision35_patch2.py "$@"; fi
