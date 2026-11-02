
"""Send new daily stock signals to Discord, without duplicate alerts."""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from scanner import OUT

STATE = Path(__file__).resolve().parent / "data" / "alert_state.json"


def notify():
    payload = json.loads(OUT.read_text(encoding="utf-8"))

    scanned = payload["scanned"]
    universe = payload["universe_size"]

    if scanned < max(1, int(universe * 0.8)):
        raise RuntimeError("Insufficient scan coverage; alerts suppressed")

    previous = (
        json.loads(STATE.read_text(encoding="utf-8"))
        if STATE.exists()
        else {}
    )

    active = {
        r["ticker"]: f'{r["date"]}:{r["signal"]}'
        for r in payload["results"]
        if r["signal"] != "NONE"
    }

    fresh = [
        r for r in payload["results"]
        if r["ticker"] in active
        and previous.get(r["ticker"]) != active[r["ticker"]]
    ]

    webhook = os.getenv("DISCORD_WEBHOOK_URL", "").strip()

    if not webhook:
        raise RuntimeError("DISCORD_WEBHOOK_URL is missing")

    if fresh:
        lines = [
            f'{r["ticker"]} | {r["signal"]} | '
            f'Close ${r["close"]} | Support ${r["support"]} | '
            f'Distance {r["distance_pct"]}%'
            for r in fresh
        ]

        # Discord messages must be under 2,000 characters.
        # Split signals into small batches.
        for start in range(0, len(lines), 10):
            batch = lines[start:start + 10]

            message = (
                "📊 **StockRadar — New Daily Signals**\n"
                + "\n".join(batch)
                + "\n\nResearch only. Not financial advice."
            )

            request = urllib.request.Request(
                webhook,
                data=json.dumps({
                    "username": "StockRadar",
                    "content": message[:1900],
                }).encode("utf-8"),
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
            except urllib.error.HTTPError as error:
                print("Discord status:", error.code)
                raise

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
