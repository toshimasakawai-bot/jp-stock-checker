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
        records = sheet.get_all_records()
        if not records:
            return [{"ticker": "7203.T", "name_jp": "トヨタ自動車", "name_en": "TOYOTA MOTOR CORP", "buy_price": 2500.0, "shares": 100},
                    {"ticker": "8306.T", "name_jp": "三菱UFJフィナンシャル・G", "name_en": "MITSUBISHI UFJ FINANCIAL", "buy_price": 1200.0, "shares": 100}]
        # 既存データにカラムが足りない場合の補正
        for r in records:
            if "name_jp" not in r: r["name_jp"] = r.get("name", "名称未設定")
            if "name_en" not in r: r["name_en"] = "-"
            if "buy_price" not in r: r["buy_price"] = 0.0
            if "shares" not in r: r["shares"] = 100
        return records
    except Exception:
        return [{"ticker": "7203.T", "name_jp": "トヨタ自動車", "name_en": "TOYOTA MOTOR CORP", "buy_price": 2500.0, "shares": 100}]

def save_portfolio(portfolio):
    sheet.clear()
    headers = ["ticker", "name_jp", "name_en", "buy_price", "shares"]
    rows = [headers] + [[item.get("ticker"), item.get("name_jp"), item.get("name_en"), item.get("buy_price"), item.get("shares")] for item in portfolio]
    sheet.update(rows)

if "portfolio" not in st.session_state:
    st.session_state.portfolio = load_portfolio()

st.title("📈 日本株 配当・株価チェッカー")
st.write("ポートフォリオ管理・購入時利回り算出対応版")

# ==========================================
# 3. 銘柄の追加・削除フォーム
# ==========================================
with st.form("add_ticker_form"):
    st.subheader("➕ 新規銘柄の追加")
    col1, col2 = st.columns(2)
    with col1:
        new_ticker = st.text_input("銘柄コード（例: 7203）", "")
        new_buy_price = st.number_input("購入時株価 (円)", min_value=0.0, value=0.0, step=10.0)
    with col2:
        new_name_jp = st.text_input("銘柄名（日本語）", "")
        new_shares = st.number_input("保有株数", min_value=1, value=100, step=1)
    
    submitted = st.form_submit_button("情報を取得して追加する")
    if submitted and new_ticker:
        clean_code = new_ticker.strip().upper()
        if not clean_code.endswith(".T") and clean_code.isdigit():
            clean_code += ".T"
        
        # すでに登録されているかチェック
        exists = any(item["ticker"] == clean_code for item in st.session_state.portfolio)
        if not exists:
            # yfinanceで英語名や現在価格を取得して自動補完
            fetched_en = clean_code
            try:
                stock = yf.Ticker(clean_code)
                info = stock.info
                fetched_en = info.get("longName", clean_code)
            except Exception:
                pass
            
            display_name_jp = new_name_jp.strip() if new_name_jp.strip() else clean_code

            new_item = {
                "ticker": clean_code,
                "name_jp": display_name_jp,
                "name_en": fetched_en,
                "buy_price": float(new_buy_price),
                "shares": int(new_shares)
            }
            st.session_state.portfolio.append(new_item)
            save_portfolio(st.session_state.portfolio)
            st.success(f"{clean_code} ({display_name_jp}) を追加しました！")
            st.rerun()
        else:
            st.warning("すでにリストに登録されています。")

if st.session_state.portfolio:
    st.subheader("🗑️ 銘柄の削除")
    ticker_options = [f"{item['ticker']} - {item['name_jp']}" for item in st.session_state.portfolio]
    to_remove_label = st.selectbox("削除する銘柄を選択", ticker_options)
    if st.button("選択した銘柄を削除"):
        target_ticker = to_remove_label.split(" - ")[0]
        st.session_state.portfolio = [item for item in st.session_state.portfolio if item["ticker"] != target_ticker]
        save_portfolio(st.session_state.portfolio)
        st.success(f"{target_ticker} を削除しました！")
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
            name_jp = item["name_jp"]
            name_en = item.get("name_en", "-")
            buy_price = item.get("buy_price", 0.0)
            shares = item.get("shares", 0)
            
            try:
                stock = yf.Ticker(t)
                info = stock.info
                
                current_price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
                dividend_rate = info.get("dividendRate") or 0.0 # 1株あたりの年間配当額
                
                # 現在株価ベースの配当利回り
                current_yield = round((dividend_rate / current_price) * 100, 2) if current_price > 0 and dividend_rate > 0 else 0.0
                
                # 購入時株価ベースの配当利回り (配当金 ÷ 購入時株価)
                buy_yield = round((dividend_rate / buy_price) * 100, 2) if buy_price > 0 and dividend_rate > 0 else 0.0

                data_list.append({
                    "銘柄コード": t,
                    "銘柄名(日本語)": name_jp,
                    "銘柄名(英語)": name_en,
                    "現在株価 (円)": current_price,
                    "年間配当 (円)": dividend_rate,
                    "現在利回り (%)": current_yield,
                    "購入時株価 (円)": buy_price,
                    "購入時利回り (%)": buy_yield,
                    "保有株数": shares
                })
            except Exception:
                data_list.append({
                    "銘柄コード": t,
                    "銘柄名(日本語)": name_jp,
                    "銘柄名(英語)": name_en,
                    "現在株価 (円)": 0,
                    "年間配当 (円)": 0,
                    "現在利回り (%)": 0.0,
                    "購入時株価 (円)": buy_price,
                    "購入時利回り (%)": 0.0,
                    "保有株数": shares
                })

    df = pd.DataFrame(data_list)
    st.dataframe(df, use_container_width=True)
