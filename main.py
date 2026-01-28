import streamlit as st
import pandas as pd
import yfinance as yf
import FinanceDataReader as fdr
from datetime import datetime, timedelta
import plotly.express as px
import os
import time

# 1. UI 및 기본 설정 (최종 확정 디자인)
st.set_page_config(layout="wide", page_title="X-Asset Sovereign V25.6", page_icon="🚀")

PORT_FILE = "my_assets_v24.csv"
LOG_FILE = "daily_history_v24.csv"

if "refresh_count" not in st.session_state:
    st.session_state.refresh_count = 0
if "last_change_time" not in st.session_state:
    st.session_state.last_change_time = datetime.now()

# 머스크님이 확정하신 화이트/다크블루 스타일링
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #1A1C23; }
    [data-testid="stSidebar"] { background-color: #F8F9FA; border-right: 1px solid #DEE2E6; }
    .metric-card {
        background: #FFFFFF; padding: 20px; border-radius: 12px;
        border: 1px solid #E9ECEF; text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 15px;
    }
    .metric-label { color: #6C757D; font-size: 14px; font-weight: 600; }
    .metric-value { color: #1A1C23; font-size: 24px; font-weight: 800; margin-top: 8px; }
    </style>
    """, unsafe_allow_html=True)

# 2. 데이터 영속성 로직 (KeyError 방어형)
def load_db(path):
    if os.path.exists(path):
        try:
            temp_df = pd.read_csv(path)
            if 'Date' in temp_df.columns: temp_df.rename(columns={'Date': '날짜'}, inplace=True)
            if 'Total_Value' in temp_df.columns: temp_df.rename(columns={'Total_Value': '총자산'}, inplace=True)
            return temp_df
        except: return pd.DataFrame()
    return pd.DataFrame()

def save_db(df, path):
    df.to_csv(path, index=False)
    st.session_state.last_change_time = datetime.now()

@st.cache_data(ttl=3600)
def get_krx_listing():
    try: return fdr.StockListing('KRX')[['Name', 'Code']]
    except: return pd.DataFrame(columns=['Name', 'Code'])

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = load_db(PORT_FILE)
    if st.session_state.portfolio.empty:
        st.session_state.portfolio = pd.DataFrame(columns=['Name', 'Ticker', 'BuyPrice', 'Quantity', 'Currency', 'Category'])

# 3. 사이드바 - 전략 제어 센터
krx_df = get_krx_listing()
with st.sidebar:
    st.title("🛰️ Strategic Center")
    st.info(f"⏱️ 실시간 동기화 중 ({st.session_state.refresh_count}회)")
    msg_slot = st.empty()
    
    with st.form("add_form", clear_on_submit=True):
        st.subheader("🆕 종목 등록")
        search_q = st.text_input("종목명(국내) 또는 티커(해외)")
        n_input = st.text_input("표시 별칭 (필요시)")
        category = st.selectbox("자산 분류", ["성장주", "ETF", "금/원자재", "배당주", "현금성", "기타"])
        c_p = st.number_input("매입단가", min_value=0.0, format="%.2f")
        c_q = st.number_input("보유주수", min_value=0.0, format="%.2f")
        curr = st.radio("구매 통화", ["KRW", "USD"], horizontal=True)
        
        if st.form_submit_button("포트폴리오에 추가"):
            if search_q:
                # 국내 주식 정밀 매칭 (FinanceDataReader + yfinance)
                match = krx_df[krx_df['Name'] == search_q] if not krx_df.empty else pd.DataFrame()
                if not match.empty:
                    code = match.iloc[0]['Code']
                    ticker = f"{code}.KS"
                    try:
                        if yf.Ticker(ticker).fast_info['last_price'] is None: ticker = f"{code}.KQ"
                    except: ticker = f"{code}.KQ"
                else:
                    ticker = search_q.upper()

                try:
                    tk = yf.Ticker(ticker)
                    price = tk.fast_info['last_price']
                    if price:
                        new_row = pd.DataFrame([{
                            'Name': n_input if n_input else search_q, 'Ticker': ticker,
                            'BuyPrice': c_p, 'Quantity': c_q, 'Currency': curr, 'Category': category
                        }])
                        st.session_state.portfolio = pd.concat([st.session_state.portfolio, new_row], ignore_index=True)
                        save_db(st.session_state.portfolio, PORT_FILE)
                        st.rerun()
                    else:
                        msg_slot.error("❌ 종목을 찾을 수 없습니다."); time.sleep(2); msg_slot.empty()
                except:
                    msg_slot.error("❌ 시스템 조회 오류"); time.sleep(2); msg_slot.empty()

    if not st.session_state.portfolio.empty:
        st.markdown("---")
        st.subheader("🗑️ 종목 관리")
        del_options = {f"{r['Name']} ({r['Category']})": i for i, r in st.session_state.portfolio.iterrows()}
        target = st.selectbox("제거할 종목", list(del_options.keys()))
        if st.button("선택 종목 제거", use_container_width=True):
            st.session_state.portfolio = st.session_state.portfolio.drop(del_options[target]).reset_index(drop=True)
            save_db(st.session_state.portfolio, PORT_FILE)
            st.rerun()

# 4. 분석 엔진 (환율/수수료/기록)
if not st.session_state.portfolio.empty:
    df = st.session_state.portfolio.copy()
    with st.spinner('Calculating Global Assets...'):
        try:
            ex_rate = float(yf.download("KRW=X", period="1d", progress=False)['Close'].iloc[-1])
        except:
            ex_rate = 1350.0

        v_krw, b_krw, cp_krw, bp_krw, chg_1d = [], [], [], [], []
        for _, row in df.iterrows():
            try:
                tk = yf.Ticker(row['Ticker'])
                cp = tk.fast_info['last_price']
                hist = tk.history(period="2d")
                day_chg = ((cp - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2] * 100) if len(hist) >= 2 else 0.0
                
                m = ex_rate if row['Currency'] == "USD" else 1
                cp_krw.append(cp * m)
                bp_krw.append(row['BuyPrice'] * m)
                v_krw.append(cp * row['Quantity'] * m)
                b_krw.append(row['BuyPrice'] * row['Quantity'] * m)
                chg_1d.append(day_chg)
            except:
                cp_krw.append(0); bp_krw.append(0); v_krw.append(0); b_krw.append(0); chg_1d.append(0)

        df['매수가(₩)'], df['현재가(₩)'], df['평가금액(₩)'], df['매입금액(₩)'] = bp_krw, cp_krw, v_krw, b_krw
        df['수익률(%)'] = (df['평가금액(₩)'] - df['매입금액(₩)']) / df['매입금액(₩)'] * 100
        df['전일대비(%)'] = chg_1d
        
        total_val = sum(v_krw)
        total_buy = sum(b_krw)
        total_prof = total_val - total_buy
        total_roi = (total_prof / total_buy * 100) if total_buy > 0 else 0
        cat_sums = df.groupby('Category')['평가금액(₩)'].sum().to_dict()

        # 5분 누적 대기 로직 (머스크님 확정안)
        now_dt = datetime.now().strftime("%Y-%m-%d")
        log_df = load_db(LOG_FILE)
        can_log = False
        if log_df.empty or log_df.iloc[-1]['날짜'] != now_dt:
            if datetime.now() > st.session_state.last_change_time + timedelta(minutes=5):
                can_log = True
        
        if can_log:
            new_log = {'날짜': now_dt, '총자산': total_val}
            new_log.update(cat_sums)
            log_df = pd.concat([log_df, pd.DataFrame([new_log])], ignore_index=True)
            save_db(log_df, LOG_FILE)

    # 5. 메인 대시보드 출력
    st.title("🏆 X-Asset Sovereign V25.6")
    m1, m2, m3, m4, m5 = st.columns(5)
    met = [("현재 총 자산가치", f"₩ {total_val:,.0f}"), ("매입 총 자산", f"₩ {total_buy:,.0f}"), 
           ("자산 등락 금액", f"₩ {total_prof:+,.0f}"), ("매입 대비 수익률", f"{total_roi:+,.2f}%"), ("실시간 환율", f"₩ {ex_rate:,.1f}")]
    for i, col in enumerate([m1, m2, m3, m4, m5]):
        col.markdown(f'<div class="metric-card"><div class="metric-label">{met[i][0]}</div><div class="metric-value">{met[i][1]}</div></div>', unsafe_allow_html=True)

    t1, t2 = st.tabs(["📊 실시간 현황", "📅 성장 분석 리포트"])
    
    with t1:
        st.subheader("📌 통합 포트폴리오 (원화 환산)")
        disp = df[['Name', 'Category', '매수가(₩)', '현재가(₩)', '수익률(%)', '전일대비(%)', 'Quantity']].copy()
        disp.columns = ['이름', '분류', '매수가(₩)', '현재가(₩)', '수익률', '전일대비', '수량']
        st.dataframe(disp.style.format({'매수가(₩)':'{:,.0f}','현재가(₩)':'{:,.0f}','수익률':'{:+.2f}%','전일대비':'{:+.2f}%','수량':'{:,.2f}'})
                     .applymap(lambda x: 'color: #D90429' if (isinstance(x, float) and x > 0) else ('color: #0077B6' if (isinstance(x, float) and x < 0) else ''), subset=['수익률', '전일대비']), use_container_width=True)
        
        st.subheader("🍕 자산군별 비중")
        st.plotly_chart(px.pie(df, values='평가금액(₩)', names='Category', hole=0.4, template="plotly_white"), use_container_width=True)

    with t2:
        st.subheader("📅 성장 역사 및 종류별 비중")
        if not log_df.empty:
            report = log_df.copy().sort_values('날짜', ascending=False)
            report['자산 변화'] = report['총자산'].diff(periods=-1)
            report['변화율(%)'] = (report['자산 변화'] / report['총자산'].shift(-1)) * 100
            
            # 머스크님의 요청: [날짜, 총자산, 자산 변화, 변화율, 자산종류들...] 순서
            main_cols = ['날짜', '총자산', '자산 변화', '변화율(%)']
            cat_cols = [c for c in report.columns if c not in main_cols]
            st.dataframe(report[main_cols + cat_cols].style.format({
                '총자산': '{:,.0f}', '자산 변화': '{:+,.0f}', '변화율(%)': '{:+.2f}%'
            }).fillna(0), use_container_width=True)
        else:
            st.info("데이터 기록 대기 중 (최초 수정 후 5분 뒤 생성됩니다)")

    st.session_state.refresh_count += 1
    time.sleep(60); st.rerun()
