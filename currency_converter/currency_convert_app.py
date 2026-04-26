from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable

import pandas as pd
import plotly.express as px
import streamlit as st
import yfinance as yf


# =========================
# Yahoo Finance Tickers
# =========================

YAHOO_TICKERS = {
    "USDTWD": ["TWD=X", "USDTWD=X"],
    "USDJPY": ["JPY=X", "USDJPY=X"],
    "JPYTWD": ["JPYTWD=X"],
    "BTCUSD": ["BTC-USD"],
    "DXY": ["DX-Y.NYB"],
}


# =========================
# 基礎工具函式
# =========================

def _normalize_yfinance_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    return df.reset_index()


def _pick_price_column(df: pd.DataFrame) -> str:
    if "Close" in df.columns:
        return "Close"

    if "Adj Close" in df.columns:
        return "Adj Close"

    raise ValueError("資料中找不到 Close 或 Adj Close 欄位。")


@st.cache_data(ttl=300)
def get_yahoo_history(
    tickers: Iterable[str],
    period: str = "1mo",
    interval: str = "1d",
) -> pd.DataFrame:
    last_error = None

    for ticker in tickers:
        try:
            raw = yf.download(
                ticker,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=False,
                threads=False,
            )

            df = _normalize_yfinance_df(raw)

            if df.empty:
                continue

            price_col = _pick_price_column(df)

            if "Date" in df.columns:
                date_col = "Date"
            elif "Datetime" in df.columns:
                date_col = "Datetime"
            else:
                date_col = df.columns[0]

            result = df[[date_col, price_col]].copy()
            result.columns = ["date", "value"]
            result["date"] = pd.to_datetime(result["date"], errors="coerce")
            result["value"] = pd.to_numeric(result["value"], errors="coerce")
            result = result.dropna(subset=["date", "value"]).sort_values("date")

            if not result.empty:
                result["ticker"] = ticker
                return result

        except Exception as error:
            last_error = error

    if last_error:
        raise ValueError(f"Yahoo Finance 擷取失敗：{last_error}")

    raise ValueError(f"Yahoo Finance 無法取得資料：{list(tickers)}")


@st.cache_data(ttl=300)
def get_core_market_data(days: int = 30) -> Dict[str, object]:
    period = "3mo" if days > 60 else "1mo"

    usdtwd_history = get_yahoo_history(YAHOO_TICKERS["USDTWD"], period=period)
    usdjpy_history = get_yahoo_history(YAHOO_TICKERS["USDJPY"], period=period)
    btcusd_history = get_yahoo_history(YAHOO_TICKERS["BTCUSD"], period=period)

    try:
        jpytwd_history = get_yahoo_history(YAHOO_TICKERS["JPYTWD"], period=period)
    except Exception:
        merged = pd.merge(
            usdtwd_history[["date", "value"]],
            usdjpy_history[["date", "value"]],
            on="date",
            how="inner",
            suffixes=("_USDTWD", "_USDJPY"),
        )

        merged["value"] = merged["value_USDTWD"] / merged["value_USDJPY"]
        jpytwd_history = merged[["date", "value"]].copy()
        jpytwd_history["ticker"] = "computed: USDTWD / USDJPY"

    try:
        dxy_history = get_yahoo_history(YAHOO_TICKERS["DXY"], period=period)
    except Exception:
        dxy_history = pd.DataFrame(columns=["date", "value", "ticker"])

    usdtwd_history = usdtwd_history.tail(days)
    usdjpy_history = usdjpy_history.tail(days)
    jpytwd_history = jpytwd_history.tail(days)
    btcusd_history = btcusd_history.tail(days)
    dxy_history = dxy_history.tail(days)

    return {
        "USDTWD": {
            "current": float(usdtwd_history["value"].iloc[-1]),
            "history": usdtwd_history,
        },
        "USDJPY": {
            "current": float(usdjpy_history["value"].iloc[-1]),
            "history": usdjpy_history,
        },
        "JPYTWD": {
            "current": float(jpytwd_history["value"].iloc[-1]),
            "history": jpytwd_history,
        },
        "BTCUSD": {
            "current": float(btcusd_history["value"].iloc[-1]),
            "history": btcusd_history,
        },
        "DXY": {
            "current": (
                float(dxy_history["value"].iloc[-1])
                if not dxy_history.empty
                else None
            ),
            "history": dxy_history,
        },
    }


def plot_line(
    df: pd.DataFrame,
    title: str,
    y_label: str,
) -> None:
    if df.empty or "date" not in df.columns or "value" not in df.columns:
        st.warning(f"{title}：沒有可顯示的資料。")
        return

    fig = px.line(
        df,
        x="date",
        y="value",
        title=title,
        labels={
            "date": "日期",
            "value": y_label,
        },
    )

    fig.update_layout(
        margin=dict(l=20, r=20, t=50, b=20),
        height=360,
    )

    st.plotly_chart(fig, use_container_width=True)


# =========================
# 幣別換算邏輯
# =========================

def build_usd_based_rates(market_data: Dict[str, object]) -> Dict[str, float]:
    """
    建立「1 USD 可以換多少該幣別」的表。

    USD: 1
    TWD: USD/TWD
    JPY: USD/JPY
    BTC: 1 / BTCUSD
    """
    usdtwd = float(market_data["USDTWD"]["current"])
    usdjpy = float(market_data["USDJPY"]["current"])
    btcusd = float(market_data["BTCUSD"]["current"])

    return {
        "USD": 1.0,
        "TWD": usdtwd,
        "JPY": usdjpy,
        "BTC": 1.0 / btcusd,
    }


def convert_currency(
    amount: float,
    from_currency: str,
    to_currency: str,
    usd_based_rates: Dict[str, float],
) -> float:
    if from_currency == to_currency:
        return amount

    usd_value = amount / usd_based_rates[from_currency]
    target_value = usd_value * usd_based_rates[to_currency]

    return target_value


def format_number(value: float, currency: str | None = None) -> str:
    if currency == "BTC":
        return f"{value:,.8f}"

    if abs(value) >= 1000:
        return f"{value:,.2f}"

    if abs(value) >= 1:
        return f"{value:,.4f}"

    return f"{value:,.8f}"


def swap_currencies() -> None:
    st.session_state.from_currency, st.session_state.to_currency = (
        st.session_state.to_currency,
        st.session_state.from_currency,
    )


# =========================
# Streamlit App
# =========================

st.set_page_config(
    page_title="即時匯率工具",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }

    div[data-testid="stMetric"] {
        background-color: rgba(250, 250, 250, 0.06);
        border: 1px solid rgba(128, 128, 128, 0.18);
        padding: 1rem;
        border-radius: 1rem;
    }

    .small-caption {
        font-size: 0.9rem;
        color: gray;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("即時匯率 + 匯率差異比較工具")
st.caption("資料來源：Yahoo Finance / yfinance。資料每 5 分鐘快取更新一次。")


# =========================
# Sidebar
# =========================

with st.sidebar:
    st.header("設定")

    days = st.slider(
        "歷史走勢天數",
        min_value=7,
        max_value=90,
        value=30,
        step=1,
    )

    if st.button("清除快取並重新擷取"):
        st.cache_data.clear()
        st.rerun()

    st.caption(f"目前時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


# =========================
# 讀取市場資料
# =========================

try:
    market_data = get_core_market_data(days=days)

except Exception as error:
    st.error(f"讀取即時資料失敗：{error}")
    st.stop()


# =========================
# First Block：即時匯率卡片
# =========================

st.header("主要匯率總覽")

usdtwd_current = market_data["USDTWD"]["current"]
jpytwd_current = market_data["JPYTWD"]["current"]
btcusd_current = market_data["BTCUSD"]["current"]
dxy_current = market_data["DXY"]["current"]

card1, card2, card3, card4 = st.columns(4)

card1.metric(
    "USD/TWD",
    f"{usdtwd_current:,.4f}",
    help="1 美元可換多少台幣",
)

card2.metric(
    "JPY/TWD",
    f"{jpytwd_current:,.6f}",
    help="1 日圓可換多少台幣",
)

card3.metric(
    "BTC/USD",
    f"{btcusd_current:,.2f}",
    help="1 BTC 約等於多少美元",
)

if dxy_current is None:
    card4.metric("DXY", "N/A", help="目前無法取得 DXY 資料")
else:
    card4.metric(
        "DXY",
        f"{dxy_current:,.2f}",
        help="美元指數",
    )


# =========================
# 歷史圖表 Tabs
# =========================

st.subheader("歷史走勢")

tab1, tab2, tab3, tab4 = st.tabs(
    ["USD/TWD", "JPY/TWD", "BTC/USD", "DXY"]
)

with tab1:
    plot_line(
        market_data["USDTWD"]["history"],
        title=f"USD/TWD 近 {days} 天走勢",
        y_label="USD/TWD",
    )

with tab2:
    plot_line(
        market_data["JPYTWD"]["history"],
        title=f"JPY/TWD 近 {days} 天走勢",
        y_label="JPY/TWD",
    )

with tab3:
    plot_line(
        market_data["BTCUSD"]["history"],
        title=f"BTC/USD 近 {days} 天走勢",
        y_label="BTC/USD",
    )

with tab4:
    dxy_history = market_data["DXY"]["history"]

    if dxy_current is None or dxy_history.empty:
        st.warning("目前無法取得 DXY 資料。")
    else:
        plot_line(
            dxy_history,
            title=f"DXY 近 {days} 天走勢",
            y_label="DXY",
        )


# =========================
# Second Block：換匯計算器
# =========================

st.header("換匯計算器")

if "from_currency" not in st.session_state:
    st.session_state.from_currency = "TWD"

if "to_currency" not in st.session_state:
    st.session_state.to_currency = "USD"

if "amount" not in st.session_state:
    st.session_state.amount = 10000.0

currencies = ["TWD", "USD", "JPY", "BTC"]

with st.container(border=True):
    st.subheader("來源幣別 ⇄ 目標幣別")

    col_from, col_swap, col_to = st.columns([5, 1, 5])

    with col_from:
        st.selectbox(
            "來源幣別",
            currencies,
            key="from_currency",
        )

    with col_swap:
        st.markdown("<br>", unsafe_allow_html=True)
        st.button(
            "⇄",
            on_click=swap_currencies,
            help="交換來源幣別與目標幣別",
            use_container_width=True,
        )

    with col_to:
        st.selectbox(
            "目標幣別",
            currencies,
            key="to_currency",
        )

    amount = st.number_input(
        "輸入來源金額",
        min_value=0.0,
        step=100.0,
        key="amount",
    )

    from_currency = st.session_state.from_currency
    to_currency = st.session_state.to_currency

    if from_currency == to_currency:
        st.warning("請選擇不同幣別進行換算。")

    else:
        try:
            usd_based_rates = build_usd_based_rates(market_data)

            converted_now = convert_currency(
                amount=amount,
                from_currency=from_currency,
                to_currency=to_currency,
                usd_based_rates=usd_based_rates,
            )

            current_rate = converted_now / amount if amount > 0 else 0.0
            inverse_rate = 1 / current_rate if current_rate > 0 else 0.0

            st.divider()

            rate_col1, rate_col2 = st.columns([3, 2])

            with rate_col1:
                show_inverse_rate = st.toggle(
                    "反向顯示匯率",
                    value=False,
                    help=(
                        "例如 TWD → USD 時，開啟後會顯示 1 USD = xx TWD，"
                        "但換算邏輯仍然維持 TWD → USD。"
                    ),
                )

            with rate_col2:
                st.caption("這個選項只影響匯率顯示，不改變實際換算方向。")

            if show_inverse_rate:
                rate_label = (
                    f"1 {to_currency} = "
                    f"{format_number(inverse_rate, from_currency)} {from_currency}"
                )
                display_rate_value = inverse_rate
                display_rate_from = to_currency
                display_rate_to = from_currency
            else:
                rate_label = (
                    f"1 {from_currency} = "
                    f"{format_number(current_rate, to_currency)} {to_currency}"
                )
                display_rate_value = current_rate
                display_rate_from = from_currency
                display_rate_to = to_currency

            min_rate = max(display_rate_value * 0.5, 0.00000001)
            max_rate = max(display_rate_value * 1.5, min_rate + 0.00000001)

            slider_step = (
                display_rate_value * 0.001
                if display_rate_value > 1
                else max(display_rate_value * 0.01, 0.00000001)
            )

            custom_display_rate = st.slider(
                f"自訂匯率：1 {display_rate_from} = ? {display_rate_to}",
                min_value=float(min_rate),
                max_value=float(max_rate),
                value=float(display_rate_value),
                step=float(slider_step),
                format="%.8f",
            )

            if show_inverse_rate:
                custom_actual_rate = (
                    1 / custom_display_rate
                    if custom_display_rate > 0
                    else 0.0
                )
            else:
                custom_actual_rate = custom_display_rate

            converted_custom = amount * custom_actual_rate
            diff = converted_custom - converted_now

            result_col1, result_col2, result_col3 = st.columns(3)

            result_col1.metric(
                "目前匯率",
                rate_label,
            )

            result_col2.metric(
                "目前可換得",
                f"{format_number(converted_now, to_currency)} {to_currency}",
            )

            result_col3.metric(
                "自訂匯率可換得",
                f"{format_number(converted_custom, to_currency)} {to_currency}",
            )

            st.info(
                f"兩種匯率可換得目標幣別差額："
                f"**{format_number(diff, to_currency)} {to_currency}**"
            )

        except Exception as error:
            st.error(f"換匯計算失敗：{error}")


# =========================
# Footer
# =========================

st.caption(
    "提醒：Yahoo Finance 匯率資料可能有延遲，實際換匯請以銀行、券商或交易所報價為準。"
)