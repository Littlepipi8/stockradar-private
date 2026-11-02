"""End-of-day scanner. Heuristic technical signals, not investment advice."""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import requests
import yfinance as yf

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'data' / 'latest.json'
STARTER = 'GOOG AAPL MSFT NVDA AMZN META GOOGL BRK-B AVGO TSLA JPM V UNH XOM COST WMT NFLX AMD HD PG'.split()

def constituents():
    # Wikipedia list is not guaranteed to be available or perfectly up to date.
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    html = requests.get(url, headers={'User-Agent': 'StockRadar personal research scanner (contact: local)'}, timeout=30)
    html.raise_for_status()
    from io import StringIO
    table = pd.read_html(StringIO(html.text))[0]
    return sorted(set(table['Symbol'].astype(str).str.replace('.', '-', regex=False)))

def pivot_indices(values, width=5):
    a = np.asarray(values, dtype=float)
    return [i for i in range(width, len(a)-width) if a[i] <= np.min(a[i-width:i+width+1])]

def pivot_high_indices(values, width=5):
    a = np.asarray(values, dtype=float)
    return [
        i for i in range(width, len(a) - width)
        if a[i] >= np.max(a[i-width:i+width+1])
    ]

def analyze(symbol, frame, proximity=2.0, width=5):
    frame = frame.dropna(subset=['Open','High','Low','Close']).copy()
    if len(frame) < 110: return None
    close = frame['Close'].to_numpy(dtype=float)
    low = frame['Low'].to_numpy(dtype=float)
    volume = frame['Volume'].to_numpy(dtype=float)
    piv = pivot_indices(low, width)
    if not piv: return None
    # Find the nearest confirmed pivot low at or below the latest close.
eligible = [
    i for i in piv
    if i < len(close) - width
    and low[i] <= close[-1]
]

support = (
    max(float(low[i]) for i in eligible)
    if eligible else None
)
    
    highs = frame['High'].to_numpy(dtype=float)
    high_pivots = pivot_high_indices(highs, width)

    # Find the nearest confirmed pivot high at or above the latest close.
resistance_candidates = [
    float(highs[i])
    for i in high_pivots
    if i < len(close) - width
    and highs[i] >= close[-1]
]

resistance = (
    min(resistance_candidates)
    if resistance_candidates else None
)
    resistance_distance = (
        (resistance - close[-1]) / resistance * 100
        if resistance is not None else None
    )

    near_resistance = (
        resistance_distance is not None
        and 0 <= resistance_distance <= proximity
    )

    resistance_break = (
        resistance is not None
        and close[-2] <= resistance
        and close[-1] > resistance
    )

dist = (
    (close[-1] / support - 1) * 100
    if support is not None else None
)

near = (
    dist is not None
    and 0 <= dist <= proximity
)

breakdown = (
    support is not None
    and close[-2] >= support
    and close[-1] < support
)
    trend = None
    trend_break = False
    for j in range(len(piv)-1, 0, -1):
        i1, i2 = piv[j-1], piv[j]
        if low[i2] <= low[i1]: continue
        slope = (low[i2]-low[i1])/(i2-i1)
        trend = float(low[i2]+slope*(len(close)-1-i2))
        prior_trend = float(trend-slope)
        trend_break = close[-2] >= prior_trend and close[-1] < trend
        break
    avg_vol = float(np.nanmean(volume[-21:-1]))
    vol_ratio = float(volume[-1]/avg_vol) if avg_vol > 0 else None
   
    signal = (
        'SUPPORT BREAK' if breakdown else
        'TREND BREAK' if trend_break else
        'RESISTANCE BREAK' if resistance_break else
        'NEAR SUPPORT' if near else
        'NEAR RESISTANCE' if near_resistance else
        'NONE'
    )

    return dict(
        ticker=symbol,
        date=str(frame.index[-1].date()),
        close=round(float(close[-1]), 2),
        support=round(support, 2),
        resistance=round(resistance, 2) if resistance is not None else None,
        distance_pct=round(float(dist), 2),
        resistance_distance_pct=round(float(resistance_distance), 2)
            if resistance_distance is not None else None,
        trendline=round(trend, 2) if trend is not None else None,
        volume_ratio=round(vol_ratio, 2) if vol_ratio is not None else None,
        signal=signal
    )


def fetch(symbol):
    df = yf.download(symbol, period='2y', interval='1d', auto_adjust=True,
                     progress=False, threads=False, timeout=25)
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    return df

def scan(tickers, proximity=2.0, width=5, pause=0.15):
    rows, failed = [], []
    for idx, symbol in enumerate(tickers, 1):
        try:
            result = analyze(symbol, fetch(symbol), proximity, width)
            if result: rows.append(result)
            else: failed.append(symbol)
        except Exception as exc:
            failed.append(symbol)
            print(f'Failed {symbol}: {exc}', flush=True)
        if idx % 25 == 0: print(f'Processed {idx}/{len(tickers)}', flush=True)
        time.sleep(pause)
    rank = {'SUPPORT BREAK':0, 'TREND BREAK':1, 'RESISTANCE BREAK':2, 'NEAR SUPPORT':3, 'NEAR RESISTANCE':4, 'NONE':5}
    rows.sort(key=lambda r:(rank[r['signal']], abs(r['distance_pct'])))
    return dict(generated_at=datetime.now(timezone.utc).isoformat(),
                universe_size=len(tickers), scanned=len(rows), failed=failed,
                proximity_pct=proximity, pivot_width=width, results=rows)

def save(payload, path=OUT):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding='utf-8')

def main():
    mode = os.getenv('STOCKRADAR_UNIVERSE', 'sp500').lower()
    tickers = STARTER if mode == 'starter' else constituents() if mode == 'sp500' else [s.strip().upper() for s in mode.split(',') if s.strip()]
    payload = scan(tickers, proximity=float(os.getenv('SUPPORT_PROXIMITY', '2')))
    save(payload)
    print(f"Saved {payload['scanned']}/{payload['universe_size']} to {OUT}")
    if payload['scanned'] < max(1, int(len(tickers)*0.8)):
        raise RuntimeError('Scan incomplete (<80%); alerts suppressed')
    return payload

if __name__ == '__main__': main()
