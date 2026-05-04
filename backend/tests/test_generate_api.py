from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.generate import create_generate_router
from core.config import Settings
from core.database import init_schema


@dataclass
class FakeRetriever:
    calls: list[tuple[str, str, str]] = field(default_factory=list)
    infer_calls: list[tuple[str, str]] = field(default_factory=list)

    async def query(self, category: str, product_desc: str, length: str) -> list[dict[str, object]]:
        self.calls.append((category, product_desc, length))
        return await self.query_ranked(category, product_desc, length, 3)

    async def query_ranked(
        self, category: str, product_desc: str, length: str, limit: int
    ) -> list[dict[str, object]]:
        self.calls.append((category, product_desc, length))
        return [
            {
                "id": "tmpl_1",
                "name": "AH→PP→FB→CTA",
                "categories": "tech",
                "freq_score": 0.8,
                "seq_len": 4,
                "example_product_desc": "a",
                "semantic_distance": 0.11,
                "semantic_rank": 1,
                "bt_score": 1.2,
                "final_score": 1.2,
                "final_rank": 1,
            },
            {
                "id": "tmpl_2",
                "name": "AH→FB→CTA",
                "categories": "tech",
                "freq_score": 0.6,
                "seq_len": 3,
                "example_product_desc": "b",
                "semantic_distance": 0.13,
                "semantic_rank": 2,
                "bt_score": 0.7,
                "final_score": 0.7,
                "final_rank": 2,
            },
            {
                "id": "tmpl_3",
                "name": "PP→FB→SP→CTA",
                "categories": "tech",
                "freq_score": 0.5,
                "seq_len": 4,
                "example_product_desc": "c",
                "semantic_distance": 0.21,
                "semantic_rank": 3,
                "bt_score": None,
                "final_score": 0.5,
                "final_rank": 3,
            },
        ][:limit]

    async def infer_category(self, product_desc: str, length: str) -> str:
        self.infer_calls.append((product_desc, length))
        return "tech"


@dataclass
class FakeTextGenerator:
    calls: list[tuple[str, str]] = field(default_factory=list)

    async def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        if "Return only valid JSON" in system_prompt:
            sequence_line = next(
                (line for line in user_prompt.splitlines() if line.startswith("Sequence: ")),
                "Sequence: AH -> CTA",
            )
            labels = [part.strip() for part in sequence_line.removeprefix("Sequence: ").split("->")]
            segment_payload = ",".join(
                f'{{"label":"{label}","text":"{label} line."}}' for label in labels
            )
            return f'{{"segments":[{segment_payload}]}}'
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
async def test_template_variant_route_supports_auto_find_category_and_variant_generation(tmp_path: Path) -> None:
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
        "/api/generate/find-templates",
        json={
            "category": "auto",
            "product_desc": "No-code analytics for teams",
            "length": "m",
            "generation_prompt": None,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["category"] == "tech"
    assert len(payload["templates"]) == 3
    assert retriever.infer_calls == [("No-code analytics for teams", "m")]

    variant_response = client.post(
        "/api/generate/template-variant",
        json={
            "template_id": "tmpl_2",
            "category": "tech",
            "product_desc": "No-code analytics for teams",
            "length": "m",
            "generation_prompt": None,
        },
    )
    assert variant_response.status_code == 200
    variant = variant_response.json()
    assert variant["template_id"] == "tmpl_2"
    assert len(variant["segments"]) == 3


@pytest.mark.asyncio
async def test_find_templates_and_direct_routes(tmp_path: Path) -> None:
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

    find_response = client.post(
        "/api/generate/find-templates",
        json={
            "category": "auto",
            "product_desc": "No-code analytics for teams",
            "length": "m",
            "generation_prompt": None,
        },
    )
    assert find_response.status_code == 200
    find_payload = find_response.json()
    assert find_payload["category"] == "tech"
    assert len(find_payload["templates"]) == 3
    assert find_payload["templates"][0]["semantic_distance"] == 0.11
    assert find_payload["templates"][0]["semantic_rank"] == 1
    assert find_payload["templates"][0]["final_rank"] == 1

    direct_response = client.post(
        "/api/generate/direct",
        json={
            "category": "tech",
            "product_desc": "No-code analytics for teams",
            "length": "m",
            "generation_prompt": "Practical tone.",
        },
    )
    assert direct_response.status_code == 200
    direct_payload = direct_response.json()
    assert str(direct_payload["output"]).startswith("Generated::")


@pytest.mark.asyncio
async def test_template_editing_routes(tmp_path: Path) -> None:
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

    full_response = client.post(
        "/api/generate/template-regenerate-full",
        json={
            "template_id": "tmpl_2",
            "category": "tech",
            "product_desc": "No-code analytics for teams",
            "length": "m",
            "generation_prompt": "Plain tone.",
        },
    )
    assert full_response.status_code == 200
    full_payload = full_response.json()
    assert full_payload["template_id"] == "tmpl_2"
    assert len(full_payload["segments"]) == 3

    apply_response = client.post(
        "/api/generate/template-apply-instructions",
        json={
            "template_id": "tmpl_2",
            "category": "tech",
            "product_desc": "No-code analytics for teams",
            "length": "m",
            "generation_prompt": "Plain tone.",
            "current_segments": [
                {"label": "AH", "label_full": "Attention Hook", "text": "Keep this."},
                {"label": "FB", "label_full": "Feature-Benefit", "text": "Middle line."},
                {"label": "CTA", "label_full": "Call To Action", "text": "Close now."},
            ],
            "instructions": [
                {"mode": "none", "prompt": None},
                {"mode": "disable", "prompt": None},
                {"mode": "regenerate", "prompt": "Make it urgent."},
            ],
        },
    )
    assert apply_response.status_code == 200
    apply_payload = apply_response.json()
    assert apply_payload["segments"][0]["text"] == "Keep this."
    assert apply_payload["segments"][1]["text"] == ""
    assert apply_payload["segments"][2]["text"] == "CTA line."
