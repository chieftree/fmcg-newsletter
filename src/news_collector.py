import hashlib
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import feedparser
import requests


REGION_CONFIG = {
    "global": ("en-US", "US", "US:en"),
    "asia":   ("en-SG", "SG", "SG:en"),
    "korea":  ("ko",    "KR", "KR:ko"),
}

YOUTUBE_THRESHOLDS = {
    "viral_social":     {"min_views": 500_000, "min_subs": 50_000},
    "brand_activation": {"min_views":  50_000, "min_subs": 50_000},
    "award_campaigns":  {"min_views":  50_000, "min_subs": 50_000},
    "byron_sharp":      {"min_views":  10_000, "min_subs": 50_000},
    "mars_snacking":    {"min_views": 100_000, "min_subs": 50_000},
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


# ── URL Validation ─────────────────────────────────────────────────────────────

def _check_url(url: str) -> tuple:
    try:
        resp = requests.head(
            url, allow_redirects=True, timeout=5,
            headers={"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"},
        )
        return url, resp.status_code < 400
    except Exception:
        return url, False


def _filter_valid_urls(articles: list) -> list:
    """Parallel HEAD-check; drops dead/4xx/5xx links. Skips reliable sources."""
    SKIP_TYPES = {"youtube", "reddit", "guardian", "gnews"}
    to_check = [a for a in articles if a.get("source_type") not in SKIP_TYPES]
    trusted  = [a for a in articles if a.get("source_type") in SKIP_TYPES]

    if not to_check:
        return articles

    url_status: dict = {}
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {pool.submit(_check_url, a["url"]): a["url"] for a in to_check}
        for future in as_completed(futures):
            try:
                url, ok = future.result()
                url_status[url] = ok
            except Exception:
                url_status[futures[future]] = False

    valid = [a for a in to_check if url_status.get(a["url"], False)]
    dropped = len(to_check) - len(valid)
    if dropped:
        print(f"[INFO] URL check: removed {dropped} dead links")
    return valid + trusted


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
                link  = entry.get("link", "")
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
                    "title": title, "url": link,
                    "description": description[:300], "hash": h,
                    "date": date_str, "source_type": "google_news",
                })
        except Exception as exc:
            print(f"[WARN] Google News RSS — query='{query}' region={region}: {exc}")
        time.sleep(0.4)

    return articles


# ── Marketing Publication RSS ──────────────────────────────────────────────────

def _fetch_premium_rss(rss_sources: list, lookback_days: int,
                       seen_hashes: set, seen_titles: set) -> list:
    articles = []
    cutoff = datetime.utcnow() - timedelta(days=lookback_days)

    for source in rss_sources:
        url         = source.get("url", "")
        source_name = source.get("name", "")
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                title = entry.get("title", "").strip()
                link  = entry.get("link", "")
                description = _clean_html(
                    entry.get("summary", "") or entry.get("description", "")
                )

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
                    "title": title, "url": link,
                    "description": description[:300], "hash": h,
                    "date": date_str, "source_type": "magazine",
                    "source_name": source_name,
                })
        except Exception as exc:
            print(f"[WARN] Premium RSS — source='{source_name}': {exc}")
        time.sleep(0.3)

    return articles


# ── NewsAPI ────────────────────────────────────────────────────────────────────

def _fetch_newsapi(queries: list, api_key: str, lookback_days: int,
                   seen_hashes: set, seen_titles: set) -> list:
    if not api_key:
        return []

    articles  = []
    from_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    for query in queries[:4]:
        try:
            resp = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": query, "from": from_date, "language": "en",
                    "sortBy": "relevancy", "pageSize": 10, "apiKey": api_key,
                },
                timeout=10,
            )
            data = resp.json()
            if data.get("status") != "ok":
                print(f"[WARN] NewsAPI: {data.get('message', '')}")
                break

            for item in data.get("articles", []):
                url   = item.get("url", "")
                title = (item.get("title") or "").strip()
                if not url or url == "[Removed]" or title in ("", "[Removed]"):
                    continue
                description = item.get("description") or item.get("content") or ""
                pub_date    = (item.get("publishedAt") or "")[:10]
                source_name = item.get("source", {}).get("name", "NewsAPI")

                title_key = re.sub(r"\W+", "", title.lower())[:60]
                h = _url_hash(url)
                if h in seen_hashes or title_key in seen_titles:
                    continue

                seen_hashes.add(h)
                seen_titles.add(title_key)
                articles.append({
                    "title": title, "url": url,
                    "description": description[:300], "hash": h,
                    "date": pub_date, "source_type": "newsapi",
                    "source_name": source_name,
                })
        except Exception as exc:
            print(f"[WARN] NewsAPI — query='{query}': {exc}")
        time.sleep(0.3)

    return articles


# ── The Guardian API ───────────────────────────────────────────────────────────

def _fetch_guardian(queries: list, api_key: str, lookback_days: int,
                    seen_hashes: set, seen_titles: set) -> list:
    if not api_key:
        return []

    articles  = []
    from_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    for query in queries[:4]:
        try:
            resp = requests.get(
                "https://content.guardianapis.com/search",
                params={
                    "q": query, "from-date": from_date,
                    "show-fields": "trailText", "page-size": 10,
                    "order-by": "relevance", "api-key": api_key,
                },
                timeout=10,
            )
            for item in resp.json().get("response", {}).get("results", []):
                url      = item.get("webUrl", "")
                title    = item.get("webTitle", "").strip()
                desc     = _clean_html(item.get("fields", {}).get("trailText", ""))
                pub_date = (item.get("webPublicationDate") or "")[:10]

                title_key = re.sub(r"\W+", "", title.lower())[:60]
                h = _url_hash(url)
                if h in seen_hashes or title_key in seen_titles:
                    continue

                seen_hashes.add(h)
                seen_titles.add(title_key)
                articles.append({
                    "title": title, "url": url,
                    "description": desc[:300], "hash": h,
                    "date": pub_date, "source_type": "guardian",
                    "source_name": "The Guardian",
                })
        except Exception as exc:
            print(f"[WARN] Guardian API — query='{query}': {exc}")
        time.sleep(0.3)

    return articles


# ── GNews API ──────────────────────────────────────────────────────────────────

def _fetch_gnews(queries: list, api_key: str, lookback_days: int,
                 seen_hashes: set, seen_titles: set, region: str = "global") -> list:
    if not api_key:
        return []

    articles    = []
    lang_map    = {"global": "en", "asia": "en", "korea": "ko"}
    country_map = {"global": "us", "asia": "sg", "korea": "kr"}

    for query in queries[:3]:
        try:
            resp = requests.get(
                "https://gnews.io/api/v4/search",
                params={
                    "q": query,
                    "lang": lang_map.get(region, "en"),
                    "country": country_map.get(region, "us"),
                    "max": 10, "apikey": api_key,
                },
                timeout=10,
            )
            data = resp.json()
            if "errors" in data:
                print(f"[WARN] GNews: {data['errors']}")
                break

            for item in data.get("articles", []):
                url   = item.get("url", "")
                title = (item.get("title") or "").strip()
                if not url or not title:
                    continue
                description = item.get("description") or item.get("content") or ""
                pub_date    = (item.get("publishedAt") or "")[:10]
                source_name = item.get("source", {}).get("name", "GNews")

                title_key = re.sub(r"\W+", "", title.lower())[:60]
                h = _url_hash(url)
                if h in seen_hashes or title_key in seen_titles:
                    continue

                seen_hashes.add(h)
                seen_titles.add(title_key)
                articles.append({
                    "title": title, "url": url,
                    "description": description[:300], "hash": h,
                    "date": pub_date, "source_type": "gnews",
                    "source_name": source_name,
                })
        except Exception as exc:
            print(f"[WARN] GNews — query='{query}': {exc}")
        time.sleep(1.5)  # GNews rate limit

    return articles


# ── Currents API ──────────────────────────────────────────────────────────────

def _fetch_currents(queries: list, api_key: str, lookback_days: int,
                    seen_hashes: set, seen_titles: set, region: str = "global") -> list:
    if not api_key:
        return []

    articles   = []
    lang_map   = {"global": "en", "asia": "en", "korea": "ko"}
    start_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d %H:%M:%S +0000")

    for query in queries[:3]:
        try:
            resp = requests.get(
                "https://api.currentsapi.services/v1/search",
                params={
                    "apiKey":     api_key,
                    "keywords":   query,
                    "language":   lang_map.get(region, "en"),
                    "start_date": start_date,
                    "page_size":  10,
                },
                timeout=10,
            )
            data = resp.json()
            if data.get("status") != "ok":
                print(f"[WARN] Currents API: {data.get('message', '')}")
                break

            for item in data.get("news", []):
                url   = item.get("url", "")
                title = (item.get("title") or "").strip()
                if not url or not title:
                    continue
                description = item.get("description") or ""
                pub_date    = (item.get("published") or "")[:10]
                source_name = item.get("author") or "Currents"

                title_key = re.sub(r"\W+", "", title.lower())[:60]
                h = _url_hash(url)
                if h in seen_hashes or title_key in seen_titles:
                    continue

                seen_hashes.add(h)
                seen_titles.add(title_key)
                articles.append({
                    "title": title, "url": url,
                    "description": description[:300], "hash": h,
                    "date": pub_date, "source_type": "currents",
                    "source_name": source_name,
                })
        except Exception as exc:
            print(f"[WARN] Currents API — query='{query}': {exc}")
        time.sleep(0.3)

    return articles


# ── Naver News Search API ─────────────────────────────────────────────────────

def _fetch_naver_news(queries: list, client_id: str, client_secret: str,
                      lookback_days: int, seen_hashes: set, seen_titles: set) -> list:
    if not client_id or not client_secret:
        return []

    articles = []
    cutoff   = datetime.utcnow() - timedelta(days=lookback_days)
    headers  = {
        "X-Naver-Client-Id":     client_id,
        "X-Naver-Client-Secret": client_secret,
    }

    for query in queries[:5]:
        try:
            resp = requests.get(
                "https://openapi.naver.com/v1/search/news.json",
                headers=headers,
                params={"query": query, "display": 20, "sort": "date"},
                timeout=10,
            )
            if resp.status_code != 200:
                print(f"[WARN] Naver News API {resp.status_code}: {resp.text[:80]}")
                break

            for item in resp.json().get("items", []):
                title = _clean_html(item.get("title", "")).strip()
                url   = item.get("originallink") or item.get("link", "")
                desc  = _clean_html(item.get("description", ""))
                # pubDate format: "Mon, 19 May 2026 10:00:00 +0900"
                try:
                    pub_dt   = datetime.strptime(
                        item.get("pubDate", ""), "%a, %d %b %Y %H:%M:%S %z"
                    ).replace(tzinfo=None)
                    if pub_dt < cutoff:
                        continue
                    date_str = pub_dt.strftime("%Y-%m-%d")
                except Exception:
                    date_str = "Unknown"

                title_key = re.sub(r"\W+", "", title.lower())[:60]
                h = _url_hash(url)
                if h in seen_hashes or title_key in seen_titles:
                    continue

                seen_hashes.add(h)
                seen_titles.add(title_key)
                articles.append({
                    "title": title, "url": url,
                    "description": desc[:300], "hash": h,
                    "date": date_str, "source_type": "naver",
                    "source_name": "Naver News",
                })
        except Exception as exc:
            print(f"[WARN] Naver News — query='{query}': {exc}")
        time.sleep(0.3)

    return articles


# ── New York Times Article Search API ─────────────────────────────────────────

def _fetch_nyt(queries: list, api_key: str, lookback_days: int,
               seen_hashes: set, seen_titles: set) -> list:
    if not api_key:
        return []

    articles   = []
    begin_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y%m%d")

    for query in queries[:3]:
        try:
            resp = requests.get(
                "https://api.nytimes.com/svc/search/v2/articlesearch.json",
                params={
                    "q":          query,
                    "begin_date": begin_date,
                    "sort":       "relevance",
                    "page":       0,
                    "api-key":    api_key,
                },
                timeout=10,
            )
            data = resp.json()
            if data.get("status") != "OK":
                print(f"[WARN] NYT API: {data.get('fault', {}).get('faultstring', '')}")
                break

            for item in data.get("response", {}).get("docs", []):
                url   = item.get("web_url", "")
                title = (item.get("headline", {}).get("main") or "").strip()
                if not url or not title:
                    continue
                desc     = item.get("abstract") or item.get("snippet") or ""
                pub_date = (item.get("pub_date") or "")[:10]
                source   = item.get("source", "The New York Times")

                title_key = re.sub(r"\W+", "", title.lower())[:60]
                h = _url_hash(url)
                if h in seen_hashes or title_key in seen_titles:
                    continue

                seen_hashes.add(h)
                seen_titles.add(title_key)
                articles.append({
                    "title": title, "url": url,
                    "description": desc[:300], "hash": h,
                    "date": pub_date, "source_type": "nyt",
                    "source_name": source,
                })
        except Exception as exc:
            print(f"[WARN] NYT API — query='{query}': {exc}")
        time.sleep(7)  # NYT rate limit: 10 req/min → 6s minimum between calls

    return articles


# ── Kakao (Daum) News Search API ──────────────────────────────────────────────

def _fetch_kakao_news(queries: list, api_key: str, lookback_days: int,
                      seen_hashes: set, seen_titles: set) -> list:
    if not api_key:
        return []

    articles = []
    cutoff   = datetime.utcnow() - timedelta(days=lookback_days)
    headers  = {"Authorization": f"KakaoAK {api_key}"}

    for query in queries[:5]:
        try:
            resp = requests.get(
                "https://dapi.kakao.com/v2/search/web",
                headers=headers,
                params={"query": query, "sort": "recency", "size": 20},
                timeout=10,
            )
            if resp.status_code != 200:
                print(f"[WARN] Kakao News API {resp.status_code}: {resp.text[:80]}")
                break

            for item in resp.json().get("documents", []):
                title = _clean_html(item.get("title", "")).strip()
                url   = item.get("url", "")
                desc  = _clean_html(item.get("contents", "") or item.get("description", ""))
                # datetime format: "2026-05-19T10:00:00.000+09:00"
                try:
                    pub_dt   = datetime.fromisoformat(
                        item.get("datetime", "").replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                    if pub_dt < cutoff:
                        continue
                    date_str = pub_dt.strftime("%Y-%m-%d")
                except Exception:
                    date_str = "Unknown"

                title_key = re.sub(r"\W+", "", title.lower())[:60]
                h = _url_hash(url)
                if h in seen_hashes or title_key in seen_titles:
                    continue

                seen_hashes.add(h)
                seen_titles.add(title_key)
                articles.append({
                    "title": title, "url": url,
                    "description": desc[:300], "hash": h,
                    "date": date_str, "source_type": "kakao",
                    "source_name": item.get("source", "Kakao News"),
                })
        except Exception as exc:
            print(f"[WARN] Kakao News — query='{query}': {exc}")
        time.sleep(0.3)

    return articles


# ── Reddit ─────────────────────────────────────────────────────────────────────

def _fetch_reddit(subreddits: list, lookback_days: int,
                  seen_hashes: set, seen_titles: set) -> list:
    articles    = []
    cutoff      = datetime.utcnow() - timedelta(days=lookback_days)
    headers     = {"User-Agent": "FMCG-Newsletter-Bot/1.0"}
    time_filter = "month" if lookback_days >= 30 else "week"

    for subreddit in subreddits:
        try:
            resp = requests.get(
                f"https://www.reddit.com/r/{subreddit}/top.json",
                params={"limit": 25, "t": time_filter},
                headers=headers, timeout=10,
            )
            if resp.status_code != 200:
                continue

            for post in resp.json().get("data", {}).get("children", []):
                p         = post.get("data", {})
                title     = p.get("title", "").strip()
                url       = p.get("url", "")
                permalink = f"https://www.reddit.com{p.get('permalink', '')}"
                created   = datetime.utcfromtimestamp(p.get("created_utc", 0))
                score     = p.get("score", 0)

                if created < cutoff or score < 100:
                    continue
                if not _is_relevant(title, p.get("selftext", "")):
                    continue

                final_url = (
                    url if url.startswith("https://") and "reddit.com" not in url
                    else permalink
                )
                title_key = re.sub(r"\W+", "", title.lower())[:60]
                h = _url_hash(final_url)
                if h in seen_hashes or title_key in seen_titles:
                    continue

                seen_hashes.add(h)
                seen_titles.add(title_key)
                articles.append({
                    "title": title, "url": final_url,
                    "description": p.get("selftext", "")[:300] or f"r/{subreddit} — {score} upvotes",
                    "hash": h, "date": created.strftime("%Y-%m-%d"),
                    "source_type": "reddit", "source_name": f"r/{subreddit}",
                })
        except Exception as exc:
            print(f"[WARN] Reddit — r/{subreddit}: {exc}")
        time.sleep(0.5)

    return articles


# ── YouTube Data API ───────────────────────────────────────────────────────────

def _search_youtube(queries: list, api_key: str, lookback_days: int,
                    seen_hashes: set, seen_titles: set,
                    min_views: int = 10_000, min_subs: int = 50_000) -> list:
    if not api_key:
        return []

    published_after = (
        datetime.now(timezone.utc) - timedelta(days=lookback_days)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    candidates = []
    for query in queries:
        try:
            resp = requests.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={
                    "part": "snippet", "q": query, "type": "video",
                    "maxResults": 10, "order": "relevance",
                    "relevanceLanguage": "en",
                    "publishedAfter": published_after, "key": api_key,
                },
                timeout=10,
            )
            data = resp.json()
            if "error" in data:
                print(f"[WARN] YouTube API: {data['error'].get('message', '')}")
                break
            for item in data.get("items", []):
                snippet  = item.get("snippet", {})
                video_id = item.get("id", {}).get("videoId", "")
                if not video_id:
                    continue
                candidates.append({
                    "video_id": video_id,
                    "title": snippet.get("title", "").strip(),
                    "description": snippet.get("description", "")[:300],
                    "date": snippet.get("publishedAt", "")[:10],
                    "channel_id": snippet.get("channelId", ""),
                    "channel_title": snippet.get("channelTitle", "YouTube"),
                })
        except Exception as exc:
            print(f"[WARN] YouTube search — query='{query}': {exc}")
        time.sleep(0.5)

    if not candidates:
        return []

    video_stats: dict = {}
    for i in range(0, len({c["video_id"] for c in candidates}), 50):
        batch = list({c["video_id"] for c in candidates})[i:i + 50]
        try:
            resp = requests.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params={"part": "statistics", "id": ",".join(batch), "key": api_key},
                timeout=10,
            )
            for item in resp.json().get("items", []):
                video_stats[item["id"]] = int(
                    item.get("statistics", {}).get("viewCount", 0)
                )
        except Exception as exc:
            print(f"[WARN] YouTube video stats: {exc}")

    channel_stats: dict = {}
    for i in range(0, len({c["channel_id"] for c in candidates if c["channel_id"]}), 50):
        batch = list({c["channel_id"] for c in candidates if c["channel_id"]})[i:i + 50]
        try:
            resp = requests.get(
                "https://www.googleapis.com/youtube/v3/channels",
                params={"part": "statistics", "id": ",".join(batch), "key": api_key},
                timeout=10,
            )
            for item in resp.json().get("items", []):
                channel_stats[item["id"]] = int(
                    item.get("statistics", {}).get("subscriberCount", 0)
                )
        except Exception as exc:
            print(f"[WARN] YouTube channel stats: {exc}")

    articles = []
    for c in candidates:
        if video_stats.get(c["video_id"], 0) < min_views:
            continue
        if channel_stats.get(c["channel_id"], 0) < min_subs:
            continue

        link      = f"https://www.youtube.com/watch?v={c['video_id']}"
        title_key = re.sub(r"\W+", "", c["title"].lower())[:60]
        h = _url_hash(link)
        if h in seen_hashes or title_key in seen_titles:
            continue

        seen_hashes.add(h)
        seen_titles.add(title_key)
        articles.append({
            "title": c["title"], "url": link,
            "description": c["description"], "hash": h,
            "date": c["date"], "source_type": "youtube",
            "source_name": c["channel_title"],
        })

    return articles


# ── Main collector ─────────────────────────────────────────────────────────────

def collect_all(keywords_config: dict, lookback_days: int, sent_urls: list) -> dict:
    sent_hashes: set = set(sent_urls)
    results: dict    = {}

    youtube_api_key = os.environ.get("YOUTUBE_API_KEY", "")
    newsapi_key     = os.environ.get("NEWSAPI_KEY", "")
    guardian_key    = os.environ.get("GUARDIAN_API_KEY", "")
    gnews_key       = os.environ.get("GNEWS_API_KEY", "")
    currents_key    = os.environ.get("CURRENTS_API_KEY", "")
    naver_client_id     = os.environ.get("NAVER_CLIENT_ID", "")
    naver_client_secret = os.environ.get("NAVER_CLIENT_SECRET", "")
    kakao_api_key       = os.environ.get("KAKAO_REST_API_KEY", "")
    nyt_api_key         = os.environ.get("NYT_API_KEY", "")

    rss_sources_by_region  = keywords_config.get("rss_sources", {})
    youtube_queries_by_cat = keywords_config.get("youtube_queries", {})
    reddit_subs_by_cat     = keywords_config.get("reddit_subreddits", {})

    # Pre-fetch premium RSS (shared pool, filtered per category later)
    premium_pool: dict = {}
    for region in ("global", "asia", "korea"):
        rss_list = rss_sources_by_region.get(region, [])
        if rss_list:
            premium_pool[region] = _fetch_premium_rss(rss_list, lookback_days, set(), set())
            print(f"[INFO] Premium RSS [{region}]: {len(premium_pool[region])} articles")
        else:
            premium_pool[region] = []

    # Per-region global dedup — each article appears in at most one category per region
    global_used: dict = {
        "global": set(sent_hashes),
        "asia":   set(sent_hashes),
        "korea":  set(sent_hashes),
    }

    for cat_key, cat in keywords_config["categories"].items():
        results[cat_key] = {}
        queries_by_region = cat.get("queries", {})
        yt_queries        = youtube_queries_by_cat.get(cat_key, {})
        reddit_subs       = reddit_subs_by_cat.get(cat_key, [])

        for region in ("global", "asia", "korea"):
            if cat.get("global_only") and region != "global":
                results[cat_key][region] = []
                continue

            seen_h: set    = set(global_used[region])
            seen_t: set    = set()
            region_queries = queries_by_region.get(region, [])

            # 1. Google News RSS
            gnews_articles = _fetch_google_news(
                region_queries, region, lookback_days, seen_h, seen_t
            )

            # 2. Premium RSS pool
            premium = [
                a for a in premium_pool.get(region, [])
                if _url_hash(a["url"]) not in seen_h
                and _is_relevant(a["title"], a["description"])
            ]
            for a in premium:
                seen_h.add(_url_hash(a["url"]))

            # 3. NewsAPI
            newsapi = _fetch_newsapi(
                region_queries, newsapi_key, lookback_days, seen_h, seen_t
            )

            # 4. NYT Article Search (EN only — skip Korea)
            nyt = []
            if region != "korea":
                nyt = _fetch_nyt(region_queries, nyt_api_key, lookback_days, seen_h, seen_t)

            # 5. Guardian (EN only — skip Korea)
            guardian = []
            if region != "korea":
                guardian = _fetch_guardian(
                    region_queries, guardian_key, lookback_days, seen_h, seen_t
                )

            # 5. GNews
            gnews_api = _fetch_gnews(
                region_queries, gnews_key, lookback_days, seen_h, seen_t, region
            )

            # 6. Currents API
            currents = _fetch_currents(
                region_queries, currents_key, lookback_days, seen_h, seen_t, region
            )

            # 7. Naver News (Korea only)
            naver = []
            if region == "korea":
                naver = _fetch_naver_news(
                    region_queries, naver_client_id, naver_client_secret,
                    lookback_days, seen_h, seen_t,
                )

            # 7b. Kakao (Daum) News (Korea only)
            kakao = []
            if region == "korea":
                kakao = _fetch_kakao_news(
                    region_queries, kakao_api_key, lookback_days, seen_h, seen_t,
                )

            # 8. Reddit (global only)
            reddit = []
            if region == "global" and reddit_subs:
                reddit = _fetch_reddit(reddit_subs, lookback_days, seen_h, seen_t)

            # 9. YouTube
            yt_thresh = YOUTUBE_THRESHOLDS.get(cat_key, {"min_views": 50_000, "min_subs": 50_000})
            yt = _search_youtube(
                yt_queries.get(region, []),
                youtube_api_key, lookback_days, seen_h, seen_t,
                min_views=yt_thresh["min_views"],
                min_subs=yt_thresh["min_subs"],
            )

            # Validate URLs (Google News & NewsAPI are most unreliable)
            merged_raw = gnews_articles + premium + newsapi + nyt + guardian + gnews_api + currents + naver + kakao + reddit + yt
            merged = _filter_valid_urls(merged_raw)[:25]

            # Register used URLs so other categories don't repeat them
            for a in merged:
                global_used[region].add(_url_hash(a["url"]))

            results[cat_key][region] = merged

        print(f"[INFO] Collected {cat_key}: "
              f"global={len(results[cat_key]['global'])} "
              f"asia={len(results[cat_key]['asia'])} "
              f"korea={len(results[cat_key]['korea'])}")

    return results
