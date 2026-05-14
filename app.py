import streamlit as st
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
import numpy as np
from pyxirr import xirr
import calendar
import matplotlib.font_manager as fm
import os
import urllib.request

# --- 1. 介面設定 (iOS 深色模式 CSS) ---
st.set_page_config(page_title="我的理財管家", layout="centered")

st.markdown("""
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}
.stApp { background-color: #000000; color: #ffffff; }
[data-testid="stSidebar"] { background-color: #121212; }
div[data-testid="metric-container"] {
    background-color: #1c1c1e;
    border-radius: 16px;
    padding: 16px;
    border: 1px solid #2c2c2e;
}
div[data-testid="stMetricLabel"] { color: #8e8e93; font-size: 14px; }
div[data-testid="stMetricValue"] { color: #ffffff; font-weight: 700; }
h1, h2, h3, p { color: #ffffff !important; }
.stTabs [data-baseweb="tab-list"] { background-color: transparent; }
.stTabs [data-baseweb="tab"] { color: #8e8e93; }
.stTabs [aria-selected="true"] { color: #ffffff; border-bottom-color: #ffffff; }
</style>
""", unsafe_allow_html=True)

st.title("📈 淨資產儀表板")

# --- 2. 終極解決字體亂碼問題 ---
@st.cache_resource
def load_chinese_font():
    # 下載微軟正黑體或思源黑體的輕量版 (從 GitHub 下載確保 100% 存在)
    font_url = "https://github.com/StellarCN/noto-sans-sc-provisional/raw/master/unhinted/NotoSansSC-Regular.otf"
    font_path = "NotoSansSC-Regular.otf"
    if not os.path.exists(font_path):
        urllib.request.urlretrieve(font_url, font_path)
    
    # 註冊字體
    fm.fontManager.addfont(font_path)
    prop = fm.FontProperties(fname=font_path)
    plt.rcParams['font.sans-serif'] = [prop.get_name()]
    plt.rcParams['axes.unicode_minus'] = False 
    return prop.get_name()

font_family = load_chinese_font()

# 強制設定圖表樣式
plt.style.use('dark_background')
plt.rcParams.update({
    'axes.facecolor': '#1c1c1e',
    'figure.facecolor': '#000000',
    'font.family': font_family, # 這裡設定剛下載的字體
    'text.color': 'white',
    'axes.labelcolor': 'white',
    'xtick.color': '#8e8e93',
    'ytick.color': '#8e8e93'
})

# --- 3. 側邊欄與運算 (同前) ---
uploaded_file = st.sidebar.file_uploader("上傳 trades.csv", type="csv")
st.sidebar.subheader("💰 入金紀錄")
num_inflows = st.sidebar.number_input("入金筆數", min_value=1, max_value=20, value=2)
inflow_records = {}
for i in range(int(num_inflows)):
    col1, col2 = st.sidebar.columns(2)
    with col1: d = st.date_input(f"日期 {i+1}", key=f"d_{i}")
    with col2: a = st.number_input(f"金額 {i+1}", value=200000 if i==0 else 0, key=f"a_{i}")
    if a != 0: inflow_records[d.strftime('%Y-%m-%d')] = a

if uploaded_file:
    # --- 核心邏輯區 (這部分保持原本的計算) ---
    df = pd.read_csv(uploaded_file)
    df.columns = df.columns.str.strip()
    df['買入日期'] = pd.to_datetime(df['買入日期'])
    df['賣出日期'] = pd.to_datetime(df['賣出日期'], errors='coerce')
    start_date, end_date = df['買入日期'].min(), pd.Timestamp.now().normalize()
    inflow_series = pd.Series(inflow_records)
    inflow_series.index = pd.to_datetime(inflow_series.index)
    all_dates = pd.date_range(start=start_date, end=end_date, freq='D')
    
    # ... (省略中間重複的 holdings/equity 計算，確保與你原本的功能一致) ...
    # 這裡假設已經算出 total_equity, unit_nav, daily_ret
    # 注意：請確保 total_equity = stock_value_df.sum(axis=1) + daily_cash

    # 下載數據 (這裡使用 spinner 增加流暢感)
    with st.spinner('連線 Yahoo Finance 中...'):
        # [此處插入你原本的股價與大盤下載運算代碼]
        # 為了節省空間，請確保你貼上的代碼包含計算 total_equity 與 unit_nav 的步驟
        # 關鍵在於：total_equity = stock_value_df.sum(axis=1) + daily_cash
        # 以及：daily_ret = unit_nav.pct_change().dropna()
        pass 

    # --- 關鍵修正：今日指標 ---
    try:
        daily_ret = unit_nav.pct_change().dropna()
        latest_nav = unit_nav.iloc[-1]
        prev_nav = unit_nav.iloc[-2] if len(unit_nav) > 1 else latest_nav
        day_change = (latest_nav / prev_nav - 1) * 100
        day_amt_change = total_equity.iloc[-1] - total_equity.iloc[-2] if len(total_equity)>1 else 0
        day_color = "#34c759" if day_change >= 0 else "#ff3b30"

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"""<div data-testid="metric-container"><div style="color:#8e8e93;font-size:14px;">總資產 (元)</div>
            <div style="font-size:28px;font-weight:700;">{total_equity.iloc[-1]:,.0f}</div>
            <div style="color:{day_color};font-size:14px;">{day_change:+.2f}% ({day_amt_change:+,.0f}元)</div></div>""", unsafe_allow_html=True)
        with col2:
            all_time_ret = (unit_nav.iloc[-1]-1)*100
            st.markdown(f"""<div data-testid="metric-container"><div style="color:#8e8e93;font-size:14px;">歷史總報酬</div>
            <div style="font-size:28px;font-weight:700;">{all_time_ret:+.2f}%</div>
            <div style="color:#8e8e93;font-size:14px;">All-Time High</div></div>""", unsafe_allow_html=True)

        st.write("")

        tab1, tab2 = st.tabs(["🗓️ 淨資產變動日曆", "📈 趨勢與高點"])
        with tab1:
            # --- 修正日曆顯示邏輯 ---
            if not daily_ret.empty:
                last_date = daily_ret.index.max()
                year, month = last_date.year, last_date.month
                month_ret = daily_ret[(daily_ret.index.year == year) & (daily_ret.index.month == month)] * 100
                calendar.setfirstweekday(calendar.SUNDAY)
                cal_matrix = calendar.monthcalendar(year, month)

                html_cal = f'<div style="background-color:#1c1c1e;border-radius:16px;padding:20px;margin:auto;"><h3 style="text-align:center;">{year}年{month}月</h3>'
                html_cal += '<div style="display:grid;grid-template-columns:repeat(7,1fr);gap:8px;">'
                for d in ['日','一','二','三','四','五','六']:
                    html_cal += f'<div style="text-align:center;color:#8e8e93;font-size:12px;">{d}</div>'
                
                for week in cal_matrix:
                    for day in week:
                        if day == 0: html_cal += '<div style="aspect-ratio:1/1;"></div>'
                        else:
                            date_obj = pd.Timestamp(year, month, day)
                            bg, text = "#2c2c2e", "#8e8e93" # 預設灰色
                            val_str = ""
                            if date_obj in month_ret.index:
                                val = month_ret.loc[date_obj]
                                val_str = f"{val:+.1f}%"
                                bg = "#1a3b26" if val>0 else "#3d1c1d"
                                text = "#34c759" if val>0 else "#ff3b30"
                            html_cal += f'<div style="background-color:{bg};border-radius:8px;padding:6px;aspect-ratio:1/1;display:flex;flex-direction:column;justify-content:space-between;">'
                            html_cal += f'<div style="font-size:12px;font-weight:700;">{day}</div><div style="color:{text};font-size:10px;text-align:center;">{val_str}</div></div>'
                html_cal += '</div></div>'
                st.markdown(html_cal, unsafe_allow_html=True)
            else:
                st.warning("尚無足夠的報酬資料來顯示日曆。")

        with tab2:
            fig1, ax1 = plt.subplots(figsize=(10, 5))
            ax_aum = ax1.twinx()
            ax_aum.fill_between(total_equity.index, 0, total_equity, color='#8e8e93', alpha=0.1)
            ax_aum.set_yticks([])
            ax1.plot(unit_nav.index, unit_nav, label='策略淨值', color='#0a84ff', linewidth=2.5)
            ax1.scatter(unit_nav.idxmax(), unit_nav.max(), color='#ffd60a', s=150, marker='*', zorder=5)
            ax1.set_title("累積淨值走勢圖 (標註歷史高點)", color="white", pad=20)
            ax1.legend(frameon=False)
            st.pyplot(fig1)

    except Exception as e:
        st.error(f"資料計算出現問題：{e}")
