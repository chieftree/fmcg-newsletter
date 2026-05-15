import hashlib
import os
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import feedparser
import requests


REGION_CONFIG = {
    "global": ("en-US", "US", "US:en"),
    "asia":   ("en-SG", "SG", "SG:en"),
    "korea":  ("ko",    "KR", "KR:ko"),
}

FMCG_RELEVANCE_KEYWORDS = [
    "brand", "marketing", "campaign", "consumer", "fmcg", "cpg", "food",
    "snack", "beverage", "retail", "sales", "launch", "product", "viral",
    "pop-up", "activation", "award", "market share", "growth",
    "snickers", "m&m", "pringles", "kellogg", "mars", "kellanova",
    "skittles", "twix", "starburst", "cesar", "sheba",
]


def _url_hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()


def _is_relevant(title: str, description: str) -> bool:
    text = (title + " " + description).lower()
    return any(kw in text for kw in FMCG_RELEVANCE_KEYWORDS)


def _clean_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


# ── Google News RSS ────────────────────────────────────────────────────────────

def _build_rss_url(query: str, region: str, lookback_days: int) -> str:
    hl, gl, ceid = REGION_CONFIG[region]
    tbs = "qdr:y" if lookback_days >= 365 else "qdr:w"
    return (
        f"https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&hl={hl}&gl={gl}&ceid={ceid}&tbs={tbs}"
    )


def _fetch_google_news(queries: list, region: str, lookback_days: int,
                       seen_hashes: set, seen_titles: set) -> list:
    articles = []
    cutoff = datetime.utcnow() - timedelta(days=lookback_days)

    for query in queries:
        url = _build_rss_url(query, region, lookback_days)
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                title = entry.get("title", "").strip()
                link = entry.get("link", "")
                description = _clean_html(entry.get("summary", ""))

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
                    "source_type": "news",
                })
        except Exception as exc:
            print(f"[WARN] Google News RSS failed — query='{query}' region={region}: {exc}")

        time.sleep(0.4)

    return articles


# ── Marketing Publication RSS ──────────────────────────────────────────────────

def _fetch_premium_rss(rss_sources: list, lookback_days: int,
                       seen_hashes: set, seen_titles: set) -> list:
    articles = []
    cutoff = datetime.utcnow() - timedelta(days=lookback_days)

    for source in rss_sources:
        url = source.get("url", "")
        source_name = source.get("name", "")
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                title = entry.get("title", "").strip()
                link = entry.get("link", "")
                description = _clean_html(entry.get("summary", "") or entry.get("description", ""))

                parsed = entry.get("published_parsed")
                if parsed:
                    pub_dt = datetime(*parsed[:6])
                    if pub_dt < cutoff:
                        continue
                    date_str = pub_dt.strftime("%Y-%m-%d")
                else:
                    date_str = "Unknown"

                if not _is_relevant(title, description):
                    continue

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
                    "source_type": "magazine",
                    "source_name": source_name,
                })
        except Exception as exc:
            print(f"[WARN] Premium RSS failed — source='{source_name}': {exc}")

        time.sleep(0.3)

    return articles


# ── YouTube Data API ───────────────────────────────────────────────────────────

def _search_youtube(queries: list, api_key: str, lookback_days: int,
                    seen_hashes: set, seen_titles: set) -> list:
    if not api_key:
        return []

    articles = []
    published_after = (
        datetime.now(timezone.utc) - timedelta(days=lookback_days)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    for query in queries:
        try:
            resp = requests.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={
                    "part": "snippet",
                    "q": query,
                    "type": "video",
                    "maxResults": 5,
                    "order": "relevance",
                    "relevanceLanguage": "en",
                    "publishedAfter": published_after,
                    "key": api_key,
                },
                timeout=10,
            )
            data = resp.json()
            if "error" in data:
                print(f"[WARN] YouTube API error: {data['error'].get('message', '')}")
                break

            for item in data.get("items", []):
                snippet = item.get("snippet", {})
                video_id = item.get("id", {}).get("videoId", "")
                if not video_id:
                    continue

                title = snippet.get("title", "").strip()
                description = snippet.get("description", "")[:300]
                link = f"https://www.youtube.com/watch?v={video_id}"
                date_str = snippet.get("publishedAt", "")[:10]
                channel = snippet.get("channelTitle", "YouTube")

                title_key = re.sub(r"\W+", "", title.lower())[:60]
                h = _url_hash(link)
                if h in seen_hashes or title_key in seen_titles:
                    continue

                seen_hashes.add(h)
                seen_titles.add(title_key)
                articles.append({
                    "title": title,
                    "url": link,
                    "description": description,
                    "hash": h,
                    "date": date_str,
                    "source_type": "youtube",
                    "source_name": channel,
                })
        except Exception as exc:
            print(f"[WARN] YouTube search failed — query='{query}': {exc}")

        time.sleep(0.5)

    return articles


# ── Main collector ─────────────────────────────────────────────────────────────

def collect_all(keywords_config: dict, lookback_days: int, sent_urls: list) -> dict:
    sent_hashes: set = set(sent_urls)
    results: dict = {}

    youtube_api_key = os.environ.get("YOUTUBE_API_KEY", "")
    rss_sources_by_region = keywords_config.get("rss_sources", {})
    youtube_queries_by_cat = keywords_config.get("youtube_queries", {})

    # Pre-fetch premium RSS articles (shared across categories)
    premium_pool: dict = {}
    for region in ("global", "asia", "korea"):
        rss_list = rss_sources_by_region.get(region, [])
        if rss_list:
            premium_pool[region] = _fetch_premium_rss(
                rss_list, lookback_days, set(), set()
            )
            print(f"[INFO] Premium RSS [{region}]: {len(premium_pool[region])} articles")
        else:
            premium_pool[region] = []

    for cat_key, cat in keywords_config["categories"].items():
        results[cat_key] = {}
        queries_by_region = cat.get("queries", {})
        yt_queries = youtube_queries_by_cat.get(cat_key, {})

        for region in ("global", "asia", "korea"):
            if cat.get("global_only") and region != "global":
                results[cat_key][region] = []
                continue

            # Shared seen sets per region×category to deduplicate across sources
            seen_h: set = set(sent_hashes)
            seen_t: set = set()

            # 1. Google News RSS
            gnews = _fetch_google_news(
                queries_by_region.get(region, []),
                region, lookback_days, seen_h, seen_t,
            )

            # 2. Relevant articles from premium RSS pool (keyword-filtered)
            cat_keywords = [w.lower() for w in (
                cat.get("name", "").split() +
                queries_by_region.get(region, [])[:2]
            )]
            premium = [
                a for a in premium_pool.get(region, [])
                if _url_hash(a["url"]) not in seen_h
                and _is_relevant(a["title"], a["description"])
            ]
            for a in premium:
                seen_h.add(_url_hash(a["url"]))

            # 3. YouTube
            yt = _search_youtube(
                yt_queries.get(region, []),
                youtube_api_key, lookback_days, seen_h, seen_t,
            )

            merged = (gnews + premium + yt)[:25]
            results[cat_key][region] = merged

        print(f"[INFO] Collected {cat_key}: "
              f"global={len(results[cat_key]['global'])} "
              f"asia={len(results[cat_key]['asia'])} "
              f"korea={len(results[cat_key]['korea'])}")

    return results
