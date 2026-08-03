# Elentrx™ — Privacy Policy

**Last updated:** August 3, 2026  
**Operator:** Brendan Fox

> **Important:** Template policy for self-hosted / personal deployment. If you offer
> Elentrx to other users or collect data from third parties, have a privacy attorney
> review and update this document.

## 1. Overview

Elentrx monitors public clinical trial data and may send alerts to a configured phone
number. This policy describes what data the Software processes when **you** deploy and
run it.

## 2. Who this applies to

This policy applies when you run Elentrx yourself (locally, on Streamlit Cloud, or via
GitHub Actions). **You** are the operator of your deployment and are responsible for
compliance with privacy laws applicable to your use (e.g., TCPA for SMS in the U.S.).

## 3. Information we process

### 3.1 Information you provide

| Data | Purpose |
|------|---------|
| Phone number (`ALERT_PHONE`) | SMS alert delivery |
| API keys (OpenAI, Twilio, etc.) | Stored in your `.env` / GitHub Secrets — **never commit to git** |
| GitHub account (if using Actions) | Workflow execution |

### 3.2 Information collected automatically

| Data | Purpose |
|------|---------|
| Clinical trial records | Scraped from public ClinicalTrials.gov API |
| Phase change events | Stored in local SQLite (`data/snapshots.db`) |
| Research briefs & ML scores | Generated for dashboard and alerts |
| Pipeline run logs | Debugging and dashboard "Runs" tab |
| Alert history | Dedupe and audit in SQLite |

### 3.3 Information sent to third parties

When you enable integrations, data may be sent to:

| Provider | Data shared | Their policy |
|----------|-------------|--------------|
| **OpenAI** | Trial context, ticker, sponsor, drug names for web search & LLM | [OpenAI Privacy Policy](https://openai.com/policies/privacy-policy) |
| **Twilio** | SMS body, recipient phone number | [Twilio Privacy](https://www.twilio.com/legal/privacy) |
| **Yahoo Finance** (yfinance) | Ticker symbols for price history | Yahoo terms of use |
| **GitHub** | Committed snapshots if workflow pushes to repo | [GitHub Privacy](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement) |
| **Streamlit Cloud** (optional) | App traffic, secrets you configure | [Streamlit Privacy](https://streamlit.io/privacy-policy) |

We do not operate a central Elentrx server that collects your data. Processing occurs
in **your** environment.

## 4. How we use information

- Detect phase changes on publicly listed trial sponsors
- Generate research summaries and favorability scores
- Send optional SMS notifications
- Display history in the Streamlit dashboard
- Train and evaluate ML models locally (historical datasets stay on your machine unless you commit them)

## 5. What we do not do

- Sell personal information
- Operate a multi-tenant SaaS with a shared user database (in default self-hosted setup)
- Provide accounts or authenticate end users (unless you add that)

## 6. Data retention

Retention depends on **your** configuration:

- SQLite snapshots persist until you delete them
- Cached news files in `data/news_cache/` can be deleted at any time
- GitHub Actions may commit `data/snapshots.db` to your repo if enabled in workflow

You should rotate API keys if a secret is exposed.

## 7. Security

- Keep `.env` and GitHub Secrets private
- Use repository secrets for CI, not plaintext keys in code
- Restrict Streamlit Cloud access if the dashboard is public

No system is 100% secure. You use the Service at your own risk.

## 8. Your choices

- **Disable SMS:** Remove Twilio credentials
- **Disable LLM:** Use `--no-llm` for evaluation; skip OpenAI key for dry runs
- **Delete data:** Remove `data/snapshots.db`, caches, and historical JSON files
- **SMS opt-out:** Configure Twilio STOP handling for production SMS programs

## 9. Children's privacy

The Service is not directed to individuals under 18. We do not knowingly collect
information from children.

## 10. International users

If you access the Service from outside the United States, you consent to processing
in the U.S. and your local jurisdiction as applicable. Third-party providers may
process data in other countries.

## 11. Changes

We may update this policy in the repository. Check the "Last updated" date.

## 12. Contact

Questions: GitHub repository issues or owner contact on https://github.com/brendan12fox/Elentrx
