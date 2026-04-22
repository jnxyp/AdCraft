"""Build pattern-sequence templates from annotated ads.

Run from pipeline/:
    python template_builder.py
    python template_builder.py --input data/ds0_annotated.json --output data/ds0_templates.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import NotRequired, TypedDict, cast

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)


class Ad(TypedDict):
    ad_id: str
    body: str
    product_desc: str
    categories: list[str]
    sequence: list[str]
    source: NotRequired[str]


class Template(TypedDict):
    id: str
    sequence: list[str]
    name: str
    seq_len: int
    count: int
    freq_score: float
    categories: list[str]
    example_ad_id: str
    example_body: str
    example_product_desc: str


class TemplateOutput(TypedDict):
    source: str
    template_count: int
    ad_count: int
    templates: list[Template]


def load_ads(path: Path) -> list[Ad]:
    raw_ads = json.loads(path.read_text(encoding="utf-8"))
    ads = cast(list[Ad], raw_ads)
    missing: list[str] = []
    for index, ad in enumerate(ads):
        if not ad.get("ad_id"):
            missing.append(f"{index}:ad_id")
        if not ad.get("body"):
            missing.append(f"{index}:body")
        if not ad.get("product_desc"):
            missing.append(f"{index}:product_desc")
        if not ad.get("categories"):
            missing.append(f"{index}:categories")
        if not ad.get("sequence"):
            missing.append(f"{index}:sequence")
    if missing:
        preview = ", ".join(missing[:10])
        raise ValueError(f"Annotated ads are missing required fields: {preview}")
    return ads


def sequence_key(sequence: list[str]) -> str:
    return json.dumps(sequence, ensure_ascii=False, separators=(",", ":"))


def template_id(sequence: list[str]) -> str:
    digest = hashlib.sha1(sequence_key(sequence).encode("utf-8")).hexdigest()[:12]
    return f"tmpl_{digest}"


def template_name(sequence: list[str]) -> str:
    return "→".join(sequence)


def build_templates(ads: list[Ad]) -> list[Template]:
    grouped: dict[str, list[Ad]] = defaultdict(list)
    for ad in ads:
        grouped[sequence_key(ad["sequence"])].append(ad)

    total = len(ads)
    templates: list[Template] = []
    for key, members in grouped.items():
        sequence = cast(list[str], json.loads(key))
        example = members[0]
        categories = sorted({category for ad in members for category in ad["categories"]})
        count = len(members)
        templates.append({
            "id": template_id(sequence),
            "sequence": sequence,
            "name": template_name(sequence),
            "seq_len": len(sequence),
            "count": count,
            "freq_score": count / total,
            "categories": categories,
            "example_ad_id": example["ad_id"],
            "example_body": example["body"],
            "example_product_desc": example["product_desc"],
        })

    return sorted(
        templates,
        key=lambda item: (-item["count"], item["seq_len"], item["name"], item["id"]),
    )


def print_summary(templates: list[Template], ad_count: int) -> None:
    by_len: dict[int, int] = defaultdict(int)
    for template in templates:
        by_len[template["seq_len"]] += 1

    log.info("Built %d templates from %d ads", len(templates), ad_count)
    log.info(
        "Top templates: %s",
        "; ".join(
            f"{template['name']} ({template['count']})" for template in templates[:10]
        ),
    )
    log.info(
        "Template seq_len distribution: %s",
        ", ".join(f"{seq_len}x{count}" for seq_len, count in sorted(by_len.items())),
    )


def write_output(path: Path, source: Path, templates: list[Template], ad_count: int) -> None:
    output: TemplateOutput = {
        "source": str(source),
        "template_count": len(templates),
        "ad_count": ad_count,
        "templates": templates,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log.info("Saved %d templates -> %s", len(templates), path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build pattern-sequence templates from annotated ads")
    parser.add_argument("--input", default="data/ds0_annotated.json", help="Annotated ads JSON")
    parser.add_argument("--output", default="data/ds0_templates.json", help="Template output JSON")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    ads = load_ads(input_path)
    log.info("Loaded %d annotated ads from %s", len(ads), input_path)
    templates = build_templates(ads)
    print_summary(templates, len(ads))
    write_output(output_path, input_path, templates, len(ads))


if __name__ == "__main__":
    main()
