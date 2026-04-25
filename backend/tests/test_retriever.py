from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pytest

from retrieval.retriever import QueryResult, Retriever, Where


@dataclass(frozen=True)
class FakeTemplate:
    id: str
    name: str
    categories: str
    freq_score: float
    seq_len: int
    document: str


@dataclass
class FakeChromaCollection:
    templates: list[FakeTemplate]
    contains_mode: Literal["substring", "empty"] = "substring"
    calls: list[Where] = field(default_factory=list)

    def query(self, query_texts: list[str], n_results: int, where: Where) -> QueryResult:
        self.calls.append(where)
        matches = [template for template in self.templates if self._matches(template, where)]
        limited = matches[:n_results]
        return {
            "ids": [[template.id for template in limited]],
            "documents": [[template.document for template in limited]],
            "metadatas": [
                [
                    {
                        "name": template.name,
                        "categories": template.categories,
                        "freq_score": template.freq_score,
                        "seq_len": template.seq_len,
                    }
                    for template in limited
                ]
            ],
        }

    def _matches(self, template: FakeTemplate, where: Where) -> bool:
        clauses = where.get("$and")
        if not isinstance(clauses, list):
            return True
        for clause in clauses:
            if not isinstance(clause, dict):
                continue
            if "categories" in clause and not self._matches_category(template, clause["categories"]):
                return False
            if "seq_len" in clause and not self._matches_seq_len(template, clause["seq_len"]):
                return False
        return True

    def _matches_category(self, template: FakeTemplate, raw_filter: object) -> bool:
        if not isinstance(raw_filter, dict):
            return False
        category = raw_filter.get("$contains")
        if not isinstance(category, str):
            return False
        if self.contains_mode == "empty":
            return False
        return category in template.categories

    def _matches_seq_len(self, template: FakeTemplate, raw_filter: object) -> bool:
        if not isinstance(raw_filter, dict):
            return False
        min_len = raw_filter.get("$gte", 1)
        max_len = raw_filter.get("$lte", 100)
        if not isinstance(min_len, int) or not isinstance(max_len, int):
            return False
        return min_len <= template.seq_len <= max_len


@dataclass
class FakeChromaClient:
    collection: FakeChromaCollection

    def get_collection(self, name: str) -> FakeChromaCollection:
        assert name == "ad_templates"
        return self.collection


@pytest.mark.asyncio
async def test_query_reranks_candidates_with_bt_scores() -> None:
    collection = FakeChromaCollection(
        templates=[
            FakeTemplate("tmpl_a", "AH", "tech", 0.2, 4, "Product A"),
            FakeTemplate("tmpl_b", "PP", "tech", 0.9, 4, "Product B"),
            FakeTemplate("tmpl_c", "CTA", "tech", 0.3, 5, "Product C"),
            FakeTemplate("tmpl_d", "FB", "tech", 0.8, 5, "Product D"),
        ]
    )
    retriever = Retriever(FakeChromaClient(collection))
    retriever.refresh_bt_scores({"tmpl_c": 3.0, "tmpl_a": 2.0, "tmpl_b": 1.0})

    results = await retriever.query("tech", "wireless keyboard", "m")

    assert [template["id"] for template in results] == ["tmpl_c", "tmpl_a", "tmpl_b"]
    assert collection.calls[0] == {
        "$and": [
            {"categories": {"$contains": "tech"}},
            {"seq_len": {"$gte": 4}},
            {"seq_len": {"$lte": 5}},
        ]
    }


@pytest.mark.asyncio
async def test_query_widens_seq_len_when_fewer_than_three_candidates_match() -> None:
    collection = FakeChromaCollection(
        templates=[
            FakeTemplate("tmpl_a", "AH", "tech", 0.5, 4, "Product A"),
            FakeTemplate("tmpl_b", "PP", "tech", 0.4, 5, "Product B"),
            FakeTemplate("tmpl_c", "CTA", "tech", 0.3, 6, "Product C"),
        ]
    )
    retriever = Retriever(FakeChromaClient(collection))

    results = await retriever.query("tech", "wireless keyboard", "m")

    assert [template["id"] for template in results] == ["tmpl_a", "tmpl_b", "tmpl_c"]
    assert collection.calls[1] == {
        "$and": [
            {"categories": {"$contains": "tech"}},
            {"seq_len": {"$gte": 3}},
            {"seq_len": {"$lte": 6}},
        ]
    }


@pytest.mark.asyncio
async def test_query_falls_back_to_local_category_filter_when_contains_returns_empty() -> None:
    collection = FakeChromaCollection(
        templates=[
            FakeTemplate("tmpl_a", "AH", "health|tech", 0.2, 4, "Product A"),
            FakeTemplate("tmpl_b", "PP", "finance", 0.9, 4, "Product B"),
            FakeTemplate("tmpl_c", "CTA", "tech", 0.3, 5, "Product C"),
        ],
        contains_mode="empty",
    )
    retriever = Retriever(FakeChromaClient(collection))

    results = await retriever.query("tech", "wireless keyboard", "m")

    assert [template["id"] for template in results] == ["tmpl_c", "tmpl_a"]
    assert "categories" in collection.calls[0]["$and"][0]
    assert collection.calls[1] == {
        "$and": [
            {"seq_len": {"$gte": 4}},
            {"seq_len": {"$lte": 5}},
        ]
    }
