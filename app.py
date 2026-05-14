import streamlit as st
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from pyxirr import xirr
import calendar
import matplotlib.font_manager as fm
import subprocess

# --- 1. 介面設定 ---
st.set_page_config(page_title="我的理財管家", layout="centered")
st.title("📈 投資組合即時監控")

# --- 2. 解決中文字體問題 ---
@st.cache_resource
def load_font():
    try:
        # 安裝字體 (如果是部署在 Streamlit Cloud 需此步驟)
        subprocess.run(['apt-get', '-qq', 'update'])
        subprocess.run(['apt-get', '-qq', 'install', '-y', 'fonts-noto-cjk'])
        font_path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
        fm.fontManager.addfont(font_path)
        return fm.FontProperties(fname=font_path).get_name()
    except:
        return None

font_name = load_font()
if font_name:
    plt.rcParams['font.sans-serif'] = [font_name]
plt.rcParams['axes.unicode_minus'] = False

# --- 3. 側邊欄：上傳與設定 ---
st.sidebar.header("設定中心")
uploaded_file = st.sidebar.file_uploader("上傳 trades.csv", type="csv")

# 允許使用者在介面修改入金紀錄 (示範)
st.sidebar.subheader("入金紀錄")
inflow_date_1 = st.sidebar.date_input("入金日期 1", value=pd.to_datetime("2024-01-01"))
inflow_amt_1 = st.sidebar.number_input("金額 1", value=200000)

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    df.columns = df.columns.str.strip()
    df['代號'] = df['代號'].astype(str).str.strip()
    df['買入日期'] = pd.to_datetime(df['買入日期'])
    df['賣出日期'] = pd.to_datetime(df['賣出日期'], errors='coerce')

    # 運算邏輯 (同前次對話)
    start_date = df['買入日期'].min()
    end_date = pd.Timestamp.now().normalize()
    
    # 動態入金字典
    inflow_records = {inflow_date_1.strftime('%Y-%m-%d'): inflow_amt_1}
    inflow_series = pd.Series(inflow_records)
    inflow_series.index = pd.to_datetime(inflow_series.index)

    # --- 核心計算 (省略細節以節省篇幅，邏輯同前) ---
    # (此處應放入之前處理 holdings, cash_flow, yf.download 的代碼)
    # 假設我們已經算出了 unit_nav, total_equity, daily_ret...
    
    # ------------------------------------------
    # 4. 手機版精華：今日關鍵指標 (Metrics)
    # ------------------------------------------
    st.subheader("今日戰報")
    
    # 計算今日損益
    latest_nav = unit_nav.iloc[-1]
    prev_nav = unit_nav.iloc[-2] if len(unit_nav) > 1 else latest_nav
    day_change = (latest_nav / prev_nav - 1) * 100
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("總資產 (AUM)", f"${total_equity.iloc[-1]:,.0f}", f"{day_change:+.2f}%")
    with col2:
        ytd_start = pd.Timestamp(f"{end_date.year}-01-01")
        if ytd_start in unit_nav.index:
            ytd_ret = (unit_nav.iloc[-1] / unit_nav.loc[ytd_start] - 1) * 100
            st.metric("今年以來 (YTD)", f"{ytd_ret:+.2f}%")
            
    # --- 5. 歷史高點與回撤 ---
    ath_val = unit_nav.max()
    mdd = ((unit_nav / unit_nav.cummax()) - 1).min()
    st.write(f"🏆 歷史最高淨值: `{ath_val:.3f}` | ⚠️ 最大回撤: `{mdd:.2%}`")

    # --- 6. 圖表分頁 ---
    tab1, tab2, tab3 = st.tabs(["走勢圖", "月度績效", "每日日曆"])
    
    with tab1:
        fig1, ax1 = plt.subplots()
        ax1.plot(unit_nav.index, unit_nav, color='#d62728')
        # 標註 ATH
        ax1.scatter(unit_nav.idxmax(), ath_val, color='gold', s=100, marker='*')
        st.pyplot(fig1)

    with tab2:
        # 每月報酬 Heatmap (代碼同前)
        # st.pyplot(fig_heatmap)
        pass

    with tab3:
        # 剛剛寫好的日曆圖 (代碼同前)
        # st.pyplot(fig_calendar)
        pass

else:
    st.info("請先在上傳側邊欄上傳您的 trades.csv 檔案來開始分析。")