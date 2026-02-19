import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# --- 頁面配置 ---
st.set_page_config(page_title="實時股票趨勢與反轉監控", layout="wide")
st.title("📊 實時股票趨勢分析與反轉警告")

# --- 側邊欄參數 ---
symbol = st.sidebar.text_input("輸入股票代碼 (例如: AAPL, TSLA, 2330.TW)", "AAPL")
interval = st.sidebar.selectbox("實時頻率", ("1m", "2m", "5m", "15m"), index=0)
ema_fast = st.sidebar.slider("快速 EMA 週期", 5, 20, 9)
ema_slow = st.sidebar.slider("慢速 EMA 週期", 21, 50, 21)

def fetch_data(ticker, interval):
    data = yf.download(ticker, period="1d", interval=interval, progress=False)
    # 如果是多級索引（yfinance 新版常見），只保留第一層指標名稱（Open, Close...）
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    return data

def analyze_trend(df):
    if len(df) < ema_slow:
        return df, "計算中...", "等待數據", None, False
    
    # 計算指標
    df['EMA_Fast'] = df['Close'].ewm(span=ema_fast, adjust=False).mean()
    df['EMA_Slow'] = df['Close'].ewm(span=ema_slow, adjust=False).mean()
    df['Vol_MA'] = df['Volume'].rolling(window=10).mean()
    
    # 獲取最後兩列，並確保它們是數值
    last_row = df.iloc[-1]
    prev_row = df.iloc[-2]
    
    # 使用 float() 確保比較的是數值而非 Series
    curr_fast = float(last_row['EMA_Fast'])
    curr_slow = float(last_row['EMA_Slow'])
    prev_fast = float(prev_row['EMA_Fast'])
    prev_slow = float(prev_row['EMA_Slow'])
    curr_vol = float(last_row['Volume'])
    avg_vol = float(last_row['Vol_MA'])
    
    # 趨勢判斷
    is_bullish = curr_fast > curr_slow
    vol_spike = curr_vol > (avg_vol * 1.5)
    
    signal = "穩定"
    alert = None
    
    # 偵測交叉 (現在比較的是 float，不會再有模糊問題)
    if prev_fast <= prev_slow and curr_fast > curr_slow:
        signal = "反轉向上"
        alert = "⚠️ 趨勢反轉：偵測到黃金交叉 (看漲)"
    elif prev_fast >= prev_slow and curr_fast < curr_slow:
        signal = "反轉向下"
        alert = "⚠️ 趨勢反轉：偵測到死亡交叉 (看跌)"
    
    trend = "看漲 (Uptrend)" if is_bullish else "看跌 (Downtrend)"
    return df, trend, signal, alert, vol_spike

# --- 主體循環 ---
placeholder = st.empty()

while True:
    with placeholder.container():
        df = fetch_data(symbol, interval)
        if not df.empty:
            df, trend, signal, alert, vol_spike = analyze_trend(df)
            
            # 第一行：指標看板
            col1, col2, col3, col4 = st.columns(4)
            current_p = df['Close'].iloc[-1]
            change = current_p - df['Close'].iloc[-2]
            
            col1.metric("當前股價", f"{current_p:.2f}", f"{change:.2f}")
            col2.metric("當前趨勢", trend)
            col3.metric("信號狀態", signal)
            col4.metric("成交量異常", "是" if vol_spike else "否")

            # 警告通知
            if alert:
                st.error(alert)
            if vol_spike:
                st.warning("⚡ 注意：成交量異常放大，可能預示價格劇烈波動！")

            # 圖表繪製
            fig = go.Figure()
            # K線圖
            fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], 
                                        low=df['Low'], close=df['Close'], name="K線"))
            # EMA 線
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA_Fast'], name=f'EMA {ema_fast}', line=dict(color='orange', width=1)))
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA_Slow'], name=f'EMA {ema_slow}', line=dict(color='blue', width=1)))
            
            fig.update_layout(title=f"{symbol} 實時走勢 ({interval})", xaxis_rangeslider_visible=False, height=600)
            st.plotly_chart(fig, use_container_width=True)
            
            # 顯示最近數據表
            st.write("最近交易數據", df.tail(5))
        
        else:
            st.warning("無法獲取數據，請檢查股票代碼。")
        
        # 每分鐘刷新一次 (配合 1m 間隔)
        time.sleep(60)
