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

### Optional: PostgreSQL (recommended)

SQLite on Railway is ephemeral (resets on redeploy). Add Railway **PostgreSQL** and set:

```
DATABASE_URL=${{Postgres.DATABASE_URL}}
```

### Resource tips

- Use **512MB–1GB RAM** minimum (scans use yfinance + pandas).
- Strategy scan **Limit 200–300** on cloud to avoid timeouts.
- Keep `ENABLE_LIVE_TRADING=false` unless you fully accept real-money risk.

## Safety defaults

All dangerous flags default to off in `.env.example`. The app uses MockBroker when Alpaca keys are missing.
