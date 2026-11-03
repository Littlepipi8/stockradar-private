
"""Send new stock signals to Discord without repeated alerts."""

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from scanner import OUT

STATE = Path(__file__).resolve().parent / "data" / "alert_state.json"

SIGNALS = {
    "NEAR SUPPORT",
    "SUPPORT BREAK",
    "TREND BREAK",
    "NEAR RESISTANCE",
    "RESISTANCE BREAK",
}

EMOJI = {
    "NEAR SUPPORT": "🟠",
    "SUPPORT BREAK": "🔴",
    "TREND BREAK": "🔴",
    "NEAR RESISTANCE": "🟡",
    "RESISTANCE BREAK": "🟢",
}


def format_price(value):
    if value is None:
        return "N/A"
    return f"${float(value):,.2f}"


def send_discord(webhook, message):
    request_data = json.dumps({
        "username": "StockRadar",
        "content": message,
    }).encode("utf-8")

    for attempt in range(6):
        request = urllib.request.Request(
            webhook,
            data=request_data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "StockRadar/1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request, timeout=20
            ) as response:
                print("Discord response:", response.status)
            time.sleep(2)
            return

        except urllib.error.HTTPError as error:
            if error.code != 429:
                raise

            retry_after = error.headers.get("Retry-After")

            try:
                wait = float(retry_after) if retry_after else 5.0
            except (TypeError, ValueError):
                wait = 5.0

            wait = max(1.0, min(wait, 120.0))
            print(f"Discord rate limit. Waiting {wait} seconds...")
            time.sleep(wait + 1)

    raise RuntimeError("Discord rate limit persisted after 6 attempts")


def notify():
    payload = json.loads(OUT.read_text(encoding="utf-8"))

    scanned = payload["scanned"]
    universe = payload["universe_size"]

    if scanned < max(1, int(universe * 0.8)):
        raise RuntimeError(
            "Insufficient scan coverage; alerts suppressed"
        )

    previous = (
        json.loads(STATE.read_text(encoding="utf-8"))
        if STATE.exists()
        else {}
    )

    active = {
        r["ticker"]: r["signal"]
        for r in payload["results"]
        if r["signal"] in SIGNALS
    }

    fresh = [
        r for r in payload["results"]
        if r["signal"] in SIGNALS
        and previous.get(r["ticker"]) != r["signal"]
    ]

    if os.getenv("STOCKRADAR_INITIALIZE_ALERTS") == "1":
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(
            json.dumps(active, indent=2),
            encoding="utf-8",
        )
        print(f"Initialized alert history for {len(active)} stocks.")
        print("No Discord messages sent.")
        return

    webhook = os.getenv("DISCORD_WEBHOOK_URL", "").strip()

    if not webhook:
        raise RuntimeError("DISCORD_WEBHOOK_URL is missing")

    if fresh:
        lines = []

        for r in fresh:
            signal = r["signal"]
            symbol = r["ticker"]
            close = format_price(r.get("close"))

            if signal in ("NEAR SUPPORT", "SUPPORT BREAK"):
                level = format_price(r.get("support"))
                detail = f"Support: {level}"

            elif signal in ("NEAR RESISTANCE", "RESISTANCE BREAK"):
                level = format_price(r.get("resistance"))
                detail = f"Resistance: {level}"

            else:
                level = format_price(r.get("trendline"))
                detail = f"Trendline: {level}"

            lines.append(
                f"{EMOJI[signal]} **{symbol} — {signal}**\n"
                f"Close: {close} | {detail}"
            )

        # Send small batches, staying below Discord's message limit.
        for start in range(0, len(lines), 8):
            batch = lines[start:start + 8]

            message = (
                "📊 **StockRadar — New Daily Signals**\n\n"
                + "\n\n".join(batch)
                + "\n\nResearch only. Not financial advice."
            )

            send_discord(webhook, message[:1900])

        print(f"Sent {len(fresh)} new Discord signals")

    else:
        print("No new alerts")

    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(
        json.dumps(active, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    notify()
