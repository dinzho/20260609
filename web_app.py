import yfinance as yf
import pandas as pd
import numpy as np
import mplfinance as mpf
import streamlit as st
from io import BytesIO
from datetime import datetime, timedelta

# 计算技术指标
def calculate_indicators(df):
    df = df.copy()
    df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]

    # 均线
    df['MA50'] = df['Close'].rolling(50).mean()
    df['MA100'] = df['Close'].rolling(100).mean()
    df['MA200'] = df['Close'].rolling(200).mean()

    # 布林带
    df['BB_Mid'] = df['Close'].rolling(20).mean()
    df['BB_Upper'] = df['BB_Mid'] + 2 * df['Close'].rolling(20).std()
    df['BB_Lower'] = df['BB_Mid'] - 2 * df['Close'].rolling(20).std()

    # RSI
    delta = df['Close'].diff(1)
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # MACD
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']

    # CMF
    df['MF_Multiplier'] = ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / (df['High'] - df['Low'])
    df['MF_Volume'] = df['MF_Multiplier'] * df['Volume']
    df['CMF'] = df['MF_Volume'].rolling(20).sum() / df['Volume'].rolling(20).sum()

    # ATR 止盈止损
    df['TR'] = np.maximum(df['High'] - df['Low'],
                          np.maximum(abs(df['High'] - df['Close'].shift(1)),
                                     abs(df['Low'] - df['Close'].shift(1))))
    df['ATR'] = df['TR'].rolling(14).mean()
    return df

# 获取支撑压力位
def get_support_resistance(df):
    df_recent = df.tail(60)
    support = round(df_recent['Low'].min(), 2)
    resistance = round(df_recent['High'].max(), 2)
    return support, resistance

# 判断单只标的多空状态
def get_trend_status(df):
    latest = df.iloc[-1]
    status = ""
    if latest['Close'] > latest['MA50'] and latest['Close'] > latest['MA100']:
        status = "偏多"
    elif latest['Close'] < latest['MA50'] and latest['Close'] < latest['MA100']:
        status = "偏空"
    else:
        status = "中性"
    return status

# 生成K线图表
def create_chart(df, ticker):
    df = df.dropna()
    apds = [
        mpf.make_addplot(df['MA50'], color='#8A2BE2', label='MA50'),
        mpf.make_addplot(df['MA100'], color='#FFB90F', label='MA100'),
        mpf.make_addplot(df['MA200'], color='#2F4F4F', label='MA200'),
        mpf.make_addplot(df['BB_Upper'], color='#00CED1', linestyle='--', label='BB Upper'),
        mpf.make_addplot(df['BB_Mid'], color='#00CED1', label='BB Mid'),
        mpf.make_addplot(df['BB_Lower'], color='#00CED1', linestyle='--', label='BB Lower'),
        mpf.make_addplot(df['RSI'], panel=1, color='#1E90FF', label='RSI(14)'),
        mpf.make_addplot([30]*len(df), panel=1, color='red', linestyle=':'),
        mpf.make_addplot([70]*len(df), panel=1, color='red', linestyle=':'),
        mpf.make_addplot(df['MACD'], panel=2, color='#4169E1', label='MACD'),
        mpf.make_addplot(df['MACD_Signal'], panel=2, color='#FF8C00', label='Signal'),
        mpf.make_addplot(df['MACD_Hist'], panel=2, type='bar', color=np.where(df['MACD_Hist']>0,'#32CD32','#DC143C')),
        mpf.make_addplot(df['CMF'], panel=3, color='#8B0000', label='CMF(20)'),
        mpf.make_addplot([0]*len(df), panel=3, color='gray', linestyle=':'),
    ]
    buf = BytesIO()
    mpf.plot(df, type='candle', volume=True, addplot=apds,
             title=f"{ticker} Technical Chart",
             figratio=(14,8), panel_ratios=(4,1,1.2,1), style='yahoo', savefig=buf)
    buf.seek(0)
    return buf

# 个股综合分析
def get_analysis(df):
    latest = df.iloc[-1]
    signals = []
    # 均线
    if latest['Close'] < latest['MA50'] and latest['Close'] < latest['MA100'] and latest['Close'] < latest['MA200']:
        signals.append("MA：全均线压制 → 强空头")
    elif latest['Close'] > latest['MA50'] and latest['Close'] > latest['MA100'] and latest['Close'] > latest['MA200']:
        signals.append("MA：站稳全均线 → 强多头")
    else:
        signals.append("MA：趋势中性")

    # 布林带
    signals.append("布林带：跌破中轨 → 偏空" if latest['Close'] < latest['BB_Mid'] else "布林带：中轨上方 → 偏多")

    # RSI
    if latest['RSI'] < 30:
        signals.append("RSI：超卖区 → 可能反弹")
    elif latest['RSI'] > 70:
        signals.append("RSI：超买区 → 可能回调")
    else:
        signals.append("RSI：中性区")

    # MACD
    signals.append("MACD：死叉 → 空头格局" if latest['MACD'] < latest['MACD_Signal'] else "MACD：金叉 → 多头格局")

    # CMF
    signals.append("CMF：资金流出" if latest['CMF'] < 0 else "CMF：资金流入")

    # 支撑压力
    support, resistance = get_support_resistance(df)
    # ATR 止盈止损
    atr = latest['ATR']
    stop_loss_long = round(latest['Close'] - atr, 2)
    take_profit_long = round(latest['Close'] + 2*atr, 2)
    stop_loss_short = round(latest['Close'] + atr, 2)
    take_profit_short = round(latest['Close'] - 2*atr, 2)

    bear = sum(1 for s in signals if "空" in s or "流出" in s)
    bull = sum(1 for s in signals if "多" in s or "流入" in s)
    if bear >= 3:
        conclusion = "📉 空头共振 → 建议观望"
    elif bull >= 3:
        conclusion = "📈 多头共振 → 可考虑布局"
    else:
        conclusion = "➖ 信号混杂 → 耐心等待"

    return latest, signals, bear, bull, conclusion, support, resistance, stop_loss_long, take_profit_long, stop_loss_short, take_profit_short

# 网页主程序
st.set_page_config(page_title="大盘共振分析", layout="wide")
st.title("📊 股票多指標 + 美股大盤共振分析工具")
ticker = st.text_input("輸入股票代碼（例：ORCL、MSFT、V、AAPL）")
days = st.slider("統計天數", 120, 720, 365)

if st.button("開始分析") and ticker:
    with st.spinner("正在獲取個股 + 大盤數據，請稍候..."):
        end = datetime.now()
        start = end - timedelta(days=days)

        # 1. 獲取個股數據
        df_stock = yf.download(ticker, start=start, end=end)
        if df_stock.empty:
            st.error("❌ 無法獲取個股數據，請檢查代碼！")
        else:
            df_stock = calculate_indicators(df_stock)
            stock_latest, sigs, bear, bull, stock_conclusion, sup, res, sl_long, tp_long, sl_short, tp_short = get_analysis(df_stock)
            stock_trend = get_trend_status(df_stock)

            # 2. 獲取標普500大盤 (^GSPC)
            df_spx = yf.download("^GSPC", start=start, end=end)
            df_spx = calculate_indicators(df_spx)
            spx_trend = get_trend_status(df_spx)

            # 3. 判斷大盤共振關係
            if stock_trend == spx_trend:
                if stock_trend == "偏多":
                    resonance = "✅ 多頭共振：個股跟隨大盤走強，做多安全性高"
                elif stock_trend == "偏空":
                    resonance = "⚠️ 空頭共振：大盤走弱+個股跟跌，謹慎操作"
                else:
                    resonance = "➡️ 整體中性：大盤與個股方向一致，觀望為主"
            else:
                if stock_trend == "偏多" and spx_trend == "偏空":
                    resonance = "🔥 逆勢強勢：大盤弱、個股獨立走強，強勢標的"
                elif stock_trend == "偏空" and spx_trend == "偏多":
                    resonance = "❌ 頂背離：大盤漲、個股獨立走弱，避險為主"
                else:
                    resonance = "🔄 方向分化：個股與大盤走勢不一致"

            # ========== 頁面展示 ==========
            # 基礎數據
            st.subheader("📌 個股最新數據")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("收盤價", f"${stock_latest['Close']:.2f}")
            c2.metric("RSI", f"{stock_latest['RSI']:.1f}")
            c3.metric("CMF", f"{stock_latest['CMF']:.3f}")
            c4.metric("ATR(14)", f"${stock_latest['ATR']:.2f}")

            # 關鍵價位
            st.subheader("📍 支撐 / 壓力位")
            cs, cr = st.columns(2)
            cs.info(f"近期支撐位：${sup}")
            cr.info(f"近期壓力位：${res}")

            # 大盤共振專區
            st.subheader("🌐 美股大盤（標普500）共振分析")
            st.write(f"個股趨勢：**{stock_trend}** | 大盤趨勢：**{spx_trend}**")
            st.success(resonance)

            # 止盈止損
            st.subheader("🎯 ATR 止盈止損參考")
            if bull >= 3:
                st.success(f"做多止損：${sl_long} ｜ 多目標位：${tp_long}")
            elif bear >= 3:
                st.warning(f"做空止損：${sl_short} ｜ 空目標位：${tp_short}")
            else:
                st.info("趨勢混亂，暫不建議開倉")

            # 指標信號
            st.subheader("📊 各項指標信號")
            for s in sigs:
                st.write(f"- {s}")
            st.info(f"空頭信號：{bear} 個 ｜ 多頭信號：{bull} 個")
            st.success(f"綜合結論：{stock_conclusion}")

            # 技術圖表
            st.subheader("📈 個股技術走勢圖")
            st.image(create_chart(df_stock, ticker))
