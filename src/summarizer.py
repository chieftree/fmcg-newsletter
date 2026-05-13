import json
import time

from google import genai
from google.genai import types


REGION_LABELS = {
    "global": "Global",
    "asia": "Asia",
    "korea": "Korea",
}


def _build_prompt(cat_name: str, region: str, articles: list, is_first_issue: bool) -> str:
    period = "the past 12 months" if is_first_issue else "the past 7 days"
    region_label = REGION_LABELS[region]
    articles_text = "\n".join(
        f"- [{a['date']}] {a['title']} | {a['description'][:200]} | URL: {a['url']}"
        for a in articles[:15]
    )
    return f"""You are an FMCG marketing intelligence analyst.
Analyze these news articles about "{cat_name}" in the {region_label} region for {period}.

ARTICLES:
{articles_text}

Return ONLY a valid JSON object with this exact structure (no markdown, no extra text):
{{
  "has_content": true,
  "items": [
    {{
      "headline_en": "Bold headline in English (max 12 words)",
      "headline_kr": "한국어 헤드라인 (최대 12단어)",
      "summary_en": "2-3 sentence summary in English with key insights and metrics if available",
      "summary_kr": "한국어로 2-3문장 요약, 핵심 인사이트와 수치 포함",
      "key_metric": "One standout stat or number (e.g. +45% sales, 5M views) — empty string if none",
      "source_name": "Publication or website name",
      "url": "Article URL",
      "date": "YYYY-MM-DD"
    }}
  ],
  "section_insight_en": "One sentence overall regional insight in English",
  "section_insight_kr": "이 지역 전체 인사이트 한 문장 (한국어)"
}}

Rules:
- Include 2 to 4 of the most relevant and insightful items only.
- If no genuinely relevant FMCG marketing content exists, return {{"has_content": false, "items": [], "section_insight_en": "No significant updates this period.", "section_insight_kr": "이번 기간 주요 업데이트 없음."}}
- Focus on actionable marketing insights, not generic company news."""


PREFERRED_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash-001",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
    "gemini-1.5-flash-latest",
]


def _pick_model(client: genai.Client) -> str:
    """Return the first available generative model from the preferred list."""
    try:
        available = {m.name.split("/")[-1] for m in client.models.list()}
        for name in PREFERRED_MODELS:
            if name in available:
                print(f"[INFO] Using model: {name}")
                return name
    except Exception as exc:
        print(f"[WARN] Could not list models: {exc}")
    # Fallback: try preferred names in order without listing
    return PREFERRED_MODELS[0]


def summarize_all(
    collected: dict,
    keywords_config: dict,
    is_first_issue: bool,
    api_key: str,
) -> dict:
    client = genai.Client(api_key=api_key)
    model = _pick_model(client)

    results: dict = {}
    regions = ("global", "asia", "korea")

    for cat_key, cat in keywords_config["categories"].items():
        results[cat_key] = {
            "name": cat["name"],
            "name_kr": cat["name_kr"],
            "icon": cat["icon"],
            "color": cat["color"],
            "conditional": cat.get("conditional", False),
            "global_only": cat.get("global_only", False),
            "regions": {},
        }

        for region in regions:
            articles = collected.get(cat_key, {}).get(region, [])

            if cat.get("global_only") and region != "global":
                results[cat_key]["regions"][region] = {
                    "has_content": False, "items": [],
                    "section_insight_en": "", "section_insight_kr": "",
                }
                continue

            if not articles:
                results[cat_key]["regions"][region] = {
                    "has_content": False, "items": [],
                    "section_insight_en": "No significant updates this period.",
                    "section_insight_kr": "이번 기간 주요 업데이트 없음.",
                }
                continue

            prompt = _build_prompt(cat["name"], region, articles, is_first_issue)
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                )
                raw = response.text.strip()
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                    raw = raw.strip()
                region_data = json.loads(raw)
                results[cat_key]["regions"][region] = region_data
                print(f"[INFO] Summarized {cat_key}/{region}: "
                      f"has_content={region_data.get('has_content')} "
                      f"items={len(region_data.get('items', []))}")
            except Exception as exc:
                print(f"[WARN] Gemini error for {cat_key}/{region}: {exc}")
                results[cat_key]["regions"][region] = {
                    "has_content": False, "items": [],
                    "section_insight_en": "Data temporarily unavailable.",
                    "section_insight_kr": "데이터를 일시적으로 사용할 수 없습니다.",
                }

            time.sleep(1)

    return results
