from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.generate import create_generate_router
from core.config import Settings
from core.database import connect, init_schema


@dataclass
class FakeRetriever:
    calls: list[tuple[str, str, str]] = field(default_factory=list)

    async def query(self, category: str, product_desc: str, length: str) -> list[dict[str, object]]:
        self.calls.append((category, product_desc, length))
        return [
            {"id": "tmpl_1", "name": "AH→PP→FB→CTA", "categories": "tech", "freq_score": 0.8, "seq_len": 4, "example_product_desc": "a"},
            {"id": "tmpl_2", "name": "AH→FB→CTA", "categories": "tech", "freq_score": 0.6, "seq_len": 3, "example_product_desc": "b"},
            {"id": "tmpl_3", "name": "PP→FB→SP→CTA", "categories": "tech", "freq_score": 0.5, "seq_len": 4, "example_product_desc": "c"},
        ]


@dataclass
class FakeTextGenerator:
    calls: list[tuple[str, str]] = field(default_factory=list)

    async def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return f"Generated::{len(self.calls)}"


def _settings(db_path: Path) -> Settings:
    data_dir = db_path.parent
    return Settings(
        backend_root=Path("."),
        data_dir=data_dir,
        db_path=db_path,
        chromadb_dir=data_dir / "chromadb",
        static_images_dir=data_dir / "images",
        pipeline_data_dir=Path("."),
        openai_api_key="test",
        openai_chat_model="gpt-5-mini",
        openai_embedding_model="text-embedding-3-small",
        openai_image_model="gpt-image-2",
        bt_refit_interval_seconds=600,
        eval_max_votes=5,
        chroma_collection_name="ad_templates",
    )


@pytest.mark.asyncio
async def test_generate_route_returns_variants_and_persists_row(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    await init_schema(db_path)
    retriever = FakeRetriever()
    generator = FakeTextGenerator()

    app = FastAPI()
    app.include_router(
        create_generate_router(
            db_path,
            retriever_override=retriever,
            text_generator_override=generator,
            settings_override=_settings(db_path),
        )
    )
    client = TestClient(app)

    response = client.post(
        "/api/generate",
        json={
            "category": "tech",
            "product_desc": "No-code analytics for teams",
            "length": "m",
            "generation_prompt": "Practical tone.",
        },
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["category"] == "tech"
    assert payload["product_desc"] == "No-code analytics for teams"
    assert len(payload["structured_variants"]) == 3
    assert payload["direct_output"] == "Generated::4"
    assert len(generator.calls) == 4
    assert retriever.calls == [("tech", "No-code analytics for teams", "m")]

    async with connect(db_path) as conn:
        row = await (
            await conn.execute(
                "SELECT category, product_desc, generation_prompt, variants, direct_output, image_path FROM generations"
            )
        ).fetchone()
    assert row is not None
    assert row["category"] == "tech"
    assert row["product_desc"] == "No-code analytics for teams"
    assert row["generation_prompt"] == "Practical tone."
    variants = json.loads(str(row["variants"]))
    assert len(variants) == 3
    assert row["direct_output"] == "Generated::4"
    assert row["image_path"] is None
