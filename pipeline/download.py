"""Download both datasets and save as JSON to pipeline/data/."""
import json
from pathlib import Path

from loaders.dataset1 import load as load_ds1
from loaders.dataset2 import load as load_ds2

DATA_DIR = Path(__file__).parent / "data"


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)

    print("Downloading DS1...")
    ds1 = load_ds1()
    out1 = DATA_DIR / "raw_ds1.json"
    out1.write_text(json.dumps(ds1, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Saved {len(ds1)} rows -> {out1}")

    print("Downloading DS2...")
    ds2 = load_ds2()
    out2 = DATA_DIR / "raw_ds2.json"
    out2.write_text(json.dumps(ds2, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Saved {len(ds2)} rows -> {out2}")


if __name__ == "__main__":
    main()
