#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
if [ ! -f data/finance.sqlite ]; then .venv/bin/python scripts/generate_data.py; fi
