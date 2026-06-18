#!/bin/bash
# ============================================================
# Phang batch runner — edit the three variables below, then run:
#   bash run_batch.sh
# ============================================================

# Path to your batch list markdown file (Windows path via /mnt/c/...)
BATCH_LIST="/mnt/c/Users/YOUR_NAME/Desktop/phang/phage_batch_list.md"

# Parent folder that contains all your phage FASTA sub-folders
INPUT_DIR="/mnt/c/Users/YOUR_NAME/Downloads/Phage sequencing"

# Where outputs are written (inside WSL home is fine)
OUTPUT_DIR="$HOME/phang_batch_output"

# ============================================================
export PATH="$HOME/miniforge3/bin:$HOME/miniforge3/condabin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

python3 -m phang batch \
  --list   "$BATCH_LIST" \
  --input-dir "$INPUT_DIR" \
  --output "$OUTPUT_DIR" \
  --verbose
