import streamlit as st
import yfinance as yf
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="日本株 配当・株価チェッカー", layout="centered")

# ==========================================
# 1. パスワード認証機能
# ==========================================
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False

    if st.session_state.password_correct:
        return True

    st.title("🔒 認証が必要です")
    password = st.text_input("パスワードを入力してください", type="password")
    if st.button("ログイン"):
        correct_password = st.secrets.get("APP_PASSWORD", "secret123")
        if password == correct_password:
            st.session_state.password_correct = True
            st.rerun()
        else:
            st.error("パスワードが違います")
    return False

if not check_password():
    st.stop()

# ==========================================
# 2. Googleスプレッドシート連携
# ==========================================
@st.cache_resource
def init_sheet_connection():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    sheet_url = st.secrets["SHEET_URL"]
    return client.open_by_url(sheet_url).sheet1

try:
    sheet = init_sheet_connection()
except Exception as e:
    st.error(f"スプレッドシートへの接続に失敗しました。エラー: {e}")
    st.stop()

def load_portfolio():
    try:
        # スプレッドシートからレコードを取得 (A列: ticker, B列: name)
        records = sheet.get_all_records()
        if not records:
            return [{"ticker": "7203.T", "name": "トヨタ自動車"},
                    {"ticker": "8306.T", "name": "三菱UFJフィナンシャル・G"},
                    {"ticker": "9432.T", "name": "日本電信電話"}]
        return records
    except Exception:
        # 旧形式（1列のみ）のデータが存在した場合の互換用フォールバック
        data = sheet.col_values(1)
        if data and data[0].lower() in ["ticker", "銘柄コード", "コード"]:
            data = data[1:]
        return [{"ticker": t.strip(), "name": t.strip()} for t in data if t.strip()]

def save_portfolio(portfolio):
    sheet.clear()
    rows = [["ticker", "name"]] + [[item["ticker"], item["name"]] for item in portfolio]
    sheet.update(rows)

# セッションへの読み込み
if "portfolio" not in st.session_state:
    st.session_state.portfolio = load_portfolio()

st.title("📈 日本株 配当・株価チェッカー")
st.write("スプレッドシート連動版（日本語名・正しい利回り対応）")

# ==========================================
# 3. 銘柄の追加・削除フォーム
# ==========================================
with st.form("add_ticker_form"):
    col1, col2 = st.columns(2)
    with col1:
        new_ticker = st.text_input("銘柄コード（例: 7203）", "")
    with col2:
        new_name = st.text_input("銘柄名（任意・日本語可）", "")
    
    submitted = st.form_submit_button("銘柄を追加する")
    if submitted and new_ticker:
        clean_code = new_ticker.strip().upper()
        if not clean_code.endswith(".T") and clean_code.isdigit():
            clean_code += ".T"
        
        display_name = new_name.strip() if new_name.strip() else clean_code
        
        # すでに登録されているかチェック
        exists = any(item["ticker"] == clean_code for item in st.session_state.portfolio)
        if not exists:
            st.session_state.portfolio.append({"ticker": clean_code, "name": display_name})
            save_portfolio(st.session_state.portfolio)
            st.success(f"{clean_code} ({display_name}) を追加しました！")
            st.rerun()
        else:
            st.warning("すでにリストに登録されています。")

if st.session_state.portfolio:
    st.subheader("🗑️ 銘柄の削除")
    ticker_options = [item["ticker"] for item in st.session_state.portfolio]
    to_remove = st.selectbox("削除する銘柄を選択", ticker_options)
    if st.button("選択した銘柄を削除"):
        st.session_state.portfolio = [item for item in st.session_state.portfolio if item["ticker"] != to_remove]
        save_portfolio(st.session_state.portfolio)
        st.success(f"{to_remove} を削除しました！")
        st.rerun()

st.divider()

# ==========================================
# 4. 株価・配当情報の取得と一覧表示
# ==========================================
st.subheader("📊 保有銘柄一覧")

if not st.session_state.portfolio:
    st.info("銘柄が登録されていません。")
else:
    if st.button("🔄 最新情報を更新"):
        st.rerun()

    data_list = []
    with st.spinner("株価と配当情報を取得中..."):
        for item in st.session_state.portfolio:
            t = item["ticker"]
            default_name = item["name"]
            try:
                stock = yf.Ticker(t)
                info = stock.info
                
                # 株価の取得
                current_price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
                
                # 配当利回りの計算（yfinanceのdividendRate(年間配当額)から正確に算出）
                dividend_rate = info.get("dividendRate") # 1株あたりの年間配当（円）
                dividend_yield = info.get("dividendYield")
                
                if dividend_rate and current_price and current_price > 0:
                    dividend_yield_val = round((dividend_rate / current_price) * 100, 2)
                elif dividend_yield is not None:
                    dividend_yield_val = round(dividend_yield * 100, 2)
                else:
                    dividend_yield_val = 0.0

                data_list.append({
                    "銘柄コード": t,
                    "銘柄名": default_name,
                    "株価 (円)": current_price,
                    "年間配当 (円)": dividend_rate if dividend_rate else 0,
                    "配当利回り (%)": dividend_yield_val
                })
            except Exception:
                data_list.append({
                    "銘柄コード": t,
                    "銘柄名": default_name,
                    "株価 (円)": 0,
                    "年間配当 (円)": 0,
                    "配当利回り (%)": 0.0
                })

    df = pd.DataFrame(data_list)
    st.dataframe(df, use_container_width=True)
    
    st.info("💡 ヒント: Googleスプレッドシート側で直接2列目（銘柄名）を日本語に書き換えても、アプリにそのまま反映されます。")
