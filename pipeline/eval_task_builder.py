"""Build deterministic human evaluation tasks from clusters and templates.

Run from pipeline/:
    python eval_task_builder.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from itertools import combinations
from pathlib import Path
from typing import Literal, NotRequired, TypedDict, cast

import template_builder

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)

Slot = Literal["a", "b"]
RANDOM_SEED: int = 20260501
MAX_AD_USES_PER_CLUSTER: int = 3
TARGET_TOTAL_TASKS: int = 1000
MAX_CROSS_CLUSTER_AD_USES: int = 3


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
    clusters: list[Cluster]


class Template(TypedDict):
    id: str
    sequence: list[str]
    name: str
    seq_len: int
    count: int


class TemplateOutput(TypedDict):
    source: str
    templates: list[Template]


class Candidate(TypedDict):
    ad_id: str
    body: str
    sequence: list[str]
    sequence_key: str
    template_id: str
    template_count: int
    seq_len: int
    length_bucket: str
    category: str
    cluster_id: str


class TaskAd(TypedDict):
    slot: Slot
    ad_id: str
    body: str
    template_id: str
    sequence: list[str]


class EvalTask(TypedDict):
    id: str
    task_type: Literal["pair"]
    pair_scope: Literal["same_cluster", "cross_cluster"]
    category: str
    cluster_id: str
    ads: list[TaskAd]


class EvalTaskOutput(TypedDict):
    source_ads: str
    source_clusters: str
    source_templates: str
    task_count: int
    tasks: list[EvalTask]


def read_ads(path: Path) -> dict[str, Ad]:
    rows = cast(list[Ad], json.loads(path.read_text(encoding="utf-8")))
    return {row["ad_id"]: row for row in rows}


def read_clusters(path: Path) -> list[Cluster]:
    data = cast(ClusterOutput, json.loads(path.read_text(encoding="utf-8")))
    return data["clusters"]


def read_templates(path: Path) -> dict[str, Template]:
    data = cast(TemplateOutput, json.loads(path.read_text(encoding="utf-8")))
    return {template_builder.sequence_key(template["sequence"]): template for template in data["templates"]}


def task_id(ads: list[TaskAd]) -> str:
    key = json.dumps(sorted(ad["ad_id"] for ad in ads), separators=(",", ":"))
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    return f"eval_{digest}"


def length_bucket(seq_len: int) -> str | None:
    if 1 <= seq_len <= 2:
        return "xs"
    if seq_len == 3:
        return "s"
    if 4 <= seq_len <= 5:
        return "m"
    if 6 <= seq_len <= 8:
        return "l"
    if 9 <= seq_len <= 15:
        return "xl"
    return None


def candidates_for_cluster(
    cluster: Cluster,
    ads_by_id: dict[str, Ad],
    templates_by_sequence: dict[str, Template],
) -> list[Candidate]:
    candidates: list[Candidate] = []
    for ad_id in cluster["ad_ids"]:
        ad = ads_by_id.get(ad_id)
        if ad is None:
            continue
        seq_key = template_builder.sequence_key(ad["sequence"])
        template = templates_by_sequence.get(seq_key)
        if template is None:
            continue
        bucket = length_bucket(template["seq_len"])
        if bucket is None:
            continue
        candidates.append({
            "ad_id": ad["ad_id"],
            "body": ad["body"],
            "sequence": ad["sequence"],
            "sequence_key": seq_key,
            "template_id": template["id"],
            "template_count": template["count"],
            "seq_len": template["seq_len"],
            "length_bucket": bucket,
            "category": cluster["category"],
            "cluster_id": cluster["cluster_id"],
        })
    return candidates


def desired_task_count(cluster_size: int) -> int:
    return cluster_size * MAX_AD_USES_PER_CLUSTER // 2


def choose_pair(candidates: list[Candidate], ad_use_counts: dict[str, int], used_pair_keys: set[tuple[str, str]]) -> list[Candidate] | None:
    available = [
        candidate
        for candidate in candidates
        if ad_use_counts.get(candidate["ad_id"], 0) < MAX_AD_USES_PER_CLUSTER
    ]
    best: tuple[int, int, tuple[str, str], tuple[Candidate, Candidate]] | None = None
    for combo in combinations(available, 2):
        sequence_keys = {candidate["sequence_key"] for candidate in combo}
        if len(sequence_keys) != 2:
            continue
        buckets = {candidate["length_bucket"] for candidate in combo}
        if len(buckets) != 1:
            continue
        ad_ids = tuple(candidate["ad_id"] for candidate in combo)
        pair_key = tuple(sorted(ad_ids))
        if pair_key in used_pair_keys:
            continue
        use_penalty = sum(ad_use_counts.get(ad_id, 0) for ad_id in ad_ids)
        score = sum(candidate["template_count"] for candidate in combo)
        ranked = (use_penalty, -score, ad_ids, combo)
        if best is None or ranked < best:
            best = ranked
    if best is None:
        return None
    return list(best[3])


def make_task(
    category: str,
    cluster_id: str,
    pair_scope: Literal["same_cluster", "cross_cluster"],
    candidates: list[Candidate],
) -> EvalTask:
    slots: list[Slot] = ["a", "b"]
    task_ads: list[TaskAd] = []
    for slot, candidate in zip(slots, candidates):
        task_ads.append({
            "slot": slot,
            "ad_id": candidate["ad_id"],
            "body": candidate["body"],
            "template_id": candidate["template_id"],
            "sequence": candidate["sequence"],
        })
    return {
        "id": task_id(task_ads),
        "task_type": "pair",
        "pair_scope": pair_scope,
        "category": category,
        "cluster_id": cluster_id,
        "ads": task_ads,
    }


def pair_key_for(candidates: list[Candidate]) -> tuple[str, str]:
    return tuple(sorted(candidate["ad_id"] for candidate in candidates))


def grouped_candidates_by_category_and_bucket(
    clusters: list[Cluster],
    ads_by_id: dict[str, Ad],
    templates_by_sequence: dict[str, Template],
) -> dict[tuple[str, str], list[Candidate]]:
    grouped: dict[tuple[str, str], list[Candidate]] = {}
    for cluster in clusters:
        for candidate in candidates_for_cluster(cluster, ads_by_id, templates_by_sequence):
            key = (cluster["category"], candidate["length_bucket"])
            grouped.setdefault(key, []).append(candidate)
    return grouped


def choose_cross_cluster_pair(
    candidates: list[Candidate],
    ad_use_counts: dict[str, int],
    used_pair_keys: set[tuple[str, str]],
) -> list[Candidate] | None:
    available = [
        candidate
        for candidate in candidates
        if ad_use_counts.get(candidate["ad_id"], 0) < MAX_CROSS_CLUSTER_AD_USES
    ]
    best: tuple[int, int, tuple[str, str], tuple[Candidate, Candidate]] | None = None
    for combo in combinations(available, 2):
        left, right = combo
        if left["cluster_id"] == right["cluster_id"]:
            continue
        if left["length_bucket"] != right["length_bucket"]:
            continue
        if left["sequence_key"] == right["sequence_key"] or left["template_id"] == right["template_id"]:
            continue
        pair_key = pair_key_for(list(combo))
        if pair_key in used_pair_keys:
            continue
        use_penalty = sum(ad_use_counts.get(ad_id, 0) for ad_id in pair_key)
        score = left["template_count"] + right["template_count"]
        ranked = (use_penalty, -score, pair_key, combo)
        if best is None or ranked < best:
            best = ranked
    if best is None:
        return None
    return list(best[3])


def build_eval_tasks(
    ads_by_id: dict[str, Ad],
    clusters: list[Cluster],
    templates_by_sequence: dict[str, Template],
) -> list[EvalTask]:
    tasks: list[EvalTask] = []
    skipped = 0
    used_pair_keys: set[tuple[str, str]] = set()
    for cluster in clusters:
        candidates = candidates_for_cluster(cluster, ads_by_id, templates_by_sequence)
        ad_use_counts: dict[str, int] = {}
        cluster_tasks = 0
        for _ in range(desired_task_count(len(candidates))):
            pair = choose_pair(candidates, ad_use_counts, used_pair_keys)
            if pair is None:
                break
            pair_key = pair_key_for(pair)
            used_pair_keys.add(pair_key)
            for candidate in pair:
                ad_use_counts[candidate["ad_id"]] = ad_use_counts.get(candidate["ad_id"], 0) + 1
            tasks.append(make_task(cluster["category"], cluster["cluster_id"], "same_cluster", pair))
            cluster_tasks += 1
        if cluster_tasks == 0:
            skipped += 1

    same_cluster_count = len(tasks)
    cross_target = max(0, TARGET_TOTAL_TASKS - same_cluster_count)
    cross_use_counts: dict[str, int] = {}
    cross_tasks = 0
    grouped = grouped_candidates_by_category_and_bucket(clusters, ads_by_id, templates_by_sequence)
    bucket_keys = sorted(grouped)
    same_cluster_counts: dict[tuple[str, str], int] = {}
    for category, length in bucket_keys:
        same_cluster_counts[(category, length)] = sum(
            1
            for task in tasks
            if task["category"] == category
            and all(length_bucket(len(ad["sequence"])) == length for ad in task["ads"])
        )
    total_same_cluster = sum(same_cluster_counts.values())
    allocated_targets: dict[tuple[str, str], int] = {}
    remainders: list[tuple[float, tuple[str, str]]] = []
    allocated_total = 0
    for key in bucket_keys:
        same_count = same_cluster_counts[key]
        if total_same_cluster == 0 or same_count == 0:
            allocated_targets[key] = 0
            continue
        raw_target = cross_target * same_count / total_same_cluster
        base_target = int(raw_target)
        allocated_targets[key] = base_target
        allocated_total += base_target
        remainders.append((raw_target - base_target, key))
    for _, key in sorted(remainders, reverse=True):
        if allocated_total >= cross_target:
            break
        allocated_targets[key] += 1
        allocated_total += 1

    for (category, _), candidates in grouped.items():
        category_target = allocated_targets[(category, candidates[0]["length_bucket"])] if candidates else 0
        for _ in range(category_target):
            pair = choose_cross_cluster_pair(candidates, cross_use_counts, used_pair_keys)
            if pair is None:
                break
            pair_key = pair_key_for(pair)
            used_pair_keys.add(pair_key)
            for candidate in pair:
                cross_use_counts[candidate["ad_id"]] = cross_use_counts.get(candidate["ad_id"], 0) + 1
            cluster_id = f"cross:{pair[0]['cluster_id']}|{pair[1]['cluster_id']}"
            tasks.append(make_task(category, cluster_id, "cross_cluster", pair))
            cross_tasks += 1
    tasks.sort(key=lambda task: (task["category"], task["pair_scope"], task["id"]))
    log.info(
        "Built %d eval tasks (%d same-cluster, %d cross-cluster; target=%d); skipped %d clusters without enough distinct sequences",
        len(tasks),
        same_cluster_count,
        cross_tasks,
        cross_target,
        skipped,
    )
    return tasks


def write_output(
    path: Path,
    ads_path: Path,
    clusters_path: Path,
    templates_path: Path,
    tasks: list[EvalTask],
) -> None:
    output: EvalTaskOutput = {
        "source_ads": str(ads_path),
        "source_clusters": str(clusters_path),
        "source_templates": str(templates_path),
        "task_count": len(tasks),
        "tasks": tasks,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log.info("Saved %d eval tasks -> %s", len(tasks), path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build pairwise eval task JSON from clusters and templates")
    parser.add_argument("--ads", default="data/ds0_annotated.json", help="Annotated ads JSON")
    parser.add_argument("--clusters", default="data/ds0_clusters.json", help="Cluster JSON")
    parser.add_argument("--templates", default="data/ds0_templates.json", help="Template JSON")
    parser.add_argument("--output", default="data/ds0_eval_tasks.json", help="Eval task output JSON")
    args = parser.parse_args()

    ads_path = Path(args.ads)
    clusters_path = Path(args.clusters)
    templates_path = Path(args.templates)
    output_path = Path(args.output)

    ads_by_id = read_ads(ads_path)
    clusters = read_clusters(clusters_path)
    templates_by_sequence = read_templates(templates_path)
    tasks = build_eval_tasks(ads_by_id, clusters, templates_by_sequence)
    write_output(output_path, ads_path, clusters_path, templates_path, tasks)


if __name__ == "__main__":
    main()
