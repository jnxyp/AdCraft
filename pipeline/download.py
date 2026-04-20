"""Download all datasets and save as JSON to pipeline/data/.

DS0 (Facebook Ad Library) is the primary dataset; DS1 and DS2 are backups.
DS0 requires a live fb_config.json with browser session tokens — run scrape()
manually when tokens need refreshing. This script only calls load() which
reads the already-scraped raw_ds0.json.
"""
import json
from pathlib import Path

from loaders.dataset0 import load as load_ds0
from loaders.dataset1 import load as load_ds1
from loaders.dataset2 import load as load_ds2

DATA_DIR = Path(__file__).parent / "data"


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)

    print("Loading DS0 (Facebook Ad Library)...")
    ds0 = load_ds0()
    out0 = DATA_DIR / "raw_ds0.json"
    out0.write_text(json.dumps(ds0, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  {len(ds0)} rows -> {out0}")

    print("Loading DS1 (smangrul/ad-copy-generation, backup)...")
    ds1 = load_ds1()
    out1 = DATA_DIR / "raw_ds1.json"
    out1.write_text(json.dumps(ds1, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  {len(ds1)} rows -> {out1}")

    print("Loading DS2 (PeterBrendan/Ads_Creative, backup)...")
    ds2 = load_ds2()
    out2 = DATA_DIR / "raw_ds2.json"
    out2.write_text(json.dumps(ds2, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  {len(ds2)} rows -> {out2}")


if __name__ == "__main__":
    main()
