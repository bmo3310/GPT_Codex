from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from pandas_datareader import data as pdr

FRANKFURTER_BASE = "https://api.frankfurter.app"
COINGECKO_BASE = "https://api.coingecko.com/api/v3"


def _get_json(url: str, params: Dict | None = None) -> Dict:
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    return response.json()


@st.cache_data(ttl=300)
def get_latest_fx(base: str, symbols: str) -> Dict:
    data = _get_json(f"{FRANKFURTER_BASE}/latest", {"from": base, "to": symbols})
    rates = data.get("rates", {})
    return {k.upper(): float(v) for k, v in rates.items()}


@st.cache_data(ttl=300)
def get_fx_timeseries(base: str, symbols: str, days: int = 30) -> pd.DataFrame:
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days)
    url = f"{FRANKFURTER_BASE}/{start_date.isoformat()}..{end_date.isoformat()}"
    data = _get_json(url, {"from": base, "to": symbols})

    rates = data.get("rates", {})
    rows = []
    for date_str, rate_data in rates.items():
        row = {"date": pd.to_datetime(date_str)}
        for symbol in symbols.split(","):
            key = symbol.upper()
            if key in rate_data:
                row[key] = float(rate_data[key])
        rows.append(row)

    df = pd.DataFrame(rows).sort_values("date")
    return df


@st.cache_data(ttl=300)
def get_btc_usd_current() -> float:
    data = _get_json(
        f"{COINGECKO_BASE}/simple/price",
        params={"ids": "bitcoin", "vs_currencies": "usd"},
    )
    return float(data["bitcoin"]["usd"])


@st.cache_data(ttl=300)
def get_btc_usd_history(days: int = 30) -> pd.DataFrame:
    data = _get_json(
        f"{COINGECKO_BASE}/coins/bitcoin/market_chart",
        params={"vs_currency": "usd", "days": str(days), "interval": "daily"},
    )
    rows = [
        {"date": pd.to_datetime(item[0], unit="ms"), "BTCUSD": float(item[1])}
        for item in data["prices"]
    ]
    return pd.DataFrame(rows)


@st.cache_data(ttl=300)
def get_dxy_current_and_history(days: int = 30) -> tuple[float, pd.DataFrame]:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days + 5)
    dxy = pdr.DataReader("^DXY", "stooq", start, end).sort_index()
    if dxy.empty:
        raise ValueError("無法取得 DXY 資料。")
    history = dxy.tail(days).reset_index()[["Date", "Close"]]
    history.columns = ["date", "DXY"]
    current = float(history["DXY"].iloc[-1])
    return current, history


def plot_line(df: pd.DataFrame, x_col: str, y_col: str, title: str):
    fig = px.line(df, x=x_col, y=y_col, title=title)
    fig.update_layout(margin=dict(l=20, r=20, t=50, b=20), height=320)
    st.plotly_chart(fig, use_container_width=True)


st.set_page_config(page_title="即時匯率工具", layout="wide")
st.title("即時匯率 + 匯率差異比較工具")
st.caption("資料每 5 分鐘快取更新一次。")

st.header("First Block：各種匯率即時顯示")

try:
    fx_latest = get_latest_fx(base="USD", symbols="TWD,JPY")
    fx_history = get_fx_timeseries(base="USD", symbols="TWD,JPY", days=30)
    btc_current = get_btc_usd_current()
    btc_history = get_btc_usd_history(days=30)
    dxy_current, dxy_history = get_dxy_current_and_history(days=30)

    fx_history["USDTWD"] = fx_history["TWD"]
    fx_history["JPYTWD"] = fx_history["TWD"] / fx_history["JPY"]

    col1, col2 = st.columns(2)
    with col1:
        st.metric("美元指數 DXY", f"{dxy_current:,.2f}")
        plot_line(dxy_history, "date", "DXY", "DXY 近 30 天走勢")
    with col2:
        usdtwd_now = fx_latest["TWD"]
        st.metric("美元 / 台幣 (USD/TWD)", f"{usdtwd_now:,.4f}")
        plot_line(fx_history, "date", "USDTWD", "USD/TWD 近 30 天走勢")

    col3, col4 = st.columns(2)
    with col3:
        jpytwd_now = fx_latest["TWD"] / fx_latest["JPY"]
        st.metric("日圓 / 台幣 (JPY/TWD)", f"{jpytwd_now:,.6f}")
        plot_line(fx_history, "date", "JPYTWD", "JPY/TWD 近 30 天走勢")
    with col4:
        st.metric("比特幣 / 美元 (BTC/USD)", f"{btc_current:,.2f}")
        plot_line(btc_history, "date", "BTCUSD", "BTC/USD 近 30 天走勢")
except Exception as error:
    st.error(f"讀取即時資料失敗：{error}")


st.header("Second Block：兩個匯率下可換得目標幣別比較")

currencies = ["TWD", "USD", "JPY", "BTC"]
left_col, right_col = st.columns(2)
with left_col:
    from_currency = st.selectbox("選擇一（來源幣別）", currencies, index=0)
with right_col:
    to_currency = st.selectbox("選擇二（目標幣別）", currencies, index=1)

amount = st.number_input("輸入來源金額", min_value=0.0, value=10000.0, step=100.0)

if from_currency == to_currency:
    st.warning("請選擇不同幣別進行換算。")
else:
    try:
        symbols = ",".join(sorted(set([from_currency, to_currency]) - {"USD", "BTC"}))
        usd_rates = get_latest_fx(base="USD", symbols=symbols) if symbols else {}
        btc_usd = get_btc_usd_current()

        def from_currency_to_usd(value: float, ccy: str) -> float:
            if ccy == "USD":
                return value
            if ccy == "BTC":
                return value * btc_usd
            return value / usd_rates[ccy]

        def from_usd_to_currency(value: float, ccy: str) -> float:
            if ccy == "USD":
                return value
            if ccy == "BTC":
                return value / btc_usd
            return value * usd_rates[ccy]

        usd_value = from_currency_to_usd(amount, from_currency)
        converted_now = from_usd_to_currency(usd_value, to_currency)
        current_rate = converted_now / amount if amount > 0 else 0.0

        min_rate = max(current_rate * 0.5, 0.00000001)
        max_rate = max(current_rate * 1.5, min_rate + 0.00000001)
        custom_rate = st.slider(
            "滑動調整目標匯率",
            min_value=float(min_rate),
            max_value=float(max_rate),
            value=float(current_rate),
            step=float(current_rate * 0.001 if current_rate > 1 else max(current_rate * 0.01, 0.00000001)),
            format="%.8f",
        )

        converted_custom = amount * custom_rate
        diff = converted_custom - converted_now

        c1, c2, c3 = st.columns(3)
        c1.metric("當前匯率", f"1 {from_currency} = {current_rate:,.8f} {to_currency}")
        c2.metric("當前匯率可換得", f"{converted_now:,.8f} {to_currency}")
        c3.metric("自訂匯率可換得", f"{converted_custom:,.8f} {to_currency}")
        st.info(f"兩種匯率可換得目標幣別差額：**{diff:,.8f} {to_currency}**")
    except Exception as error:
        st.error(f"換匯計算失敗：{error}")
