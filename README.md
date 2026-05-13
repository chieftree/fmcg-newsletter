# FMCG Marketing Intelligence Newsletter

Weekly FMCG marketing intelligence newsletter — auto-generated every Monday 06:00 KST.

## Setup (one-time, ~15 minutes)

### 1. Create GitHub repository
Push this project to a new **public** GitHub repository.

### 2. Enable GitHub Pages
Go to **Settings → Pages → Source: Deploy from a branch → Branch: main → Folder: /docs** → Save.

Your newsletter URL will be: `https://YOUR_USERNAME.github.io/REPO_NAME/`

### 3. Add repository secrets
Go to **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret name | Value |
|---|---|
| `GEMINI_API_KEY` | Your Google AI Studio API key ([get one](https://aistudio.google.com)) |
| `GMAIL_USER` | Your Gmail address (e.g. `chieftree@gmail.com`) |
| `GMAIL_APP_PASSWORD` | Gmail App Password ([how to create](https://myaccount.google.com/apppasswords)) |

> **Gmail App Password**: Google Account → Security → 2-Step Verification → App passwords → create one for "Mail".

### 4. Run manually to send the first issue
Go to **Actions → Weekly FMCG Newsletter → Run workflow** — this sends the Year in Review (past 12 months).

After that, it runs automatically every **Monday at 06:00 KST**.

---

## Adding subscribers

Edit [`config/subscribers.json`](config/subscribers.json) and add an entry:

```json
{ "email": "new@example.com", "name": "Name", "active": true }
```

Commit and push — done.

## Project structure

```
├── main.py                    # Orchestration
├── src/
│   ├── news_collector.py      # Google News RSS
│   ├── summarizer.py          # Gemini AI summarization
│   ├── renderer.py            # HTML generation (web + email)
│   └── email_sender.py        # Gmail SMTP
├── config/
│   ├── keywords.json          # Search queries per category/region
│   ├── subscribers.json       # Subscriber list
│   └── sent_history.json      # Deduplication tracking (auto-updated)
├── docs/                      # GitHub Pages output (auto-generated)
└── .github/workflows/
    └── weekly.yml             # Cron schedule
```

## Newsletter categories

| # | Category | Regions | Conditional |
|---|---|---|---|
| 1 | 🔥 Viral on Social Media | Global / Asia / Korea | Always shown |
| 2 | 📈 Sales Surge Brands | Global / Asia / Korea | Always shown |
| 3 | 🏆 Award-Winning Campaigns | Global / Asia / Korea | Only when results exist |
| 4 | 🎓 Byron Sharp & Laws of Growth | Global only | Always shown |
| 5 | 🍫 Mars Snacking Brand News | Global / Asia / Korea | Always shown |

## Cost

**$0/month** — GitHub Actions (free) + Google News RSS (free) + Gemini free tier + Gmail SMTP (free).
