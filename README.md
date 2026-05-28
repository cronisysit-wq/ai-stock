# AI Trading Assistant

Educational US stock trading assistant — Streamlit UI, paper trading, strategy scans, AI chat.

**Not financial advice.** Live trading is disabled by default.

## Run locally

```bash
pip install -r requirements.txt
cp .env.example .env   # add API keys
python -m streamlit run app.py
```

## Deploy on Railway

1. Push this repo to GitHub (do **not** commit `.env`).
2. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub**.
3. Select the repo. Railway uses the `Dockerfile` automatically.
4. In **Variables**, add at minimum:

| Variable | Example |
|----------|---------|
| `GEMINI_API_KEY` | your Gemini key |
| `OPENAI_API_KEY` | your OpenAI key |
| `AI_PROVIDER` | `gemini` |
| `AI_STOCK_PROVIDER` | `openai` |
| `ENABLE_LIVE_TRADING` | `false` |
| `ENABLE_AUTO_MODE` | `false` |

5. **Settings → Networking → Generate Domain** to get a public URL.

### PostgreSQL (required for instant scan cache)

Without Postgres, scan results reset on every redeploy. Link Postgres and set on the **app** service:

| Variable | Value |
|----------|--------|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (Railway reference) |
| `SCAN_CACHE_REFRESH_MINUTES` | `5` (full scan refresh; overwrites cache row) |
| `SCAN_UI_POLL_SECONDS` | `30` (UI picks up new cache) |

**How cache works:** Every 5 minutes the server runs a **full new scan** and **updates** one row in `app_settings` (JSON). It does **not** wipe your database — paper trades, logs, and proposals stay. Only the scan snapshot is replaced.

Use the **internal** Postgres URL on Railway (`postgres.railway.internal`) when both services are in the same project.

### Resource tips

- Use **512MB–1GB RAM** minimum (scans use yfinance + pandas).
- Strategy scan **Limit 200–300** on cloud to avoid timeouts.
- Keep `ENABLE_LIVE_TRADING=false` unless you fully accept real-money risk.

## Safety defaults

All dangerous flags default to off in `.env.example`. The app uses MockBroker when Alpaca keys are missing.
