"""Entry point for the FMCG Marketing Intelligence Newsletter."""

import json
import os
from datetime import datetime
from pathlib import Path

from src.email_sender import send_newsletter
from src.news_collector import collect_all
from src.renderer import render_email, render_web
from src.shopping_insight import fetch_search_trends
from src.summarizer import summarize_all

CONFIG_DIR = Path("config")
DOCS_DIR   = Path("docs")


def _load(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _latest_redirect(issue_date: str) -> str:
    return f"""<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="0;url=newsletters/{issue_date}/">
<title>FMCG Marketing Intelligence</title>
</head><body>
<p>Redirecting to <a href="newsletters/{issue_date}/">latest newsletter ({issue_date})</a>…</p>
</body></html>"""


def main() -> None:
    keywords    = _load(CONFIG_DIR / "keywords.json")
    subscribers = _load(CONFIG_DIR / "subscribers.json")
    history     = _load(CONFIG_DIR / "sent_history.json")

    is_first_issue = history["last_sent"] is None
    lookback_days  = 365 if is_first_issue else 4
    issue_date     = datetime.utcnow().strftime("%Y-%m-%d")

    if is_first_issue:
        issue_label = "Launch Issue: Year in Review 2025–2026"
    else:
        dt = datetime.strptime(issue_date, "%Y-%m-%d")
        day_name = dt.strftime("%A")  # Monday / Thursday
        date_str = dt.strftime("%B %d, %Y").replace(" 0", " ")
        issue_label = f"{day_name} Issue — {date_str}"

    print(f"[INFO] Issue: {issue_label}  |  lookback={lookback_days}d")

    # ── 1. Collect ─────────────────────────────────────────────────────────────
    print("[INFO] Collecting news…")
    collected = collect_all(keywords, lookback_days, history.get("sent_urls", []))

    # ── 2. Summarize ───────────────────────────────────────────────────────────
    print("[INFO] Summarizing with Gemini…")
    summarized = summarize_all(
        collected, keywords, is_first_issue,
        api_key=os.environ["GEMINI_API_KEY"],
    )

    # ── 2b. Korea shopping / search trends ────────────────────────────────────
    print("[INFO] Fetching Naver search trends…")
    shopping_insight = fetch_search_trends(
        client_id=os.environ.get("NAVER_CLIENT_ID", ""),
        client_secret=os.environ.get("NAVER_CLIENT_SECRET", ""),
        lookback_days=lookback_days,
    )
    if shopping_insight:
        print(f"[INFO] Naver trends: {len(shopping_insight['items'])} groups, period={shopping_insight['period']}")
    else:
        print("[WARN] Naver trends unavailable — skipping block")

    # ── 3. Determine GitHub Pages URL ─────────────────────────────────────────
    repo = os.environ.get("GITHUB_REPOSITORY", "user/fmcg-newsletter")
    gh_user = repo.split("/")[0]
    repo_name = repo.split("/")[1]
    web_url = f"https://{gh_user}.github.io/{repo_name}/newsletters/{issue_date}/"

    # ── 4. Render HTML ─────────────────────────────────────────────────────────
    print("[INFO] Rendering HTML…")
    web_html   = render_web(summarized, issue_date, issue_label, is_first_issue, shopping_insight=shopping_insight)
    email_html = render_email(summarized, issue_date, issue_label, web_url, shopping_insight=shopping_insight)

    # ── 5. Write to docs/ ──────────────────────────────────────────────────────
    out_dir = DOCS_DIR / "newsletters" / issue_date
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(web_html, encoding="utf-8")
    (DOCS_DIR / "index.html").write_text(_latest_redirect(issue_date), encoding="utf-8")
    print(f"[INFO] Saved → {out_dir}/index.html")

    # ── 6. Send emails ─────────────────────────────────────────────────────────
    print("[INFO] Sending emails…")
    smtp_user = os.environ["GMAIL_USER"]
    smtp_pass = os.environ["GMAIL_APP_PASSWORD"]

    for sub in subscribers["subscribers"]:
        if not sub.get("active", True):
            continue
        try:
            send_newsletter(
                smtp_user=smtp_user,
                smtp_password=smtp_pass,
                to_email=sub["email"],
                to_name=sub.get("name", ""),
                subject=f"FMCG Marketing Intelligence — {issue_label}",
                html_body=email_html,
            )
            print(f"[INFO] ✓ Sent → {sub['email']}")
        except Exception as exc:
            print(f"[ERROR] Failed to send to {sub['email']}: {exc}")

    # ── 7. Update history ──────────────────────────────────────────────────────
    new_hashes = [
        a["hash"]
        for cat_articles in collected.values()
        for region_articles in cat_articles.values()
        for a in region_articles
    ]
    history["last_sent"]  = issue_date
    history["sent_urls"]  = list(set(history.get("sent_urls", []) + new_hashes))[-2000:]
    _save(CONFIG_DIR / "sent_history.json", history)
    print("[INFO] History updated.")
    print("[INFO] Done ✓")


if __name__ == "__main__":
    main()
