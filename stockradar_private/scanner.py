close = float(frame['Close'].iloc[-1])
    previous_close = float(frame['Close'].iloc[-2])
    buffer = CONFIRMATION_PCT / 100.0

    # A new break must cross a confirmed weekly level with a 1% buffer.
    broken_supports = [
        level for level in support_levels
        if previous_close >= level * (1 - buffer)
        and close < level * (1 - buffer)
    ]
    broken_resistances = [
        level for level in resistance_levels
        if previous_close <= level * (1 + buffer)
        and close > level * (1 + buffer)
    ]

    breakdown_level = max(broken_supports, default=None)
    breakout_level = min(broken_resistances, default=None)

    # Normal levels bracket the latest close. When a break occurs, display
    # the specific crossed level so the signal and chart agree.
    support = max((x for x in support_levels if x <= close), default=None)
    resistance = min((x for x in resistance_levels if x >= close), default=None)
    if breakdown_level is not None:
        support = breakdown_level
    if breakout_level is not None:
        resistance = breakout_level

    support_distance = ((close / support) - 1) * 100 if support else None
    resistance_distance = ((resistance - close) / resistance) * 100 if resistance else None
    near_support = support_distance is not None and 0 <= support_distance <= proximity
    near_resistance = resistance_distance is not None and 0 <= resistance_distance <= proximity

    # Rising trendline based on the last pair of rising weekly pivot lows.
    trend = None
    trend_break = False
    pivots = pivot_indices(lows, width)
    for j in range(len(pivots) - 1, 0, -1):
        i1, i2 = pivots[j-1], pivots[j]
        if lows[i2] <= lows[i1]:
            continue
        slope = (lows[i2] - lows[i1]) / (i2 - i1)
        # Estimate at current and previous daily close, in fractional weeks.
        weeks_since = (pd.Timestamp(frame.index[-1]) - weekly.index[i2]).days / 7.0
        trend = float(lows[i2] + slope * weeks_since)
        prior_trend = trend - slope / 5.0
        trend_break = previous_close >= prior_trend * (1 - buffer) and close < trend * (1 - buffer)
        break

    volumes = frame['Volume'].to_numpy(dtype=float)
    avg_volume = float(np.nanmean(volumes[-21:-1]))
    volume_ratio = float(volumes[-1] / avg_volume) if avg_volume > 0 else None

    signal = (
        'SUPPORT BREAK' if breakdown_level is not None else
        'TREND BREAK' if trend_break else
        'RESISTANCE BREAK' if breakout_level is not None else
        'NEAR SUPPORT' if near_support else
        'NEAR RESISTANCE' if near_resistance else
        'NONE'
    )

    return {
        'ticker': symbol,
        'date': str(pd.Timestamp(frame.index[-1]).date()),
        'close': round(close, 2),
        'support': round(support, 2) if support is not None else None,
        'resistance': round(resistance, 2) if resistance is not None else None,
        'distance_pct': round(support_distance, 2) if support_distance is not None else None,
        'resistance_distance_pct': round(resistance_distance, 2) if resistance_distance is not None else None,
        'trendline': round(trend, 2) if trend is not None else None,
        'volume_ratio': round(volume_ratio, 2) if volume_ratio is not None else None,
        'signal': signal,
    }


def fetch(symbol):
    df = yf.download(symbol, period='2y', interval='1d', auto_adjust=True,
                     progress=False, threads=False, timeout=25)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def scan(tickers, proximity=2.0, width=WEEKLY_PIVOT_WIDTH, pause=0.15):
    rows, failed = [], []
    for idx, symbol in enumerate(tickers, 1):
        try:
            result = analyze(symbol, fetch(symbol), proximity, width)
            if result is not None:
                rows.append(result)
            else:
                failed.append(symbol)
        except Exception as exc:
            failed.append(symbol)
            print(f'Failed {symbol}: {exc}', flush=True)
        if idx % 25 == 0:
            print(f'Processed {idx}/{len(tickers)}', flush=True)
        time.sleep(pause)
    rank = {'SUPPORT BREAK': 0, 'TREND BREAK': 1, 'RESISTANCE BREAK': 2,
            'NEAR SUPPORT': 3, 'NEAR RESISTANCE': 4, 'NONE': 5}
    rows.sort(key=lambda r: (
        rank[r['signal']],
        abs(r['distance_pct']) if r['distance_pct'] is not None else float('inf')
    ))
    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'universe_size': len(tickers), 'scanned': len(rows), 'failed': failed,
        'proximity_pct': proximity, 'pivot_width': width,
        'confirmation_pct': CONFIRMATION_PCT,
        'level_timeframe': 'weekly', 'results': rows,
    }


def save(payload, path=OUT):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding='utf-8')


def main():
    mode = os.getenv('STOCKRADAR_UNIVERSE', 'sp500').lower()
    tickers = (STARTER if mode == 'starter' else
               constituents() if mode == 'sp500' else
               [s.strip().upper() for s in mode.split(',') if s.strip()])
    payload = scan(tickers, proximity=float(os.getenv('SUPPORT_PROXIMITY', '2')))
    save(payload)
    print(f"Saved {payload['scanned']}/{payload['universe_size']} to {OUT}")
    if payload['scanned'] < max(1, int(len(tickers) * 0.8)):
        raise RuntimeError('Scan incomplete (<80%); alerts suppressed')
    return payload


if __name__ == '__main__':
    main()
