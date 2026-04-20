"""Inspect HuggingFace dataset fields and print sample rows."""
import json
import sys
from datasets import load_dataset  # type: ignore[import-untyped]


def safe_print(text: str) -> None:
    """Print with non-ASCII chars escaped to avoid GBK console errors."""
    sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))
    sys.stdout.buffer.flush()


def inspect(dataset_id: str, n_samples: int = 3) -> None:
    safe_print(f"\n{'='*60}")
    safe_print(f"Dataset: {dataset_id}")
    safe_print("="*60)
    ds = load_dataset(dataset_id)
    for split_name, split in ds.items():
        safe_print(f"\n--- split: {split_name}  ({len(split)} rows) ---")
        safe_print("features: " + json.dumps({k: str(v) for k, v in split.features.items()}, indent=2))
        safe_print(f"\nFirst {n_samples} rows:")
        for i, row in enumerate(split.select(range(min(n_samples, len(split))))):
            safe_print(f"\n[{i}] " + json.dumps(row, indent=2, ensure_ascii=True, default=str))


if __name__ == "__main__":
    inspect("smangrul/ad-copy-generation")
    inspect("PeterBrendan/Ads_Creative_Ad_Copy_Programmatic")
