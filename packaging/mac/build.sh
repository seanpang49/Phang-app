#!/bin/bash
# Build the Phang Apple Silicon (.pkg) installer with conda constructor.
#
# Run on an Apple Silicon Mac using the isolated Passport miniforge. It:
#   1. builds the phang wheel into packaging/mac/dist/
#   2. generates the app icon (Phang.icns) from phang/gui/assets/icon.png
#   3. runs constructor against construct.yaml → packaging/mac/out/Phang-*.pkg
#
# Isolation: source /Volumes/Passport/phang.envrc first so HOME/TMPDIR/caches
# stay on the Passport. CONDA_SUBDIR is forced to osx-arm64 below.
#
# Usage:
#   source /Volumes/Passport/phang.envrc
#   bash packaging/mac/build.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # packaging/mac
REPO="$(cd "$HERE/../.." && pwd)"                       # repo root

BUILD_ENV="${PHANG_BUILD_ENV:-/Volumes/Passport/miniforge3/envs/_pkgbuild}"
PY="$BUILD_ENV/bin/python"
CONSTRUCTOR="$BUILD_ENV/bin/constructor"

if [ ! -x "$CONSTRUCTOR" ]; then
  echo "ERROR: constructor not found at $CONSTRUCTOR" >&2
  echo "Create the build env first, e.g.:" >&2
  echo "  mamba create -p $BUILD_ENV -c conda-forge python=3.11 constructor pip wheel setuptools -y" >&2
  exit 1
fi

# Build native arm64 artifacts regardless of the sourced default.
export CONDA_SUBDIR=osx-arm64

echo "==> Repo:      $REPO"
echo "==> Build env: $BUILD_ENV"
echo "==> Subdir:    $CONDA_SUBDIR"

# ---------------------------------------------------------------------------
# 1. phang wheel
# ---------------------------------------------------------------------------
echo "==> [1/3] Building phang wheel"
rm -rf "$HERE/dist"
mkdir -p "$HERE/dist"
"$PY" -m pip wheel "$REPO" --no-deps --no-build-isolation -w "$HERE/dist"
WHEEL="$(ls "$HERE"/dist/phang-*.whl | head -1)"
echo "    $WHEEL"

# construct.yaml lists an explicit wheel filename; verify it matches the build
# so a version bump in pyproject.toml fails loudly here instead of in constructor.
EXPECT="$(grep -oE 'phang-[0-9][^ ]*\.whl' "$HERE/construct.yaml" | head -1)"
if [ -n "$EXPECT" ] && [ "$(basename "$WHEEL")" != "$EXPECT" ]; then
  echo "ERROR: built wheel $(basename "$WHEEL") != construct.yaml's $EXPECT" >&2
  echo "       Update the extra_files entry in construct.yaml to match." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# 2. app icon
# ---------------------------------------------------------------------------
echo "==> [2/3] Generating Phang.icns"
ICON_SRC="$REPO/phang/gui/assets/icon.png"
rm -f "$HERE/Phang.icns"
if command -v iconutil >/dev/null 2>&1 && command -v sips >/dev/null 2>&1 && [ -f "$ICON_SRC" ]; then
  ICONSET="$(mktemp -d)/Phang.iconset"; mkdir -p "$ICONSET"
  for s in 16 32 128 256 512; do
    sips -z "$s" "$s"             "$ICON_SRC" --out "$ICONSET/icon_${s}x${s}.png"    >/dev/null 2>&1 || true
    sips -z "$((s*2))" "$((s*2))" "$ICON_SRC" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null 2>&1 || true
  done
  if iconutil -c icns "$ICONSET" -o "$HERE/Phang.icns" 2>/dev/null; then
    echo "    Phang.icns created"
  else
    echo "    WARN: iconutil failed — building without a custom icon"
  fi
else
  echo "    WARN: iconutil/sips/icon.png unavailable — building without a custom icon"
fi

# construct.yaml references Phang.icns in extra_files; if we couldn't make one,
# drop the line from a temporary copy so the build still succeeds.
CONSTRUCT_DIR="$HERE"
if [ ! -f "$HERE/Phang.icns" ]; then
  CONSTRUCT_DIR="$(mktemp -d)"
  grep -v 'Phang.icns' "$HERE/construct.yaml" > "$CONSTRUCT_DIR/construct.yaml"
  cp "$HERE/post_install.sh" "$CONSTRUCT_DIR/"
  mkdir -p "$CONSTRUCT_DIR/dist"; cp "$HERE"/dist/phang-*.whl "$CONSTRUCT_DIR/dist/"
fi

# ---------------------------------------------------------------------------
# 3. constructor
# ---------------------------------------------------------------------------
echo "==> [3/3] Running constructor (osx-arm64)"
rm -rf "$HERE/out"; mkdir -p "$HERE/out"
"$CONSTRUCTOR" "$CONSTRUCT_DIR" --platform osx-arm64 --output-dir "$HERE/out"

echo ""
echo "==> Built:"
ls -lh "$HERE"/out/*.pkg
echo ""
echo "Next: test on a CLEAN Apple Silicon Mac — install the .pkg, then open"
echo "Phang from /Applications (right-click → Open the first time; it is unsigned)."
