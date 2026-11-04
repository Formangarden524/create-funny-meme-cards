#!/bin/zsh
cd -- "${0:A:h}" || exit 1
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv || exit 1
fi
if ! .venv/bin/python -c 'import yaml, jsonschema' 2>/dev/null; then
  .venv/bin/python -m pip install -r tools/requirements.txt || exit 1
fi
exec .venv/bin/python tools/local_workbench.py --open
