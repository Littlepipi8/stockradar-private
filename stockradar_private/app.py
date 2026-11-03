
import hmac
import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from scanner import fetch, OUT


st.set_page_config(
    page_title="StockRadar",
    page_icon="📉",
    layout="wide"
)

st.title("StockRadar · Private Daily Scanner")


# Password protection
try:
    password = st.secrets["APP_PASSWORD"]
except Exception:
    password = None

if not password:
    st.error(
        "APP_PASSWORD is missing. Configure Streamlit secrets "
        "before using the dashboard."
    )
    st.stop()

if not st.session_state.get("authenticated", False):
    entered = st.text_input(
        "Dashboard password",
        type="password"
    )

    if st.button("Sign in"):
        if hmac.compare_digest(entered, str(password)):
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password")

    st.stop()

if st.sidebar.button("Sign out"):
    st.session_state["authenticated"] = False
    st.rerun()


# Load latest scan
if not OUT.exists():
    st.info(
        "No scan yet. Run python scanner.py or trigger "
        "the scheduled GitHub Action."
    )
    st.stop()

data = json.loads(OUT.read_text(encoding="utf-8"))
rows = data["results"]

st.caption(
    f"Latest scan: {data['generated_at']} (UTC) · "
    "Daily end-of-day research signals · Not financial advice"
)


# Dashboard metrics
a, b, c, d = st.columns(4)

a.metric("Universe", data["universe_size"])
b.metric("Scanned", data["scanned"])
c.metric(
    "Near support",
    sum(r["signal"] == "NEAR SUPPORT" for r in rows)
)
d.metric(
    "Breakdowns",
    sum("BREAK" in r["signal"] for r in rows)
)

if data["failed"]:
    st.warning(
        f"Incomplete coverage: {len(data['failed'])} "
        "symbols failed. Interpret results cautiously."
    )


# Signal filters
signal_options = [
    "SUPPORT BREAK",
    "TREND BREAK",
    "RESISTANCE BREAK",
    "NEAR SUPPORT",
    "NEAR RESISTANCE"
]

signals = st.multiselect(
    "Show signals",
    signal_options,
    default=signal_options
)

filtered = [
    r for r in rows
    if r["signal"] in signals
]

if filtered:
    frame = pd.DataFrame(filtered).rename(
        columns={
            "ticker": "Ticker",
            "date": "Date",
            "close": "Close",
            "resistance": "Resistance",
            "resistance_distance_pct": "Resistance distance %",
            "support": "Support",
            "distance_pct": "Distance %",
            "trendline": "Trendline",
            "volume_ratio": "Volume x20",
            "signal": "Signal"
        }
    )

    st.dataframe(
        frame,
        hide_index=True,
        use_container_width=True
    )

    st.download_button(
        "Download CSV",
        frame.to_csv(index=False),
        "stockradar_scan.csv",
        "text/csv"
    )
else:
    st.info("No matching signals in the latest scan.")


# Stock chart
choices = [r["ticker"] for r in rows]

if choices:
    st.subheader("Stock Chart")

    ticker = st.selectbox(
        "Inspect stock",
        choices,
        index=choices.index("VST") if "VST" in choices else 0
    )

    timeframe = st.selectbox(
        "Chart timeframe",
        ["3 Months", "6 Months", "1 Year", "2 Years"],
        index=3
    )

    @st.cache_data(ttl=3600)
    def load(symbol):
        return fetch(symbol)

    try:
        history = load(ticker)

        # Change the visible chart timeframe.
        periods = {
            "3 Months": 3,
            "6 Months": 6,
            "1 Year": 12,
            "2 Years": 24
        }

        months = periods[timeframe]

        cutoff = (
            history.index.max()
            - pd.DateOffset(months=months)
        )

        chart_history = history.loc[
            history.index >= cutoff
        ].copy()

        if chart_history.empty:
            st.warning(
                "No price history available for this timeframe."
            )
            st.stop()

        fig = go.Figure(
            data=[
                go.Candlestick(
                    x=chart_history.index,
                    open=chart_history["Open"],
                    high=chart_history["High"],
                    low=chart_history["Low"],
                    close=chart_history["Close"],
                    name=ticker
                )
            ]
        )

        row = next(
            r for r in rows
            if r["ticker"] == ticker
        )

        # Support line
        if row.get("support") is not None:
            fig.add_hline(
                y=row["support"],
                line_dash="dash",
                line_color="orange",
                annotation_text=f"Support ${row['support']}"
            )

        # Resistance line
        if row.get("resistance") is not None:
            fig.add_hline(
                y=row["resistance"],
                line_dash="dash",
                line_color="red",
                annotation_text=f"Resistance ${row['resistance']}"
            )

        fig.update_layout(
            template="plotly_dark",
            height=600,
            xaxis_rangeslider_visible=False,
            xaxis_title="Date",
            yaxis_title="Price (USD)",
            title=f"{ticker} · {timeframe}",
            margin=dict(
                l=20,
                r=20,
                t=60,
                b=20
            )
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

        st.caption(
            "Support and resistance levels come from the "
            "latest scanner results. Chart timeframe changes "
            "the visible history, not the calculated levels."
        )

        # Show detailed levels
        st.subheader("Technical Levels")

        col1, col2, col3 = st.columns(3)

        col1.metric(
            "Latest Close",
            f"${row['close']:,.2f}"
        )

        col2.metric(
            "Support",
            (
                f"${row['support']:,.2f}"
                if row.get("support") is not None
                else "N/A"
            )
        )

        col3.metric(
            "Resistance",
            (
                f"${row['resistance']:,.2f}"
                if row.get("resistance") is not None
                else "N/A"
            )
        )

        st.write(
            f"**Current signal:** {row['signal']}"
        )

    except Exception as exc:
        st.warning(
            f"Chart temporarily unavailable: {exc}"
        )

