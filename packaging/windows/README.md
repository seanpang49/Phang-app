# Phang — Windows installer (WSL2)

The Windows analogue of `packaging/mac/`. Phang's analysis tools are Bioconda
packages (Linux/macOS only), so on Windows **everything runs inside WSL2**
(Windows Subsystem for Linux 2) and the Windows side is only a launcher. This is
**Model A** — the Tkinter GUI itself renders on the Windows desktop through
**WSLg** (built into Windows 11), and the NVIDIA GPU passes through to WSL2 via
the CUDA-on-WSL driver.

## What the installer does

| Done at install time (fast, needs internet) | Done on first launch |
|---|---|
| Verify WSL2 + an Ubuntu distro (guide `wsl --install` if missing) | The **9 analysis tool-envs** (pharokka, phold, phynteny, phastyle, phabox2, defensefinder, vcontact3, rbpdetect, deposcope) |
| Ensure **Miniforge3** inside WSL2 | Their **reference databases**, ~30 GB (from Zenodo) |
| Create the `phang` conda env + `pip install` phang inside WSL2 | A `DB_MANIFEST.json` marking setup complete |
| Create Start-Menu + Desktop shortcuts | |

**Why the split?** Same reason as the macOS `.pkg`: the ~30 GB download is
long, per-user, and resumable, so it belongs in the first-run GUI (which already
shows a progress window, `phang/gui/app.py`) rather than behind a generic
installer progress bar. `~/.phang` is deliberately placed on the **WSL2 native
filesystem** (`/home/<user>/.phang`), never `/mnt/c`, because cross-OS small-file
I/O over `/mnt/c` makes conda env creation and tool runs crawl.

## Files

- **`wsl_setup.sh`** — runs *inside* WSL2. The heart of the port: ensures
  Miniforge, creates the `phang` conda env, installs phang, and drives
  `phang bootstrap`. Subcommands: `install | bootstrap | all | gui | run | doctor`.
  Also usable by hand:
  `wsl -- bash /mnt/c/.../packaging/windows/wsl_setup.sh doctor`
- **`phang_setup.ps1`** — the Windows-side orchestrator. Checks WSL2, stages
  `wsl_setup.sh` into WSL2, runs it, and creates the launchers. This *is* a
  complete installer on its own.
- **`Install-Phang.bat`** — double-click entry point; runs `phang_setup.ps1`
  with an execution-policy bypass so users needn't touch PowerShell settings.
- **`phang.iss`** — [Inno Setup](https://jrsoftware.org/isdl.php) script that
  wraps the above into a single `Phang-<ver>-Windows-x64-Setup.exe` with an
  Add/Remove-Programs entry (the polished, `.pkg`-equivalent deliverable).

## Install (for users)

**Easiest:** double-click **`Install-Phang.bat`** (or run the `.exe` once built).

**Requirements**
- Windows 11 (recommended — WSLg shows the GUI) or Windows 10 22H2 with WSLg.
- WSL2 + an Ubuntu distro. No WSL2 yet? Open **PowerShell as Administrator**,
  run `wsl --install`, reboot, finish the Ubuntu user setup, then run the installer.
- ~40 GB free disk and an internet connection for the one-time first-run download.
- Optional: an NVIDIA GPU + the [CUDA-on-WSL driver](https://developer.nvidia.com/cuda/wsl)
  for acceleration. No GPU → automatic CPU fallback.

Advanced: `Install-Phang.bat -SkipBootstrap` sets up phang but defers the 30 GB
download to the first time you open Phang.

## Build the `.exe` (for maintainers)

```powershell
winget install JRSoftware.InnoSetup      # one-time
iscc packaging\windows\phang.iss
# -> packaging\windows\out\Phang-0.2.8-Windows-x64-Setup.exe
```

> Bumping `version` in `pyproject.toml`? Update `#define AppVer` at the top of
> `phang.iss` to match.

## Test (on a clean Windows 11 PC)

1. Run the installer; if WSL2 is absent it guides `wsl --install` + reboot.
2. Confirm the `phang` env is created and phang installs
   (`wsl -- bash ~/.phang-setup/wsl_setup.sh doctor`).
3. Open **Phang** from the Start Menu. First launch downloads tools + databases
   with a progress window; when done, drag in a folder of FASTAs → **Run Pipeline**.
4. Confirm 12/12 steps complete and `report_card.html` is produced; with an
   NVIDIA GPU, confirm the CUDA path is used (`wsl -- nvidia-smi`).

Logs: `~/.phang/…/phang_run.log` and per-step `_logs/` inside the output folder.
Data: `~/.phang/` inside WSL2 (envs + databases).

## Not done here (later)

- **Code signing** (Authenticode) to drop the SmartScreen "Run anyway" prompt —
  this beta is intentionally unsigned, mirroring the unsigned macOS beta.
- **Windows 10 without WSLg** — GUI needs WSLg; on older builds use an X server
  (VcXsrv) or run headless via `wsl -- bash ~/.phang-setup/wsl_setup.sh run -i … -o …`.
- A **clean-PC end-to-end test** must be run on a second machine — it cannot be
  fully validated on the build machine.
