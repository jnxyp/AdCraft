"""Run the local pipeline after raw data has been collected.

This entry point does not collect data. It starts from existing raw JSON files and
rebuilds downstream artifacts only when they are missing or explicitly forced.

Run from pipeline/:
    python main.py
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import TypedDict, cast

from dotenv import load_dotenv
from openai import OpenAI

import annotator
import cluster_builder
import dedup
import eval_task_builder
import template_builder

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)

PIPELINE_DIR: Path = Path(__file__).resolve().parent


class PipelinePaths(TypedDict):
    raw: Path
    deduped: Path
    annotated: Path
    clusters: Path
    templates: Path
    eval_tasks: Path
    embedding_cache: Path


def paths_for(dataset: str) -> PipelinePaths:
    data_dir = Path("data")
    return {
        "raw": data_dir / f"{dataset}_raw.json",
        "deduped": data_dir / f"{dataset}_dedup.json",
        "annotated": data_dir / f"{dataset}_annotated.json",
        "clusters": data_dir / f"{dataset}_clusters.json",
        "templates": data_dir / f"{dataset}_templates.json",
        "eval_tasks": data_dir / f"{dataset}_eval_tasks.json",
        "embedding_cache": data_dir / f"{dataset}_product_desc_embeddings.json",
    }


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def is_dedup_ready(path: Path) -> bool:
    if not path.exists():
        return False
    rows = cast(list[dict[str, object]], read_json(path))
    return bool(rows) and all(row.get("ad_id") and row.get("body") for row in rows)


def is_annotated_ready(path: Path) -> bool:
    if not path.exists():
        return False
    rows = cast(list[dict[str, object]], read_json(path))
    if not rows:
        return False
    for row in rows:
        sequence = row.get("sequence")
        if (
            not row.get("ad_id")
            or not row.get("body")
            or not row.get("product_desc")
            or not row.get("categories")
            or not isinstance(sequence, list)
            or not sequence
            or "sentences" in row
        ):
            return False
    return True


def is_cluster_ready(path: Path) -> bool:
    if not path.exists():
        return False
    data = cast(dict[str, object], read_json(path))
    clusters = data.get("clusters")
    if not isinstance(clusters, list) or not clusters:
        return False
    for item in clusters:
        cluster = cast(dict[str, object], item)
        if "ad_indices" in cluster:
            return False
        ad_ids = cluster.get("ad_ids")
        if not cluster.get("cluster_id") or not cluster.get("category") or not isinstance(ad_ids, list) or not ad_ids:
            return False
    return True


def is_template_ready(path: Path) -> bool:
    if not path.exists():
        return False
    data = cast(dict[str, object], read_json(path))
    templates = data.get("templates")
    if not isinstance(templates, list) or not templates:
        return False
    return all(cast(dict[str, object], item).get("id") for item in templates)


def is_eval_task_ready(path: Path) -> bool:
    if not path.exists():
        return False
    data = cast(dict[str, object], read_json(path))
    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return False
    for item in tasks:
        task = cast(dict[str, object], item)
        ads = task.get("ads")
        if not task.get("id") or task.get("task_type") != "pair" or not isinstance(ads, list) or len(ads) != 2:
            return False
    return True


def write_ads_sorted(path: Path, rows: list[dict[str, object]]) -> None:
    rows.sort(key=lambda row: str(row.get("ad_id", "")))
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_dedup(paths: PipelinePaths, force: bool) -> None:
    if is_dedup_ready(paths["deduped"]) and not force:
        log.info("Step 1.5 dedup: cache hit -> %s", paths["deduped"])
        return
    if not paths["raw"].exists():
        raise FileNotFoundError(f"Raw input not found: {paths['raw']}")

    rows = cast(list[dict[str, object]], read_json(paths["raw"]))
    log.info("Step 1.5 dedup: loaded %d raw ads from %s", len(rows), paths["raw"])
    deduped = dedup.exact_dedup(rows)
    client = OpenAI()
    deduped = dedup.near_dedup(deduped, client, threshold=dedup.NEAR_THRESHOLD)
    paths["deduped"].parent.mkdir(parents=True, exist_ok=True)
    write_ads_sorted(paths["deduped"], deduped)
    log.info("Step 1.5 dedup: saved %d ads -> %s", len(deduped), paths["deduped"])


def run_annotate(paths: PipelinePaths, force: bool) -> None:
    checkpoint_path = paths["annotated"].with_suffix("").with_suffix(".checkpoint.json")
    if is_annotated_ready(paths["annotated"]) and not force and not checkpoint_path.exists():
        log.info("Step 2/4 annotation: LLM cache hit -> %s", paths["annotated"])
        return
    if force and paths["annotated"].exists():
        paths["annotated"].unlink()
    asyncio.run(annotator.annotate(paths["deduped"], paths["annotated"], checkpoint_path))


def run_clusters(paths: PipelinePaths, force: bool) -> None:
    if is_cluster_ready(paths["clusters"]) and not force:
        log.info("Step 3 clusters: cache hit -> %s", paths["clusters"])
        return
    ads = cluster_builder.load_ads(paths["annotated"])
    embeddings = cluster_builder.load_or_create_embeddings(ads, paths["annotated"], paths["embedding_cache"])
    clusters = cluster_builder.build_clusters(
        ads,
        embeddings,
        cluster_builder.SIMILARITY_THRESHOLD,
        cluster_builder.MIN_CLUSTER_SIZE,
        cluster_builder.TARGET_CLUSTER_SIZE,
    )
    cluster_builder.write_output(
        paths["clusters"],
        paths["annotated"],
        clusters,
        cluster_builder.SIMILARITY_THRESHOLD,
        cluster_builder.MIN_CLUSTER_SIZE,
        cluster_builder.TARGET_CLUSTER_SIZE,
    )


def run_templates(paths: PipelinePaths, force: bool) -> None:
    if is_template_ready(paths["templates"]) and not force:
        log.info("Step 5 templates: cache hit -> %s", paths["templates"])
        return
    ads = template_builder.load_ads(paths["annotated"])
    templates = template_builder.build_templates(ads)
    template_builder.print_summary(templates, len(ads))
    template_builder.write_output(paths["templates"], paths["annotated"], templates, len(ads))


def run_eval_tasks(paths: PipelinePaths, force: bool) -> None:
    if is_eval_task_ready(paths["eval_tasks"]) and not force:
        log.info("Step 6 eval tasks: cache hit -> %s", paths["eval_tasks"])
        return
    ads_by_id = eval_task_builder.read_ads(paths["annotated"])
    clusters = eval_task_builder.read_clusters(paths["clusters"])
    templates_by_sequence = eval_task_builder.read_templates(paths["templates"])
    tasks = eval_task_builder.build_eval_tasks(ads_by_id, clusters, templates_by_sequence)
    eval_task_builder.write_output(
        paths["eval_tasks"],
        paths["annotated"],
        paths["clusters"],
        paths["templates"],
        tasks,
    )


def main() -> None:
    load_dotenv(PIPELINE_DIR.parent / ".env")

    parser = argparse.ArgumentParser(description="Run the pipeline after raw data collection")
    parser.add_argument("--dataset", default="ds0", help="Dataset prefix, e.g. ds0")
    parser.add_argument("--force-all", action="store_true", help="Rebuild all downstream artifacts")
    parser.add_argument("--force-dedup", action="store_true", help="Rebuild the deduped JSON")
    parser.add_argument("--force-annotate", action="store_true", help="Rebuild LLM annotations")
    parser.add_argument("--force-clusters", action="store_true", help="Rebuild clusters")
    parser.add_argument("--force-templates", action="store_true", help="Rebuild templates")
    parser.add_argument("--force-eval-tasks", action="store_true", help="Rebuild eval task JSON")
    args = parser.parse_args()

    if Path.cwd().resolve() != PIPELINE_DIR:
        log.info("Changing working directory to %s", PIPELINE_DIR)
        import os
        os.chdir(PIPELINE_DIR)

    paths = paths_for(str(args.dataset))
    force_all = bool(args.force_all)

    run_dedup(paths, force_all or bool(args.force_dedup))
    run_annotate(paths, force_all or bool(args.force_annotate))
    run_clusters(paths, force_all or bool(args.force_clusters))
    run_templates(paths, force_all or bool(args.force_templates))
    run_eval_tasks(paths, force_all or bool(args.force_eval_tasks))
    log.info("Pipeline complete for %s", args.dataset)


if __name__ == "__main__":
    main()
