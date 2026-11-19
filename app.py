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
            return [
                {"ticker": "7203.T", "name_jp": "トヨタ自動車", "name_en": "TOYOTA MOTOR CORP", "buy_price": 2500.0, "shares": 100},
                {"ticker": "8306.T", "name_jp": "三菱UFJフィナンシャル・G", "name_en": "MITSUBISHI UFJ FINANCIAL", "buy_price": 1200.0, "shares": 100},
            ]
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
    rows = [headers] + [
        [item.get("ticker"), item.get("name_jp"), item.get("name_en"), item.get("buy_price"), item.get("shares")]
        for item in portfolio
    ]
    sheet.update(rows)

if "portfolio" not in st.session_state:
    st.session_state.portfolio = load_portfolio()

st.title("📈 日本株 配当・株価チェッカー")
st.write("キャッシュ最適化・レート制限対策版")

# ==========================================
# 3. yfinance データ取得（1時間キャッシュ）
# ==========================================
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_stock_bundle(ticker: str):
    """
    1銘柄分の株価・年間配当・過去5年履歴をまとめて取得し、1時間キャッシュする。
    レート制限対策として info / fast_info / history を段階的にフォールバックする。
    """
    stock = yf.Ticker(ticker)

    # 過去5年分の日足取得（トレンド判定・割安判定・現在価格フォールバックに共用）
    hist_5y = pd.DataFrame()
    try:
        hist_5y = stock.history(period="5y")
    except Exception:
        hist_5y = pd.DataFrame()

    # 配当履歴取得
    divs = pd.Series(dtype="float64")
    try:
        divs = stock.dividends
    except Exception:
        divs = pd.Series(dtype="float64")

    # info / fast_info 取得
    info = {}
    try:
        info = stock.info or {}
    except Exception:
        info = {}

    name_en = info.get("longName") or info.get("shortName") or ticker

    # 現在株価の決定（info -> fast_info -> hist_5y終値 の順でフォールバック）
    current_price = info.get("currentPrice") or info.get("regularMarketPrice")
    if not current_price:
        try:
            current_price = getattr(stock.fast_info, "last_price", None)
        except Exception:
            current_price = None
    if not current_price and not hist_5y.empty and "Close" in hist_5y.columns:
        last_close = hist_5y["Close"].dropna()
        if not last_close.empty:
            current_price = float(last_close.iloc[-1])

    current_price = float(current_price) if current_price and current_price > 0 else None

    # 年間配当額（1株あたり）の決定（info.dividendRate -> 直近1年の配当合計）
    dividend_rate = info.get("dividendRate")
    if (dividend_rate is None or dividend_rate <= 0) and not divs.empty:
        divs_naive = divs.copy()
        if getattr(divs_naive.index, "tz", None) is not None:
            divs_naive.index = divs_naive.index.tz_localize(None)
        one_year_ago = pd.Timestamp.now().tz_localize(None) - pd.Timedelta(days=365)
        recent_divs = divs_naive[divs_naive.index >= one_year_ago]
        if not recent_divs.empty:
            dividend_rate = float(recent_divs.sum())

    dividend_rate = float(dividend_rate) if dividend_rate and dividend_rate > 0 else 0.0

    # 割高/割安判定（過去5年・パーセンタイル方式）
    valuation = "データ不足"
    current_yield = round((dividend_rate / current_price) * 100, 2) if (current_price and dividend_rate > 0) else 0.0

    try:
        if not hist_5y.empty and not divs.empty and current_price and current_price > 0 and "Close" in hist_5y.columns:
            h_df = hist_5y.copy()
            d_ser = divs.copy()
            if getattr(h_df.index, "tz", None) is not None:
                h_df.index = h_df.index.tz_localize(None)
            if getattr(d_ser.index, "tz", None) is not None:
                d_ser.index = d_ser.index.tz_localize(None)

            full_date_range = pd.date_range(start=h_df.index.min(), end=h_df.index.max(), freq="D")
            div_daily = d_ser.resample("D").sum().reindex(full_date_range, fill_value=0.0)
            annual_div_series = div_daily.rolling(window=365, min_periods=1).sum()

            historical_yields = []
            for dt, row in h_df.iterrows():
                close = row["Close"]
                if pd.notna(close) and close > 0:
                    d_sum = annual_div_series.asof(dt)
                    if pd.notna(d_sum) and d_sum > 0:
                        historical_yields.append((float(d_sum) / float(close)) * 100.0)

            if len(historical_yields) >= 30:
                s = pd.Series(historical_yields)
                p75 = s.quantile(0.75)
                p25 = s.quantile(0.25)
                if current_yield >= p75:
                    valuation = "割安 🟢"
                elif current_yield <= p25:
                    valuation = "割高 🔴"
                else:
                    valuation = "適正 ⚪"
    except Exception:
        valuation = "判定不能"

    # トレンド判定（200日移動平均線 + 20営業日前の傾き）
    trend = "データ不足"
    try:
        if not hist_5y.empty and "Close" in hist_5y.columns:
            h_trend = hist_5y["Close"].dropna().to_frame(name="Close")
            if len(h_trend) >= 220:
                h_trend["MA200"] = h_trend["Close"].rolling(window=200).mean()
                h_trend = h_trend.dropna(subset=["MA200"])
                if len(h_trend) >= 20:
                    px_now = float(h_trend["Close"].iloc[-1])
                    ma_now = float(h_trend["MA200"].iloc[-1])
                    ma_prev = float(h_trend["MA200"].iloc[-20])
                    if px_now > ma_now and ma_now > ma_prev:
                        trend = "上昇トレンド 📈"
                    elif px_now < ma_now and ma_now < ma_prev:
                        trend = "下降トレンド 📉"
                    else:
                        trend = "レンジ / 停滞 〰️"
    except Exception:
        trend = "判定不能"

    return {
        "name_en": name_en,
        "current_price": current_price,
        "dividend_rate": dividend_rate,
        "current_yield": current_yield,
        "valuation": valuation,
        "trend": trend,
    }

# ==========================================
# 4. 銘柄のプレビュー＆追加セクション
# ==========================================
st.subheader("➕ 新規銘柄の追加")

if "preview_data" not in st.session_state:
    st.session_state.preview_data = None

col1, col2 = st.columns([3, 1])
with col1:
    input_ticker = st.text_input("銘柄コード（例: 7203）", value="")
with col2:
    st.write("")
    preview_btn = st.button("🔍 プレビュー")

if preview_btn and input_ticker:
    clean_code = input_ticker.strip().upper()
    if not clean_code.endswith(".T") and clean_code.isdigit():
        clean_code += ".T"

    with st.spinner("情報を取得中..."):
        bundle = fetch_stock_bundle(clean_code)
        if bundle["current_price"] is not None:
            st.session_state.preview_data = {
                "ticker": clean_code,
                "name_en": bundle["name_en"],
                "current_price": bundle["current_price"],
                "dividend_yield": bundle["current_yield"],
            }
        else:
            st.warning("現在株価を取得できませんでした。銘柄コードやYahoo Financeの制限をご確認ください。")
            st.session_state.preview_data = None

if st.session_state.preview_data:
    p = st.session_state.preview_data
    st.info(
        f"**【プレビュー結果】**\n\n"
        f"- **銘柄コード**: `{p['ticker']}`\n"
        f"- **英語銘柄名**: `{p['name_en']}`\n"
        f"- **現在の株価**: `{p['current_price']:,} 円`\n"
        f"- **現在の配当利回り**: `{p['dividend_yield']}%`"
    )

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
                    "shares": int(reg_shares),
                }
                st.session_state.portfolio.append(new_item)
                save_portfolio(st.session_state.portfolio)
                st.success(f"{p['ticker']} ({new_item['name_jp']}) を追加しました！")
                st.session_state.preview_data = None
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
# 5. 保有銘柄一覧の表示
# ==========================================
st.subheader("📊 保有銘柄一覧 ＆ 分析")

if not st.session_state.portfolio:
    st.info("銘柄が登録されていません。")
else:
    col_ref1, col_ref2 = st.columns([1, 2])
    with col_ref1:
        if st.button("🔄 最新情報・分析を更新"):
            fetch_stock_bundle.clear()
            st.rerun()
    with col_ref2:
        st.caption("※データは1時間キャッシュされます。今すぐ最新取得したい場合は更新ボタンを押してください。")

    data_list = []
    has_missing_price = False

    with st.spinner("株価データ取得および分析を実行中..."):
        for item in st.session_state.portfolio:
            t = item["ticker"]
            name_jp = item["name_jp"]
            buy_price = float(item.get("buy_price", 0.0))
            shares = int(item.get("shares", 0))

            bundle = fetch_stock_bundle(t)
            current_price = bundle["current_price"]
            dividend_rate = bundle["dividend_rate"]
            current_yield = bundle["current_yield"]

            if current_price is None:
                has_missing_price = True
                display_price = "取得失敗"
                buy_yield = "-"
            else:
                display_price = current_price
                buy_yield = round((dividend_rate / buy_price) * 100, 2) if (buy_price > 0 and dividend_rate > 0) else 0.0

            data_list.append({
                "銘柄コード": t,
                "銘柄名(日本語)": name_jp,
                "現在株価 (円)": display_price,
                "購入時株価 (円)": buy_price,
                "現在利回り (%)": current_yield if current_price is not None else "-",
                "購入時利回り (%)": buy_yield,
                "割高/割安判定": bundle["valuation"],
                "トレンド判定": bundle["trend"],
                "保有株数": shares,
            })

    if has_missing_price:
        st.warning("一部銘柄の株価が取得できませんでした。Yahoo Finance側のアクセス制限が起きている可能性があるため、時間を置いて「🔄 最新情報・分析を更新」をお試しください。")

    df = pd.DataFrame(data_list)
    st.dataframe(df, use_container_width=True)
