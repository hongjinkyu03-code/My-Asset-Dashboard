import streamlit as st
import pandas as pd
import yfinance as yf
import FinanceDataReader as fdr
from datetime import datetime, timedelta
import plotly.express as px
import os
import time

# 1. UI 및 기본 설정 (v24.2 + v25)
st.set_page_config(layout="wide", page_title="X-Asset Sovereign V25.1", page_icon="🚀")

PORT_FILE = "my_assets_v25.csv"
LOG_FILE = "daily_history_v25.csv"

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

# 2. 데이터베이스 로직 (누적 보관 필수)
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

# 3. 사이드바 및 정밀 검색 (v25 강화 로직)
krx_df = get_krx_data()
with st.sidebar:
    st.title("🛰️ Strategic Center")
    st.info(f"⏱️ 1분 주기 동기화 중 ({st.session_state.refresh_count})")
    msg_slot = st.empty()
    
    with st.form("add_form", clear_on_submit=True):
        st.subheader("🆕 종목 등록")
        search_q = st.text_input("종목명(국내) 또는 티커(해외)")
        n_input = st.text_input("표시 별칭 (생략 가능)")
        category = st.selectbox("자산 분류", ["성장주", "ETF", "금/원자재", "배당주", "현금성", "기타"])
        c_p = st.number_input("매입단가 (달러/원 구분)", min_value=0.0, format="%.2f")
        c_q = st.number_input("보유주수", min_value=0.0, format="%.2f")
        curr = st.radio("구매 통화", ["KRW", "USD"], horizontal=True)
        
        if st.form_submit_button("포트폴리오에 추가"):
            if search_q:
                # v25: 국내 주식 정밀 매칭
                match = krx_df[krx_df['Name'] == search_q]
                if not match.empty:
                    code = match.iloc[0]['Code']
                    ticker = f"{code}.KS"
                    try: # 코스피/코스닥 판별
                        if yf.Ticker(ticker).fast_info['last_price'] is None: ticker = f"{code}.KQ"
                    except: ticker = f"{code}.KQ"
                else:
                    ticker = search_q.upper()

                try:
                    tk = yf.Ticker(ticker)
                    price = tk.fast_info['last_price']
                    if price is None or price == 0:
                        msg_slot.error("❌ 종목을 찾을 수 없습니다."); time.sleep(2); msg_slot.empty()
                    else:
                        new_row = pd.DataFrame([{'Name': n_input if n_input else search_q, 'Ticker': ticker, 
                                                 'BuyPrice': c_p, 'Quantity': c_q, 'Currency': curr, 'Category': category}])
                        st.session_state.portfolio = pd.concat([st.session_state.portfolio, new_row], ignore_index=True)
                        save_db(st.session_state.portfolio, PORT_FILE)
                        st.rerun()
                except:
                    msg_slot.error("❌ 시스템 오류"); time.sleep(2); msg_slot.empty()

    if not st.session_state.portfolio.empty:
        st.markdown("---")
        st.subheader("🗑️ 종목 삭제")
        delete_options = {f"{row['Name']} ({row['Category']})": idx for idx, row in st.session_state.portfolio.iterrows()}
        target_label = st.selectbox("삭제 종목 선택", list(delete_options.keys()))
        if st.button("선택 종목 제거", use_container_width=True):
            st.session_state.portfolio = st.session_state.portfolio.drop(delete_options[target_label]).reset_index(drop=True)
            save_db(st.session_state.portfolio, PORT_FILE)
            st.rerun()

# 4. 실시간 엔진 및 누적 기록 로직 (v24 기능 그대로!)
if not st.session_state.portfolio.empty:
    df = st.session_state.portfolio.copy()
    with st.spinner('Synchronizing...'):
        try:
            ex_rate = float(yf.download("KRW=X", period="1d", progress=False)['Close'].iloc[-1])
        except: ex_rate = 1350.0

        # v25: 모든 지표 원화 통합 연산
        vals_krw, buy_vals_krw, cp_krw, buy_p_krw, d_changes = [], [], [], [], []
        for _, row in df.iterrows():
            try:
                tk = yf.Ticker(row['Ticker'])
                cp = tk.fast_info['last_price']
                hist = tk.history(period="2d")
                change_val = ((cp - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2] * 100) if len(hist) >= 2 else 0.0
                
                m = ex_rate if row['Currency'] == "USD" else 1
                cp_krw.append(cp * m)
                buy_p_krw.append(row['BuyPrice'] * m)
                vals_krw.append(cp * row['Quantity'] * m)
                buy_vals_krw.append(row['BuyPrice'] * row['Quantity'] * m)
                d_changes.append(change_val)
            except: 
                cp_krw.append(0); buy_p_krw.append(0); vals_krw.append(0); buy_vals_krw.append(0); d_changes.append(0)

        df['매수가(₩)'] = buy_p_krw
        df['현재가(₩)'] = cp_krw
        df['평가금액(₩)'] = vals_krw
        df['매입금액(₩)'] = buy_vals_krw
        df['수익률(%)'] = ((df['현재가(₩)'] - df['매수가(₩)']) / df['매수가(₩)'] * 100)
        df['전일대비(%)'] = d_changes
        
        total_val = sum(vals_krw)
        total_buy_val = sum(buy_vals_krw)
        total_profit_amt = total_val - total_buy_val
        total_asset_roi = (total_profit_amt / total_buy_val * 100) if total_buy_val > 0 else 0

        # [기록 로직] v24와 동일하게 5분 대기 유지
        now = datetime.now()
        log_df = load_db(LOG_FILE)
        if log_df.empty:
            if now > st.session_state.last_change_time + timedelta(minutes=5):
                save_db(pd.DataFrame([{'Date': now.strftime("%Y-%m-%d"), 'Total_Value': total_val}]), LOG_FILE)
        elif log_df.iloc[-1]['Date'] != now.strftime("%Y-%m-%d"):
            save_db(pd.concat([log_df, pd.DataFrame([{'Date': now.strftime("%Y-%m-%d"), 'Total_Value': total_val}])]), LOG_FILE)

    # 5. 메인 대시보드 UI
    st.title("🏆 X-Asset Sovereign Intelligence V25.1")
    
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.markdown(f'<div class="metric-card"><div class="metric-label">현재 총 자산가치</div><div class="metric-value">₩ {total_val:,.0f}</div></div>', unsafe_allow_html=True)
    m2.markdown(f'<div class="metric-card"><div class="metric-label">매입 총 자산</div><div class="metric-value">₩ {total_buy_val:,.0f}</div></div>', unsafe_allow_html=True)
    m3.markdown(f'<div class="metric-card"><div class="metric-label">자산 등락 금액</div><div class="metric-value" style="color:{"#D90429" if total_profit_amt>=0 else "#0077B6"};">₩ {total_profit_amt:+,.0f}</div></div>', unsafe_allow_html=True)
    m4.markdown(f'<div class="metric-card"><div class="metric-label">매입 대비 수익률</div><div class="metric-value" style="color:{"#D90429" if total_profit_amt>=0 else "#0077B6"};">{total_asset_roi:+,.2f}%</div></div>', unsafe_allow_html=True)
    m5.markdown(f'<div class="metric-card"><div class="metric-label">실시간 환율</div><div class="metric-value">₩ {ex_rate:,.1f}</div></div>', unsafe_allow_html=True)

    t1, t2 = st.tabs(["📊 실시간 현황", "📅 성장 분석"])

    with t1:
        st.subheader("포트폴리오 상세 (원화 통합)")
        v_df = df[['Name', 'Category', '매수가(₩)', '현재가(₩)', '수익률(%)', '전일대비(%)', 'Quantity']].copy()
        v_df.columns = ['이름', '분류', '매수가(₩)', '현재가(₩)', '수익률', '전일대비', '수량']
        v_df.index = range(1, len(v_df) + 1)
        st.dataframe(v_df.style.format({'매수가(₩)': '{:,.0f}', '현재가(₩)': '{:,.0f}', '수익률': '{:+.2f}%', '전일대비': '{:+.2f}%', '수량': '{:,.2f}'})
                     .applymap(lambda x: 'color: #D90429' if (isinstance(x, float) and x > 0) else ('color: #0077B6' if (isinstance(x, float) and x < 0) else ''), subset=['수익률', '전일대비']), use_container_width=True)
        
        st.subheader("자산군 비중")
        cat_group = df.groupby('Category')['평가금액(₩)'].sum().reset_index()
        fig = px.pie(cat_group, values='평가금액(₩)', names='Category', hole=0.4, template="plotly_white")
        fig.update_traces(textinfo='label+percent', textposition='outside')
        st.plotly_chart(fig, use_container_width=True)

    with t2:
        st.subheader("📅 총 자산 성장 히스토리")
        if not log_df.empty:
            fig_line = px.line(log_df, x='Date', y='Total_Value', markers=True, title="일별 자산 추이")
            st.plotly_chart(fig_line, use_container_width=True)
            st.dataframe(log_df.sort_values('Date', ascending=False), use_container_width=True)
        else:
            st.info("데이터 기록 대기 중입니다 (수정 후 5분 뒤 첫 기록 생성)")

    st.session_state.refresh_count += 1
    time.sleep(60); st.rerun()
