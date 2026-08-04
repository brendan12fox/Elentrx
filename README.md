# Elentrx™ — Healthcare Clinical Trial Scraper & Alerter

Monitors **ClinicalTrials.gov** for phase changes on trials led by **publicly traded** sponsors, rotates through therapeutic sectors hourly at **minute :58 UTC**, runs LLM research + ML favorability scoring, and texts you on bullish signals.

> **Legal:** Not financial advice. See [DISCLAIMER.md](DISCLAIMER.md), [TERMS_OF_USE.md](TERMS_OF_USE.md), [PRIVACY_POLICY.md](PRIVACY_POLICY.md), and [TRADEMARKS.md](TRADEMARKS.md). Elentrx™ is a trademark of Brendan Fox.

## Architecture

- **GitHub Actions** (`58 * * * *`) — scraper + analysis + email alerts
- **Streamlit Community Cloud** — dashboard reading committed SQLite snapshots
- **ClinicalTrials.gov v2 API** — trial registry (no brittle FDA HTML scraping)
- **OpenAI Responses API** — built-in `web_search` tool for news + structured research briefs (one API key)
- **sklearn GradientBoosting** — favorability classifier (bootstrapped on historical returns)
- **SMTP email** — free/cheap alert delivery (Gmail, SendGrid, etc.)

## Sector rotation

8 sectors → each refreshes every **8 hours**:

1. Oncology  
2. Immunology / Inflammation  
3. CNS / Neurology  
4. Cardiology / Metabolic  
5. Infectious Disease  
6. Rare Disease / Orphan  
7. Hematology  
8. Other / Multi-indication  

`sector_index = hour_utc % len(sectors)`

## Setup

### 1. Install locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m src.ml.train
```

### 2. Secrets

Copy `.env.example` to `.env` and fill in:

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | LLM + web search (Responses API) |
| `OPENAI_SEARCH_MODEL` | Model with web search support (default `gpt-4o`) |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | Bootstrap dashboard login (or create first user in UI) |
| `ALERT_EMAIL` | Where trial alert emails are sent |
| `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` | Email delivery (Gmail, SendGrid, etc.) |
| `FAVORABILITY_THRESHOLD` | Default `0.65` |

Add the same secrets to **GitHub Actions** repo secrets for the cron job.

### 3. Run manually

```bash
# List sectors
python -m src.pipeline.run_hourly --list-sectors

# Dry run for current UTC hour's sector
python -m src.pipeline.run_hourly --dry-run

# Override sector via hour
python -m src.pipeline.run_hourly --hour-utc 3 --dry-run
```

### 4. Historical evaluation (temporal train/test)

Build a point-in-time labeled dataset and measure classifier quality:

```bash
# OpenAI web search + LLM briefs (default)
python -m src.ml.evaluate --rebuild --max-events 200 --start-date 2020-01-01 --end-date 2024-10-01
python -m src.ml.train

# Fast/cheap mode without OpenAI web search
python -m src.ml.evaluate --rebuild --max-events 200 --no-llm
```

**News:** OpenAI Responses API `web_search` tool — one API key, no Serper/Tavily/RSS required. Used for both training and live alerts.

**Anti-leakage rules:**
- News/articles are restricted to on or before each trial's `event_date`
- Labels use 5-day forward stock returns *after* the event (never fed to the model)
- Train/test split is **temporal** (oldest 80% train, newest 20% test — no random shuffle)

Reports saved to `data/evaluation_report.json` and shown in the Streamlit **Evaluation** tab.

### 5. Streamlit dashboard (the UI)

**Local:**

```bash
streamlit run app.py
```

Open **http://localhost:8501** in your browser.

**First visit:** create an admin username/password on the login screen (or set `ADMIN_USERNAME` + `ADMIN_PASSWORD` in `.env` before starting).

**Tabs:** Rotation · Trials · Changes · Alerts · Runs · Evaluation · Config · **Account** · Legal

**Cloud deploy:** [Streamlit Community Cloud](https://streamlit.io/cloud) → connect https://github.com/brendan12fox/Elentrx → entrypoint `app.py` → add secrets (`ADMIN_PASSWORD`, `OPENAI_API_KEY`, SMTP vars, etc.).

### 6. Email alerts

Alerts are **email only** (free/cheap via Gmail or SendGrid):

| Provider | Free tier |
|----------|-----------|
| **Gmail** | Free (~500/day); use an [App Password](https://support.google.com/accounts/answer/185833) |
| **SendGrid** | 100 emails/day free |
| **Resend** | 3,000/month free |
| **Amazon SES** | ~$0.10 per 1,000 emails |

Example Gmail `.env`:

```env
ALERT_EMAIL=you@gmail.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your-16-char-app-password
SMTP_FROM=Elentrx Alerts <you@gmail.com>
```

Set your alert address in the **Account** tab after login.

### 7. Daily watchlist (shared cache)

The **Watchlist** tab shows a shared daily digest for all users — fast load, no per-user LLM calls.

```bash
# Build or refresh manually
python -m src.research.refresh_watchlist

# Force rebuild even if cache is fresh
python -m src.research.refresh_watchlist --force
```

- Refreshes automatically when stale (~24h) during the hourly pipeline
- Caches headlines (RSS) + one batched LLM brief (`gpt-4o-mini` by default)
- Stored in SQLite + `data/watchlist_digest.json`

## GitHub Actions

Workflow: [`.github/workflows/hourly.yml`](.github/workflows/hourly.yml)

- Runs at **:58** every hour UTC
- Commits `data/snapshots.db` and model updates back to the repo
- Manual dispatch supports `hour_utc` override and `dry_run`

## Public sponsor filter

Trials are kept only when the lead sponsor fuzzy-matches [`data/sponsor_tickers.csv`](data/sponsor_tickers.csv). Expand this file to widen coverage.

## Legal

| Document | Purpose |
|----------|---------|
| [LICENSE](LICENSE) | Proprietary license — all rights reserved |
| [DISCLAIMER.md](DISCLAIMER.md) | Not financial/medical advice; ML & AI limitations |
| [TERMS_OF_USE.md](TERMS_OF_USE.md) | Acceptable use, liability limits, SMS responsibilities |
| [PRIVACY_POLICY.md](PRIVACY_POLICY.md) | Data handling for self-hosted deployments |
| [TRADEMARKS.md](TRADEMARKS.md) | Elentrx™ brand and third-party mark attributions |
| [NOTICE.md](NOTICE.md) | Open-source and data-source attributions |

**Elentrx™** is a trademark of Brendan Fox. ClinicalTrials.gov®, OpenAI®, Twilio®, Streamlit®, and other marks are property of their respective owners. This software is not affiliated with or endorsed by NIH, FDA, SEC, or any listed company.

By using or deploying this software, you agree to the Terms of Use and Disclaimer.
