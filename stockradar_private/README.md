# StockRadar Private — deployable starter

A password-protected Streamlit dashboard with automated end-of-day S&P 500 scanning and optional SMTP email alerts. **Not yet deployed**. Price data is from Yahoo Finance (`yfinance`), which is unofficial and may rate-limit or fail. Signals are research heuristics, not recommendations.

## 1. Local setup

```bash
python -m venv .venv
# activate .venv for your operating system
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edit secrets.toml: set a long unique APP_PASSWORD
STOCKRADAR_UNIVERSE=starter python scanner.py   # fast smoke test
streamlit run app.py
```

On Windows PowerShell use `$env:STOCKRADAR_UNIVERSE="starter"; python scanner.py` instead of the Unix env assignment. For full scan, run `python scanner.py` (may take many minutes and hit provider limits).

## 2. GitHub setup

1. Create a **private** GitHub repository and upload the project contents including `.github/workflows/daily-scan.yml` and `data/alert_state.json`. Do not upload `.streamlit/secrets.toml`.
2. Repository Settings → Actions → General: permit workflows. The workflow needs permission to write repository contents. If necessary, select **Read and write permissions** under Workflow permissions (organization policies may override).
3. Actions → **Daily S&P 500 scan** → Run workflow to test. The schedule is 01:00 UTC Tuesday–Saturday, following US weekday market sessions. GitHub scheduled workflows may be delayed, disabled after prolonged inactivity on public repos, and do not guarantee execution.
4. Workflow commits `data/latest.json` and `data/alert_state.json` back to the default branch. If branch protection blocks pushes, use a dedicated results branch or a database instead.

## 3. Optional email alerts

GitHub repo → Settings → Secrets and variables → Actions → New repository secret:

- `SMTP_HOST` (e.g. smtp.gmail.com)
- `SMTP_PORT` (`587`)
- `SMTP_USER` (your SMTP login)
- `SMTP_PASSWORD` (SMTP app password, **not** your account password)
- `ALERT_EMAIL_TO` (recipient address)
- `ALERT_EMAIL_FROM` (optional; defaults to SMTP_USER)

Only signals newly seen for a symbol on a particular daily candle are emailed. The first successful run can generate a large initial batch. The notification state is committed only after successful sending. If SMTP secrets are missing, email is skipped, and state is not updated for those signals.

## 4. Website deployment

Simplest: connect the private GitHub repo to [Streamlit Community Cloud](https://share.streamlit.io/) (subject to its current private-repo and app visibility policies), set entrypoint `app.py`, and configure `APP_PASSWORD` under app Secrets. **Password gate is application-level access control, not a guarantee of private infrastructure.** Check platform visibility and sharing settings; if you need strict private network access, deploy behind authenticated access on a paid hosting service or VPN. Streamlit's GitHub sync/redeployment behavior can vary; verify that a new committed `data/latest.json` appears on the live app after each scan. If it doesn't, use external object storage/database or a redeploy hook.

If your deployment platform restarts the app or blocks private repo access, check logs and secrets. Avoid exposing GitHub or SMTP credentials in Streamlit secrets unless needed there; only `APP_PASSWORD` belongs in Streamlit app secrets.

## 5. Definitions and caveats

- **Near support:** close is between 0% and +2% of the most recent confirmed pivot low eligible relative to the previous close.
- **Support break:** yesterday's close was at/above the pivot and today's close is below it.
- **Trend break:** close crosses below an extrapolated line joining the latest qualifying pair of confirmed rising pivot lows.
- **Confirmed pivot:** 5 trading bars on each side, so confirmation is delayed. This is not a hand-drawn 'major support' zone and can select minor pivots.
- Signals use adjusted daily OHLC data; free data may be delayed, revised, or inconsistent. No intraday alerts.
- The S&P 500 member list comes from Wikipedia and may fail or change. Symbol substitutions may be needed.
- The scanner suppresses alerts when fewer than 80% of symbols succeed, but this does not guarantee accurate or complete market data.
- Daily workflow runs on exchange holidays too; it may show the previous session's data. Duplicate email signals are suppressed via per-symbol date and signal.
- A long 500-stock run may exceed GitHub runner time or yfinance limits. For reliability, migrate to a licensed API with bulk endpoints and persistent storage.
- A GitHub repository containing scan results exposes those results to anyone with repository access; don't store passwords or account details in scan files.
