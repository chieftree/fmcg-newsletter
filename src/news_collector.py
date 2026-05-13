import hashlib
import re
import time
from datetime import datetime, timedelta
from urllib.parse import quote_plus

import feedparser


REGION_CONFIG = {
    "global": ("en-US", "US", "US:en"),
    "asia":   ("en-SG", "SG", "SG:en"),
    "korea":  ("ko",    "KR", "KR:ko"),
}


def _build_rss_url(query: str, region: str, lookback_days: int) -> str:
    hl, gl, ceid = REGION_CONFIG[region]
    tbs = "qdr:y" if lookback_days >= 365 else "qdr:w"
    return (
        f"https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&hl={hl}&gl={gl}&ceid={ceid}&tbs={tbs}"
    )


def _url_hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()


def _fetch_articles(queries: list, region: str, lookback_days: int, sent_hashes: set) -> list:
    articles = []
    seen_hashes = set(sent_hashes)
    seen_titles: set = set()
    cutoff = datetime.utcnow() - timedelta(days=lookback_days)

    for query in queries:
        url = _build_rss_url(query, region, lookback_days)
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                title = entry.get("title", "").strip()
                link = entry.get("link", "")
                description = re.sub(r"<[^>]+>", "", entry.get("summary", ""))

                parsed = entry.get("published_parsed")
                if parsed:
                    pub_dt = datetime(*parsed[:6])
                    if pub_dt < cutoff:
                        continue
                    date_str = pub_dt.strftime("%Y-%m-%d")
                else:
                    date_str = "Unknown"

                title_key = re.sub(r"\W+", "", title.lower())[:60]
                h = _url_hash(link)
                if h in seen_hashes or title_key in seen_titles:
                    continue

                seen_hashes.add(h)
                seen_titles.add(title_key)
                articles.append({
                    "title": title,
                    "url": link,
                    "description": description[:300],
                    "hash": h,
                    "date": date_str,
                })
        except Exception as exc:
            print(f"[WARN] RSS fetch failed — query='{query}' region={region}: {exc}")

        time.sleep(0.5)

    return articles[:20]


def collect_all(keywords_config: dict, lookback_days: int, sent_urls: list) -> dict:
    sent_hashes = set(sent_urls)
    results: dict = {}

    for cat_key, cat in keywords_config["categories"].items():
        results[cat_key] = {}
        queries_by_region = cat.get("queries", {})

        if cat.get("global_only"):
            results[cat_key]["global"] = _fetch_articles(
                queries_by_region.get("global", []), "global", lookback_days, sent_hashes
            )
            results[cat_key]["asia"] = []
            results[cat_key]["korea"] = []
        else:
            for region in ("global", "asia", "korea"):
                results[cat_key][region] = _fetch_articles(
                    queries_by_region.get(region, []), region, lookback_days, sent_hashes
                )

        print(f"[INFO] Collected {cat_key}: "
              f"global={len(results[cat_key]['global'])} "
              f"asia={len(results[cat_key]['asia'])} "
              f"korea={len(results[cat_key]['korea'])}")

    return results
