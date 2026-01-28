import streamlit as st
import pandas as pd
import yfinance as yf
import FinanceDataReader as fdr
from datetime import datetime, timedelta
import plotly.express as px
import os
import time
from difflib import get_close_matches

# 1. UI 및 기본 설정 (원본 문구 및 스타일 보존)
st.set_page_config(layout="wide", page_title="X-Asset Sovereign V25.8", page_icon="🚀")

PORT_FILE = "my_assets_v24.csv"
LOG_FILE = "daily_history_v24.csv"

if "refresh_count" not in st.session_state:
    st.session_state.refresh_count = 0
if "last_change_time" not in st.session_state:
    st.session_state.last_change_time = datetime.now()

st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #1A1C23; }
    .metric-card {
        background: #FFFFFF; padding: 20px; border-radius: 12px;
        border: 1px solid #E9ECEF; text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 15px;
    }
    .metric-label { color: #6C757D; font-size: 14px; font-weight: 600; }
    .metric-value { color: #1A1C23; font-size: 24px; font-weight: 800; margin-top: 8px; }
    </style>
    """, unsafe_allow_html=True)

# 2. 데이터 영속성 로직
def load_db(path):
    if os.path.exists(path):
        try:
            temp_df = pd.read_csv(path)
            # 호환성 유지 (한글 항목명 강제화)
            rename_map = {'Date': '날짜', 'Total_Value': '총자산'}
            temp_df.rename(columns={k: v for k, v in rename_map.items() if k in temp_df.columns}, inplace=True)
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

# 3. 사이드바 - [정밀 검색 및 오류 메시지 강화]
krx_df = get_krx_listing()
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
                # [복구] 유사도 매칭 엔진
                krx_names = krx_df['Name'].tolist() if not krx_df.empty else []
                matches = get_close_matches(search_q, krx_names, n=1, cutoff=0.2)
                
                if matches:
                    actual_name = matches[0]
                    code = krx_df[krx_df['Name'] == actual_name].iloc[0]['Code']
                    ticker = f"{code}.KS"
                    try:
                        if yf.Ticker(ticker).fast_info['last_price'] is None: ticker = f"{code}.KQ"
                    except: ticker = f"{code}.KQ"
                    final_name = n_input if n_input else actual_name
                else:
                    ticker = search_q.upper()
                    final_name = n_input if n_input else search_q

                try:
                    tk = yf.Ticker(ticker)
                    info = tk.fast_info
                    if info['last_price'] is not None:
                        new_row = pd.DataFrame([{'Name': final_name, 'Ticker': ticker, 'BuyPrice': c_p, 'Quantity': c_q, 'Currency': curr, 'Category': category}])
                        st.session_state.portfolio = pd.concat([st.session_state.portfolio, new_row], ignore_index=True)
                        save_db(st.session_state.portfolio, PORT_FILE)
                        st.success(f"✅ {final_name}({ticker}) 추가 성공")
                        st.rerun()
                    else:
                        msg_slot.error(f"❌ '{ticker}'는 유효한 티커가 아닙니다. 다시 확인해주세요.")
                except Exception as e:
                    msg_slot.error(f"❌ 시스템 오류: {str(e)}")

# 4. 분석 엔진 (1분 기록 및 비중 연산)
if not st.session_state.portfolio.empty:
    df = st.session_state.portfolio.copy()
    with st.spinner('Syncing Global Markets...'):
        try: ex_rate = float(yf.download("KRW=X", period="1d", progress=False)['Close'].iloc[-1])
        except: ex_rate = 1350.0

        v_krw, b_krw, cp_krw, bp_krw, chg_1d = [], [], [], [], []
        for _, row in df.iterrows():
            try:
                tk = yf.Ticker(row['Ticker'])
                cp = tk.fast_info['last_price']
                hist = tk.history(period="2d")
                day_chg = ((cp - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2] * 100) if len(hist) >= 2 else 0.0
                m = ex_rate if row['Currency'] == "USD" else 1
                cp_krw.append(cp * m); bp_krw.append(row['BuyPrice'] * m)
                v_krw.append(cp * row['Quantity'] * m); b_krw.append(row['BuyPrice'] * row['Quantity'] * m); chg_1d.append(day_chg)
            except: [x.append(0) for x in [cp_krw, bp_krw, v_krw, b_krw, chg_1d]]

        df['매수가(₩)'], df['현재가(₩)'], df['평가금액(₩)'], df['매입금액(₩)'] = bp_krw, cp_krw, v_krw, b_krw
        df['수익률(%)'] = (df['평가금액(₩)'] - df['매입금액(₩)']) / df['매입금액(₩)'] * 100
        df['전일대비(%)'] = chg_1d
        
        total_val, total_buy = sum(v_krw), sum(b_krw)
        total_prof = total_val - total_buy
        total_roi = (total_prof / total_buy * 100) if total_buy > 0 else 0
        cat_sums = df.groupby('Category')['평가금액(₩)'].sum().to_dict()

        # [1분 대기 기록 로직]
        now_dt = datetime.now().strftime("%Y-%m-%d")
        log_df = load_db(LOG_FILE)
        if (log_df.empty or log_df.iloc[-1]['날짜'] != now_dt) and (datetime.now() > st.session_state.last_change_time + timedelta(minutes=1)):
            new_log = {'날짜': now_dt, '총자산': total_val}
            new_log.update(cat_sums)
            log_df = pd.concat([log_df, pd.DataFrame([new_log])], ignore_index=True)
            save_db(log_df, LOG_FILE)

    # 5. 메인 UI (원본 문구 보존)
    st.title("🏆 X-Asset Sovereign V25.8")
    cols = st.columns(5)
    metrics = [("현재 총 자산가치", f"₩ {total_val:,.0f}"), ("매입 총 자산", f"₩ {total_buy:,.0f}"), ("자산 등락 금액", f"₩ {total_prof:+,.0f}"), ("수익률", f"{total_roi:+,.2f}%"), ("실시간 환율", f"₩ {ex_rate:,.1f}")]
    for i, col in enumerate(cols):
        col.markdown(f'<div class="metric-card"><div class="metric-label">{metrics[i][0]}</div><div class="metric-value">{metrics[i][1]}</div></div>', unsafe_allow_html=True)

    t1, t2 = st.tabs(["📊 실시간 현황", "📅 성장 분석 리포트"])
    
    with t1:
        st.subheader("📌 통합 포트폴리오 (원화 환산)")
        st.dataframe(df[['Name', 'Category', '매수가(₩)', '현재가(₩)', '수익률(%)', '전일대비(%)', 'Quantity']].style.format({'매수가(₩)':'{:,.0f}','현재가(₩)':'{:,.0f}','수익률(%)':'{:+.2f}%','전일대비(%)':'{:+.2f}%','Quantity':'{:,.2f}'})
                     .applymap(lambda x: 'color: #D90429' if (isinstance(x, float) and x > 0) else ('color: #0077B6' if (isinstance(x, float) and x < 0) else ''), subset=['수익률(%)', '전일대비(%)']), use_container_width=True)
        st.plotly_chart(px.pie(df, values='평가금액(₩)', names='Category', hole=0.4, template="plotly_white"), use_container_width=True)

    with t2:
        st.subheader("📅 성장 역사 및 자산별 비중")
        if not log_df.empty:
            report = log_df.copy().sort_values('날짜', ascending=False)
            # [AttributeError/fillna 방어]
            if len(report) > 1:
                report['자산 변화'] = report['총자산'].diff(periods=-1)
                report['변화율(%)'] = (report['자산 변화'] / report['총자산'].shift(-1)) * 100
            else:
                report['자산 변화'], report['변화율(%)'] = 0.0, 0.0
            
            main_cols = ['날짜', '총자산', '자산 변화', '변화율(%)']
            cat_cols = [c for c in report.columns if c not in main_cols]
            # 최종 결측치 처리 후 출력
            final_report = report[main_cols + cat_cols].fillna(0)
            st.dataframe(final_report.style.format({
                '총자산': '{:,.0f}', '자산 변화': '{:+,.0f}', '변화율(%)': '{:+.2f}%'
            }), use_container_width=True)
        else: st.info("기록 대기 중 (1분 뒤 생성)")

    st.session_state.refresh_count += 1
    time.sleep(60); st.rerun()
