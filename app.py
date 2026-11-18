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
st.write("プレビュー機能付き・ポートフォリオ管理アプリ")

# ==========================================
# 3. 銘柄のプレビュー＆追加セクション
# ==========================================
st.subheader("➕ 新規銘柄の追加")

if "preview_data" not in st.session_state:
    st.session_state.preview_data = None

# コード入力とプレビューボタンを横並び配置
col1, col2 = st.columns([3, 1])
with col1:
    input_ticker = st.text_input("銘柄コード（例: 7203）", value="")
with col2:
    st.write("") # ボタンの位置調整用パディング
    preview_btn = st.button("🔍 プレビュー")

if preview_btn and input_ticker:
    clean_code = input_ticker.strip().upper()
    if not clean_code.endswith(".T") and clean_code.isdigit():
        clean_code += ".T"
    
    with st.spinner("情報を取得中..."):
        try:
            stock = yf.Ticker(clean_code)
            info = stock.info
            name_en = info.get("longName", clean_code)
            current_price = info.get("currentPrice") or info.get("regularMarketPrice") or 0.0
            dividend_rate = info.get("dividendRate") or 0.0
            dividend_yield = round((dividend_rate / current_price) * 100, 2) if current_price > 0 and dividend_rate > 0 else 0.0
            
            st.session_state.preview_data = {
                "ticker": clean_code,
                "name_en": name_en,
                "current_price": current_price,
                "dividend_yield": dividend_yield
            }
        except Exception as e:
            st.error(f"データの取得に失敗しました: {e}")
            st.session_state.preview_data = None

# プレビュー結果が存在する場合のみ、詳細情報と追加フォームを表示
if st.session_state.preview_data:
    p = st.session_state.preview_data
    st.info(f"**【プレビュー結果】**\n\n"
            f"- **銘柄コード**: `{p['ticker']}`\n"
            f"- **英語銘柄名**: `{p['name_en']}`\n"
            f"- **現在の株価**: `{p['current_price']:,} 円`\n"
            f"- **現在の配当利回り**: `{p['dividend_yield']}%`")

    with st.form("register_form"):
        st.write("上記を確認の上、詳細情報を入力して追加してください。")
        reg_name_jp = st.text_input("銘柄名（日本語）", value="")
        reg_buy_price = st.number_input("購入時株価 (円)", min_value=0.0, value=float(p["current_price"]), step=10.0)
        reg_shares = st.number_input("保有株数", min_value=1, value=100, step=1)
        
        submitted = st.form_submit_button("この内容でポートフォリオに追加する")
        if submitted:
            exists = any(item["ticker"] == p["ticker"] for item in st.session_state.portfolio)
            if not exists:
                new_item = {
                    "ticker": p["ticker"],
                    "name_jp": reg_name_jp.strip() if reg_name_jp.strip() else p["name_en"],
                    "name_en": p["name_en"],
                    "buy_price": float(reg_buy_price),
                    "shares": int(reg_shares)
                }
                st.session_state.portfolio.append(new_item)
                save_portfolio(st.session_state.portfolio)
                st.success(f"{p['ticker']} ({new_item['name_jp']}) を追加しました！")
                st.session_state.preview_data = None  # 登録完了後にプレビューをリセット
                st.rerun()
            else:
                st.warning("すでにリストに登録されています。")

st.divider()

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
# 4. 保有銘柄一覧の表示
# ==========================================
st.subheader("📊 保有銘柄一覧")

if not st.session_state.portfolio:
    st.info("銘柄が登録されていません。")
else:
    if st.button("🔄 最新情報を更新"):
        st.rerun()

    data_list = []
    with st.spinner("株価と配当情報を更新中..."):
        for item in st.session_state.portfolio:
            t = item["ticker"]
            name_jp = item["name_jp"]
            name_en = item.get("name_en", "-")
            buy_price = item.get("buy_price", 0.0)
            shares = item.get("shares", 0)
            
            try:
                stock = yf.Ticker(t)
                info = stock.info
                
                current_price = info.get("currentPrice") or info.get("regularMarketPrice") or 0.0
                dividend_rate = info.get("dividendRate") or 0.0
                
                current_yield = round((dividend_rate / current_price) * 100, 2) if current_price > 0 and dividend_rate > 0 else 0.0
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
