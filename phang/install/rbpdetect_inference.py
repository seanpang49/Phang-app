#!/usr/bin/env python3
"""
Local PhageRBPdetect wrapper that loads the finetuned model from a local path.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Iterable

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer


def _parse_fasta(fasta_path: Path) -> list[tuple[str, str]]:
    records: list[tuple[str, str]] = []
    current_id: str | None = None
    chunks: list[str] = []

    with open(fasta_path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            if line.startswith(">"):
                if current_id is not None:
                    records.append((current_id, "".join(chunks)))
                current_id = line[1:].split()[0]
                chunks = []
            else:
                chunks.append(line)

    if current_id is not None:
        records.append((current_id, "".join(chunks)))

    return records


def _resolve_device(requested: str) -> str:
    if requested == "auto":
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        return "cpu"
    if requested == "cuda" and not torch.cuda.is_available():
        return "cpu"
    if requested == "mps":
        mps_available = hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
        return "mps" if mps_available else "cpu"
    return requested


def _pick_rbp_label_id(id2label: dict) -> int:
    for key, value in id2label.items():
        if "rbp" in str(value).lower():
            try:
                return int(key)
            except (TypeError, ValueError):
                continue
    return 1


def _batched(records: list[tuple[str, str]], batch_size: int) -> Iterable[list[tuple[str, str]]]:
    for idx in range(0, len(records), batch_size):
        yield records[idx : idx + batch_size]


def run_inference(
    faa_path: Path,
    model_dir: Path,
    out_dir: Path,
    device: str,
    batch_size: int,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / "predictions.csv"

    tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(
        str(model_dir),
        local_files_only=True,
    )
    device = _resolve_device(device)
    model = model.to(device)
    model.eval()

    id2label = getattr(model.config, "id2label", {}) or {}
    rbp_label_id = _pick_rbp_label_id(id2label)

    records = _parse_fasta(faa_path)
    max_len = getattr(tokenizer, "model_max_length", 1024) or 1024
    if not isinstance(max_len, int) or max_len <= 0 or max_len > 4096:
        max_len = 1024

    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["protein_name", "preds", "score"])
        writer.writeheader()

        for batch in _batched(records, batch_size):
            ids = [record[0] for record in batch]
            seqs = [record[1] for record in batch]

            inputs = tokenizer(
                seqs,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=max_len,
            )
            inputs = {key: value.to(device) for key, value in inputs.items()}

            with torch.no_grad():
                logits = model(**inputs).logits
                probs = torch.softmax(logits, dim=-1)
                rbp_scores = probs[:, rbp_label_id].detach().cpu().tolist()

            for protein_id, score in zip(ids, rbp_scores):
                writer.writerow(
                    {
                        "protein_name": protein_id,
                        "preds": 1 if score >= 0.5 else 0,
                        "score": round(float(score), 6),
                    }
                )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda", "mps"])
    parser.add_argument("--batch-size", default=16, type=int)
    args = parser.parse_args()

    run_inference(
        faa_path=args.input,
        model_dir=args.model,
        out_dir=args.output,
        device=args.device,
        batch_size=max(args.batch_size, 1),
    )


if __name__ == "__main__":
    main()
