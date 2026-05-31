import json
import time

from google import genai
from google.genai import types


REGION_LABELS = {
    "global": "Global",
    "asia": "Asia",
    "korea": "Korea",
}


BRAND_NAME_RULE = (
    "Brand names must keep their original spelling in Korean text — never translate brand names as Korean words: "
    "마즈(Mars, NOT 화성), 켈레노바(Kellanova, NOT 켈라노바), 스니커즈(Snickers), 엠앤엠즈(M&M's), "
    "트윅스(Twix), 스키틀즈(Skittles), 프링글스(Pringles), 다브(Dove chocolate), "
    "몰티저스(Maltesers), 위스카스(Whiskas), 페디그리(Pedigree), 에클립스(Eclipse), "
    "에어웨이브스(Airwaves), 더블민트(Doublemint), 카인드(Kind/BeKind)."
)


def _build_byron_sharp_prompt(region: str, articles: list, is_first_issue: bool) -> str:
    period = "the past 12 months" if is_first_issue else "the past 4 days"
    articles_text = "\n".join(
        f"- [{a['date']}] {a['title']} | {a['description'][:200]} | URL: {a['url']}"
        for a in articles[:20]
    )
    return f"""You are a marketing science expert applying Byron Sharp's "How Brands Grow" framework, briefing the CMO of Mars Asia Snacking.

Analyze these articles for real-world examples of Byron Sharp's three core principles from {period}. Each case should illuminate a specific principle with concrete evidence.

ARTICLES:
{articles_text}

Return ONLY valid JSON (no markdown, no extra text):
{{
  "has_content": true,
  "items": [
    {{
      "subsection": "Mental Availability",
      "subsection_kr": "멘탈 어베일러빌리티",
      "headline_en": "Insight-led headline (max 12 words) — what this reveals about brand salience or recall",
      "headline_kr": "한국어 헤드라인 (최대 12단어)",
      "summary_en": "2-3 sentences: Sentence 1: the evidence/data. Sentence 2: how this exemplifies Mental Availability (brand salience, category entry points, reach). Sentence 3: implication for Mars snacking brands.",
      "summary_kr": "한국어 2-3문장 (같은 구조)",
      "key_metric": "Most compelling stat — empty string if none",
      "source_name": "Publication name",
      "url": "Article URL",
      "date": "YYYY-MM-DD"
    }}
  ],
  "section_insight_en": "One sharp sentence: the single most important marketing science takeaway for Mars Asia Snacking this period.",
  "section_insight_kr": "한 문장: 마즈 아시아 스낵킹을 위한 이번 기간 가장 중요한 마케팅 사이언스 시사점."
}}

Rules:
- Include AT MOST ONE item per subsection. The three possible subsection values are:
  * "Mental Availability" / "멘탈 어베일러빌리티" — brand salience, category entry points, reach, awareness, recall
  * "Physical Availability" / "피지컬 어베일러빌리티" — distribution, shelf presence, channel expansion, out-of-stock, e-commerce penetration
  * "Distinctive Brand Assets" / "차별적 브랜드 자산" — logos, colors, pack design, brand characters, jingles, slogans working as recognizable triggers
- ONLY include a subsection when you find genuinely evidence-backed content. Skip subsections with no strong example.
- Each item must come from a DIFFERENT story/source.
- {BRAND_NAME_RULE}
- If fewer than 1 strong evidence-backed item exists: return {{"has_content": false, "items": [], "section_insight_en": "No significant updates this period.", "section_insight_kr": "이번 기간 주요 업데이트 없음."}}"""


def _build_prompt(cat_name: str, region: str, articles: list, is_first_issue: bool) -> str:
    period = "the past 12 months" if is_first_issue else "the past 4 days"
    region_label = REGION_LABELS[region]
    articles_text = "\n".join(
        f"- [{a['date']}] {a['title']} | {a['description'][:200]} | URL: {a['url']}"
        for a in articles[:20]
    )
    return f"""You are a senior marketing intelligence analyst briefing the CMO and marketing leadership team of Mars Asia Snacking — the company behind Snickers, M&M's, Twix, Skittles, Dove chocolate, Pringles, and Kellogg brands across Asia Pacific.

Your audience are senior FMCG marketers who need sharp, strategic intelligence — not news summaries. They want to know: "What does this mean for our brands, our categories, and our competitors?"

Analyze these articles about "{cat_name}" in the {region_label} region for {period}.

ARTICLES:
{articles_text}

Return ONLY a valid JSON object with this exact structure (no markdown, no extra text):
{{
  "has_content": true,
  "items": [
    {{
      "headline_en": "Sharp, insight-led headline in English (max 12 words) — lead with the strategic implication",
      "headline_kr": "한국어 헤드라인 (최대 12단어) — 전략적 의미 중심",
      "summary_en": "2-3 sentences in English. Sentence 1: what happened and key data. Sentence 2: why it matters strategically for FMCG/snacking brands. Sentence 3: implication or watch-out for marketing leaders.",
      "summary_kr": "한국어 2-3문장. 1문장: 핵심 사실과 수치. 2문장: FMCG/스낵 브랜드 관점의 전략적 의미. 3문장: 마케팅 리더를 위한 시사점.",
      "key_metric": "The single most compelling number or stat (e.g. +34% category growth, 12M views in 48h, #1 share of voice) — empty string if none",
      "source_name": "Publication name",
      "url": "Article URL",
      "date": "YYYY-MM-DD"
    }}
  ],
  "section_insight_en": "One sharp sentence: the single most important strategic takeaway for Mars Asia Snacking leadership from this section.",
  "section_insight_kr": "한 문장: 이 섹션에서 마즈 아시아 스낵킹 리더십에 가장 중요한 전략적 시사점."
}}

Strict rules:
- Select ONLY 2 to 3 items — the highest signal, most strategically relevant stories. Quality over volume.
- Each item must come from a DIFFERENT story/source. Never summarize the same event twice from different angles.
- Prioritize: concrete data and metrics, clear competitive or category implications, novel trends with evidence.
- Exclude: generic corporate announcements without strategic relevance, opinion pieces without data, duplicate stories.
- {BRAND_NAME_RULE}
- If fewer than 2 genuinely high-quality items exist, return {{"has_content": false, "items": [], "section_insight_en": "No significant updates this period.", "section_insight_kr": "이번 기간 주요 업데이트 없음."}}"""


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

            if cat_key == "byron_sharp":
                prompt = _build_byron_sharp_prompt(region, articles, is_first_issue)
            else:
                prompt = _build_prompt(cat["name"], region, articles, is_first_issue)
            region_data = None
            for attempt in range(4):  # up to 4 attempts
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
                    print(f"[INFO] Summarized {cat_key}/{region}: "
                          f"has_content={region_data.get('has_content')} "
                          f"items={len(region_data.get('items', []))}")
                    break
                except Exception as exc:
                    msg = str(exc)
                    if "503" in msg or "UNAVAILABLE" in msg or "429" in msg:
                        wait = 15 * (2 ** attempt)
                        print(f"[WARN] Gemini {cat_key}/{region} attempt {attempt+1} — retrying in {wait}s: {msg[:80]}")
                        time.sleep(wait)
                    elif "Expecting" in msg or "JSONDecodeError" in msg or "json" in msg.lower():
                        # Malformed JSON from model — retry once
                        wait = 10
                        print(f"[WARN] Gemini JSON parse error {cat_key}/{region} attempt {attempt+1} — retrying in {wait}s")
                        time.sleep(wait)
                    else:
                        print(f"[WARN] Gemini error for {cat_key}/{region}: {msg[:120]}")
                        break

            if region_data is None:
                results[cat_key]["regions"][region] = {
                    "has_content": False, "items": [],
                    "section_insight_en": "Data temporarily unavailable.",
                    "section_insight_kr": "데이터를 일시적으로 사용할 수 없습니다.",
                }
            else:
                results[cat_key]["regions"][region] = region_data

            time.sleep(2)

    return results
