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
        # StreamlitのSecretsからパスワードを取得（未設定の場合は "secret123" がデフォルト）
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
    st.error(f"スプレッドシートへの接続に失敗しました。Secretsの設定を確認してください。エラー: {e}")
    st.stop()

def load_tickers():
    try:
        data = sheet.col_values(1)
        if data and data[0].lower() in ["ticker", "銘柄コード", "コード"]:
            data = data[1:]
        return [t.strip() for t in data if t.strip()]
    except Exception:
        return ["7203.T", "8306.T", "9432.T"]

def save_tickers(tickers):
    sheet.clear()
    rows = [["ticker"]] + [[t] for t in tickers]
    sheet.update(rows)

# セッションへの読み込み
if "tickers" not in st.session_state:
    st.session_state.tickers = load_tickers()

st.title("📈 日本株 配当・株価チェッカー")
st.write("Googleスプレッドシートと連携したポートフォリオ管理アプリです。")

# ==========================================
# 3. アプリのUI（追加・削除・一覧）
# ==========================================
with st.form("add_ticker_form"):
    new_ticker = st.text_input("銘柄コード（4桁、例: 7203）を追加", "")
    submitted = st.form_submit_button("銘柄を追加する")
    if submitted and new_ticker:
        clean_code = new_ticker.strip().upper()
        if not clean_code.endswith(".T") and clean_code.isdigit():
            clean_code += ".T"
        
        if clean_code not in st.session_state.tickers:
            st.session_state.tickers.append(clean_code)
            save_tickers(st.session_state.tickers)
            st.success(f"{clean_code} を追加し、スプレッドシートに保存しました！")
            st.rerun()
        else:
            st.warning("すでにリストに登録されています。")

if st.session_state.tickers:
    st.subheader("🗑️ 銘柄の削除")
    to_remove = st.selectbox("削除する銘柄を選択", st.session_state.tickers)
    if st.button("選択した銘柄を削除"):
        st.session_state.tickers.remove(to_remove)
        save_tickers(st.session_state.tickers)
        st.success(f"{to_remove} を削除しました！")
        st.rerun()

st.divider()

st.subheader("📊 保有銘柄一覧")

if not st.session_state.tickers:
    st.info("銘柄が登録されていません。上のフォームから追加してください。")
else:
    if st.button("🔄 最新情報を更新"):
        st.rerun()

    data_list = []
    with st.spinner("株価と配当情報を取得中..."):
        for t in st.session_state.tickers:
            try:
                stock = yf.Ticker(t)
                info = stock.info
                name = info.get("longName", t)
                current_price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
                dividend_yield = info.get("dividendYield")
                
                dividend_yield_val = 0.0 if dividend_yield is None else round(dividend_yield * 100, 2)

                data_list.append({
                    "銘柄コード": t,
                    "銘柄名": name,
                    "株価 (円)": current_price,
                    "配当利回り (%)": dividend_yield_val
                })
            except Exception:
                data_list.append({
                    "銘柄コード": t,
                    "銘柄名": "取得エラー",
                    "株価 (円)": 0,
                    "配当利回り (%)": 0.0
                })

    df = pd.DataFrame(data_list)
    st.dataframe(df, use_container_width=True)
