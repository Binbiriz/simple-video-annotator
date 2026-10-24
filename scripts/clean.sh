#!/usr/bin/env bash
# Removes generated files (build output, AppImage, caches) and optionally the virtualenv.
# usage: ./scripts/clean.sh [--venv] [--dry-run]
#   (default)  remove build/, dist/, *.egg-info, __pycache__, .pytest_cache, .ruff_cache
#   --venv     also remove .venv (runtime and dev dependencies; run.sh recreates it)
#   --dry-run  only list what would be removed
set -euo pipefail
cd "$(dirname "$0")/.."

venv=0
dry=0
for arg in "$@"; do
  case "$arg" in
    --venv) venv=1 ;;
    --dry-run|-n) dry=1 ;;
    -h|--help) sed -n '2,6p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

targets=(build dist src/vidnote.egg-info .pytest_cache .ruff_cache .mypy_cache)
[ "$venv" -eq 1 ] && targets+=(.venv)

while IFS= read -r -d '' dir; do
  targets+=("$dir")
done < <(find . \( -path ./.venv -o -path ./.git -o -path ./build -o -path ./dist \) -prune \
  -o -name __pycache__ -type d -print0)

for target in "${targets[@]}"; do
  [ -e "$target" ] || continue
  size="$(du -sh "$target" | cut -f1)"
  if [ "$dry" -eq 1 ]; then
    echo "would remove $target ($size)"
  else
    rm -rf -- "$target"
    echo "removed $target ($size)"
  fi
done
