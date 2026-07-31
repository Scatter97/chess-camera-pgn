#!/usr/bin/env bash
cd "$(dirname "$0")"
if [ -x .venv/bin/python ]; then .venv/bin/python revision35_features.py "$@"; else python3 revision35_features.py "$@"; fi
