#!/usr/bin/env bash
set -e
if [ -x .venv/bin/python ]; then .venv/bin/python revision35.py "$@"; else python3 revision35.py "$@"; fi
