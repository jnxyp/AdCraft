from __future__ import annotations

from pathlib import Path

import pytest

from core.config import load_settings


def test_load_settings_defaults_to_project_data_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADFRAME_DATA_DIR", raising=False)
    monkeypatch.delenv("ADFRAME_PIPELINE_DATA_DIR", raising=False)

    settings = load_settings()
    project_root = Path(__file__).resolve().parents[2]

    assert settings.data_dir == project_root / "data"
    assert settings.db_path == project_root / "data" / "adcraft.db"
    assert settings.chromadb_dir == project_root / "data" / "chromadb"
    assert settings.static_images_dir == project_root / "data" / "images"
    assert settings.pipeline_data_dir == project_root / "pipeline" / "data"


def test_load_settings_allows_data_dir_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ADFRAME_DATA_DIR", str(tmp_path / "runtime"))

    settings = load_settings()

    assert settings.data_dir == tmp_path / "runtime"
    assert settings.db_path == tmp_path / "runtime" / "adcraft.db"
