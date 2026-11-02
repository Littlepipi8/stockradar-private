import hmac
import json
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from scanner import fetch, analyze, OUT

st.set_page_config(page_title='StockRadar', page_icon='📉', layout='wide')
st.title('StockRadar · Private Daily Scanner')

# Require a password: do not accidentally expose a publicly deployed dashboard.
try: password = st.secrets['APP_PASSWORD']
except Exception: password = None
if not password:
    st.error('APP_PASSWORD is missing. Configure Streamlit secrets before using the dashboard.')
    st.stop()
if not st.session_state.get('authenticated', False):
    entered = st.text_input('Dashboard password', type='password')
    if st.button('Sign in'):
        if hmac.compare_digest(entered, str(password)):
            st.session_state['authenticated'] = True
            st.rerun()
        else: st.error('Incorrect password')
    st.stop()
if st.sidebar.button('Sign out'):
    st.session_state['authenticated'] = False
    st.rerun()

if not OUT.exists():
    st.info('No scan yet. Run `python scanner.py` locally or trigger the scheduled GitHub Action.')
    st.stop()
data = json.loads(OUT.read_text())
st.caption(f"Latest scan: {data['generated_at']} (UTC) · Daily end-of-day research signals · Not financial advice")
a,b,c,d = st.columns(4)
rows = data['results']
a.metric('Universe', data['universe_size'])
b.metric('Scanned', data['scanned'])
c.metric('Near support', sum(r['signal']=='NEAR SUPPORT' for r in rows))
d.metric('Breakdowns', sum('BREAK' in r['signal'] for r in rows))
if data['failed']:
    st.warning(f"Incomplete coverage: {len(data['failed'])} symbols failed. Interpret results cautiously.")
signals = st.multiselect('Show signals', ['SUPPORT BREAK','TREND BREAK','NEAR SUPPORT','NONE'],
                         default=['SUPPORT BREAK','TREND BREAK','NEAR SUPPORT'])
filtered = [r for r in rows if r['signal'] in signals]
if filtered:
    frame = pd.DataFrame(filtered).rename(columns={'ticker':'Ticker','date':'Date','close':'Close',
        'support':'Support','distance_pct':'Distance %','trendline':'Trendline',
        'volume_ratio':'Volume x20','signal':'Signal'})
    st.dataframe(frame, hide_index=True, use_container_width=True)
    st.download_button('Download CSV', frame.to_csv(index=False), 'stockradar_scan.csv', 'text/csv')
else: st.info('No matching signals in the latest scan.')
choices = [r['ticker'] for r in rows]
if choices:
    ticker = st.selectbox('Inspect stock', choices, index=choices.index('GOOG') if 'GOOG' in choices else 0)
    @st.cache_data(ttl=3600)
    def load(symbol): return fetch(symbol)
    try:
        history = load(ticker)
        fig = go.Figure(data=[go.Candlestick(x=history.index, open=history.Open, high=history.High,
                                            low=history.Low, close=history.Close, name=ticker)])
        row = next(r for r in rows if r['ticker']==ticker)
        fig.add_hline(y=row['support'], line_dash='dash', line_color='orange',
                      annotation_text=f"Support {row['support']}")
        fig.update_layout(template='plotly_dark', height=520, xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
        st.caption('Horizontal line is an algorithmic pivot reference, not a manually verified support zone.')
    except Exception as exc: st.warning(f'Chart temporarily unavailable: {exc}')
