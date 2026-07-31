#!/usr/bin/env bash
cd "$(dirname "$0")"
if [ -x .venv/bin/python ]; then .venv/bin/python chess_camera.py "$@"; else python3 chess_camera.py "$@"; fi
