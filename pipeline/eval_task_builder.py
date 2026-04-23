"""Build human evaluation tasks from product clusters and sequence templates.

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


class TaskAd(TypedDict):
    slot: Slot
    ad_id: str
    body: str
    template_id: str
    sequence: list[str]


class EvalTask(TypedDict):
    id: str
    task_type: Literal["pair"]
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


def task_id(category: str, cluster_id: str, ads: list[TaskAd]) -> str:
    payload = {
        "category": category,
        "cluster_id": cluster_id,
        "ads": [
            {
                "slot": ad["slot"],
                "ad_id": ad["ad_id"],
                "template_id": ad["template_id"],
            }
            for ad in ads
        ],
    }
    digest = hashlib.sha1(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:12]
    return f"eval_{digest}"


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
        candidates.append({
            "ad_id": ad["ad_id"],
            "body": ad["body"],
            "sequence": ad["sequence"],
            "sequence_key": seq_key,
            "template_id": template["id"],
            "template_count": template["count"],
        })
    return candidates


def desired_task_count(cluster_size: int) -> int:
    return cluster_size // 2


def choose_pair(candidates: list[Candidate], used_ad_ids: set[str]) -> list[Candidate] | None:
    available = [candidate for candidate in candidates if candidate["ad_id"] not in used_ad_ids]
    best: tuple[int, tuple[str, str], tuple[Candidate, Candidate]] | None = None
    for combo in combinations(available, 2):
        sequence_keys = {candidate["sequence_key"] for candidate in combo}
        if len(sequence_keys) != 2:
            continue
        score = sum(candidate["template_count"] for candidate in combo)
        ad_ids = tuple(candidate["ad_id"] for candidate in combo)
        ranked = (-score, ad_ids, combo)
        if best is None or ranked < best:
            best = ranked
    if best is None:
        return None
    return list(best[2])


def make_task(category: str, cluster_id: str, candidates: list[Candidate]) -> EvalTask:
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
        "id": task_id(category, cluster_id, task_ads),
        "task_type": "pair",
        "category": category,
        "cluster_id": cluster_id,
        "ads": task_ads,
    }


def build_eval_tasks(
    ads_by_id: dict[str, Ad],
    clusters: list[Cluster],
    templates_by_sequence: dict[str, Template],
) -> list[EvalTask]:
    tasks: list[EvalTask] = []
    skipped = 0
    for cluster in clusters:
        candidates = candidates_for_cluster(cluster, ads_by_id, templates_by_sequence)
        used_ad_ids: set[str] = set()
        cluster_tasks = 0
        for _ in range(desired_task_count(len(candidates))):
            pair = choose_pair(candidates, used_ad_ids)
            if pair is None:
                break
            used_ad_ids.update(candidate["ad_id"] for candidate in pair)
            tasks.append(make_task(cluster["category"], cluster["cluster_id"], pair))
            cluster_tasks += 1
        if cluster_tasks == 0:
            skipped += 1
    tasks.sort(key=lambda task: (task["category"], task["task_type"], task["id"]))
    log.info("Built %d eval tasks; skipped %d clusters without enough distinct sequences", len(tasks), skipped)
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
