from pathlib import Path

import pytest

from phang.install import deposcope, phold, rbpdetect


def test_find_phold_db_dir_requires_runtime_assets(tmp_path, monkeypatch):
    db_root = tmp_path / "phold_db"
    partial = db_root / "phold_search_db_v_1_0_0"
    partial.mkdir(parents=True)
    (partial / "acrs_plddt_over_70_metadata.tsv").write_text("", encoding="utf-8")

    monkeypatch.setattr(phold, "_phold_search_roots", lambda: [db_root])

    with pytest.raises(RuntimeError):
        phold.find_phold_db_dir()

    (partial / "all_phold_structures").write_text("", encoding="utf-8")
    assert phold.find_phold_db_dir() == partial


def test_get_rbpdetect_script_prefers_bundled_wrapper(tmp_path, monkeypatch):
    bundled = tmp_path / "rbpdetect_inference.py"
    bundled.write_text("# bundled\n", encoding="utf-8")

    legacy_root = tmp_path / "legacy"
    legacy_script = legacy_root / "PhageRBPdetect_v4" / "PhageRBPdetect_v4_inference.py"
    legacy_script.parent.mkdir(parents=True)
    legacy_script.write_text("# legacy\n", encoding="utf-8")

    monkeypatch.setattr(rbpdetect, "_bundled_script_path", lambda: bundled)
    monkeypatch.setattr(rbpdetect, "_RBP_SCRIPT_DIR", legacy_root)

    assert rbpdetect.get_rbpdetect_script() == bundled


def test_get_deposcope_model_paths_prefers_checkpoint_with_vocab(tmp_path, monkeypatch):
    model_root = tmp_path / "deposcope_model"
    checkpoint = (
        model_root
        / "esm2_t12_35M_UR50D__fulltrain__finetuneddepolymerase.2103.4_labels"
        / "checkpoint-2255"
    )
    checkpoint.mkdir(parents=True)
    (checkpoint / "vocab.txt").write_text("", encoding="utf-8")
    dpo_model = model_root / "Deposcope.esm2_t12_35M_UR50D.2203.full.model"
    dpo_model.write_text("", encoding="utf-8")

    monkeypatch.setattr(deposcope, "_DEPOSCOPE_MODEL_DIR", model_root)

    esm2_dir, resolved_dpo_model = deposcope.get_deposcope_model_paths()
    assert esm2_dir == checkpoint
    assert resolved_dpo_model == dpo_model
