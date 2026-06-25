# 🦠 Phang

**End-to-end bacteriophage genome characterisation — from FASTA to a phage-therapy verdict, in one click.**

[![Latest release](https://img.shields.io/github/v/release/seanpang49/Phang-app?label=download&color=6366f1)](../../releases/latest)
[![Platform](https://img.shields.io/badge/platform-Apple%20Silicon-000000?logo=apple&logoColor=white)](../../releases/latest)
[![License: MIT](https://img.shields.io/github/license/seanpang49/Phang-app?color=brightgreen)](LICENSE)
[![Downloads](https://img.shields.io/github/downloads/seanpang49/Phang-app/total?color=blue)](../../releases)

Phang takes one or more bacteriophage genome FASTA files and runs a 12-step pipeline across **nine specialised tools** to annotate genes, predict lifestyle and host, place the phage in viral taxonomy, screen for safety red-flags, and judge **phage-therapy suitability** — then packages everything into an interactive HTML report card and a submission-ready NCBI BankIt file.

No terminal, no conda setup: **download the macOS installer, double-click, and run.**

---

## ✨ Highlights

- **One-click desktop app** for Apple Silicon Macs — no command line needed.
- **Phage-therapy verdict** — flags whether a phage is a candidate (strictly lytic, and free of antimicrobial-resistance / virulence / lysogeny genes), and shows the evidence behind every call.
- **Interactive report card** — genome map, gene annotations, lifestyle, predicted host, viral taxonomy, defense systems, depolymerases, and receptor-binding proteins.
- **Batch dashboard** — analyse many phages at once and compare them at a glance.
- **NCBI BankIt package** — submission-ready FASTA + feature table.
- **Nine tools, one workflow** — Pharokka, Phold, Phynteny, PhaStyle, PhaBOX2/CHERRY, vConTACT3, DefenseFinder, PhageRBPdetect, DepoScope.

## 💻 Requirements

- Apple Silicon Mac (M1 or later) — runs natively, no Rosetta
- macOS 11 or later
- ~35 GB free disk space (a one-time ~30 GB database download on first launch)
- Internet connection for the first-run setup

## ⬇️ Installation

1. Download **`Phang-<version>-MacOSX-arm64.pkg`** from the **[latest release](../../releases/latest)** and double-click it.
2. This beta is **unsigned**, so macOS Gatekeeper blocks it the first time:
   - **macOS 15 (Sequoia) or later** — on the *"cannot be opened…"* warning click **Done**, then open **System Settings → Privacy & Security**, scroll to **Security**, and click **Open Anyway**.
   - **macOS 11–14** — right-click (Control-click) the file in Finder → **Open** → **Open**.
3. Click through the installer (**Continue → Install**; it asks for your Mac password). Phang installs to **/Applications**.
4. Open **Phang** from Applications or Launchpad. The app is also unsigned, so apply the **same Gatekeeper step once** the first time you open it.

## 🚀 First launch

On first launch, Phang downloads its analysis tools and reference databases (~30 GB) into `~/.phang`. A progress window shows the status — keep it open. You can quit to pause; finished downloads are kept and it resumes next time.

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
| | | **Total (single genome)** | **~8–9 min** |

## 💊 How the phage-therapy verdict works

A phage is labelled a **candidate** when it is **strictly lytic** *and* shows **no antimicrobial-resistance genes, no virulence factors, and no integrase / recombinase** (lysogeny markers). Antimicrobial-resistance and virulence are judged by Pharokka sequence homology against CARD and VFDB (≥80% identity); low-identity structural look-alikes from Phold are shown as informational notes and do **not** count against a phage. Every call on the report card has a hover tooltip explaining how it was derived.

## 🙏 Acknowledgements

Phang orchestrates these excellent open-source tools — **please cite them** if you use Phang in your work: Pharokka, Phold, Phynteny, PhaStyle (ProkBERT), PhaBOX2 / CHERRY, vConTACT3, DefenseFinder, PhageRBPdetect, and DepoScope.

## 📄 License

[MIT](LICENSE) © seanpang49

---

<sub>Phang is research software provided as an unsigned beta. Results are predictions and should be confirmed experimentally before any clinical or therapeutic decision.</sub>
