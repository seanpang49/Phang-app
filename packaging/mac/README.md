# Phang — macOS installer (Apple Silicon)

Builds an unsigned `.pkg` for Apple Silicon (`osx-arm64`) using conda
[`constructor`](https://github.com/conda/constructor).

## What the installer contains

| Shipped in the `.pkg` | Installed on first launch |
|---|---|
| A self-contained conda **base env**: Python 3.11, `conda` + libmamba solver, and the GUI's runtime deps (pandas, pyarrow, matplotlib, biopython, jinja2, pyCirclize) | The **9 analysis tool-envs** (pharokka, phold, phynteny, phastyle, phabox2, defensefinder, vcontact3, rbpdetect, deposcope) |
| The `phang` package (installed into the base env by `post_install.sh`) | Their **reference databases**, ~30 GB incl. the 13 GB phold_db |
| `/Applications/Phang.app` launcher | A `DB_MANIFEST.json` marking setup complete |

**Why the split?** A conda `.pkg` runs its `post_install` as **root** behind the
installer's generic, non-cancelable progress bar with `$HOME=/var/root`. Pushing
a multi-hour ~30 GB download through there means root-owned user data, broken
per-user permissions, and no real progress. Instead the heavy step runs on first
launch via `phang bootstrap` (wired into the GUI, `phang/gui/app.py`), per-user,
with a visible and resumable progress window.

## Build

Requires an Apple Silicon Mac with the isolated Passport miniforge and a build
env containing `constructor`:

```bash
# one-time: create the build env (if missing)
mamba create -p /Volumes/Passport/miniforge3/envs/_pkgbuild \
  -c conda-forge python=3.11 constructor pip wheel setuptools -y

# build
source /Volumes/Passport/phang.envrc      # isolation: HOME/TMPDIR/caches on Passport
bash packaging/mac/build.sh
```

`build.sh` (1) builds the `phang` wheel into `dist/`, (2) generates `Phang.icns`
from `phang/gui/assets/icon.png`, and (3) runs `constructor --platform osx-arm64`.
Output: `packaging/mac/out/Phang-0.2.0-osx-arm64.pkg`.

> Bumping `version` in `pyproject.toml`? Also update the wheel filename in
> `construct.yaml`'s `extra_files:` — `build.sh` fails loudly if they diverge.

## Test (on a clean Apple Silicon Mac)

1. Copy the `.pkg` over and double-click it; complete the installer.
2. Open **Phang** from `/Applications`. Because the beta is unsigned, the first
   open is blocked — **right-click (Control-click) → Open**, then confirm
   **Open**. (Or: System Settings → Privacy & Security → "Open Anyway".)
3. First launch shows the one-time setup window downloading tools + databases.
   When it finishes, drag a folder of FASTAs in and **Run Pipeline**.
4. Confirm it runs natively (no Rosetta prompt, no SIGILL) and produces
   `report_card.html`.

Logs: `~/Library/Logs/Phang/phang-gui.log`. Data: `~/.phang/` (envs + databases).

## Files

- `construct.yaml` — constructor spec (base env, channels, unsigned, texts).
- `post_install.sh` — root post-install: pip-installs the phang wheel into the
  base env and creates `/Applications/Phang.app`. No heavy downloads.
- `build.sh` — wheel + icns + constructor driver.

## Not done here (later)

- **Signing + notarization** (Developer ID) to drop the right-click-Open step.
- **Intel (`osx-64`) build** — deferred; this beta is Apple Silicon only.
- **Clean-Mac end-to-end test** must be run on a second machine — it cannot be
  validated on the build machine.
