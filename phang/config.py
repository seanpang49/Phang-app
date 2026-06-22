"""
Central configuration: all paths and constants for the phang pipeline.
"""

import os
from pathlib import Path

VERSION = "0.2.4"

# --- Base directories ---
# Defaults to ~/.phang, but the PHANG_HOME environment variable takes
# precedence so installers (Mac .pkg post-install, Windows launcher) can
# place data deliberately without relying on a fragile HOME override.
PHANG_HOME = Path(os.environ.get("PHANG_HOME") or Path.home() / ".phang")
ENVS_DIR = PHANG_HOME / "envs"
DB_DIR = PHANG_HOME / "databases"

# --- Conda environment paths ---
ENV_PHAROKKA = ENVS_DIR / "pharokka"
ENV_PHOLD = ENVS_DIR / "phold"
ENV_PHYNTENY = ENVS_DIR / "phynteny"
ENV_PHASTYLE = ENVS_DIR / "phastyle"
ENV_PHABOX2 = ENVS_DIR / "phabox2"
ENV_CHERRY = ENV_PHABOX2
ENV_DEFENSEFINDER = ENVS_DIR / "defensefinder"
ENV_VCONTACT3 = ENVS_DIR / "vcontact3"
ENV_RBPDETECT = ENVS_DIR / "rbpdetect"
ENV_DEPOSCOPE = ENVS_DIR / "deposcope"
# Dedicated env for phanotate (DepoScope shells out to phanotate.py). Kept
# separate because the only arm64 phanotate build is on bioconda for py3.9,
# while the deposcope env is py3.10 for the ESM-2 stack.
ENV_PHANOTATE = ENVS_DIR / "phanotate"

# --- Database paths ---
DB_PHAROKKA = DB_DIR / "pharokka_db"
DB_PHOLD = DB_DIR / "phold_db"
DB_PHYNTENY_MODELS = DB_DIR / "phynteny_models"
DB_PHABOX2 = DB_DIR / "phabox_db_v2_1"
DB_CHERRY = DB_PHABOX2
DB_DEFENSEFINDER_MODELS = DB_DIR / "defensefinder_models"
DB_VCONTACT3 = DB_DIR / "vcontact3_db"

# --- Python version pins per environment ---
PYTHON_VERSIONS = {
    "pharokka": "3.12",
    "phold": "3.12",
    "phynteny": "3.9",
    "phastyle": "3.12",
    "phabox2": "3.9",
    "cherry": "3.9",
    "defensefinder": "3.10",
    "vcontact3": "3.10",
    "rbpdetect": "3.10",
    "deposcope": "3.10",
    "phanotate": "3.9",
}

# --- FASTA extensions recognised by the pipeline ---
FASTA_EXTENSIONS = {".fa", ".fna", ".fasta"}

# --- Conda channels used for bioinformatics installs ---
CONDA_CHANNELS = ["-c", "conda-forge", "-c", "bioconda"]

# --- Manifest filename used inside each DB directory ---
DB_MANIFEST_FILENAME = "DB_MANIFEST.json"
