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

st.sidebar.subheader("💰 入金紀錄 (動態新增)")
# [優化 1] 讓使用者自己決定要幾筆入金
num_inflows = st.sidebar.number_input("您要輸入幾筆入金紀錄？", min_value=1, max_value=20, value=2, step=1)

inflow_records = {}
for i in range(int(num_inflows)):
    col1, col2 = st.sidebar.columns(2)
    with col1:
        d = st.date_input(f"日期 {i+1}", key=f"date_{i}")
    with col2:
        # 預設第一筆為 20萬，其餘為 0
        default_amt = 200000 if i == 0 else 0
        a = st.number_input(f"金額 {i+1}", value=default_amt, step=10000, key=f"amt_{i}")
    
    if a != 0:
        date_str = d.strftime('%Y-%m-%d')
        # 如果同一天有多筆入金，自動加總
        inflow_records[date_str] = inflow_records.get(date_str, 0) + a

if uploaded_file:
    # 讀取與清理資料
    df = pd.read_csv(uploaded_file)
    df.columns = df.columns.str.strip()
    df['代號'] = df['代號'].astype(str).str.strip()
    df['買入日期'] = pd.to_datetime(df['買入日期'])
    df['賣出日期'] = pd.to_datetime(df['賣出日期'], errors='coerce')

    start_date = df['買入日期'].min()
    end_date = pd.Timestamp.now().normalize()
    
    inflow_series = pd.Series(inflow_records)
    inflow_series.index = pd.to_datetime(inflow_series.index)

    # 運算持倉與現金流
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

    # 下載股價與計算 AUM
    with st.spinner('⏳ 正在下載最新股價與大盤，請稍候...'):
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

        # 計算 NAV
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

        # 下載大盤
        twii_data = yf.download('^TWII', start=start_date, end=end_date + pd.Timedelta(days=1), progress=False)
        twii = twii_data['Close'] if 'Close' in twii_data.columns else twii_data.iloc[:, 0]
        if isinstance(twii, pd.DataFrame): twii = twii.iloc[:, 0]
        benchmark = twii.reindex(all_dates).ffill()
        benchmark = pd.to_numeric(benchmark, errors='coerce').astype(float)
        benchmark_ret = benchmark / benchmark.iloc[0]

    # ------------------------------------------
    # 4. 手機版精華：今日關鍵指標 (Metrics)
    # ------------------------------------------
    st.subheader("📊 總體戰報")
    daily_ret = unit_nav.pct_change().dropna()
    latest_nav = unit_nav.iloc[-1]
    prev_nav = unit_nav.iloc[-2] if len(unit_nav) > 1 else latest_nav
    prev_equity = total_equity.iloc[-2] if len(total_equity) > 1 else total_equity.iloc[-1]
    
    # [優化 3] 計算當日跳動的「絕對金額」與「百分比」
    day_amt_change = total_equity.iloc[-1] - prev_equity
    day_change = (latest_nav / prev_nav - 1) * 100
    
    # 排版分為上下兩排，適合手機觀看
    col1, col2 = st.columns(2)
    with col1:
        # [優化 2] 改為台幣(元)顯示，不再用 $
        st.metric("總資產 (AUM)", f"{total_equity.iloc[-1]:,.0f} 元", f"{day_amt_change:+,.0f} 元 ({day_change:+.2f}%)")
    with col2:
        # [優化 4] 新增歷史總報酬
        all_time_ret = (unit_nav.iloc[-1] - 1) * 100
        st.metric("歷史總報酬", f"{all_time_ret:+.2f}%")
        
    col3, col4 = st.columns(2)
    with col3:
        ytd_start = pd.Timestamp(f"{end_date.year}-01-01")
        if ytd_start in unit_nav.index:
            ytd_ret = (unit_nav.iloc[-1] / unit_nav.loc[ytd_start] - 1) * 100
        else:
            ytd_ret = (unit_nav.iloc[-1] / unit_nav.iloc[0] - 1) * 100
        st.metric("今年以來 (YTD)", f"{ytd_ret:+.2f}%")
    with col4:
        try:
            xirr_val = xirr([(d,-v) for d,v in inflow_records.items()]+[(all_dates[-1],total_equity.iloc[-1])])
            st.metric("真實年化 (XIRR)", f"{xirr_val:.2%}")
        except:
            st.metric("真實年化 (XIRR)", "N/A")

    # 歷史高點與回撤
    ath_val = unit_nav.max()
    mdd = ((unit_nav / unit_nav.cummax()) - 1).min()
    st.write(f"🏆 歷史最高淨值: `{ath_val:.3f}` | ⚠️ 最大回撤: `{mdd:.2%}`")

    # ------------------------------------------
    # 5. 圖表分頁
    # ------------------------------------------
    tab1, tab2, tab3 = st.tabs(["📈 走勢圖", "🔥 每月績效", "🗓️ 每日日曆"])
    
    with tab1:
        fig1, ax1 = plt.subplots(figsize=(10, 5))
        ax_aum = ax1.twinx()
        ax_aum.fill_between(total_equity.index, 0, total_equity, color='gray', alpha=0.1)
        ax_aum.set_yticks([])
        ax1.plot(unit_nav.index, unit_nav, label='Strategy (NAV)', color='#d62728', linewidth=2)
        ax1.plot(benchmark_ret.index, benchmark_ret, label='Market (^TWII)', color='#2ca02c', linestyle='--', alpha=0.6)
        ath_date = unit_nav.idxmax()
        ax1.scatter(ath_date, ath_val, color='gold', s=150, marker='*', edgecolors='black', zorder=5)
        ax1.legend(loc='upper left')
        st.pyplot(fig1)

    with tab2:
        fig2, ax2 = plt.subplots(figsize=(8, 5))
        monthly_ret = unit_nav.resample('ME').last().pct_change().fillna(unit_nav.iloc[0]-1)
        heatmap_df = monthly_ret.to_frame(name='ret')
        heatmap_df['year'] = heatmap_df.index.year
        heatmap_df['month'] = heatmap_df.index.month
        sns.heatmap(heatmap_df.pivot_table(index='year', columns='month', values='ret') * 100,
                    annot=True, fmt=".1f", cmap='RdYlGn', center=0, ax=ax2)
        st.pyplot(fig2)

    with tab3:
        fig3, ax3 = plt.subplots(figsize=(8, 5))
        last_date = daily_ret.index.max()
        year, month = last_date.year, last_date.month
        month_ret = daily_ret[(daily_ret.index.year == year) & (daily_ret.index.month == month)] * 100
        cal_matrix = calendar.monthcalendar(year, month)
        cal_df = pd.DataFrame(cal_matrix, columns=['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'], dtype=float)
        heat_data = pd.DataFrame(index=cal_df.index, columns=cal_df.columns, dtype=float)
        annot_data = pd.DataFrame(index=cal_df.index, columns=cal_df.columns, dtype=object)
        
        for week in range(len(cal_matrix)):
            for day_idx, day in enumerate(cal_matrix[week]):
                if day == 0:
                    heat_data.iat[week, day_idx] = np.nan
                    annot_data.iat[week, day_idx] = ""
                else:
                    date_obj = pd.Timestamp(year, month, day)
                    if date_obj in month_ret.index:
                        val = month_ret.loc[date_obj]
                        heat_data.iat[week, day_idx] = val
                        # [優化 5] 拿掉 '日' 這個字，直接顯示數字與百分比，徹底解決亂碼
                        annot_data.iat[week, day_idx] = f"{day}\n{val:+.2f}%"
                    else:
                        heat_data.iat[week, day_idx] = 0.0
                        # [優化 5] 同樣拿掉 '日'
                        annot_data.iat[week, day_idx] = f"{day}\n--"
                        
        sns.heatmap(heat_data, annot=annot_data, fmt="", cmap="RdYlGn", center=0, cbar=False,
                    linewidths=2, linecolor='white', ax=ax3)
        ax3.set_yticks([])
        ax3.xaxis.tick_top()
        st.pyplot(fig3)

else:
    st.info("👈 請在左側側邊欄上傳您的 trades.csv 檔案來開始分析！")
