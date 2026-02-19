import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
import requests

# --- 從 Secrets 讀取 Telegram 設定 ---
try:
    BOT_TOKEN = st.secrets["telegram"]["bot_token"]
    CHAT_ID = st.secrets["telegram"]["chat_id"]
except KeyError:
    st.error("請在 .streamlit/secrets.toml 中設定 Telegram 配置")
    st.stop()

def send_telegram_msg(message):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload, timeout=5)
    except: pass

# --- 頁面配置 ---
st.set_page_config(page_title="頂級多指標監控系統", layout="wide")
st.title("🛡️ 專業全指標監控 (BB + MACD + EMA)")

if 'last_alerts' not in st.session_state:
    st.session_state.last_alerts = {}

# --- 核心運算函數 ---
def fetch_data(ticker, interval):
    try:
        # MACD 和 BB 需要較多歷史數據，抓取 5 天以確保計算穩定
        data = yf.download(ticker, period="5d", interval=interval, progress=False)
        if data.empty: return None
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        return data
    except: return None

def analyze_strategy(df, sym):
    if df is None or len(df) < 35: return None, None
    
    # 1. 布林通道 (20, 2)
    df['BB_Mid'] = df['Close'].rolling(window=20).mean()
    std = df['Close'].rolling(window=20).std()
    df['BB_Upper'] = df['BB_Mid'] + (std * 2)
    df['BB_Lower'] = df['BB_Mid'] - (std * 2)

    # 2. MACD (12, 26, 9)
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['Signal_Line']

    # 3. EMA
    df['EMA_F'] = df['Close'].ewm(span=9, adjust=False).mean()
    df['EMA_S'] = df['Close'].ewm(span=21, adjust=False).mean()

    # 數據提取
    last = df.iloc[-1]
    prev = df.iloc[-2]
    curr_p = float(last['Close'])
    
    # 策略判斷邏輯
    msg = "趨勢穩定"
    alert_level = "success"
    has_trigger = False

    # 強烈多頭訊號：EMA金叉 + MACD紅柱增加 + 股價破中軌
    if prev['EMA_F'] <= prev['EMA_S'] and last['EMA_F'] > last['EMA_S']:
        if last['MACD_Hist'] > 0:
            msg = "🔥 強烈買入 (EMA+MACD)"; alert_level = "error"; has_trigger = True
        else:
            msg = "🚀 黃金交叉"; alert_level = "warning"; has_trigger = True
            
    elif prev['EMA_F'] >= prev['EMA_S'] and last['EMA_F'] < last['EMA_S']:
        msg = "💀 死亡交叉"; alert_level = "error"; has_trigger = True

    # 布林通道突破
    if curr_p > last['BB_Upper']:
        msg = "🔔 觸碰布林上軌 (超買)"; alert_level = "warning"
    elif curr_p < last['BB_Lower']:
        msg = "📉 觸碰布林下軌 (超賣)"; alert_level = "warning"

    # Telegram 通知
    alert_key = f"{sym}_{msg}"
    if has_trigger and st.session_state.last_alerts.get(sym) != alert_key:
        tg_text = (f"🎯 *策略達成: {sym}*\n"
                   f"【訊號】: {msg}\n"
                   f"【價格】: {curr_p:.2f}\n"
                   f"【MACD】: {'📈 多方佔優' if last['MACD_Hist'] > 0 else '📉 空方佔優'}\n"
                   f"【量能比】: {float(last['Volume']/df['Volume'].tail(10).mean()):.1f}x")
        send_telegram_msg(tg_text)
        st.session_state.last_alerts[sym] = alert_key

    info = {
        "price": curr_p,
        "bb_pos": "軌道內" if last['BB_Lower'] < curr_p < last['BB_Upper'] else "軌道外",
        "macd_status": "多頭轉強" if last['MACD_Hist'] > 0 else "空頭轉強",
        "trend": "多頭 (Bullish)" if last['EMA_F'] > last['EMA_S'] else "空頭 (Bearish)",
        "msg": msg, "alert_level": alert_level
    }
    return df, info

# --- UI 介面 ---
st.sidebar.header("監控列表")
symbols = [s.strip().upper() for s in st.sidebar.text_input("輸入代碼", "AAPL, NVDA, TSLA, BTC-USD").split(",")]
interval = st.sidebar.selectbox("頻率", ("1m", "2m", "5m"), index=0)

placeholder = st.empty()

while True:
    with placeholder.container():
        st.subheader("🔔 策略監控摘要 (EMA + MACD + BB)")
        cols = st.columns(len(symbols))
        stock_cache = {}

        for idx, sym in enumerate(symbols):
            df_raw = fetch_data(sym, interval)
            df, info = analyze_strategy(df_raw, sym)
            stock_cache[sym] = (df, info)
            
            with cols[idx]:
                if info:
                    if info['alert_level'] == "error": st.error(f"**{sym} | {info['msg']}**")
                    elif info['alert_level'] == "warning": st.warning(f"**{sym} | {info['msg']}**")
                    else: st.success(f"**{sym} | 監控中**")
                    st.caption(f"趨勢: {info['trend']}")
                    st.caption(f"MACD: {info['macd_status']}")
                    st.caption(f"布林: {info['bb_pos']}")

        st.divider()
        for sym in symbols:
            df, info = stock_cache[sym]
            if df is not None:
                with st.expander(f"📊 {sym} 深度技術分析 (MACD/BB/Vol)", expanded=True):
                    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                                       row_heights=[0.5, 0.25, 0.25], vertical_spacing=0.03)
                    
                    # Row 1: K線 + 布林通道
                    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="K"), row=1, col=1)
                    fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], line=dict(color='rgba(173, 216, 230, 0.5)'), name="BB_Up"), row=1, col=1)
                    fig.add_trace(go.Scatter(x=df.index, y=df['BB_Lower'], line=dict(color='rgba(173, 216, 230, 0.5)'), fill='tonexty', name="BB_Low"), row=1, col=1)
                    
                    # Row 2: MACD
                    colors = ['red' if x < 0 else 'green' for x in df['MACD_Hist']]
                    fig.add_trace(go.Bar(x=df.index, y=df['MACD_Hist'], name="MACD Hist", marker_color=colors), row=2, col=1)
                    fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], line=dict(color='blue', width=1), name="MACD"), row=2, col=1)
                    fig.add_trace(go.Scatter(x=df.index, y=df['Signal_Line'], line=dict(color='orange', width=1), name="Signal"), row=2, col=1)

                    # Row 3: 成交量
                    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color='gray', name="Vol"), row=3, col=1)
                    
                    fig.update_layout(height=600, xaxis_rangeslider_visible=False, showlegend=False, margin=dict(t=0, b=0))
                    st.plotly_chart(fig, use_container_width=True)

        time.sleep(60)
        st.rerun()
