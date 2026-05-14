import streamlit as st
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
import numpy as np
from pyxirr import xirr
import calendar
import matplotlib.font_manager as fm
import subprocess

# --- 1. 介面設定 (加入 iOS 深色模式 CSS) ---
st.set_page_config(page_title="我的理財管家", layout="centered")

# 👇 終極深色模式 CSS (還原圖片風格) 👇
st.markdown("""
<style>
/* 隱藏系統預設元素 */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

/* 全局背景色 (極致黑) */
.stApp {
    background-color: #000000;
    color: #ffffff;
}

/* 側邊欄深灰 */
[data-testid="stSidebar"] {
    background-color: #121212;
}

/* 頂部 Metric 數據卡片 (圓角深灰) */
div[data-testid="metric-container"] {
    background-color: #1c1c1e;
    border-radius: 16px;
    padding: 16px;
    border: 1px solid #2c2c2e;
}

/* Metric 標題與文字顏色 */
div[data-testid="stMetricLabel"] {
    color: #8e8e93;
    font-size: 14px;
}
div[data-testid="stMetricValue"] {
    color: #ffffff;
    font-weight: 700;
}
/* 漲跌幅顏色微調，對齊圖片的綠色與紅色 */
div[data-testid="stMetricDelta"] svg { display: none; } /* 隱藏箭頭 */

/* 標題與一般文字 */
h1, h2, h3, p { color: #ffffff !important; }
</style>
""", unsafe_allow_html=True)

st.title("📈 淨資產儀表板")

# --- 2. 解決中文字體問題 ---
@st.cache_resource
def load_font():
    try:
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

# 圖表改為深色模式
plt.style.use('dark_background')
plt.rcParams['axes.facecolor'] = '#1c1c1e'
plt.rcParams['figure.facecolor'] = '#000000'
plt.rcParams['grid.color'] = '#2c2c2e'
plt.rcParams['grid.linestyle'] = '--'
plt.rcParams['axes.edgecolor'] = '#1c1c1e'

# --- 3. 側邊欄：上傳與設定 ---
uploaded_file = st.sidebar.file_uploader("上傳 trades.csv", type="csv")

st.sidebar.subheader("💰 入金紀錄")
num_inflows = st.sidebar.number_input("入金筆數", min_value=1, max_value=20, value=2, step=1)
inflow_records = {}
for i in range(int(num_inflows)):
    col1, col2 = st.sidebar.columns(2)
    with col1:
        d = st.date_input(f"日期 {i+1}", key=f"date_{i}")
    with col2:
        default_amt = 200000 if i == 0 else 0
        a = st.number_input(f"金額 {i+1}", value=default_amt, step=10000, key=f"amt_{i}")
    if a != 0:
        date_str = d.strftime('%Y-%m-%d')
        inflow_records[date_str] = inflow_records.get(date_str, 0) + a

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    df.columns = df.columns.str.strip()
    df['代號'] = df['代號'].astype(str).str.strip()
    df['買入日期'] = pd.to_datetime(df['買入日期'])
    df['賣出日期'] = pd.to_datetime(df['賣出日期'], errors='coerce')

    start_date = df['買入日期'].min()
    end_date = pd.Timestamp.now().normalize()
    
    inflow_series = pd.Series(inflow_records)
    inflow_series.index = pd.to_datetime(inflow_series.index)

    all_dates = pd.date_range(start=start_date, end=end_date, freq='D')
    holdings = pd.DataFrame(index=all_dates, columns=df['代號'].unique()).fillna(0)
    cash_flow = pd.Series(0.0, index=all_dates)

    for _, row in df.iterrows():
        if row['買入日期'] <= end_date:
            amount = row['股數'] * row['買入價格']
            buy_fee = row['買入手續費'] if '買入手續費' in df.columns and pd.notnull(row['買入手續費']) else 0
            holdings.loc[row['買入日期']:, row['代號']] += row['股數']
            cash_flow.loc[row['買入日期']] -= (amount + buy_fee)

        if pd.notnull(row['賣出日期']) and row['賣出日期'] <= end_date:
            amount = row['股數'] * row['賣出價格']
            sell_fee = row['賣出手續費'] if '賣出手續費' in df.columns and pd.notnull(row['賣出手續費']) else 0
            holdings.loc[row['賣出日期']:, row['代號']] -= row['股數']
            cash_flow.loc[row['賣出日期']] += (amount - sell_fee)

    daily_inflow_sum = inflow_series.reindex(all_dates).fillna(0).cumsum()
    daily_cash = daily_inflow_sum + cash_flow.cumsum()

    with st.spinner('⏳ 讀取資料中...'):
        stock_value_df = pd.DataFrame(index=all_dates).fillna(0)
        for code in holdings.columns:
            for suffix in ['.TW', '.TWO']:
                data = yf.download(f"{code}{suffix}", start=start_date, end=end_date + pd.Timedelta(days=1), progress=False)
                if not data.empty:
                    close = data['Close'].reindex(all_dates).ffill().fillna(0)
                    stock_value_df[code] = holdings[code] * (close.iloc[:,0] if isinstance(close, pd.DataFrame) else close)
                    break

        total_equity = stock_value_df.sum(axis=1) + daily_cash
        total_equity = pd.to_numeric(total_equity, errors='coerce').fillna(0).astype(float)

        unit_nav = pd.Series(index=all_dates, dtype=float)
        current_units = 0
        for date in all_dates:
            eq, inf = total_equity.loc[date], inflow_series.get(date, 0)
            if current_units == 0:
                unit_nav.loc[date], current_units = 1.0, inf
            else:
                unit_nav.loc[date] = (eq - inf) / current_units
                if inf > 0: current_units += (inf / unit_nav.loc[date])
        
        unit_nav = pd.to_numeric(unit_nav, errors='coerce').fillna(1.0).astype(float)

        twii_data = yf.download('^TWII', start=start_date, end=end_date + pd.Timedelta(days=1), progress=False)
        twii = twii_data['Close'] if 'Close' in twii_data.columns else twii_data.iloc[:, 0]
        if isinstance(twii, pd.DataFrame): twii = twii.iloc[:, 0]
        benchmark = twii.reindex(all_dates).ffill()
        benchmark = pd.to_numeric(benchmark, errors='coerce').astype(float)
        benchmark_ret = benchmark / benchmark.iloc[0]

    # ------------------------------------------
    # 4. 手機版精華：今日關鍵指標
    # ------------------------------------------
    daily_ret = unit_nav.pct_change().dropna()
    latest_nav = unit_nav.iloc[-1]
    prev_nav = unit_nav.iloc[-2] if len(unit_nav) > 1 else latest_nav
    prev_equity = total_equity.iloc[-2] if len(total_equity) > 1 else total_equity.iloc[-1]
    
    day_amt_change = total_equity.iloc[-1] - prev_equity
    day_change = (latest_nav / prev_nav - 1) * 100
    
    # 決定顏色
    day_color = "#34c759" if day_change >= 0 else "#ff3b30"
    day_sign = "+" if day_change >= 0 else ""
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
        <div data-testid="metric-container">
            <div style="color: #8e8e93; font-size: 14px;">總資產 (AUM)</div>
            <div style="color: #ffffff; font-size: 24px; font-weight: bold; margin: 5px 0;">{total_equity.iloc[-1]:,.0f}</div>
            <div style="color: {day_color}; font-size: 14px;">{day_sign}{day_amt_change:+,.0f} ({day_sign}{day_change:.2f}%)</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        all_time_ret = (unit_nav.iloc[-1] - 1) * 100
        ret_color = "#34c759" if all_time_ret >= 0 else "#ff3b30"
        ret_sign = "+" if all_time_ret >= 0 else ""
        st.markdown(f"""
        <div data-testid="metric-container">
            <div style="color: #8e8e93; font-size: 14px;">歷史總報酬</div>
            <div style="color: #ffffff; font-size: 24px; font-weight: bold; margin: 5px 0;">{ret_sign}{all_time_ret:.2f}%</div>
            <div style="color: #8e8e93; font-size: 14px;">自成立以來</div>
        </div>
        """, unsafe_allow_html=True)

    st.write("") # 間距

    # ------------------------------------------
    # 5. 深色風格日曆與圖表
    # ------------------------------------------
    tab1, tab2 = st.tabs(["🗓️ 淨資產變動日曆", "📈 趨勢與高點"])
    
    with tab1:
        # --- iOS Crypto 風格 HTML 日曆 ---
        last_date = daily_ret.index.max()
        year, month = last_date.year, last_date.month
        month_ret = daily_ret[(daily_ret.index.year == year) & (daily_ret.index.month == month)] * 100
        
        # 設定週日為第一天 (符合圖片)
        calendar.setfirstweekday(calendar.SUNDAY)
        cal_matrix = calendar.monthcalendar(year, month)
        
        st.markdown(f"<h3 style='text-align: center; color: #ffffff;'>{year}年{month}月</h3>", unsafe_allow_html=True)
        
        # CSS Grid
        html_cal = """
        <div style="background-color: #1c1c1e; border-radius: 16px; padding: 20px; max-width: 500px; margin: auto;">
            <div style="display: grid; grid-template-columns: repeat(7, 1fr); gap: 8px;">
        """
        
        # 表頭 (日 一 二 三 四 五 六)
        days_header = ['日', '一', '二', '三', '四', '五', '六']
        for d in days_header:
            html_cal += f'<div style="text-align: center; color: #8e8e93; font-size: 12px; margin-bottom: 8px;">{d}</div>'
            
        # 繪製方格
        for week in cal_matrix:
            for day in week:
                if day == 0:
                    # 空白網格
                    html_cal += '<div style="background-color: #000000; border-radius: 8px; aspect-ratio: 1/1;"></div>'
                else:
                    date_obj = pd.Timestamp(year, month, day)
                    if date_obj in month_ret.index:
                        val = month_ret.loc[date_obj]
                        if val > 0:
                            bg_color, text_color = "#1a3b26", "#34c759" # 暗綠底，亮綠字
                        elif val < 0:
                            bg_color, text_color = "#3d1c1d", "#ff3b30" # 暗紅底，亮紅字
                        else:
                            bg_color, text_color = "#2c2c2e", "#8e8e93" # 灰底，灰字
                            
                        val_str = f"+{val:.1f}%" if val > 0 else f"{val:.1f}%"
                        html_cal += f"""
                        <div style="background-color: {bg_color}; border-radius: 8px; display: flex; flex-direction: column; justify-content: space-between; padding: 6px; aspect-ratio: 1/1;">
                            <div style="color: #ffffff; font-size: 12px; font-weight: bold;">{day}</div>
                            <div style="color: {text_color}; font-size: 11px; text-align: center; font-weight: bold;">{val_str}</div>
                        </div>
                        """
                    else:
                        # 假日無資料
                        html_cal += f"""
                        <div style="background-color: #2c2c2e; border-radius: 8px; padding: 6px; aspect-ratio: 1/1;">
                            <div style="color: #8e8e93; font-size: 12px;">{day}</div>
                        </div>
                        """
        html_cal += "</div>"
        
        # 底部統計 (對齊圖片底部的 上漲日數 / 平均日增)
        month_vals = month_ret.values
        win_days = sum(month_vals > 0)
        total_trade_days = len(month_vals)
        avg_ret = month_vals.mean() if total_trade_days > 0 else 0
        best_day = month_vals.max() if total_trade_days > 0 else 0
        worst_day = month_vals.min() if total_trade_days > 0 else 0
        
        html_cal += f"""
        <div style="margin-top: 25px; padding-top: 15px; border-top: 1px solid #2c2c2e; display: flex; justify-content: space-between; text-align: center;">
            <div><div style="color: #8e8e93; font-size: 11px; margin-bottom: 4px;">上漲日數</div><div style="color: #34c759; font-size: 15px; font-weight: bold;">{win_days}/{total_trade_days}</div></div>
            <div><div style="color: #8e8e93; font-size: 11px; margin-bottom: 4px;">平均日增</div><div style="color: {'#34c759' if avg_ret>=0 else '#ff3b30'}; font-size: 15px; font-weight: bold;">{'+' if avg_ret>=0 else ''}{avg_ret:.2f}%</div></div>
            <div><div style="color: #8e8e93; font-size: 11px; margin-bottom: 4px;">最佳日</div><div style="color: #34c759; font-size: 15px; font-weight: bold;">+{best_day:.2f}%</div></div>
            <div><div style="color: #8e8e93; font-size: 11px; margin-bottom: 4px;">最差日</div><div style="color: #ff3b30; font-size: 15px; font-weight: bold;">{worst_day:.2f}%</div></div>
        </div>
        </div>
        """
        st.markdown(html_cal, unsafe_allow_html=True)

    with tab2:
        fig1, ax1 = plt.subplots(figsize=(10, 5))
        ax_aum = ax1.twinx()
        
        # 背景塗層改為深灰色
        ax_aum.fill_between(total_equity.index, 0, total_equity, color='#8e8e93', alpha=0.15)
        ax_aum.set_yticks([])
        
        # 走勢線改成高對比度的藍色與暗灰色
        ax1.plot(unit_nav.index, unit_nav, label='策略淨值', color='#0a84ff', linewidth=2.5)
        ax1.plot(benchmark_ret.index, benchmark_ret, label='大盤', color='#8e8e93', linestyle='--', alpha=0.5, linewidth=1.5)
        
        ath_val = unit_nav.max()
        ath_date = unit_nav.idxmax()
        ax1.scatter(ath_date, ath_val, color='#ffd60a', s=150, marker='*', zorder=5)
        
        for spine in ax1.spines.values():
            spine.set_visible(False)
            
        ax1.legend(loc='upper left', frameon=False, labelcolor='white')
        st.pyplot(fig1)

else:
    st.info("👈 請在左側上傳 trades.csv 來開始分析")
