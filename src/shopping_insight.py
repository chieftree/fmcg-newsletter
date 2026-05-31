"""Fetches Naver DataLab search-trend data for FMCG keyword groups."""

from __future__ import annotations
from datetime import datetime, timedelta
import requests


KEYWORD_GROUPS = [
    {"groupName": "스낵/과자",       "keywords": ["스낵", "과자", "감자칩"]},
    {"groupName": "초콜릿/캔디",     "keywords": ["초콜릿", "사탕", "캔디"]},
    {"groupName": "시리얼/그래놀라", "keywords": ["시리얼", "그래놀라", "켈로그"]},
    {"groupName": "껌/젤리",         "keywords": ["껌", "젤리", "마시멜로"]},
    {"groupName": "스니커즈/M&M",    "keywords": ["스니커즈", "엠앤엠", "프링글스"]},
]


def fetch_search_trends(
    client_id: str,
    client_secret: str,
    lookback_days: int = 4,
) -> dict | None:
    """Return FMCG keyword search-trend data, comparing current vs. prior period."""
    if not client_id or not client_secret:
        return None

    end_date   = datetime.utcnow().date()
    # Fetch 2× lookback so we have a baseline period for WoW comparison
    start_date = end_date - timedelta(days=lookback_days * 2 - 1)

    payload = {
        "startDate":     start_date.strftime("%Y-%m-%d"),
        "endDate":       end_date.strftime("%Y-%m-%d"),
        "timeUnit":      "date",
        "keywordGroups": KEYWORD_GROUPS,
        "device":        "",
        "ages":          [],
        "gender":        "",
    }
    headers = {
        "X-Naver-Client-Id":     client_id,
        "X-Naver-Client-Secret": client_secret,
        "Content-Type":          "application/json",
    }

    try:
        resp = requests.post(
            "https://openapi.naver.com/v1/datalab/search",
            headers=headers,
            json=payload,
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"[WARN] Naver DataLab: {resp.status_code} {resp.text[:120]}")
            return None
    except Exception as exc:
        print(f"[WARN] Naver DataLab exception: {exc}")
        return None

    items = []
    for result in resp.json().get("results", []):
        points = result.get("data", [])
        if not points:
            continue
        mid      = len(points) // 2
        prev_pts = points[:mid]
        curr_pts = points[mid:]
        prev_avg = sum(p["ratio"] for p in prev_pts) / len(prev_pts) if prev_pts else 0
        curr_avg = sum(p["ratio"] for p in curr_pts) / len(curr_pts) if curr_pts else 0
        change   = ((curr_avg - prev_avg) / prev_avg * 100) if prev_avg > 0 else 0
        items.append({
            "name":        result["title"],
            "current_avg": round(curr_avg, 1),
            "prev_avg":    round(prev_avg, 1),
            "change_pct":  round(change, 1),
            "direction":   "up" if change > 2 else ("down" if change < -2 else "stable"),
        })

    if not items:
        return None

    items.sort(key=lambda x: x["current_avg"], reverse=True)

    current_start = (end_date - timedelta(days=lookback_days - 1)).strftime("%b %d")
    current_end   = end_date.strftime("%b %d, %Y")
    prev_start    = start_date.strftime("%b %d")
    prev_end      = (end_date - timedelta(days=lookback_days)).strftime("%b %d")

    return {
        "period":      f"{current_start} – {current_end}",
        "prev_period": f"{prev_start} – {prev_end}",
        "items":       items,
        "max_val":     items[0]["current_avg"] if items else 100,
    }
