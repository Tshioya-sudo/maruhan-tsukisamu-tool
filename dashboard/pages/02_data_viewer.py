"""
データ閲覧ページ。
日付・機種・台番号でフィルタし、CSV/Excelエクスポートが可能。
"""
import sys
import os
import io
from pathlib import Path

_root = Path(__file__).resolve().parent.parent.parent
_site_packages = _root.parent / "Lib" / "site-packages"
if _site_packages.exists():
    sys.path.insert(0, str(_site_packages))
sys.path.insert(0, str(_root))

import streamlit as st
import pandas as pd

from scraper.sheets import SheetsManager

st.set_page_config(page_title="データ閲覧", layout="wide")

try:
    if st.secrets.get("PASSWORD") and not st.session_state.get("authenticated"):
        st.warning("トップページからログインしてください。")
        st.stop()
except (FileNotFoundError, KeyError):
    pass

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

# カラム名の互換対応
COLUMN_MAP = {
    "日付": "play_date", "機種名": "machine_name", "台番号": "unit_number",
    "総G数": "total_games", "BB回数": "bb_count", "RB回数": "rb_count",
    "合算確率": "combined_prob", "BB率": "bb_prob", "RB率": "rb_prob",
    "推定設定": "estimated_setting", "信頼度": "setting_confidence",
    "推定差枚": "estimated_diff", "曜日": "day_of_week", "台番末尾": "unit_suffix",
    "出率": "payout_rate",
}
df = df.rename(columns=COLUMN_MAP)

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
