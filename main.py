import streamlit as st
import pandas as pd
import yfinance as yf
import FinanceDataReader as fdr
from datetime import datetime, timedelta
import plotly.express as px
import os
import time

# 1. UI 및 기본 설정
st.set_page_config(layout="wide", page_title="X-Asset Sovereign V25.4", page_icon="🚀")

PORT_FILE = "my_assets_v24.csv"
LOG_FILE = "daily_history_v24.csv"

if "refresh_count" not in st.session_state:
    st.session_state.refresh_count = 0
if "last_change_time" not in st.session_state:
    st.session_state.last_change_time = datetime.now()

st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #1A1C23; }
    [data-testid="stSidebar"] { background-color: #F8F9FA; border-right: 1px solid #DEE2E6; }
    .metric-card {
        background: #FFFFFF; padding: 15px; border-radius: 12px;
        border: 1px solid #E9ECEF; text-align: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05); margin-bottom: 10px;
    }
    .metric-label { color: #6C757D; font-size: 13px; font-weight: 600; }
    .metric-value { color: #1A1C23; font-size: 20px; font-weight: 800; margin-top: 5px; }
    </style>
    """, unsafe_allow_html=True)

# 2. 데이터 로직
def load_db(path):
    if os.path.exists(path):
        try: return pd.read_csv(path)
        except: return pd.DataFrame()
    return pd.DataFrame()

def save_db(df, path):
    df.to_csv(path, index=False)
    st.session_state.last_change_time = datetime.now()

@st.cache_data(ttl=86400)
def get_krx_data():
    try: return fdr.StockListing('KRX')[['Name', 'Code']]
    except: return pd.DataFrame(columns=['Name', 'Code'])

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = load_db(PORT_FILE)
    if st.session_state.portfolio.empty:
        st.session_state.portfolio = pd.DataFrame(columns=['Name', 'Ticker', 'BuyPrice', 'Quantity', 'Currency', 'Category'])

# 3. 사이드바 (국내 주식 검색 강화 유지)
krx_df = get_krx_data()
with st.sidebar:
    st.title("🛰️ Strategic Center")
    msg_slot = st.empty()
    with st.form("add_form", clear_on_submit=True):
        st.subheader("🆕 종목 등록")
        search_q = st.text_input("종목명(국내) 또는 티커(해외)")
        n_input = st.text_input("표시 별칭")
        category = st.selectbox("자산 분류", ["성장주", "ETF", "금/원자재", "배당주", "현금성", "기타"])
        c_p = st.number_input("매입단가", min_value=0.0, format="%.2f")
        c_q = st.number_input("보유주수", min_value=0.0, format="%.2f")
        curr = st.radio("통화", ["KRW", "USD"], horizontal=True)
        
        if st.form_submit_button("포트폴리오에 추가"):
            if search_q:
                match = krx_df[krx_df['Name'] == search_q]
                if not match.empty:
                    code = match.iloc[0]['Code']
                    ticker = f"{code}.KS"
                    try:
                        if yf.Ticker(ticker).fast_info['last_price'] is None: ticker = f"{code}.KQ"
                    except: ticker = f"{code}.KQ"
                else: ticker = search_q.upper()
                
                try:
                    tk = yf.Ticker(ticker)
                    if tk.fast_info['last_price']:
                        new_row = pd.DataFrame([{'Name': n_input if n_input else search_q, 'Ticker': ticker, 
                                                 'BuyPrice': c_p, 'Quantity': c_q, 'Currency': curr, 'Category': category}])
                        st.session_state.portfolio = pd.concat([st.session_state.portfolio, new_row], ignore_index=True)
                        save_db(st.session_state.portfolio, PORT_FILE)
                        st.rerun()
                    else: msg_slot.error("❌ 종목 없음"); time.sleep(2); msg_slot.empty()
                except: msg_slot.error("❌ 오류"); time.sleep(2); msg_slot.empty()

# 4. 실시간 엔진 및 히스토리 기록 (종류별 비중 포함)
if not st.session_state.portfolio.empty:
    df = st.session_state.portfolio.copy()
    with st.spinner('Syncing...'):
        try:
            ex_rate = float(yf.download("KRW=X", period="1d", progress=False)['Close'].iloc[-1])
        except: ex_rate = 1350.0

        vals_krw, buy_vals_krw, cp_krw, d_changes = [], [], [], []
        for _, row in df.iterrows():
            tk = yf.Ticker(row['Ticker'])
            cp = tk.fast_info['last_price']
            hist = tk.history(period="2d")
            chg = ((cp - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2] * 100) if len(hist) >= 2 else 0.0
            m = ex_rate if row['Currency'] == "USD" else 1
            cp_krw.append(cp * m); vals_krw.append(cp * row['Quantity'] * m)
            buy_vals_krw.append(row['BuyPrice'] * row['Quantity'] * m); d_changes.append(chg)

        df['현재가(₩)'], df['평가금액(₩)'], df['전일대비(%)'] = cp_krw, vals_krw, d_changes
        total_val = sum(vals_krw)
        total_buy = sum(buy_vals_krw)
        
        # 종류별 자산 합산 (기록용)
        cat_sums = df.groupby('Category')['평가금액(₩)'].sum().to_dict()

        # 5분 대기 기록 로직
        now_date = datetime.now().strftime("%Y-%m-%d")
        log_df = load_db(LOG_FILE)
        
        if (log_df.empty or log_df.iloc[-1]['날짜'] != now_date) and (datetime.now() > st.session_state.last_change_time + timedelta(minutes=5)):
            new_log = {'날짜': now_date, '총자산': total_val}
            new_log.update(cat_sums) # 종류별 금액 추가
            log_df = pd.concat([log_df, pd.DataFrame([new_log])], ignore_index=True)
            save_db(log_df, LOG_FILE)

    # 5. 메인 UI
    st.title("🏆 X-Asset Sovereign V25.4")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.markdown(f'<div class="metric-card"><div class="metric-label">현재 총 자산가치</div><div class="metric-value">₩ {total_val:,.0f}</div></div>', unsafe_allow_html=True)
    m2.markdown(f'<div class="metric-card"><div class="metric-label">매입 총 자산</div><div class="metric-value">₩ {total_buy:,.0f}</div></div>', unsafe_allow_html=True)
    m3.markdown(f'<div class="metric-card"><div class="metric-label">자산 등락 금액</div><div class="metric-value" style="color:{"#D90429" if total_val-total_buy>=0 else "#0077B6"};">₩ {total_val-total_buy:+,.0f}</div></div>', unsafe_allow_html=True)
    m4.markdown(f'<div class="metric-card"><div class="metric-label">수익률</div><div class="metric-value" style="color:{"#D90429" if total_val-total_buy>=0 else "#0077B6"};">{(total_val-total_buy)/total_buy*100:+,.2f}%</div></div>', unsafe_allow_html=True)
    m5.markdown(f'<div class="metric-card"><div class="metric-label">환율</div><div class="metric-value">₩ {ex_rate:,.1f}</div></div>', unsafe_allow_html=True)

    t1, t2 = st.tabs(["📊 실시간 현황", "📅 성장 분석"])
    with t1:
        v_df = df[['Name', 'Category', 'BuyPrice', '현재가(₩)', '전일대비(%)', 'Quantity']].copy()
        st.dataframe(v_df.style.format({'현재가(₩)': '{:,.0f}', '전일대비(%)': '{:+.2f}%'}), use_container_width=True)
        st.plotly_chart(px.pie(df, values='평가금액(₩)', names='Category', hole=0.4), use_container_width=True)

    with t2:
        st.subheader("📅 성장 데이터 상세 리포트")
        if not log_df.empty:
            # 변화 및 변화율 계산
            report = log_df.copy().sort_values('날짜', ascending=False)
            report['자산 변화'] = report['총자산'].diff(periods=-1)
            report['변화율(%)'] = (report['자산 변화'] / report['총자산'].shift(-1)) * 100
            
            # 컬럼 순서 정리
            cols = ['날짜', '총자산', '자산 변화', '변화율(%)'] + [c for c in log_df.columns if c not in ['날짜', '총자산']]
            st.dataframe(report[cols].style.format({
                '총자산': '{:,.0f}', '자산 변화': '{:+,.0f}', '변화율(%)': '{:+.2f}%'
            }).fillna(0), use_container_width=True)
        else:
            st.info("기록 대기 중 (5분 뒤 생성)")

    time.sleep(60); st.rerun()
