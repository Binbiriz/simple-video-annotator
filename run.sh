#!/usr/bin/env bash
# Creates a virtualenv on first run, installs dependencies, then starts vidnote.
# usage: ./run.sh [video-file]
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install -e .
fi
exec .venv/bin/vidnote "$@"
