# Phage Batch Run — Input List

# Instructions:
# - Set "Source folder" to the parent directory containing all your phage FASTA sub-folders.
# - Each row in the table defines one phage to process.
#   - "Name" becomes the output folder name (use short, unique identifiers).
#   - "Source File" is the path to the FASTA file, relative to the Source folder.
# - Rows starting with # are ignored.
# - The pipeline skips a phage if its output folder already exists (resume-safe).

**Source folder:** `C:\Users\YOUR_NAME\Downloads\Phage sequencing\`

| # | Name    | Source File                                      |
|---|---------|--------------------------------------------------|
| 1 | Phage_A | `Sequencing_run_1/sample_A/assembly.fasta`       |
| 2 | Phage_B | `Sequencing_run_1/sample_B/assembly.fasta`       |
| 3 | Phage_C | `Sequencing_run_2/sample_C/final_assembly.fasta` |
