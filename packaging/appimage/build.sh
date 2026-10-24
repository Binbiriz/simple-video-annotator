#!/usr/bin/env bash
# Build dist/vidnote-<version>-x86_64.AppImage. Run from anywhere; needs network access
# (python-appimage downloads a manylinux Python and the PySide6 wheel) and libxcb-cursor0.
set -euo pipefail

PYTHON_APPIMAGE_VERSION=1.4.6
LINUX_TAG=manylinux_2_28_x86_64
PYTHON_VERSION=3.12

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
BUILD="$ROOT/build/appimage"

version="$(python3 - <<'PY'
import sys

if sys.version_info < (3, 11):
    sys.exit("build.sh needs Python 3.11+ (tomllib) to read the version from pyproject.toml")
import tomllib

with open("pyproject.toml", "rb") as f:
    print(tomllib.load(f)["project"]["version"])
PY
)"
[ -n "$version" ] || { echo "could not read the version from pyproject.toml" >&2; exit 1; }

cursor="$(ldconfig -p | awk '/libxcb-cursor\.so\.0 / && /x86-64/ && !found {print $NF; found=1}')"
if [ -z "$cursor" ]; then
    echo "libxcb-cursor.so.0 not found: sudo apt install libxcb-cursor0" >&2
    exit 1
fi

rm -rf "$BUILD"
mkdir -p "$BUILD/work" "$BUILD/extra/extra-libs" "$ROOT/dist"

python3 -m venv "$BUILD/venv"
"$BUILD/venv/bin/pip" install --quiet "python-appimage==$PYTHON_APPIMAGE_VERSION"

# The sources are bundled as plain data (no pip install), without caches, media or tests.
cp -r "$ROOT/src/vidnote" "$BUILD/extra/vidnote"
find "$BUILD/extra/vidnote" -name __pycache__ -type d -prune -exec rm -rf {} +
cp "$ROOT/scripts/annotate.sh" "$BUILD/extra/annotate.sh"

# Qt's xcb plugin needs libxcb-cursor and the xcb helper libraries it links to; desktops
# usually lack them. Everything else it links to is part of any X desktop.
cp -L "$cursor" "$BUILD/extra/extra-libs/"
ldd "$cursor" | awk '/libxcb-(render-util|image|util)\.so/ {print $3}' |
    while read -r lib; do cp -L "$lib" "$BUILD/extra/extra-libs/"; done

cd "$BUILD/work"
"$BUILD/venv/bin/python-appimage" build app \
    -l "$LINUX_TAG" -p "$PYTHON_VERSION" \
    "$ROOT/packaging/appimage" \
    -x "$BUILD/extra/vidnote" "$BUILD/extra/annotate.sh" "$BUILD/extra/extra-libs"

shopt -s nullglob
images=(*.AppImage)
if [ "${#images[@]}" -ne 1 ]; then
    echo "expected exactly one AppImage, found ${#images[@]}" >&2
    exit 1
fi

out="$ROOT/dist/vidnote-$version-x86_64.AppImage"
mv "${images[0]}" "$out"
chmod +x "$out"
echo "$out"
