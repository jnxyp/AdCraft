from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _env_path(key: str, default: Path) -> Path:
    raw = os.environ.get(key)
    return Path(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    backend_root: Path
    data_dir: Path
    db_path: Path
    chromadb_dir: Path
    static_images_dir: Path
    pipeline_data_dir: Path
    openai_api_key: str
    openai_chat_model: str
    openai_embedding_model: str
    openai_image_model: str
    bt_refit_interval_seconds: int
    eval_max_votes: int
    chroma_collection_name: str


def load_settings() -> Settings:
    backend_root = Path(__file__).resolve().parent.parent
    project_root = backend_root.parent
    load_dotenv(backend_root.parent / ".env")
    data_dir = _env_path("ADFRAME_DATA_DIR", project_root / "data")
    pipeline_data_dir = _env_path("ADFRAME_PIPELINE_DATA_DIR", project_root / "pipeline" / "data")
    return Settings(
        backend_root=backend_root,
        data_dir=data_dir,
        db_path=data_dir / "adcraft.db",
        chromadb_dir=data_dir / "chromadb",
        static_images_dir=data_dir / "images",
        pipeline_data_dir=pipeline_data_dir,
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        openai_chat_model=os.environ.get("OPENAI_CHAT_MODEL", "gpt-5.5"),
        openai_embedding_model=os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        openai_image_model=os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-2"),
        bt_refit_interval_seconds=int(os.environ.get("ADFRAME_BT_REFIT_INTERVAL", "600")),
        eval_max_votes=int(os.environ.get("ADFRAME_EVAL_MAX_VOTES", "5")),
        chroma_collection_name=os.environ.get("ADFRAME_CHROMA_COLLECTION", "ad_templates"),
    )
