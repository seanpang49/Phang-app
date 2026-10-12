# 🦠 Phang

**End-to-end bacteriophage genome characterisation — from FASTA to a phage-therapy verdict, in one click.**

[![Latest release](https://img.shields.io/github/v/release/seanpang49/Phang-app?label=download&color=6366f1)](../../releases/latest)
[![macOS](https://img.shields.io/badge/macOS-Apple%20Silicon-000000?logo=apple&logoColor=white)](../../releases/latest)
[![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011%20(WSL2)-0078D6?logo=windows&logoColor=white)](../../releases/latest)
[![License: MIT](https://img.shields.io/github/license/seanpang49/Phang-app?color=brightgreen)](LICENSE)
[![Downloads](https://img.shields.io/github/downloads/seanpang49/Phang-app/total?color=blue)](../../releases)

Phang takes one or more bacteriophage genome FASTA files and runs a 12-step pipeline across **nine specialised tools** to annotate genes, predict lifestyle and host, place the phage in viral taxonomy, screen for safety red-flags, and judge **phage-therapy suitability** — then packages everything into an interactive HTML report card and a submission-ready NCBI BankIt file.

No terminal, no conda setup: **download the installer for your Mac or Windows PC, double-click, and run.** Both installers carry the same Phang release, so a given version gives the same results on either platform.

---

## ✨ Highlights

- **One-click desktop app** for Apple Silicon Macs and Windows 10/11 PCs — no command line needed.
- **Phage-therapy verdict** — flags whether a phage is a candidate (strictly lytic, and free of antimicrobial-resistance / virulence / lysogeny genes), and shows the evidence behind every call.
- **Interactive report card** — genome map, gene annotations, lifestyle, predicted host, viral taxonomy, defense systems, depolymerases, and receptor-binding proteins.
- **Batch dashboard** — analyse many phages at once and compare them at a glance.
- **NCBI BankIt package** — submission-ready FASTA + feature table.
- **Nine tools, one workflow** — Pharokka, Phold, Phynteny, PhaStyle, PhaBOX2/CHERRY, vConTACT3, DefenseFinder, PhageRBPdetect, DepoScope.

## ⬇️ Download

Every release on the **[Releases page](../../releases/latest)** has one file per platform:

| Platform | File | Requirements |
|---|---|---|
| **macOS** (Apple Silicon) | `Phang-<version>-MacOSX-arm64.pkg` | M1 or later, macOS 11+ (runs natively, no Rosetta) |
| **Windows** 10/11 (64-bit) | `Phang-<version>-Windows-x64-Setup.exe` | Windows 11 recommended, or Windows 10 22H2 with WSLg; WSL2 with Ubuntu |

Both need **~40 GB free disk space** and an internet connection for the one-time ~30 GB tool and database download on first launch. On Windows, an NVIDIA GPU with the [CUDA-on-WSL driver](https://developer.nvidia.com/cuda/wsl) speeds up some steps; without one, Phang falls back to the CPU automatically.

## 🍎 Installation — macOS

1. Download **`Phang-<version>-MacOSX-arm64.pkg`** from the **[latest release](../../releases/latest)** and double-click it.
2. This beta is **unsigned**, so macOS Gatekeeper blocks it the first time:
   - **macOS 15 (Sequoia) or later** — on the *"cannot be opened…"* warning click **Done**, then open **System Settings → Privacy & Security**, scroll to **Security**, and click **Open Anyway**.
   - **macOS 11–14** — right-click (Control-click) the file in Finder → **Open** → **Open**.
3. Click through the installer (**Continue → Install**; it asks for your Mac password). Phang installs to **/Applications**.
4. Open **Phang** from Applications or Launchpad. The app is also unsigned, so apply the **same Gatekeeper step once** the first time you open it.

## 🪟 Installation — Windows

Phang's analysis tools are Linux-only (Bioconda), so on Windows they run inside **WSL2** (Windows Subsystem for Linux). The Phang window opens on your normal Windows desktop.

1. **One-time, if WSL2 is not installed yet:** open **PowerShell as Administrator**, run `wsl --install`, restart the PC, and finish the Ubuntu username/password setup.
2. Download **`Phang-<version>-Windows-x64-Setup.exe`** from the **[latest release](../../releases/latest)** and run it.
   *No-installer alternative:* download `Phang-<version>-Windows-x64.zip`, unzip it, and double-click **`Install-Phang.bat`**.
3. This beta is **unsigned**, so Windows SmartScreen warns the first time: click **More info → Run anyway**.
4. The installer prepares Phang inside WSL2 (a few minutes, needs internet) and adds **Phang** to the Start Menu and Desktop.
5. Open **Phang** from the Start Menu.

## 🚀 First launch

On first launch, Phang downloads its analysis tools and reference databases (~30 GB) into `~/.phang` (on Windows, inside WSL2). A progress window shows the status — keep it open. You can quit to pause; finished downloads are kept and it resumes next time.

## 🧬 Usage

1. Open **Phang**.
2. Click **Choose folder…** and select a FASTA file or a folder of FASTA files.
3. Choose an output folder.
4. Click **Run Pipeline**.

Accepted inputs: a single FASTA file, a folder of FASTA files, or a multi-record FASTA. Each phage gets its own `report_card.html`, and a `batch_dashboard.html` links them all together.

## 📑 What you get

```text
<output>/
├── <phage_name>/
│   └── report_card.html      ← interactive per-phage report
├── batch_dashboard.html      ← overview of every phage
├── ncbi/
│   ├── bankit_multi.fasta    ← NCBI BankIt submission
│   └── bankit_features.tbl
└── _logs/                    ← per-step logs
```

## ⚙️ The pipeline

| # | Tool | What it does | Typical time |
|---|------|--------------|--------------|
| 1 | **Pharokka** | Gene calling + functional annotation (PHROG, CARD, VFDB) | ~2 min |
| 2 | **Phold** | Structure-based annotation (ProstT5 + Foldseek) | ~36 s |
| 3 | **Phynteny** | Synteny-based annotation of hypothetical genes | <5 s |
| 4 | **PhaStyle** | Lifestyle prediction (virulent / temperate) | ~18 s |
| 5 | **PhaBOX2 / CHERRY** | Host prediction | ~34 s |
| 6 | **vConTACT3** | Viral taxonomy (genus / family) | ~4 min |
| 7 | **DefenseFinder + PhageRBPdetect** | Anti-defense systems + receptor-binding proteins | ~10 s |
| 8 | **DepoScope** | Depolymerase detection | ~21 s |
| 9–11 | Genome viz · NCBI · Report | Genome map, BankIt package, report card | ~11 s |
| | | **Total (single genome)** | **~16 min median (12.9-27.9 min, n=35)** |

## 💊 How the phage-therapy verdict works

A phage is labelled a **candidate** when it is **strictly lytic** *and* shows **no antimicrobial-resistance genes, no virulence factors, and no integrase / excisionase** (lysogeny markers). Antimicrobial-resistance and virulence are judged by Pharokka sequence homology against CARD and VFDB (≥80% identity); low-identity structural look-alikes from Phold are shown as informational notes and do **not** count against a phage. Every call on the report card has a hover tooltip explaining how it was derived.

## 🙏 Acknowledgements

Phang orchestrates these excellent open-source tools — **please cite them** if you use Phang in your work: Pharokka, Phold, Phynteny, PhaStyle (ProkBERT), PhaBOX2 / CHERRY, vConTACT3, DefenseFinder, PhageRBPdetect, and DepoScope.

## 📄 License

[MIT](LICENSE) © seanpang49

---

<sub>Phang is research software provided as an unsigned beta. Results are predictions and should be confirmed experimentally before any clinical or therapeutic decision.</sub>
