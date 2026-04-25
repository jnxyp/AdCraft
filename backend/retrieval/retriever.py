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


class ChromaCollection(Protocol):
    def query(
        self,
        query_texts: list[str],
        n_results: int,
        where: Where,
    ) -> QueryResult: ...


class ChromaClient(Protocol):
    def get_collection(self, name: str) -> ChromaCollection: ...


class Template(TypedDict):
    id: str
    name: str
    categories: str
    freq_score: float
    seq_len: int
    example_product_desc: str


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
        min_len, max_len = _length_range(length)
        candidates = self._query_candidates(category, product_desc, min_len, max_len)
        if len(candidates) < TOP_K:
            candidates = self._query_candidates(category, product_desc, max(1, min_len - 1), max_len + 1)

        ranked = rank_candidates([dict(candidate) for candidate in candidates], self._bt_scores)
        return [_coerce_template(candidate) for candidate in ranked]

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
        )
        candidates = _templates_from_query_result(result)
        category_matches = [candidate for candidate in candidates if _category_matches(category, candidate)]
        if category_matches:
            return category_matches

        fallback = self._collection.query(
            query_texts=[product_desc],
            n_results=SEMANTIC_CANDIDATES,
            where=_seq_len_filter(min_len, max_len),
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


def _coerce_template(candidate: dict[str, object]) -> Template:
    return Template(
        id=_object_str(candidate["id"]),
        name=_object_str(candidate["name"]),
        categories=_object_str(candidate["categories"]),
        freq_score=_object_float(candidate["freq_score"]),
        seq_len=_object_int(candidate["seq_len"]),
        example_product_desc=_object_str(candidate["example_product_desc"]),
    )


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
