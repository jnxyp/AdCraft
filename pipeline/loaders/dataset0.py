"""Dataset 0: Facebook Ad Library scraper (primary dataset).

Uses browser session cookies captured from Network DevTools.
Auth tokens (fb_dtsg, lsd, __dyn, __csr, etc.) must be refreshed
from a live browser session when they expire.

Usage:
    python -m pipeline.loaders.dataset0  # reads config from fb_config.json
"""

import json
import time
import uuid
from pathlib import Path
from urllib.parse import quote, urlencode

import httpx

# ── Config ─────────────────────────────────────────────────────────────────
CONFIG_PATH = Path(__file__).parent.parent / "fb_config.json"
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "ds0_raw.json"

# Keywords chosen to cover all 10 target categories.
# Expanded with stronger purchase-intent and vertical-specific phrases
# to increase unique ad coverage.
QUERY_KEYWORDS: list[str] = [
    # ecommerce / general
    "buy",          # ecommerce / general
    "shop now",     # ecommerce
    "best seller",
    "limited time",
    "flash sale",
    "free shipping",
    "discount code",
    "bundle deal",
    "clearance",
    "new arrival",
    "gift ideas",
    "subscription box",

    # health / wellness / beauty
    "wellness",     # health
    "supplement",   # health
    "skincare",     # beauty
    "hair",         # beauty
    "anti aging",
    "weight loss",
    "protein powder",
    "vitamins",
    "collagen",
    "gut health",
    "acne treatment",
    "hair growth",

    # education
    "learn",        # education
    "course",       # education
    "online class",
    "certification",
    "bootcamp",
    "tutoring",
    "masterclass",

    # finance / insurance
    "invest",       # finance
    "insurance",    # finance
    "credit card",
    "personal loan",
    "mortgage rates",
    "retirement plan",
    "tax filing",

    # food / local services
    "restaurant",   # food
    "delivery",     # food
    "meal prep",
    "coffee shop",
    "catering",

    # travel
    "travel",       # travel
    "hotel",        # travel
    "flight deals",
    "vacation package",
    "car rental",
    "resort",

    # tech / app
    "software",     # tech
    "app",          # tech
    "saas",
    "crm",
    "ai tool",
    "project management",
    "automation",
    "cybersecurity",

    # automotive / fitness
    "car",          # automotive
    "fitness",      # health
    "auto repair",
    "used cars",
    "home workout",
    "gym membership",

    # broad conversion terms
    "sale",         # ecommerce
    "offer",        # ecommerce
]

PAGES_PER_KEYWORD: int = 5   # 5 pages × 30 ads = 150 ads per keyword
MIN_BODY_WORDS: int = 10     # drop ads with very short body text
DELAY_BETWEEN_REQUESTS: float = 1.5  # seconds, to avoid rate limiting


# ── Core request ───────────────────────────────────────────────────────────

def _build_variables(
    query: str,
    cursor: str | None,
    session_id: str,
) -> str:
    variables: dict = {
        "activeStatus": "active",
        "adType": "ALL",
        "bylines": [],
        "collationToken": None,
        "contentLanguages": [],
        "countries": ["US"],
        "cursor": cursor,
        "excludedIDs": None,
        "first": 30,
        "isTargetedCountry": False,
        "location": None,
        "mediaType": "all",
        "multiCountryFilterMode": None,
        "pageIDs": [],
        "potentialReachInput": None,
        "publisherPlatforms": [],
        "queryString": query,
        "regions": None,
        "searchType": "keyword_unordered",
        "sessionID": session_id,
        "sortData": {"direction": "DESCENDING", "mode": "SORT_BY_TOTAL_IMPRESSIONS"},
        "source": "NAV_HEADER",
        "startDate": None,
        "v": "3a20eb",
        "viewAllPageID": "0",
    }
    return json.dumps(variables, separators=(",", ":"))


def _parse_response(raw: str) -> tuple[list[dict], str | None, bool]:
    """Return (ads, next_cursor, has_next_page)."""
    # Facebook sometimes prepends `for (;;);` as XSS guard
    if raw.startswith("for (;;);"):
        raw = raw[9:]
    data = json.loads(raw)

    if "error" in data:
        raise RuntimeError(f"FB API error {data.get('error')}: {data.get('errorSummary')}")

    conn = data["data"]["ad_library_main"]["search_results_connection"]
    page_info: dict = conn.get("page_info", {})
    next_cursor: str | None = page_info.get("end_cursor")
    has_next: bool = page_info.get("has_next_page", False)

    ads: list[dict] = []
    for edge in conn.get("edges", []):
        for result in edge["node"].get("collated_results", []):
            snap: dict = result.get("snapshot", {})
            body_text: str = (snap.get("body") or {}).get("text", "").strip()
            title: str = (snap.get("title") or "").strip()
            link_desc: str = (snap.get("link_description") or "").strip()

            # Combine available text fields into a single body
            parts = [p for p in (title, body_text, link_desc) if p]
            full_body = "\n".join(parts)

            if len(full_body.split()) < MIN_BODY_WORDS:
                continue

            ads.append({
                "ad_id": str(uuid.uuid4()),
                "body": full_body,
                "product_desc": "",   # inferred by LLM in Step 2A
                "category": "",       # inferred by LLM in Step 2B
                "source": "fb",
                "_page_name": snap.get("page_name", ""),
                "_page_categories": snap.get("page_categories", []),
                "_cta_text": snap.get("cta_text", ""),
            })

    return ads, next_cursor, has_next


def _cookie_header(cfg: dict) -> str:
    """Build a raw Cookie header string, preserving URL-encoded values as-is."""
    cookies: dict = cfg["cookies"]
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def fetch_page(
    client: httpx.Client,
    cfg: dict,
    query: str,
    cursor: str | None,
    session_id: str,
) -> tuple[list[dict], str | None, bool]:
    variables_str = _build_variables(query, cursor, session_id)

    # Build form body as a raw string to avoid any re-encoding by httpx
    fields: list[tuple[str, str]] = [
        ("av", cfg["user_id"]),
        ("__aaid", "0"),
        ("__user", cfg["user_id"]),
        ("__a", "1"),
        ("__req", "d"),
        ("__hs", cfg["__hs"]),
        ("dpr", "1"),
        ("__ccg", "EXCELLENT"),
        ("__rev", cfg["__rev"]),
        ("__s", cfg["__s"]),
        ("__hsi", cfg["__hsi"]),
        ("__dyn", cfg["__dyn"]),
        ("__csr", cfg["__csr"]),
        ("__hsdp", cfg.get("__hsdp", "")),
        ("__hblp", cfg.get("__hblp", "")),
        ("__sjsp", cfg.get("__sjsp", "")),
        ("__comet_req", "94"),
        ("fb_dtsg", cfg["fb_dtsg"]),
        ("jazoest", cfg["jazoest"]),
        ("lsd", cfg["lsd"]),
        ("__spin_r", cfg["__spin_r"]),
        ("__spin_b", "trunk"),
        ("__spin_t", cfg["__spin_t"]),
        ("__jssesw", "1"),
        ("fb_api_caller_class", "RelayModern"),
        ("fb_api_req_friendly_name", "AdLibrarySearchPaginationQuery"),
        ("server_timestamps", "true"),
        ("variables", variables_str),
        ("doc_id", cfg["doc_id"]),
    ]
    # Use httpx's urlencode-equivalent but pass as content with explicit Content-Type
    from urllib.parse import urlencode as _urlencode
    raw_body = _urlencode(fields)

    resp = client.post(
        "https://www.facebook.com/api/graphql/",
        content=raw_body.encode("utf-8"),
        headers={
            "content-type": "application/x-www-form-urlencoded",
            "cookie": _cookie_header(cfg),
            "origin": "https://www.facebook.com",
            "referer": "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&q=buy&search_type=keyword_unordered",
            "x-fb-friendly-name": "AdLibrarySearchPaginationQuery",
            "x-fb-lsd": cfg["lsd"],
            "user-agent": cfg["user_agent"],
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "dnt": "1",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "x-asbd-id": "359341",
        },
    )
    resp.raise_for_status()
    return _parse_response(resp.text)


# ── Main scrape loop ────────────────────────────────────────────────────────

def scrape(target_per_keyword: int = PAGES_PER_KEYWORD) -> list[dict]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Missing {CONFIG_PATH}. Copy fb_config.example.json and fill in your session tokens."
        )
    cfg: dict = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    seen_bodies: set[str] = set()
    all_ads: list[dict] = []

    with httpx.Client(
        timeout=30.0,
        follow_redirects=True,
    ) as client:
        for keyword in QUERY_KEYWORDS:
            print(f"\n[keyword={keyword!r}]")
            cursor: str | None = None
            session_id = str(uuid.uuid4())
            pages_fetched = 0

            while pages_fetched < target_per_keyword:
                try:
                    ads, next_cursor, has_next = fetch_page(
                        client, cfg, keyword, cursor, session_id
                    )
                except Exception as exc:
                    print(f"  ERROR: {exc}")
                    break

                new_ads = [a for a in ads if a["body"] not in seen_bodies]
                for a in new_ads:
                    seen_bodies.add(a["body"])
                all_ads.extend(new_ads)
                pages_fetched += 1
                print(f"  page {pages_fetched}: +{len(new_ads)} new ads (total {len(all_ads)})", flush=True)
                OUTPUT_PATH.write_text(json.dumps(all_ads, ensure_ascii=False, indent=2), encoding="utf-8")

                if not has_next or next_cursor is None:
                    break
                cursor = next_cursor
                time.sleep(DELAY_BETWEEN_REQUESTS)

    return all_ads


def load() -> list[dict[str, str]]:
    """Return previously scraped FB ads from raw_fb.json."""
    if not OUTPUT_PATH.exists():
        raise FileNotFoundError(f"{OUTPUT_PATH} not found — run scrape() first.")
    data: list[dict[str, str]] = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    return data


if __name__ == "__main__":
    ads = scrape()
    OUTPUT_PATH.write_text(json.dumps(ads, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved {len(ads)} ads -> {OUTPUT_PATH}")
