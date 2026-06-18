# Phang Quickstart

## What Phang Does

Phang is a local phage-genomics pipeline that takes one or more phage FASTA files and produces an NCBI BankIt submission package, an interactive HTML report card, and a full set of organized intermediate analysis outputs.

## Supported Platforms

| Platform | Support |
|----------|---------|
| macOS (Intel & Apple Silicon) | Fully supported |
| Windows 11 with WSL2 (Ubuntu) | Fully supported |
| Linux (Ubuntu/Debian) | Should work — not yet validated |
| Native Windows (no WSL2) | Not supported — bioconda tools require Linux |

## Prerequisites

### macOS

- [Miniforge3](https://github.com/conda-forge/miniforge/releases/latest) or Miniconda installed and on PATH
- Git available (`brew install git` if needed)
- ~25 GB free disk space for tool environments and databases

### Windows

- WSL2 enabled with an Ubuntu distribution installed
- [Miniforge3](https://github.com/conda-forge/miniforge/releases/latest) installed **inside WSL2** (not Windows-side conda)
- Git available inside WSL2 (`sudo apt install git`)
- ~25 GB free disk space (inside WSL2 or a mounted drive)

To enable WSL2 and install Ubuntu, open PowerShell as Administrator and run:

```powershell
wsl --install
```

Then install Miniforge3 inside WSL2:

```bash
wsl
curl -L https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh -o miniforge.sh
bash miniforge.sh -b -p ~/miniforge3
~/miniforge3/bin/conda init bash
exit
```

## Install Phang

### macOS

```bash
cd /path/to/phang
pip install -e .
```

### Windows (run all commands from PowerShell or Command Prompt)

The project lives on your Windows filesystem but runs inside WSL2. The path `C:\Users\you\phang` maps to `/mnt/c/Users/you/phang` inside WSL2.

```powershell
wsl -- bash -c "export PATH=""$HOME/miniforge3/bin:$PATH"" && pip install -e '/mnt/c/Users/you/OneDrive/Desktop/phang'"
```

Replace the path with the actual location of the phang folder on your machine.

## Install All Tools and Databases

After installing the phang package, run the one-time installer. This downloads and sets up all managed tools and databases (~25 GB) under `~/.phang/`:

### macOS

```bash
phang install
```

### Windows

```powershell
wsl -- bash -c 'export PATH="$HOME/miniforge3/bin:$PATH" && phang install'
```

This takes 15–30 minutes depending on your internet connection. It is safe to re-run — already-installed components are skipped. If it is interrupted, run the same command again to resume.

Tools and databases are installed to:

- `~/.phang/envs/` — one conda environment per tool
- `~/.phang/databases/` — reference databases

## Run the Pipeline

### macOS

```bash
phang run --input /path/to/phage.fasta --output ./phang_output --threads 8 --verbose
```

### Windows

```powershell
wsl -- bash -c 'export PATH="$HOME/miniforge3/bin:$PATH" && phang run --input "/mnt/c/Users/you/phage.fasta" --output ~/phang_output --threads 8 --verbose'
```

Accepted input types:

- a single FASTA file
- a directory of FASTA files
- a multi-record FASTA file

Useful optional flags:

| Flag | Effect |
|------|--------|
| `--threads N` | CPU threads for parallel tools (default: 8) |
| `--gpu` | Force GPU (CUDA/MPS) |
| `--cpu` | Force CPU-only |
| `--force` | Overwrite existing outputs |
| `--verbose` | Print debug-level logs to console |

## Open the GUI

```bash
phang gui
```

The GUI lets you choose inputs and outputs without running commands in the terminal.

## Create a Desktop Shortcut (macOS / Linux)

```bash
phang setup
```

## Where Outputs Go

```text
<output>/
├── <phage_name>/
│   └── report_card.html      ← main interactive report
├── ncbi/
│   ├── bankit_multi.fasta    ← NCBI BankIt submission
│   └── bankit_features.tbl
├── _logs/                    ← per-step logs
└── phang_run.log             ← full run log
```

## Expected Runtime (single phage genome)

| Step | Tool | Typical time |
|------|------|-------------|
| s01 | Pharokka | ~2 min |
| s02 | Phold | ~36 s |
| s03 | Phynteny | <5 s |
| s04 | PhaStyle | ~18 s |
| s05 | PhaBOX2/CHERRY | ~34 s |
| s06 | vConTACT3 | ~4 min |
| s07 | DefenseFinder + RBPdetect | ~10 s |
| s08 | DepoScope | ~21 s |
| s09–s11 | Viz + NCBI + Report | ~11 s |
| **Total** | | **~8–9 min** |

## Troubleshooting

- **"command not found: phang"** — conda/miniforge3 is not on PATH. Prefix commands with `export PATH="$HOME/miniforge3/bin:$PATH"`.
- **"Neither conda nor mamba was found"** — same cause. Ensure miniforge3 is installed inside WSL2, not only on the Windows side.
- **Install interrupted** — re-run `phang install`. It skips already-completed steps.
- **Verbose logs** — add `--verbose` to any `phang run` command and inspect `<output>/phang_run.log` and `<output>/_logs/`.
- **Full reset** — delete `~/.phang` and re-run `phang install` to start from scratch:

  ```bash
  rm -rf ~/.phang
  phang install
  ```
