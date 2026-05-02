from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, TypedDict

from ranking.bradley_terry import rank_candidates

LENGTH_RANGES: dict[str, tuple[int, int]] = {
    "xs": (1, 2),
    "s": (3, 3),
    "m": (4, 5),
    "l": (6, 8),
    "xl": (9, 15),
}

TOP_K = 3
SEMANTIC_CANDIDATES = 20

Scalar = str | int | float | bool
MetadataValue = Scalar | None
Where = dict[str, object]


class QueryResult(TypedDict, total=False):
    ids: list[list[str]]
    documents: list[list[str | None]]
    metadatas: list[list[Mapping[str, MetadataValue] | None]]
    distances: list[list[float]]


class ChromaCollection(Protocol):
    def query(
        self,
        query_texts: list[str],
        n_results: int,
        where: Where,
        include: list[str] | None = None,
    ) -> QueryResult: ...


class ChromaClient(Protocol):
    def get_collection(self, name: str) -> ChromaCollection: ...


class TemplateBase(TypedDict):
    id: str
    name: str
    categories: str
    freq_score: float
    seq_len: int
    example_product_desc: str


class Template(TemplateBase, total=False):
    semantic_distance: float | None
    semantic_rank: int
    bt_score: float | None
    final_score: float
    final_rank: int


class Retriever:
    def __init__(
        self,
        chroma_client: ChromaClient,
        collection_name: str = "ad_templates",
    ) -> None:
        self._collection = chroma_client.get_collection(collection_name)
        self._bt_scores: dict[str, float] = {}

    def refresh_bt_scores(self, scores: dict[str, float]) -> None:
        self._bt_scores = dict(scores)

    async def query(
        self,
        category: str,
        product_desc: str,
        length: str,
    ) -> list[Template]:
        ranked = await self.query_ranked(
            category=category,
            product_desc=product_desc,
            length=length,
            limit=TOP_K,
        )
        return ranked[:TOP_K]

    async def query_ranked(
        self,
        category: str,
        product_desc: str,
        length: str,
        limit: int,
    ) -> list[Template]:
        min_len, max_len = _length_range(length)
        candidates = self._query_candidates(category, product_desc, min_len, max_len)
        if len(candidates) < TOP_K:
            candidates = self._query_candidates(category, product_desc, max(1, min_len - 1), max_len + 1)

        ranked = rank_candidates([dict(candidate) for candidate in candidates], self._bt_scores, top_k=limit)
        templates = [_coerce_template(candidate) for candidate in ranked]
        for idx, template in enumerate(templates):
            template_id = template["id"]
            bt_score = self._bt_scores.get(template_id)
            template["bt_score"] = bt_score if bt_score is not None else None
            template["final_score"] = bt_score if bt_score is not None else template["freq_score"]
            template["final_rank"] = idx + 1
        return templates

    async def infer_category(
        self,
        product_desc: str,
        length: str,
    ) -> str:
        min_len, max_len = _length_range(length)
        result = self._collection.query(
            query_texts=[product_desc],
            n_results=SEMANTIC_CANDIDATES,
            where=_seq_len_filter(min_len, max_len),
            include=["metadatas", "documents", "distances"],
        )
        candidates = _templates_from_query_result(result)
        counts: dict[str, int] = {}
        for candidate in candidates:
            for category in candidate["categories"].split("|"):
                if category:
                    counts[category] = counts.get(category, 0) + 1
        if not counts:
            raise ValueError("cannot infer category from empty candidate set")
        return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]

    def _query_candidates(
        self,
        category: str,
        product_desc: str,
        min_len: int,
        max_len: int,
    ) -> list[Template]:
        result = self._collection.query(
            query_texts=[product_desc],
            n_results=SEMANTIC_CANDIDATES,
            where=_where_filter(category, min_len, max_len),
            include=["metadatas", "documents", "distances"],
        )
        candidates = _templates_from_query_result(result)
        category_matches = [candidate for candidate in candidates if _category_matches(category, candidate)]
        if category_matches:
            return category_matches

        fallback = self._collection.query(
            query_texts=[product_desc],
            n_results=SEMANTIC_CANDIDATES,
            where=_seq_len_filter(min_len, max_len),
            include=["metadatas", "documents", "distances"],
        )
        return [
            candidate
            for candidate in _templates_from_query_result(fallback)
            if _category_matches(category, candidate)
        ]


def _length_range(length: str) -> tuple[int, int]:
    try:
        return LENGTH_RANGES[length]
    except KeyError as exc:
        allowed = ", ".join(sorted(LENGTH_RANGES))
        raise ValueError(f"unsupported length '{length}', expected one of: {allowed}") from exc


def _where_filter(category: str, min_len: int, max_len: int) -> Where:
    return {
        "$and": [
            {"categories": {"$contains": category}},
            {"seq_len": {"$gte": min_len}},
            {"seq_len": {"$lte": max_len}},
        ]
    }


def _seq_len_filter(min_len: int, max_len: int) -> Where:
    return {
        "$and": [
            {"seq_len": {"$gte": min_len}},
            {"seq_len": {"$lte": max_len}},
        ]
    }


def _templates_from_query_result(result: QueryResult) -> list[Template]:
    ids = _first_str_batch(result.get("ids", []))
    documents = _first_document_batch(result.get("documents", []))
    metadatas = _first_metadata_batch(result.get("metadatas", []))
    distances = _first_distance_batch(result.get("distances", []))

    templates: list[Template] = []
    for idx, template_id in enumerate(ids):
        metadata = metadatas[idx] if idx < len(metadatas) else None
        if metadata is None:
            continue
        raw_document = documents[idx] if idx < len(documents) else None
        document = raw_document if raw_document is not None else ""
        templates.append(
            Template(
                id=template_id,
                name=_metadata_str(metadata, "name"),
                categories=_metadata_str(metadata, "categories"),
                freq_score=_metadata_float(metadata, "freq_score"),
                seq_len=_metadata_int(metadata, "seq_len"),
                example_product_desc=document,
                semantic_distance=distances[idx] if idx < len(distances) else None,
                semantic_rank=idx + 1,
            )
        )
    return templates


def _first_str_batch(values: list[list[str]]) -> list[str]:
    return values[0] if values else []


def _first_document_batch(values: list[list[str | None]]) -> list[str | None]:
    return values[0] if values else []


def _first_metadata_batch(
    values: list[list[Mapping[str, MetadataValue] | None]],
) -> list[Mapping[str, MetadataValue] | None]:
    return values[0] if values else []


def _first_distance_batch(values: list[list[float]]) -> list[float]:
    return values[0] if values else []


def _coerce_template(candidate: dict[str, object]) -> Template:
    template = Template(
        id=_object_str(candidate["id"]),
        name=_object_str(candidate["name"]),
        categories=_object_str(candidate["categories"]),
        freq_score=_object_float(candidate["freq_score"]),
        seq_len=_object_int(candidate["seq_len"]),
        example_product_desc=_object_str(candidate["example_product_desc"]),
    )
    if "semantic_distance" in candidate:
        distance = candidate["semantic_distance"]
        template["semantic_distance"] = _object_float(distance) if distance is not None else None
    if "semantic_rank" in candidate:
        template["semantic_rank"] = _object_int(candidate["semantic_rank"])
    if "bt_score" in candidate:
        bt_score = candidate["bt_score"]
        template["bt_score"] = _object_float(bt_score) if bt_score is not None else None
    if "final_score" in candidate:
        template["final_score"] = _object_float(candidate["final_score"])
    if "final_rank" in candidate:
        template["final_rank"] = _object_int(candidate["final_rank"])
    return template


def _category_matches(category: str, template: Template) -> bool:
    return category in template["categories"].split("|")


def _metadata_str(metadata: Mapping[str, MetadataValue], key: str) -> str:
    value = metadata.get(key)
    if isinstance(value, str):
        return value
    raise ValueError(f"metadata field '{key}' must be a string")


def _metadata_float(metadata: Mapping[str, MetadataValue], key: str) -> float:
    value = metadata.get(key)
    if isinstance(value, int | float):
        return float(value)
    raise ValueError(f"metadata field '{key}' must be numeric")


def _metadata_int(metadata: Mapping[str, MetadataValue], key: str) -> int:
    value = metadata.get(key)
    if isinstance(value, int):
        return value
    raise ValueError(f"metadata field '{key}' must be an integer")


def _object_str(value: object) -> str:
    if isinstance(value, str):
        return value
    raise ValueError(f"expected string value: {value!r}")


def _object_float(value: object) -> float:
    if isinstance(value, int | float):
        return float(value)
    raise ValueError(f"expected numeric value: {value!r}")


def _object_int(value: object) -> int:
    if isinstance(value, int):
        return value
    raise ValueError(f"expected integer value: {value!r}")
