import yfinance as yf
import pandas as pd
import numpy as np
import mplfinance as mpf
import streamlit as st
from io import BytesIO
from datetime import datetime, timedelta

# 计算指标
def calculate_indicators(df):
    df = df.copy()
    df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]

    df['MA50'] = df['Close'].rolling(50).mean()
    df['MA100'] = df['Close'].rolling(100).mean()
    df['MA200'] = df['Close'].rolling(200).mean()

    df['BB_Mid'] = df['Close'].rolling(20).mean()
    df['BB_Upper'] = df['BB_Mid'] + 2 * df['Close'].rolling(20).std()
    df['BB_Lower'] = df['BB_Mid'] - 2 * df['Close'].rolling(20).std()

    delta = df['Close'].diff(1)
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))

    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']

    df['MF_Multiplier'] = ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / (df['High'] - df['Low'])
    df['MF_Volume'] = df['MF_Multiplier'] * df['Volume']
    df['CMF'] = df['MF_Volume'].rolling(20).sum() / df['Volume'].rolling(20).sum()

    return df

# 生成图表并转为图片流
def create_chart(df, ticker):
    df = df.dropna()
    apds = [
        mpf.make_addplot(df['MA50'], color='#8A2BE2', label='MA50'),
        mpf.make_addplot(df['MA100'], color='#FFB90F', label='MA100'),
        mpf.make_addplot(df['MA200'], color='#2F4F4F', label='MA200'),
        mpf.make_addplot(df['BB_Upper'], color='#00CED1', linestyle='--'),
        mpf.make_addplot(df['BB_Mid'], color='#00CED1'),
        mpf.make_addplot(df['BB_Lower'], color='#00CED1', linestyle='--'),
        mpf.make_addplot(df['RSI'], panel=1, color='#1E90FF'),
        mpf.make_addplot([30]*len(df), panel=1, color='#FF6347', linestyle=':'),
        mpf.make_addplot([70]*len(df), panel=1, color='#FF6347', linestyle=':'),
        mpf.make_addplot(df['MACD'], panel=2, color='#4169E1'),
        mpf.make_addplot(df['MACD_Signal'], panel=2, color='#FF8C00'),
        mpf.make_addplot(df['MACD_Hist'], panel=2, type='bar', color=np.where(df['MACD_Hist']>0,'#32CD32','#DC143C')),
        mpf.make_addplot(df['CMF'], panel=3, color='#8B0000'),
        mpf.make_addplot([0]*len(df), panel=3, color='#808080', linestyle=':'),
    ]
    buf = BytesIO()
    mpf.plot(df, type='candle', volume=True, addplot=apds, title=f"{ticker} 技術圖表",
             figratio=(16,9), panel_ratios=(4,1,1,1), style='yahoo', savefig=buf)
    buf.seek(0)
    return buf

# 分析逻辑
def get_analysis(df):
    latest = df.iloc[-1]
    signals = []
    # MA
    if latest['Close'] < latest['MA50'] and latest['Close'] < latest['MA100'] and latest['Close'] < latest['MA200']:
        signals.append("MA：全均線壓制，強空頭")
    elif latest['Close'] > latest['MA50'] and latest['Close'] > latest['MA100'] and latest['Close'] > latest['MA200']:
        signals.append("MA：站穩全均線，強多頭")
    else:
        signals.append("MA：趨勢中性")
    # 布林带
    signals.append("布林帶：跌破中軌，偏空" if latest['Close'] < latest['BB_Mid'] else "布林帶：中軌上方，偏多")
    # RSI
    if latest['RSI'] < 30:
        signals.append("RSI：超賣區")
    elif latest['RSI'] > 70:
        signals.append("RSI：超買區")
    else:
        signals.append("RSI：中性區")
    # MACD
    signals.append("MACD：死叉/空頭格局" if latest['MACD'] < latest['MACD_Signal'] else "MACD：金叉/多頭格局")
    # CMF
    signals.append("CMF：資金流出" if latest['CMF'] < 0 else "CMF：資金流入")

    bear = sum(1 for s in signals if "空" in s or "流出" in s)
    bull = sum(1 for s in signals if "多" in s or "流入" in s)

    if bear >=3:
        conclusion = "📉 多指標空頭共振，建議觀望"
    elif bull >=3:
        conclusion = "📈 多指標多頭共振，可擇機佈局"
    else:
        conclusion = "➖ 信號雜亂，方向不明，耐心等待"

    return latest, signals, bear, bull, conclusion

# 网页主体
st.set_page_config(page_title="股票多指標分析", layout="wide")
st.title("📊 股票多指標共振分析工具")

ticker = st.text_input("請輸入股票代碼（如 MSFT、V、AAPL）", value="")
days = st.slider("選擇查詢天數", min_value=120, max_value=720, value=365)

if st.button("開始分析") and ticker:
    with st.spinner("正在獲取數據、計算指標..."):
        end = datetime.now()
        start = end - timedelta(days=days)
        df = yf.download(ticker, start=start, end=end)
        if df.empty:
            st.error("❌ 無法獲取數據，請檢查股票代碼！")
        else:
            df = calculate_indicators(df)
            latest, signals, bear, bull, conclusion = get_analysis(df)

            # 基础数据
            st.subheader("基礎行情")
            col1, col2, col3 = st.columns(3)
            col1.metric("最新收市價", f"${latest['Close']:.2f}")
            col2.metric("RSI(14)", f"{latest['RSI']:.2f}")
            col3.metric("CMF(20)", f"{latest['CMF']:.3f}")

            # 信号列表
            st.subheader("指標信號清單")
            for s in signals:
                st.write(f"- {s}")
            st.info(f"空頭信號：{bear} 個 | 多頭信號：{bull} 個")
            st.success(f"綜合結論：{conclusion}")

            # 图表
            st.subheader("技術走勢圖")
            img_buf = create_chart(df, ticker)
            st.image(img_buf)
