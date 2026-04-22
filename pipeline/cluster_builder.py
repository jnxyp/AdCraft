"""Cluster annotated ads by product_desc within each category.

Run from pipeline/:
    python cluster_builder.py
    python cluster_builder.py --input data/ds0_annotated.json --output data/ds0_clusters.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import NotRequired, TypedDict, cast

import numpy as np
from dotenv import load_dotenv
from openai import OpenAI

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)

EMBED_MODEL: str = "text-embedding-3-small"
EMBED_BATCH: int = 200
MAX_CHARS: int = 24_000
SIMILARITY_THRESHOLD: float = 0.60
MIN_CLUSTER_SIZE: int = 5
TARGET_CLUSTER_SIZE: int = 6


class Ad(TypedDict):
    ad_id: str
    body: str
    product_desc: str
    categories: list[str]
    sequence: list[str]
    source: NotRequired[str]


class Cluster(TypedDict):
    cluster_id: str
    category: str
    size: int
    ad_ids: list[str]


class ClusterOutput(TypedDict):
    source: str
    embedding_model: str
    similarity_threshold: float
    distance_threshold: float
    min_cluster_size: int
    target_cluster_size: int
    clusters: list[Cluster]


class EmbeddingCache(TypedDict):
    source: str
    embedding_model: str
    ad_ids: list[str]
    embeddings: list[list[float]]


def load_ads(path: Path) -> list[Ad]:
    raw_ads = json.loads(path.read_text(encoding="utf-8"))
    ads = cast(list[Ad], raw_ads)
    missing: list[str] = []
    for index, ad in enumerate(ads):
        if not ad.get("ad_id"):
            missing.append(f"{index}:ad_id")
        if not ad.get("product_desc"):
            missing.append(f"{index}:product_desc")
        if not ad.get("categories"):
            missing.append(f"{index}:categories")
    if missing:
        preview = ", ".join(missing[:10])
        raise ValueError(f"Annotated ads are missing required fields: {preview}")
    return ads


def embed_texts(client: OpenAI, texts: list[str]) -> np.ndarray:
    all_vecs: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH):
        batch = [text[:MAX_CHARS] for text in texts[start: start + EMBED_BATCH]]
        resp = client.embeddings.create(model=EMBED_MODEL, input=batch)
        resp.data.sort(key=lambda item: item.index)
        all_vecs.extend(item.embedding for item in resp.data)
        log.info("Embedded %d / %d product descriptions", min(start + EMBED_BATCH, len(texts)), len(texts))
    mat = np.array(all_vecs, dtype=np.float32)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    return mat / np.maximum(norms, 1e-9)


def load_or_create_embeddings(ads: list[Ad], input_path: Path, cache_path: Path) -> np.ndarray:
    ad_ids = [ad["ad_id"] for ad in ads]
    if cache_path.exists():
        cache = cast(EmbeddingCache, json.loads(cache_path.read_text(encoding="utf-8")))
        if (
            cache.get("embedding_model") == EMBED_MODEL
            and cache.get("ad_ids") == ad_ids
            and cache.get("source") == str(input_path)
        ):
            log.info("Loaded embedding cache: %s", cache_path)
            return np.array(cache["embeddings"], dtype=np.float32)
        if (
            cache.get("embedding_model") == EMBED_MODEL
            and cache.get("source") == str(input_path)
            and set(cache.get("ad_ids", [])) == set(ad_ids)
        ):
            log.info("Loaded embedding cache with reordered ad_ids: %s", cache_path)
            by_id = dict(zip(cache["ad_ids"], cache["embeddings"]))
            embeddings = np.array([by_id[ad_id] for ad_id in ad_ids], dtype=np.float32)
            cache["ad_ids"] = ad_ids
            cache["embeddings"] = embeddings.astype(float).tolist()
            cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            return embeddings
        log.info("Embedding cache is stale; rebuilding: %s", cache_path)

    client = OpenAI()
    embeddings = embed_texts(client, [ad["product_desc"] for ad in ads])
    cache_data: EmbeddingCache = {
        "source": str(input_path),
        "embedding_model": EMBED_MODEL,
        "ad_ids": ad_ids,
        "embeddings": embeddings.astype(float).tolist(),
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache_data, ensure_ascii=False), encoding="utf-8")
    log.info("Saved embedding cache: %s", cache_path)
    return embeddings


def category_indices(ads: list[Ad]) -> dict[str, list[int]]:
    by_category: dict[str, list[int]] = defaultdict(list)
    for index, ad in enumerate(ads):
        for category in ad["categories"]:
            by_category[category].append(index)
    return dict(sorted(by_category.items()))


def cluster_category(
    ads: list[Ad],
    embeddings: np.ndarray,
    category: str,
    indices: list[int],
    distance_threshold: float,
    min_cluster_size: int,
    target_cluster_size: int,
) -> list[Cluster]:
    if len(indices) < min_cluster_size:
        return []

    vectors = embeddings[indices]
    labels = average_linkage_labels(vectors, distance_threshold)
    grouped: dict[int, list[int]] = defaultdict(list)
    for local_index, label in enumerate(labels):
        grouped[int(label)].append(indices[local_index])

    clusters: list[Cluster] = []
    serial = 1
    for members in sorted(grouped.values(), key=lambda item: (-len(item), item)):
        for chunk in split_members(members, min_cluster_size, target_cluster_size):
            cluster_id = f"{category}-{serial:04d}"
            serial += 1
            clusters.append({
                "cluster_id": cluster_id,
                "category": category,
                "size": len(chunk),
                "ad_ids": [ads[index]["ad_id"] for index in chunk],
            })
    return clusters


def split_members(members: list[int], min_cluster_size: int, target_cluster_size: int) -> list[list[int]]:
    size = len(members)
    if size < min_cluster_size:
        return []
    if size <= target_cluster_size + 3:
        return [members]

    chunk_count = max(1, round(size / target_cluster_size))
    while chunk_count > 1 and size // chunk_count < min_cluster_size:
        chunk_count -= 1

    chunks: list[list[int]] = []
    start = 0
    for chunk_index in range(chunk_count):
        remaining_items = size - start
        remaining_chunks = chunk_count - chunk_index
        chunk_size = round(remaining_items / remaining_chunks)
        chunks.append(members[start: start + chunk_size])
        start += chunk_size

    if chunks and len(chunks[-1]) < min_cluster_size:
        chunks[-2].extend(chunks[-1])
        chunks.pop()
    return chunks


def average_linkage_labels(vectors: np.ndarray, distance_threshold: float) -> list[int]:
    count = int(vectors.shape[0])
    if count == 0:
        return []
    if count == 1:
        return [0]

    base_distances = 1.0 - (vectors @ vectors.T)
    np.fill_diagonal(base_distances, np.inf)

    clusters: dict[int, list[int]] = {index: [index] for index in range(count)}
    active: set[int] = set(clusters)
    next_label = count
    pair_distances: dict[tuple[int, int], float] = {}
    for left in range(count):
        for right in range(left + 1, count):
            pair_distances[(left, right)] = float(base_distances[left, right])

    while pair_distances:
        (left, right), best_distance = min(pair_distances.items(), key=lambda item: item[1])
        if best_distance > distance_threshold:
            break

        left_members = clusters.pop(left)
        right_members = clusters.pop(right)
        merged_members = left_members + right_members
        old_left_size = len(left_members)
        old_right_size = len(right_members)

        active.remove(left)
        active.remove(right)
        stale_keys = [key for key in pair_distances if left in key or right in key]
        for key in stale_keys:
            del pair_distances[key]

        new_label = next_label
        next_label += 1
        clusters[new_label] = merged_members

        for other in sorted(active):
            left_key = (min(left, other), max(left, other))
            right_key = (min(right, other), max(right, other))
            left_distance = pair_distances.get(left_key, average_distance(base_distances, left_members, clusters[other]))
            right_distance = pair_distances.get(right_key, average_distance(base_distances, right_members, clusters[other]))
            merged_distance = (
                left_distance * old_left_size + right_distance * old_right_size
            ) / (old_left_size + old_right_size)
            pair_distances[(min(new_label, other), max(new_label, other))] = merged_distance

        active.add(new_label)

    labels = [0] * count
    for output_label, members in enumerate(sorted(clusters.values(), key=lambda item: min(item))):
        for member in members:
            labels[member] = output_label
    return labels


def average_distance(distances: np.ndarray, left_members: list[int], right_members: list[int]) -> float:
    values = distances[np.ix_(left_members, right_members)]
    return float(np.mean(values))


def print_summary(clusters: list[Cluster], by_category: dict[str, list[int]]) -> None:
    log.info("Cluster summary:")
    for category, indices in by_category.items():
        category_clusters = [cluster for cluster in clusters if cluster["category"] == category]
        sizes = [cluster["size"] for cluster in category_clusters]
        size_counts = Counter(sizes)
        covered_ads = sum(sizes)
        distribution = ", ".join(f"{size}x{count}" for size, count in sorted(size_counts.items()))
        log.info(
            "  %-14s ads=%4d clusters=%3d clustered_ads=%4d sizes=[%s]",
            category,
            len(indices),
            len(category_clusters),
            covered_ads,
            distribution,
        )


def build_clusters(
    ads: list[Ad],
    embeddings: np.ndarray,
    similarity_threshold: float,
    min_cluster_size: int,
    target_cluster_size: int,
) -> list[Cluster]:
    distance_threshold = 1.0 - similarity_threshold
    by_category = category_indices(ads)
    clusters: list[Cluster] = []
    for category, indices in by_category.items():
        clusters.extend(cluster_category(
            ads,
            embeddings,
            category,
            indices,
            distance_threshold,
            min_cluster_size,
            target_cluster_size,
        ))
    print_summary(clusters, by_category)
    return clusters


def write_output(
    path: Path,
    source: Path,
    clusters: list[Cluster],
    similarity_threshold: float,
    min_cluster_size: int,
    target_cluster_size: int,
) -> None:
    output: ClusterOutput = {
        "source": str(source),
        "embedding_model": EMBED_MODEL,
        "similarity_threshold": similarity_threshold,
        "distance_threshold": 1.0 - similarity_threshold,
        "min_cluster_size": min_cluster_size,
        "target_cluster_size": target_cluster_size,
        "clusters": clusters,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log.info("Saved %d clusters -> %s", len(clusters), path)


def main() -> None:
    load_dotenv(Path(__file__).parent.parent / ".env")

    parser = argparse.ArgumentParser(description="Cluster annotated ads by product description")
    parser.add_argument("--input", default="data/ds0_annotated.json", help="Annotated ads JSON")
    parser.add_argument("--output", default="data/ds0_clusters.json", help="Cluster output JSON")
    parser.add_argument(
        "--embedding-cache",
        default="data/ds0_product_desc_embeddings.json",
        help="Embedding cache JSON",
    )
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=SIMILARITY_THRESHOLD,
        help=f"Cosine similarity cutoff for clustering (default {SIMILARITY_THRESHOLD})",
    )
    parser.add_argument(
        "--min-cluster-size",
        type=int,
        default=MIN_CLUSTER_SIZE,
        help=f"Minimum output cluster size (default {MIN_CLUSTER_SIZE})",
    )
    parser.add_argument(
        "--target-cluster-size",
        type=int,
        default=TARGET_CLUSTER_SIZE,
        help=f"Preferred output cluster size (default {TARGET_CLUSTER_SIZE})",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    cache_path = Path(args.embedding_cache)
    similarity_threshold = float(args.similarity_threshold)
    min_cluster_size = int(args.min_cluster_size)
    target_cluster_size = int(args.target_cluster_size)

    ads = load_ads(input_path)
    log.info("Loaded %d annotated ads from %s", len(ads), input_path)
    embeddings = load_or_create_embeddings(ads, input_path, cache_path)
    clusters = build_clusters(ads, embeddings, similarity_threshold, min_cluster_size, target_cluster_size)
    write_output(output_path, input_path, clusters, similarity_threshold, min_cluster_size, target_cluster_size)


if __name__ == "__main__":
    main()
