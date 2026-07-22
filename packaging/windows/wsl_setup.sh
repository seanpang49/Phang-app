#!/usr/bin/env bash
# =============================================================================
# Phang — Windows (WSL2) setup driver.  RUNS INSIDE WSL2 (Ubuntu).
# =============================================================================
# This is the Windows analogue of packaging/mac/post_install.sh + the first-run
# bootstrap.  It is invoked by ../windows/phang_setup.ps1 (or the Inno Setup
# installer), but is also safe to run by hand:
#
#     wsl -- bash /mnt/c/path/to/Phang-app/packaging/windows/wsl_setup.sh all
#
# Execution model (Model A): EVERYTHING runs inside WSL2 — Python, phang, the 9
# Bioconda tool-envs, and the Tkinter GUI (rendered on the Windows desktop via
# WSLg).  The Windows side is only a launcher.  See packaging/windows/README.md.
#
# Subcommands:
#   install     Ensure Miniforge + create the `phang` conda env + install phang.
#   bootstrap   Download the 9 tool-envs and ~30 GB of databases into ~/.phang.
#   all         install, then bootstrap  (default).
#   gui         Launch the Phang GUI (via WSLg).
#   run  ...    Forward remaining args to `phang run ...`.
#   doctor      Print environment / GPU / install status and exit.
#
# Tunables (environment variables):
#   PHANG_ENV      conda env name                  (default: phang)
#   PHANG_PY       Python version for the env       (default: 3.11)
#   MINIFORGE      Miniforge prefix                 (default: $HOME/miniforge3)
#   PHANG_SRC      phang source: a directory OR a   (default: the git repo URL)
#                  "git+https://…" URL that pip can install.
# =============================================================================

# NOTE: intentionally NOT using `set -u` — conda's activation scripts reference
# unbound shell variables and would trip it.  We keep -e and pipefail.
set -eo pipefail

PHANG_ENV="${PHANG_ENV:-phang}"
PHANG_PY="${PHANG_PY:-3.11}"
MINIFORGE="${MINIFORGE:-$HOME/miniforge3}"
PHANG_SRC="${PHANG_SRC:-git+https://github.com/seanpang49/Phang-app.git}"
MINIFORGE_URL="https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh"

# --- pretty logging ---------------------------------------------------------
_c() { printf '\033[%sm' "$1" 2>/dev/null || true; }
BOLD="$(_c '1;36')"; GOOD="$(_c '1;32')"; WARN="$(_c '1;33')"; ERR="$(_c '1;31')"; OFF="$(_c '0')"
log()  { echo "${BOLD}==>${OFF} $*"; }
ok()   { echo "${GOOD}  ok:${OFF} $*"; }
warn() { echo "${WARN}  warn:${OFF} $*" >&2; }
die()  { echo "${ERR}ERROR:${OFF} $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 1. Miniforge (conda) — install into $MINIFORGE if it is not already there.
# ---------------------------------------------------------------------------
ensure_miniforge() {
  if [ -x "$MINIFORGE/bin/conda" ]; then
    ok "Miniforge present: $MINIFORGE"
    return
  fi
  log "Installing Miniforge3 into $MINIFORGE (one-time, ~5 min)…"
  command -v curl >/dev/null 2>&1 || command -v wget >/dev/null 2>&1 \
    || die "Neither curl nor wget is available inside WSL2. Run: sudo apt-get update && sudo apt-get install -y curl"
  local sh="/tmp/miniforge_installer.sh"
  if command -v curl >/dev/null 2>&1; then
    curl -fL "$MINIFORGE_URL" -o "$sh"
  else
    wget -O "$sh" "$MINIFORGE_URL"
  fi
  bash "$sh" -b -p "$MINIFORGE"
  rm -f "$sh"
  ok "Miniforge installed."
}

# Source conda so `conda activate` works in this non-interactive shell.
activate_conda() {
  # shellcheck disable=SC1091
  source "$MINIFORGE/etc/profile.d/conda.sh"
  conda activate base
}

# ---------------------------------------------------------------------------
# 2. The `phang` conda env + the phang package.
# ---------------------------------------------------------------------------
env_prefix() { echo "$MINIFORGE/envs/$PHANG_ENV"; }

ensure_env() {
  local prefix; prefix="$(env_prefix)"
  if [ -f "$prefix/conda-meta/history" ]; then
    ok "conda env '$PHANG_ENV' already exists."
  else
    log "Creating conda env '$PHANG_ENV' (Python $PHANG_PY + Tk for the GUI)…"
    # tk  → tkinter (the GUI toolkit); git → some tool installers fetch from git;
    # pip → to install the phang package and its PyPI-only deps (tkinterdnd2).
    conda create -y -n "$PHANG_ENV" -c conda-forge \
      "python=$PHANG_PY" tk git pip
    ok "Env created: $prefix"
  fi
}

install_phang() {
  log "Installing the phang package into '$PHANG_ENV' from: $PHANG_SRC"
  conda run --no-capture-output -n "$PHANG_ENV" python -m pip install --upgrade pip >/dev/null
  # A non-editable install copies phang into the env's site-packages (WSL2
  # native FS), so it keeps working even if the Windows-side source is removed.
  conda run --no-capture-output -n "$PHANG_ENV" python -m pip install "$PHANG_SRC"
  local ver
  ver="$(conda run --no-capture-output -n "$PHANG_ENV" phang --version 2>&1 | tr -d '\r')"
  [ -n "$ver" ] || die "phang installed but 'phang --version' produced no output."
  ok "Installed: $ver"
}

# ---------------------------------------------------------------------------
# 3. Bootstrap — the heavy first-run download (9 tool-envs + ~30 GB databases).
#    Idempotent & resumable: re-running skips completed components.
# ---------------------------------------------------------------------------
bootstrap_phang() {
  log "Bootstrapping tools + databases into ~/.phang (this is the ~30 GB step)…"
  warn "Keep this window open. First run takes 15-60+ min depending on your connection."
  # Unbuffered so progress lines stream to the installer console / log in real time.
  conda run --no-capture-output -n "$PHANG_ENV" python -u -m phang.cli bootstrap
  ok "Bootstrap complete. Manifest: ~/.phang/DB_MANIFEST.json"
}

# ---------------------------------------------------------------------------
# 4. GUI / run passthroughs.
# ---------------------------------------------------------------------------
launch_gui() {
  log "Launching Phang GUI (WSLg)…"
  # Agg keeps matplotlib headless for the genome-map rendering; the Tkinter
  # window itself is shown by WSLg's Wayland/X server (built into Windows 11).
  MPLBACKEND=Agg conda run --no-capture-output -n "$PHANG_ENV" phang gui
}

run_phang() {
  # The `run` subcommand forwards its args to `phang run ...` (see header).
  MPLBACKEND=Agg conda run --no-capture-output -n "$PHANG_ENV" phang run "$@"
}

# ---------------------------------------------------------------------------
# 5. Doctor — quick environment report.
# ---------------------------------------------------------------------------
doctor() {
  echo "── Phang WSL2 doctor ─────────────────────────────────────────────"
  echo "distro:     $(. /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-unknown}")"
  echo "kernel:     $(uname -r)"
  echo "miniforge:  $MINIFORGE  ($( [ -x "$MINIFORGE/bin/conda" ] && echo present || echo MISSING ))"
  echo "env:        $PHANG_ENV  ($( [ -f "$(env_prefix)/conda-meta/history" ] && echo present || echo MISSING ))"
  if [ -x "$MINIFORGE/bin/conda" ]; then
    activate_conda
    echo "phang:      $(conda run --no-capture-output -n "$PHANG_ENV" phang --version 2>/dev/null | tr -d '\r' || echo 'not installed')"
  fi
  if command -v nvidia-smi >/dev/null 2>&1; then
    echo "gpu:        $(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1) (CUDA-on-WSL2)"
  else
    echo "gpu:        none visible in WSL2 → CPU fallback"
  fi
  if [ -f "$HOME/.phang/DB_MANIFEST.json" ]; then
    echo "bootstrap:  complete (~/.phang/DB_MANIFEST.json present)"
  else
    echo "bootstrap:  NOT complete (run: wsl_setup.sh bootstrap)"
  fi
  echo "──────────────────────────────────────────────────────────────────"
}

# ---------------------------------------------------------------------------
main() {
  local cmd="${1:-all}"; shift || true
  case "$cmd" in
    doctor)     doctor ;;
    install)    ensure_miniforge; activate_conda; ensure_env; install_phang ;;
    bootstrap)  ensure_miniforge; activate_conda; bootstrap_phang ;;
    all)        ensure_miniforge; activate_conda; ensure_env; install_phang; bootstrap_phang
                ok "Phang is fully set up. Launch it with: wsl_setup.sh gui" ;;
    gui)        ensure_miniforge; activate_conda; launch_gui ;;
    run)        ensure_miniforge; activate_conda; run_phang "$@" ;;
    *)          die "Unknown subcommand '$cmd' (use: install | bootstrap | all | gui | run | doctor)" ;;
  esac
}

main "$@"
