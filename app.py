import streamlit as st
import yfinance as yf
import pandas as pd

st.set_page_config(page_title="日本株 配当・株価チェッカー", layout="centered")

st.title("📈 日本株 配当・株価チェッカー")
st.write("iPhoneのSafariから確認できるシンプルなポートフォリオ管理アプリです。")

# セッションステートの初期化（アプリ起動中の銘柄リスト）
if "tickers" not in st.session_state:
    st.session_state.tickers = ["7203.T", "8306.T", "9432.T"] # サンプル（トヨタ、三菱UFJ、NTT）

# 銘柄の追加フォーム
with st.form("add_ticker_form"):
    new_ticker = st.text_input("銘柄コード（4桁、例: 7203）を追加", "")
    submitted = st.form_submit_button("銘柄を追加する")
    if submitted and new_ticker:
        clean_code = new_ticker.strip().upper()
        # 4桁の数字なら自動で .T を付与
        if not clean_code.endswith(".T") and clean_code.isdigit():
            clean_code += ".T"
        
        if clean_code not in st.session_state.tickers:
            st.session_state.tickers.append(clean_code)
            st.success(f"{clean_code} を追加しました！")
            st.rerun()
        else:
            st.warning("すでにリストに登録されています。")

# 銘柄の削除セクション
if st.session_state.tickers:
    st.subheader("🗑️ 銘柄の削除")
    to_remove = st.selectbox("削除する銘柄を選択", st.session_state.tickers)
    if st.button("選択した銘柄を削除"):
        st.session_state.tickers.remove(to_remove)
        st.success(f"{to_remove} を削除しました！")
        st.rerun()

st.divider()

# 株価・配当情報の取得と一覧表示
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
                
                # 利回りの計算（yfinanceは小数で取得できるためパーセント変換）
                if dividend_yield is None:
                    dividend_yield_val = 0.0
                else:
                    dividend_yield_val = round(dividend_yield * 100, 2)

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
                    "配当日は取得不可": 0.0
                })

    df = pd.DataFrame(data_list)
    st.dataframe(df, use_container_width=True)
