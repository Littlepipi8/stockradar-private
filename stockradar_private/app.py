
import hmac
import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from scanner import fetch, OUT


st.set_page_config(
    page_title='StockRadar',
    page_icon='📉',
    layout='wide'
)

st.title('StockRadar · Private Daily Scanner')

# Require a password before displaying scan results.
try:
    password = st.secrets['APP_PASSWORD']
except Exception:
    password = None

if not password:
    st.error(
        'APP_PASSWORD is missing. Configure Streamlit secrets '
        'before using the dashboard.'
    )
    st.stop()

if not st.session_state.get('authenticated', False):
    entered = st.text_input('Dashboard password', type='password')

    if st.button('Sign in'):
        if hmac.compare_digest(entered, str(password)):
            st.session_state['authenticated'] = True
            st.rerun()
        else:
            st.error('Incorrect password')

    st.stop()

if st.sidebar.button('Sign out'):
    st.session_state['authenticated'] = False
    st.rerun()


# Load the latest saved scan.
if not OUT.exists():
    st.info(
        'No scan yet. Run `python scanner.py` locally '
        'or trigger the scheduled GitHub Action.'
    )
    st.stop()

data = json.loads(OUT.read_text(encoding='utf-8'))
rows = data['results']

st.caption(
    f"Latest scan: {data['generated_at']} (UTC) · "
    "Daily end-of-day research signals · Not financial advice"
)

a, b, c, d = st.columns(4)

a.metric('Universe', data['universe_size'])
b.metric('Scanned', data['scanned'])
c.metric(
    'Near support',
    sum(r['signal'] == 'NEAR SUPPORT' for r in rows)
)
d.metric(
    'Breakdowns',
    sum('BREAK' in r['signal'] for r in rows)
)

if data['failed']:
    st.warning(
        f"Incomplete coverage: {len(data['failed'])} symbols failed. "
        "Interpret results cautiously."
    )


# Signal filters.
signal_options = [
    'SUPPORT BREAK',
    'TREND BREAK',
    'RESISTANCE BREAK',
    'NEAR SUPPORT',
    'NEAR RESISTANCE'
]

signals = st.multiselect(
    'Show signals',
    signal_options,
    default=signal_options
)

filtered = [r for r in rows if r['signal'] in signals]

if filtered:
    frame = pd.DataFrame(filtered).rename(
        columns={
            'ticker': 'Ticker',
            'date': 'Date',
            'close': 'Close',
            'resistance': 'Resistance',
            'resistance_distance_pct': 'Resistance distance %',
            'support': 'Support',
            'distance_pct': 'Distance %',
            'trendline': 'Trendline',
            'volume_ratio': 'Volume x20',
            'signal': 'Signal'
        }
    )

    st.dataframe(
        frame,
        hide_index=True,
        use_container_width=True
    )

    st.download_button(
        'Download CSV',
        frame.to_csv(index=False),
        'stockradar_scan.csv',
        'text/csv'
    )
else:
    st.info('No matching signals in the latest scan.')


# Stock inspection chart.
choices = [r['ticker'] for r in rows]

if choices:
    ticker = st.selectbox(
        'Inspect stock',
        choices,
        index=choices.index('GOOG') if 'GOOG' in choices else 0
    )

    @st.cache_data(ttl=3600)
    def load(symbol):
        return fetch(symbol)

    try:
        history = load(ticker)

        fig = go.Figure(
            data=[
                go.Candlestick(
                    x=history.index,
                    open=history.Open,
                    high=history.High,
                    low=history.Low,
                    close=history.Close,
                    name=ticker
                )
            ]
        )

        row = next(
            r for r in rows if r['ticker'] == ticker
        )

        # Orange support line, if available.
        if row.get('support') is not None:
            fig.add_hline(
                y=row['support'],
                line_dash='dash',
                line_color='orange',
                annotation_text=f"Support {row['support']}"
            )

        # Red resistance line, if available.
        if row.get('resistance') is not None:
            fig.add_hline(
                y=row['resistance'],
                line_dash='dash',
                line_color='red',
                annotation_text=f"Resistance {row['resistance']}"
            )

        fig.update_layout(
            template='plotly_dark',
            height=520,
            xaxis_rangeslider_visible=False
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

        st.caption(
            'Support and resistance lines are algorithmic pivot '
            'references, not manually verified trading zones.'
        )

    except Exception as exc:
        st.warning(
            f'Chart temporarily unavailable: {exc}'
        )
