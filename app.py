import streamlit as st
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
import numpy as np
from pyxirr import xirr
import calendar
import matplotlib.font_manager as fm
import os

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
/* Tab 樣式調整 */
.stTabs [data-baseweb="tab-list"] { background-color: transparent; }
.stTabs [data-baseweb="tab"] { color: #8e8e93; }
.stTabs [aria-selected="true"] { color: #ffffff; border-bottom-color: #ffffff; }
</style>
""", unsafe_allow_html=True)

st.title("📈 淨資產儀表板")

# --- 2. 字體設定 (配合 packages.txt) ---
@st.cache_resource
def set_chinese_font():
    font_path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
    if os.path.exists(font_path):
        fm.fontManager.addfont(font_path)
        font_name = fm.FontProperties(fname=font_path).get_name()
        plt.rcParams['font.sans-serif'] = [font_name, 'sans-serif']
    else:
        plt.rcParams['font.sans-serif'] = ['PingFang TC', 'Heiti TC', 'sans-serif']
    plt.rcParams['axes.unicode_minus'] = False 

set_chinese_font()
plt.style.use('dark_background')
plt.rcParams.update({
    'axes.facecolor': '#1c1c1e', 'figure.facecolor': '#000000',
    'text.color': 'white', 'axes.labelcolor': 'white',
    'xtick.color': '#8e8e93', 'ytick.color': '#8e8e93'
})

# --- 3. 側邊欄：上傳與動態入金 ---
st.sidebar.header("設定中心")
uploaded_file = st.sidebar.file_uploader("上傳 trades.csv", type="csv")

st.sidebar.subheader("💰 入金紀錄")
num_inflows = st.sidebar.number_input("入金筆數", min_value=1, max_value=20, value=2)
inflow_records = {}
for i in range(int(num_inflows)):
    c1, c2 = st.sidebar.columns(2)
    with c1: d = st.date_input(f"日期 {i+1}", key=f"d_{i}")
    with c2: a = st.number_input(f"金額 {i+1}", value=200000 if i==0 else 0, key=f"a_{i}")
    if a != 0: inflow_records[d.strftime('%Y-%m-%d')] = a

if uploaded_file:
    # --- 4. 核心計算大腦 ---
    df = pd.read_csv(uploaded_file)
    df.columns = df.columns.str.strip()
    df['代號'] = df['代號'].astype(str).str.strip()
    df['買入日期'] = pd.to_datetime(df['買入日期'])
    df['賣出日期'] = pd.to_datetime(df['賣出日期'], errors='coerce')

    start_date = df['買入日期'].min()
    end_date = pd.Timestamp.now().normalize()
    
    inflow_series = pd.Series(inflow_records)
    inflow_series.index = pd.to_datetime(inflow_series.index)

    # 建立日期矩陣
    all_dates = pd.date_range(start=start_date, end=end_date, freq='D')
    holdings = pd.DataFrame(index=all_dates, columns=df['代號'].unique()).fillna(0)
    cash_flow = pd.Series(0.0, index=all_dates)

    # 處理買賣
    for _, row in df.iterrows():
        if row['買入日期'] <= end_date:
            amt = row['股數'] * row['買入價格']
            fee = row['買入手續費'] if '買入手續費' in df.columns and pd.notnull(row['買入手續費']) else 0
            holdings.loc[row['買入日期']:, row['代號']] += row['股數']
            cash_flow.loc[row['買入日期']] -= (amt + fee)
        if pd.notnull(row['賣出日期']) and row['賣出日期'] <= end_date:
            amt = row['股數'] * row['賣出價格']
            fee = row['賣出手續費'] if '賣出手續費' in df.columns and pd.notnull(row['賣出手續費']) else 0
            holdings.loc[row['賣出日期']:, row['代號']] -= row['股數']
            cash_flow.loc[row['賣出日期']] += (amt - fee)

    daily_inflow_sum = inflow_series.reindex(all_dates).fillna(0).cumsum()
    daily_cash = daily_inflow_sum + cash_flow.cumsum()

    with st.spinner('⏳ 正在同步 Yahoo Finance 數據...'):
        stock_value_df = pd.DataFrame(index=all_dates).fillna(0.0)
        for code in holdings.columns:
            for suffix in ['.TW', '.TWO']:
                data = yf.download(f"{code}{suffix}", start=start_date, end=end_date + pd.Timedelta(days=1), progress=False)
                if not data.empty:
                    close = data['Close'].reindex(all_dates).ffill().fillna(0)
                    stock_value_df[code] = holdings[code] * (close.iloc[:,0] if isinstance(close, pd.DataFrame) else close)
                    break
        
        total_equity = stock_value_df.sum(axis=1) + daily_cash
        total_equity = pd.to_numeric(total_equity, errors='coerce').fillna(0).astype(float)

        # 計算淨值 (NAV)
        unit_nav = pd.Series(index=all_dates, dtype=float)
        units = 0.0
        for date in all_dates:
            eq = total_equity.loc[date]
            inf = inflow_series.get(date, 0.0)
            if units == 0:
                unit_nav.loc[date], units = 1.0, inf
            else:
                unit_nav.loc[date] = (eq - inf) / units
                if inf > 0: units += (inf / unit_nav.loc[date])
        
        unit_nav = unit_nav.ffill().fillna(1.0)
        daily_ret = unit_nav.pct_change().dropna()

    # --- 5. 畫面渲染 ---
    latest_nav = unit_nav.iloc[-1]
    prev_nav = unit_nav.iloc[-2] if len(unit_nav) > 1 else latest_nav
    day_change_pct = (latest_nav / prev_nav - 1) * 100
    day_change_amt = total_equity.iloc[-1] - total_equity.iloc[-2] if len(total_equity) > 1 else 0
    day_color = "#34c759" if day_change_pct >= 0 else "#ff3b30"

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""<div data-testid="metric-container"><div style="color:#8e8e93;">總資產 (元)</div>
        <div style="font-size:28px;font-weight:700;">{total_equity.iloc[-1]:,.0f}</div>
        <div style="color:{day_color};font-size:14px;">{day_change_pct:+.2f}% ({day_change_amt:+,.0f}元)</div></div>""", unsafe_allow_html=True)
    with col2:
        all_time_ret = (unit_nav.iloc[-1] - 1) * 100
        st.markdown(f"""<div data-testid="metric-container"><div style="color:#8e8e93;">歷史總報酬</div>
        <div style="font-size:28px;font-weight:700;">{all_time_ret:+.2f}%</div>
        <div style="color:#8e8e93;font-size:14px;">All-Time High</div></div>""", unsafe_allow_html=True)

    st.write("")
    tab1, tab2 = st.tabs(["🗓️ 變動日曆", "📈 趨勢圖"])
    
    with tab1:
        # 日曆邏輯
        last_date = daily_ret.index.max()
        year, month = last_date.year, last_date.month
        m_ret = daily_ret[(daily_ret.index.year == year) & (daily_ret.index.month == month)] * 100
        cal_matrix = calendar.monthcalendar(year, month)
        
        html = f'<div style="background-color:#1c1c1e;border-radius:16px;padding:20px;"><h3 style="text-align:center;">{year}年{month}月</h3>'
        html += '<div style="display:grid;grid-template-columns:repeat(7,1fr);gap:8px;">'
        for d in ['日','一','二','三','四','五','六']: html += f'<div style="text-align:center;color:#8e8e93;font-size:12px;">{d}</div>'
        
        for week in cal_matrix:
            for day in week:
                if day == 0: html += '<div></div>'
                else:
                    d_obj = pd.Timestamp(year, month, day)
                    bg, txt, val_s = "#2c2c2e", "#8e8e93", ""
                    if d_obj in m_ret.index:
                        v = m_ret.loc[d_obj]
                        val_s = f"{v:+.1f}%"
                        bg, txt = ("#1a3b26", "#34c759") if v > 0 else ("#3d1c1d", "#ff3b30")
                    html += f'<div style="background-color:{bg};border-radius:8px;padding:6px;aspect-ratio:1/1;display:flex;flex-direction:column;justify-content:space-between;">'
                    html += f'<div style="font-size:11px;font-weight:700;">{day}</div><div style="color:{txt};font-size:10px;text-align:center;">{val_s}</div></div>'
        st.markdown(html + '</div></div>', unsafe_allow_html=True)

    with tab2:
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(unit_nav.index, unit_nav, color='#0a84ff', linewidth=2, label='策略淨值')
        ax.scatter(unit_nav.idxmax(), unit_nav.max(), color='#ffd60a', s=100, marker='*', zorder=5)
        ax.set_title("累積淨值 (NAV) 走勢", color='white')
        st.pyplot(fig)

else:
    st.info("👈 請在左側上傳您的 trades.csv 檔案")
