"""Renders the newsletter as a self-contained web page and an email snippet."""

from __future__ import annotations

CATEGORY_ORDER = ["viral_social", "brand_activation", "award_campaigns", "byron_sharp", "mars_snacking"]

REGION_LABELS = {
    "global": ("🌍 Global", "🌍 글로벌"),
    "asia":   ("🌏 Asia",   "🌏 아시아"),
    "korea":  ("Korea",     "한국"),
}


# ─── helpers ──────────────────────────────────────────────────────────────────

def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _bi(en: str, kr: str, tag: str = "span", cls: str = "") -> str:
    extra = f' class="{cls}"' if cls else ""
    return (
        f'<{tag} class="en-content{(" " + cls) if cls else ""}">{_esc(en)}</{tag}>'
        f'<{tag} class="kr-content{(" " + cls) if cls else ""}" style="display:none">{_esc(kr)}</{tag}>'
    )


def _article_card(item: dict, color: str) -> str:
    metric_html = ""
    if item.get("key_metric"):
        metric_html = f'<div class="metric">📊 {_esc(item["key_metric"])}</div>'

    source_html = ""
    if item.get("url") and item.get("source_name"):
        source_html = (
            f'<a class="source-link" href="{_esc(item["url"])}" target="_blank" rel="noopener">'
            f'{_esc(item["source_name"])} →</a>'
        )
    elif item.get("url"):
        source_html = (
            f'<a class="source-link" href="{_esc(item["url"])}" target="_blank" rel="noopener">'
            f'Read more →</a>'
        )

    date_html = f'<span class="article-date">{_esc(item.get("date", ""))}</span>' if item.get("date") else ""

    return f"""
    <div class="article-card" style="border-left-color:{color}">
      {date_html}
      <div class="en-content">
        <h4>{_esc(item.get("headline_en", ""))}</h4>
        <p>{_esc(item.get("summary_en", ""))}</p>
      </div>
      <div class="kr-content" style="display:none">
        <h4>{_esc(item.get("headline_kr", ""))}</h4>
        <p>{_esc(item.get("summary_kr", ""))}</p>
      </div>
      {metric_html}
      {source_html}
    </div>"""


def _category_section(cat_key: str, cat: dict, region: str) -> str:
    region_data = cat["regions"].get(region, {})
    has_content = region_data.get("has_content", False)
    items = region_data.get("items", [])
    color = cat["color"]
    conditional = cat.get("conditional", False)
    global_only = cat.get("global_only", False)

    # Award campaigns: hide entire section when no content
    if conditional and not has_content:
        return ""

    # Byron Sharp: global only — show placeholder for other regions
    if global_only and region != "global":
        return ""

    insight_html = ""
    if region_data.get("section_insight_en") and has_content:
        insight_html = (
            f'<div class="section-insight">'
            f'{_bi(region_data["section_insight_en"], region_data.get("section_insight_kr", ""))}'
            f'</div>'
        )

    cards_html = ""
    if has_content and items:
        cards_html = '<div class="articles-grid">' + "".join(_article_card(it, color) for it in items) + "</div>"
    else:
        cards_html = (
            f'<div class="no-updates">'
            f'{_bi("No significant updates this period.", "이번 기간 주요 업데이트 없음.")}'
            f'</div>'
        )

    global_badge = '<span class="global-badge">Global</span>' if global_only else ""

    return f"""
  <section class="category-section">
    <div class="cat-header" style="border-color:{color}">
      <span class="cat-icon">{cat["icon"]}</span>
      <h3>{_bi(cat["name"], cat["name_kr"])}{global_badge}</h3>
    </div>
    {insight_html}
    {cards_html}
  </section>"""


def _region_panel(summarized: dict, region: str) -> str:
    sections = ""
    for cat_key in CATEGORY_ORDER:
        cat = summarized.get(cat_key)
        if cat:
            sections += _category_section(cat_key, cat, region)
    if not sections.strip():
        sections = '<p class="no-updates">No content available for this region this week.</p>'
    return sections


def _shopping_insight_block(data: dict | None) -> str:
    if not data or not data.get("items"):
        return ""

    max_val  = data.get("max_val") or 100
    items    = data["items"]
    period   = data.get("period", "")
    prev_period = data.get("prev_period", "prev period")

    rows = ""
    for item in items:
        bar_pct   = (item["current_avg"] / max_val) * 100
        direction = item["direction"]
        arrow     = "▲" if direction == "up" else ("▼" if direction == "down" else "→")
        color     = "#10b981" if direction == "up" else ("#ef4444" if direction == "down" else "#6366f1")
        sign      = "+" if item["change_pct"] > 0 else ""
        change_txt = f"{arrow} {sign}{item['change_pct']}%"
        rows += f"""
      <div class="trend-row">
        <div class="trend-label">{_esc(item['name'])}</div>
        <div class="trend-bar-wrap">
          <div class="trend-bar" style="width:{bar_pct:.0f}%;background:{color};opacity:.85"></div>
        </div>
        <div class="trend-score">{item['current_avg']}</div>
        <div class="trend-change" style="color:{color}">{_esc(change_txt)}</div>
      </div>"""

    return f"""
  <section class="category-section">
    <div class="cat-header" style="border-color:#e11d48;justify-content:space-between">
      <div style="display:flex;align-items:center;gap:10px">
        <span class="cat-icon">📊</span>
        <h3>
          <span class="en-content">Korea Search Trends — Naver DataLab</span>
          <span class="kr-content" style="display:none">한국 검색 트렌드 — 네이버 데이터랩</span>
        </h3>
      </div>
      <span style="font-size:11px;color:#94a3b8;white-space:nowrap">{_esc(period)}</span>
    </div>
    <div class="trend-grid">{rows}
    </div>
    <div class="trend-footnote">
      <span class="en-content">Naver relative search volume index (0–100). ▲▼ vs. {_esc(prev_period)}.</span>
      <span class="kr-content" style="display:none">네이버 상대 검색량 지수 (0–100). ▲▼ {_esc(prev_period)} 대비.</span>
    </div>
  </section>"""


# ─── web renderer ─────────────────────────────────────────────────────────────

def render_web(
    summarized: dict,
    issue_date: str,
    issue_label: str,
    is_first_issue: bool,
    shopping_insight: dict | None = None,
) -> str:
    issue_label_kr = f"{'창간호: 2025~2026 연간 리뷰' if is_first_issue else issue_date + ' 주간'}"

    global_panel = _region_panel(summarized, "global")
    asia_panel   = _region_panel(summarized, "asia")
    korea_panel  = _region_panel(summarized, "korea") + _shopping_insight_block(shopping_insight)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FMCG Marketing Intelligence — {_esc(issue_label)}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f0f4f8;color:#1a202c;line-height:1.6}}
a{{color:#4f46e5;text-decoration:none}}
a:hover{{text-decoration:underline}}

/* Header */
.site-header{{background:linear-gradient(135deg,#1a1a2e 0%,#16213e 60%,#0f3460 100%);color:#fff;padding:32px 24px 0}}
.header-inner{{max-width:1100px;margin:0 auto}}
.header-top{{display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:16px;margin-bottom:8px}}
.site-title{{font-size:clamp(20px,4vw,28px);font-weight:700;letter-spacing:-0.5px}}
.site-subtitle{{font-size:13px;opacity:.7;margin-top:4px}}

/* Language toggle */
.lang-toggle{{display:flex;gap:8px}}
.lang-btn{{background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.3);color:#fff;padding:6px 14px;border-radius:20px;font-size:13px;cursor:pointer;transition:all .2s}}
.lang-btn.active,.lang-btn:hover{{background:rgba(255,255,255,.9);color:#1a1a2e}}

/* Region tabs */
.region-tabs{{display:flex;gap:0;margin-top:24px;border-bottom:none}}
.region-tab{{background:rgba(255,255,255,.1);border:none;color:rgba(255,255,255,.7);padding:12px 24px;font-size:14px;font-weight:500;cursor:pointer;border-radius:8px 8px 0 0;transition:all .2s;margin-right:4px}}
.region-tab.active,.region-tab:hover{{background:#fff;color:#1a1a2e}}

/* Content area */
.content-area{{max-width:1100px;margin:0 auto;padding:32px 24px 64px}}
.region-panel{{display:none}}
.region-panel.active{{display:block}}

/* Issue label */
.issue-label{{background:#fff;border-radius:0 0 12px 12px;padding:12px 24px;display:inline-block;font-size:13px;color:#64748b;margin-bottom:24px;box-shadow:0 2px 8px rgba(0,0,0,.08)}}
.first-issue-badge{{background:#f59e0b;color:#fff;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:700;margin-left:8px;vertical-align:middle}}

/* Category section */
.category-section{{background:#fff;border-radius:12px;padding:24px;margin-bottom:24px;box-shadow:0 2px 12px rgba(0,0,0,.06)}}
.cat-header{{display:flex;align-items:center;gap:10px;padding-bottom:14px;border-bottom:2px solid #e2e8f0;margin-bottom:16px}}
.cat-icon{{font-size:22px}}
.cat-header h3{{font-size:16px;font-weight:700;color:#1e293b}}
.global-badge{{font-size:10px;font-weight:600;background:#6366f1;color:#fff;padding:2px 7px;border-radius:10px;margin-left:8px;vertical-align:middle}}

/* Section insight */
.section-insight{{font-size:13px;color:#475569;background:#f8fafc;border-radius:8px;padding:10px 14px;margin-bottom:16px;font-style:italic;border-left:3px solid #e2e8f0}}

/* Article grid */
.articles-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}}
.article-card{{border-left:3px solid #ccc;padding:14px 16px;background:#fafafa;border-radius:0 8px 8px 0;transition:box-shadow .2s}}
.article-card:hover{{box-shadow:0 4px 12px rgba(0,0,0,.1);background:#fff}}
.article-date{{font-size:11px;color:#94a3b8;display:block;margin-bottom:6px}}
.article-card h4{{font-size:14px;font-weight:600;color:#1e293b;margin-bottom:6px;line-height:1.4}}
.article-card p{{font-size:13px;color:#475569;margin-bottom:10px;line-height:1.6}}
.metric{{font-size:12px;font-weight:600;color:#0f766e;background:#f0fdf4;display:inline-block;padding:3px 8px;border-radius:6px;margin-bottom:8px}}
.source-link{{font-size:12px;color:#4f46e5;font-weight:500;display:block;margin-top:6px}}

/* No updates */
.no-updates{{font-size:13px;color:#94a3b8;font-style:italic;padding:8px 0}}

/* Footer */
.site-footer{{background:#1a1a2e;color:rgba(255,255,255,.5);text-align:center;padding:32px 24px;font-size:13px}}
.site-footer a{{color:rgba(255,255,255,.7)}}

/* Trend block */
.trend-grid{{display:flex;flex-direction:column;gap:10px;margin-bottom:14px}}
.trend-row{{display:grid;grid-template-columns:130px 1fr 48px 76px;align-items:center;gap:10px}}
.trend-label{{font-size:13px;color:#1e293b;font-weight:500}}
.trend-bar-wrap{{background:#f1f5f9;border-radius:4px;height:8px;overflow:hidden}}
.trend-bar{{height:100%;border-radius:4px}}
.trend-score{{font-size:12px;color:#64748b;text-align:right;font-weight:500}}
.trend-change{{font-size:12px;font-weight:700;text-align:right}}
.trend-footnote{{font-size:11px;color:#94a3b8;margin-top:10px;padding-top:8px;border-top:1px solid #f1f5f9}}

@media(max-width:600px){{
  .header-top{{flex-direction:column}}
  .articles-grid{{grid-template-columns:1fr}}
  .region-tab{{padding:10px 14px;font-size:13px}}
  .trend-row{{grid-template-columns:90px 1fr 36px 60px;gap:6px}}
}}
</style>
</head>
<body>

<header class="site-header">
  <div class="header-inner">
    <div class="header-top">
      <div>
        <div class="site-title">FMCG Marketing Intelligence</div>
        <div class="site-subtitle">
          <span class="en-content">Global · Asia · Korea — Curated weekly for FMCG marketers</span>
          <span class="kr-content" style="display:none">글로벌 · 아시아 · 한국 — FMCG 마케터를 위한 주간 큐레이션</span>
        </div>
      </div>
      <div class="lang-toggle">
        <button class="lang-btn active" id="btn-en" onclick="setLang('en')">🌐 English</button>
        <button class="lang-btn" id="btn-kr" onclick="setLang('kr')">🇰🇷 한국어</button>
      </div>
    </div>
    <div class="region-tabs">
      <button class="region-tab active" data-region="global" onclick="setRegion('global')">🌍 Global</button>
      <button class="region-tab" data-region="asia" onclick="setRegion('asia')">🌏 Asia</button>
      <button class="region-tab" data-region="korea" onclick="setRegion('korea')">Korea</button>
    </div>
  </div>
</header>

<div class="content-area">
  <div class="issue-label">
    <span class="en-content">{_esc(issue_label)}</span>
    <span class="kr-content" style="display:none">{_esc(issue_label_kr)}</span>
    {"<span class='first-issue-badge'>Year in Review</span>" if is_first_issue else ""}
  </div>

  <div class="region-panel active" id="panel-global">
    {global_panel}
  </div>
  <div class="region-panel" id="panel-asia">
    {asia_panel}
  </div>
  <div class="region-panel" id="panel-korea">
    {korea_panel}
  </div>
</div>

<footer class="site-footer">
  <p>
    <span class="en-content">FMCG Marketing Intelligence Newsletter — Auto-generated weekly</span>
    <span class="kr-content" style="display:none">FMCG 마케팅 인텔리전스 뉴스레터 — 매주 자동 생성</span>
  </p>
</footer>

<script>
(function(){{
  function setLang(lang){{
    document.querySelectorAll('.en-content').forEach(function(el){{
      el.style.display = lang==='en' ? '' : 'none';
    }});
    document.querySelectorAll('.kr-content').forEach(function(el){{
      el.style.display = lang==='kr' ? '' : 'none';
    }});
    document.querySelectorAll('.lang-btn').forEach(function(el){{
      el.classList.remove('active');
    }});
    var btn = document.getElementById('btn-'+lang);
    if(btn) btn.classList.add('active');
    try{{ localStorage.setItem('fmcg_lang', lang); }}catch(e){{}}
  }}

  function setRegion(region){{
    document.querySelectorAll('.region-panel').forEach(function(el){{
      el.classList.remove('active');
    }});
    var panel = document.getElementById('panel-'+region);
    if(panel) panel.classList.add('active');
    document.querySelectorAll('.region-tab').forEach(function(el){{
      el.classList.remove('active');
    }});
    var tab = document.querySelector('.region-tab[data-region="'+region+'"]');
    if(tab) tab.classList.add('active');
    try{{ localStorage.setItem('fmcg_region', region); }}catch(e){{}}
  }}

  window.setLang = setLang;
  window.setRegion = setRegion;

  var lang = 'en';
  var region = 'global';
  try{{
    lang = localStorage.getItem('fmcg_lang') || 'en';
    region = localStorage.getItem('fmcg_region') || 'global';
  }}catch(e){{}}
  setLang(lang);
  setRegion(region);
}})();
</script>
</body>
</html>"""


# ─── email renderer ────────────────────────────────────────────────────────────

def _email_trend_section(data: dict | None) -> str:
    if not data or not data.get("items"):
        return ""
    rows = ""
    for item in data["items"]:
        arrow = "▲" if item["direction"] == "up" else ("▼" if item["direction"] == "down" else "→")
        color = "#10b981" if item["direction"] == "up" else ("#ef4444" if item["direction"] == "down" else "#6366f1")
        sign  = "+" if item["change_pct"] > 0 else ""
        rows += (
            f'<tr><td style="padding:4px 0 4px 8px;font-size:13px;color:#475569;">'
            f'<span style="font-weight:600;color:#1e293b;">{_esc(item["name"])}</span>'
            f' &nbsp;<span style="color:{color};font-weight:700">{arrow} {sign}{item["change_pct"]}%</span>'
            f'</td></tr>'
        )
    period = _esc(data.get("period", ""))
    return f"""
      <p style="font-size:12px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin:20px 0 8px;">
        Korea Search Trends — Naver DataLab <span style="font-weight:400;text-transform:none">({period})</span>
      </p>
      <table width="100%" cellpadding="0" cellspacing="0" style="border-top:1px solid #e2e8f0;">
        {rows}
      </table>"""

def _email_category_preview(cat: dict) -> str:
    """One-line teaser per category for the email body."""
    lines = []
    for region in ("global", "asia", "korea"):
        rd = cat["regions"].get(region, {})
        if not rd.get("has_content"):
            continue
        if cat.get("global_only") and region != "global":
            continue
        items = rd.get("items", [])
        if items:
            headline = items[0].get("headline_en", "")
            if headline:
                region_label = {"global": "Global", "asia": "Asia", "korea": "Korea"}[region]
                lines.append(f'<tr><td style="padding:4px 0 4px 8px;font-size:13px;color:#475569;">'
                              f'<span style="font-weight:600;color:#1e293b;">[{region_label}]</span> '
                              f'{_esc(headline)}</td></tr>')
    return "\n".join(lines)


def render_email(
    summarized: dict,
    issue_date: str,
    issue_label: str,
    web_url: str,
    shopping_insight: dict | None = None,
) -> str:
    category_rows = ""
    for cat_key in CATEGORY_ORDER:
        cat = summarized.get(cat_key)
        if not cat:
            continue
        conditional = cat.get("conditional", False)
        any_content = any(
            cat["regions"].get(r, {}).get("has_content")
            for r in ("global", "asia", "korea")
        )
        if conditional and not any_content:
            continue

        previews = _email_category_preview(cat)
        if not previews:
            continue

        category_rows += f"""
        <tr>
          <td style="padding:16px 0 4px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="font-size:14px;font-weight:700;color:#1e293b;border-left:3px solid {cat['color']};padding-left:10px;">
                  {cat['icon']} {_esc(cat['name'])}
                </td>
              </tr>
              {previews}
            </table>
          </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f0f4f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f4f8;padding:24px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">

  <!-- Header -->
  <tr>
    <td style="background:linear-gradient(135deg,#1a1a2e,#0f3460);border-radius:12px 12px 0 0;padding:28px 32px;">
      <p style="color:#fff;font-size:20px;font-weight:700;margin:0 0 4px;">FMCG Marketing Intelligence</p>
      <p style="color:rgba(255,255,255,.65);font-size:13px;margin:0;">{_esc(issue_label)}</p>
    </td>
  </tr>

  <!-- Body -->
  <tr>
    <td style="background:#fff;padding:24px 32px;">
      <p style="font-size:14px;color:#475569;margin:0 0 20px;">
        Your FMCG marketing intelligence briefing is ready — covering Global, Asia, and Korea.
        Click below to read the full newsletter with English / 한국어 toggle.
      </p>

      <!-- Single CTA -->
      <table cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
        <tr>
          <td>
            <a href="{_esc(web_url)}"
               style="display:inline-block;background:#4f46e5;color:#fff;padding:12px 28px;border-radius:8px;font-size:14px;font-weight:600;text-decoration:none;">
              Read Full Newsletter →
            </a>
          </td>
        </tr>
      </table>

      <!-- Preview -->
      <p style="font-size:12px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin:0 0 8px;">
        This issue's highlights
      </p>
      <table width="100%" cellpadding="0" cellspacing="0" style="border-top:1px solid #e2e8f0;">
        {category_rows}
      </table>
      {_email_trend_section(shopping_insight)}
    </td>
  </tr>

  <!-- Footer -->
  <tr>
    <td style="background:#1a1a2e;border-radius:0 0 12px 12px;padding:20px 32px;text-align:center;">
      <p style="color:rgba(255,255,255,.5);font-size:12px;margin:0;">
        FMCG Marketing Intelligence · Published Monday &amp; Thursday
      </p>
    </td>
  </tr>

</table>
</td></tr>
</table>
</body>
</html>"""
