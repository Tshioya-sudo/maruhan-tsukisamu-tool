"""
データ閲覧ページ。
日付・機種・台番号でフィルタし、CSV/Excelエクスポートが可能。
"""
import sys
import os
import io
import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from scraper.sheets import SheetsManager

st.set_page_config(page_title="データ閲覧", layout="wide")
st.title("📋 データ閲覧")


@st.cache_data(ttl=300)
def load_data():
    sheets = SheetsManager()
    records = sheets.read_all_daily_data()
    return pd.DataFrame(records)


try:
    df = load_data()
except Exception as e:
    st.error(f"データ読み込みエラー: {e}")
    st.stop()

if df.empty:
    st.warning("データがありません。")
    st.stop()

# 数値型に変換
for col in ["estimated_setting", "total_games", "bb_count", "rb_count",
            "combined_prob", "bb_prob", "rb_prob", "unit_number",
            "setting_confidence", "estimated_diff"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

# --- フィルタ ---
st.sidebar.header("フィルタ条件")

dates = sorted(df["play_date"].unique(), reverse=True)
selected_dates = st.sidebar.multiselect("日付", dates, default=dates[:3] if dates else [])

machines = sorted(df["machine_name"].unique())
selected_machines = st.sidebar.multiselect("機種", machines, default=machines)

min_setting = st.sidebar.slider("推定設定（以上）", 1, 6, 1)

unit_filter = st.sidebar.text_input("台番号（部分一致）", "")

# フィルタ適用
filtered = df.copy()
if selected_dates:
    filtered = filtered[filtered["play_date"].isin(selected_dates)]
if selected_machines:
    filtered = filtered[filtered["machine_name"].isin(selected_machines)]
filtered = filtered[
    filtered["estimated_setting"].fillna(0) >= min_setting
]
if unit_filter:
    filtered = filtered[
        filtered["unit_number"].astype(str).str.contains(unit_filter)
    ]

# --- 表示 ---
st.subheader(f"検索結果: {len(filtered)}件")
st.dataframe(
    filtered.sort_values(["play_date", "machine_name", "unit_number"],
                         ascending=[False, True, True]),
    use_container_width=True,
)

# --- エクスポート ---
st.subheader("データエクスポート")
col1, col2 = st.columns(2)

with col1:
    csv = filtered.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="📥 CSVダウンロード",
        data=csv,
        file_name="maruhan_data.csv",
        mime="text/csv",
    )

with col2:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        filtered.to_excel(writer, index=False, sheet_name="data")
    st.download_button(
        label="📥 Excelダウンロード",
        data=buffer.getvalue(),
        file_name="maruhan_data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
