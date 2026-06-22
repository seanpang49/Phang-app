#!/bin/bash
# Phang macOS .pkg post-install — runs as ROOT during installation.
#
# Deliberately light and root-safe:
#   1. install the bundled phang wheel into the base env (deps already baked in
#      via construct.yaml; only tkinterdnd2 comes from PyPI and is optional)
#   2. create the /Applications/Phang.app launcher
#
# The heavy first-run work (9 conda tool-envs + ~30 GB databases) is NOT done
# here. It runs on first launch via `phang bootstrap`, wired into the GUI, so it
# executes per-user with a visible, resumable progress window instead of as root
# behind the installer's generic progress bar.

set -euo pipefail

# constructor sets PREFIX to the installed base-env prefix.
: "${PREFIX:?post-install requires PREFIX (set by constructor)}"

PY="$PREFIX/bin/python"
LOG="${TMPDIR:-/tmp}/phang_postinstall.log"
exec > >(tee -a "$LOG") 2>&1

echo "[phang post-install] $(date)"
echo "[phang post-install] PREFIX=$PREFIX"

# ---------------------------------------------------------------------------
# 1. Install the bundled phang wheel into the base env.
# ---------------------------------------------------------------------------
WHEEL="$(ls "$PREFIX"/phang-*.whl 2>/dev/null | head -1 || true)"
if [ -z "$WHEEL" ]; then
  echo "[phang post-install] ERROR: phang wheel not found in $PREFIX" >&2
  exit 1
fi

echo "[phang post-install] installing $(basename "$WHEEL") (offline, deps prebaked)"
"$PY" -m pip install --no-deps --no-index "$WHEEL" || {
  echo "[phang post-install] ERROR: failed to install the phang wheel" >&2
  exit 1
}

# tkinterdnd2 enables drag-and-drop and is the only runtime dep not on
# conda-forge. Fetched from PyPI here; non-fatal if offline (the GUI degrades to
# click-to-browse, see phang/gui/app.py).
echo "[phang post-install] fetching tkinterdnd2 (drag-and-drop; optional)…"
"$PY" -m pip install --no-deps tkinterdnd2 \
  || echo "[phang post-install] WARN: tkinterdnd2 not installed (offline?) — GUI will be click-only."

rm -f "$WHEEL"

# ---------------------------------------------------------------------------
# 2. Create the /Applications/Phang.app launcher.
# ---------------------------------------------------------------------------
APP="/Applications/Phang.app"
echo "[phang post-install] creating $APP"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

# Launcher script: put the base env on PATH (so `conda` is found for the
# first-run bootstrap) and log to ~/Library/Logs/Phang/. $PREFIX is baked in;
# $HOME / $PATH stay as runtime variables (escaped below).
cat > "$APP/Contents/MacOS/Phang" <<LAUNCHER
#!/bin/bash
export PATH="$PREFIX/bin:\$PATH"
export MPLBACKEND=Agg
mkdir -p "\$HOME/Library/Logs/Phang"
exec "$PREFIX/bin/phang" gui >> "\$HOME/Library/Logs/Phang/phang-gui.log" 2>&1
LAUNCHER
chmod +x "$APP/Contents/MacOS/Phang"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Phang</string>
  <key>CFBundleDisplayName</key><string>Phang</string>
  <key>CFBundleIdentifier</key><string>org.phang.gui</string>
  <key>CFBundleVersion</key><string>0.2.3</string>
  <key>CFBundleShortVersionString</key><string>0.2.3</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>Phang</string>
  <key>CFBundleIconFile</key><string>Phang</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

# Optional custom icon (bundled by build.sh as Phang.icns).
if [ -f "$PREFIX/Phang.icns" ]; then
  cp "$PREFIX/Phang.icns" "$APP/Contents/Resources/Phang.icns"
  rm -f "$PREFIX/Phang.icns"
fi

# Refresh Launch Services / icon caches so the new app appears promptly.
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister \
  -f "$APP" >/dev/null 2>&1 || true

echo "[phang post-install] done — open Phang from /Applications (first launch sets up tools + databases)."
exit 0
