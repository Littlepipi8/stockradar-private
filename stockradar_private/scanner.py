
"""End-of-day S&P 500 scanner using confirmed weekly price zones.

Heuristic technical signals for research, not investment advice.
"""

import json
import os
import time
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "latest.json"

STARTER = (
    "GOOG AAPL MSFT NVDA AMZN META GOOGL BRK-B AVGO TSLA "
    "JPM V UNH XOM COST WMT NFLX AMD HD PG VST"
).split()

CONFIRMATION_PCT = 1.0
WEEKLY_PIVOT_WIDTH = 3
ZONE_TOLERANCE_PCT = 3.0
MIN_WEEKLY_TESTS = 2


def constituents():
    url = (
        "https://en.wikipedia.org/wiki/"
        "List_of_S%26P_500_companies"
    )

    response = requests.get(
        url,
        headers={
            "User-Agent": "StockRadar research scanner"
        },
        timeout=30
    )

    response.raise_for_status()

    table = pd.read_html(StringIO(response.text))[0]

    return sorted(
        set(
            table["Symbol"]
            .astype(str)
            .str.replace(".", "-", regex=False)
        )
    )


def pivot_indices(values, width=3, high=False):
    values = np.asarray(values, dtype=float)
    result = []

    for i in range(width, len(values) - width):
        window = values[
            i - width:i + width + 1
        ]

        if high:
            if values[i] >= np.max(window):
                result.append(i)
        else:
            if values[i] <= np.min(window):
                result.append(i)

    return result


def zones_from_pivots(
    values,
    indices,
    tolerance_pct=ZONE_TOLERANCE_PCT
):
    """Group nearby confirmed weekly pivot prices."""

    clusters = []

    for i in indices:
        price = float(values[i])

        matches = [
            c for c in clusters
            if abs(price - c["level"]) / c["level"] * 100
            <= tolerance_pct
        ]

        if matches:
            cluster = min(
                matches,
                key=lambda c: abs(
                    price - c["level"]
                )
            )

            cluster["prices"].append(price)
            cluster["indices"].append(i)

            cluster["level"] = float(
                np.median(cluster["prices"])
            )

        else:
            clusters.append({
                "level": price,
                "prices": [price],
                "indices": [i]
            })

    return [
        {
            "level": c["level"],
            "tests": len(set(c["indices"])),
            "last_test": max(c["indices"])
        }
        for c in clusters
    ]


def choose_zone(zones, close, side):
    """Prefer repeatedly tested weekly zones."""

    candidates = [
        z for z in zones
        if (
            z["level"] >= close
            if side == "resistance"
            else z["level"] <= close
        )
    ]

    if not candidates:
        return None

    major = [
        z for z in candidates
        if z["tests"] >= MIN_WEEKLY_TESTS
    ]

    pool = major if major else candidates

    selected = max(
        pool,
        key=lambda z: (
            z["tests"],
            z["last_test"],
            -abs(z["level"] - close)
        )
    )

    return selected["level"]


def analyze(
    symbol,
    frame,
    proximity=2.0,
    width=WEEKLY_PIVOT_WIDTH
):
    frame = (
        frame.dropna(
            subset=["Open", "High", "Low", "Close"]
        )
        .sort_index()
        .copy()
    )

    if len(frame) < 110:
        return None

    # Convert daily candles into weekly candles.
    weekly = frame.resample("W-FRI").agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last"
    }).dropna()

    last_day = pd.Timestamp(frame.index[-1])

    # Exclude an unfinished week.
    if last_day.weekday() != 4:
        weekly = weekly.iloc[:-1]

    if len(weekly) < 2 * width + 3:
        return None

    highs = weekly["High"].to_numpy(dtype=float)
    lows = weekly["Low"].to_numpy(dtype=float)

    low_pivots = pivot_indices(
        lows,
        width
    )

    high_pivots = pivot_indices(
        highs,
        width,
        high=True
    )

    support_zones = zones_from_pivots(
        lows,
        low_pivots
    )

    resistance_zones = zones_from_pivots(
        highs,
        high_pivots
    )

    close = float(frame["Close"].iloc[-1])
    previous_close = float(frame["Close"].iloc[-2])

    buffer = CONFIRMATION_PCT / 100.0

    # Select significant weekly zones.
    support = choose_zone(
        support_zones,
        close,
        "support"
    )

    resistance = choose_zone(
        resistance_zones,
        close,
        "resistance"
    )

    # Confirm support breakdowns using 1% buffer.
    broken_supports = [
        z for z in support_zones
        if previous_close >= z["level"] * (1 - buffer)
        and close < z["level"] * (1 - buffer)
        and z["tests"] >= MIN_WEEKLY_TESTS
    ]

    # Confirm resistance breakouts using 1% buffer.
    broken_resistances = [
        z for z in resistance_zones
        if previous_close <= z["level"] * (1 + buffer)
        and close > z["level"] * (1 + buffer)
        and z["tests"] >= MIN_WEEKLY_TESTS
    ]

    breakdown_level = max(
        (z["level"] for z in broken_supports),
        default=None
    )

    breakout_level = min(
        (z["level"] for z in broken_resistances),
        default=None
    )

    # Show the broken level if a break occurs.
    if breakdown_level is not None:
        support = breakdown_level

    if breakout_level is not None:
        resistance = breakout_level

    support_distance = (
        (close / support - 1) * 100
        if support is not None
        else None
    )

    resistance_distance = (
        (resistance - close) / resistance * 100
        if resistance is not None
        else None
    )

    near_support = (
        support_distance is not None
        and 0 <= support_distance <= proximity
    )

    near_resistance = (
        resistance_distance is not None
        and 0 <= resistance_distance <= proximity
    )

    # Weekly rising trendline.
    trend = None
    trend_break = False

    for j in range(len(low_pivots) - 1, 0, -1):
        i1 = low_pivots[j - 1]
        i2 = low_pivots[j]

        if lows[i2] <= lows[i1]:
            continue

        slope = (
            (lows[i2] - lows[i1])
            / (i2 - i1)
        )

        weeks_since = (
            (last_day - weekly.index[i2]).days
            / 7.0
        )

        trend = float(
            lows[i2] + slope * weeks_since
        )

        prior_trend = trend - slope / 5.0

        trend_break = (
            previous_close >= prior_trend * (1 - buffer)
            and close < trend * (1 - buffer)
        )

        break

    volumes = frame["Volume"].to_numpy(
        dtype=float
    )

    avg_volume = float(
        np.nanmean(volumes[-21:-1])
    )

    volume_ratio = (
        float(volumes[-1] / avg_volume)
        if avg_volume > 0
        else None
    )

    signal = (
        "SUPPORT BREAK"
        if breakdown_level is not None
        else "TREND BREAK"
        if trend_break
        else "RESISTANCE BREAK"
        if breakout_level is not None
        else "NEAR SUPPORT"
        if near_support
        else "NEAR RESISTANCE"
        if near_resistance
        else "NONE"
    )

    return {
        "ticker": symbol,
        "date": str(last_day.date()),
        "close": round(close, 2),
        "support": (
            round(support, 2)
            if support is not None
            else None
        ),
        "resistance": (
            round(resistance, 2)
            if resistance is not None
            else None
        ),
        "distance_pct": (
            round(support_distance, 2)
            if support_distance is not None
            else None
        ),
        "resistance_distance_pct": (
            round(resistance_distance, 2)
            if resistance_distance is not None
            else None
        ),
        "trendline": (
            round(trend, 2)
            if trend is not None
            else None
        ),
        "volume_ratio": (
            round(volume_ratio, 2)
            if volume_ratio is not None
            else None
        ),
        "signal": signal
    }


def fetch(symbol):
    df = yf.download(
        symbol,
        period="2y",
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=False,
        timeout=25
    )

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    return df


def scan(
    tickers,
    proximity=2.0,
    width=WEEKLY_PIVOT_WIDTH,
    pause=0.15
):
    rows = []
    failed = []

    for idx, symbol in enumerate(tickers, 1):
        try:
            result = analyze(
                symbol,
                fetch(symbol),
                proximity,
                width
            )

            if result is not None:
                rows.append(result)
            else:
                failed.append(symbol)

        except Exception as exc:
            failed.append(symbol)
            print(
                f"Failed {symbol}: {exc}",
                flush=True
            )

        if idx % 25 == 0:
            print(
                f"Processed {idx}/{len(tickers)}",
                flush=True
            )

        time.sleep(pause)

    rank = {
        "SUPPORT BREAK": 0,
        "TREND BREAK": 1,
        "RESISTANCE BREAK": 2,
        "NEAR SUPPORT": 3,
        "NEAR RESISTANCE": 4,
        "NONE": 5
    }

    rows.sort(
        key=lambda r: (
            rank[r["signal"]],
            abs(r["distance_pct"])
            if r["distance_pct"] is not None
            else float("inf")
        )
    )

    return {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "universe_size": len(tickers),
        "scanned": len(rows),
        "failed": failed,
        "proximity_pct": proximity,
        "pivot_width": width,
        "confirmation_pct": CONFIRMATION_PCT,
        "level_timeframe": "weekly",
        "results": rows
    }


def save(payload, path=OUT):
    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    path.write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8"
    )


def main():
    mode = os.getenv(
        "STOCKRADAR_UNIVERSE",
        "sp500"
    ).lower()

    if mode == "starter":
        tickers = STARTER

    elif mode == "sp500":
        tickers = constituents()

    else:
        tickers = [
            s.strip().upper()
            for s in mode.split(",")
            if s.strip()
        ]

    payload = scan(
        tickers,
        proximity=float(
            os.getenv("SUPPORT_PROXIMITY", "2")
        )
    )

    save(payload)

    print(
        f"Saved {payload['scanned']}/"
        f"{payload['universe_size']} to {OUT}"
    )

    if payload["scanned"] < max(
        1,
        int(len(tickers) * 0.8)
    ):
        raise RuntimeError(
            "Scan incomplete (<80%); alerts suppressed"
        )

    return payload


if __name__ == "__main__":
    main()
