"""
📱 モバイルビュー — ホール内でスマホから素早く確認するための軽量ページ。
不要なチャート・テーブルを排除し、狙い台情報だけを大きく表示する。
"""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent.parent
_site_packages = _root.parent / "Lib" / "site-packages"
if _site_packages.exists():
    sys.path.insert(0, str(_site_packages))
sys.path.insert(0, str(_root))

import streamlit as st
import pandas as pd

from scraper.sheets import SheetsManager

st.set_page_config(page_title="モバイルビュー", layout="centered")

try:
    if st.secrets.get("PASSWORD") and not st.session_state.get("authenticated"):
        st.warning("トップページからログインしてください。")
        st.stop()
except (FileNotFoundError, KeyError):
    pass

DAY_NAMES = ["月", "火", "水", "木", "金", "土", "日"]


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

COLUMN_MAP = {
    "日付": "play_date", "機種名": "machine_name", "台番号": "unit_number",
    "総G数": "total_games", "BB回数": "bb_count", "RB回数": "rb_count",
    "合算確率": "combined_prob", "BB率": "bb_prob", "RB率": "rb_prob",
    "推定設定": "estimated_setting", "信頼度": "setting_confidence",
    "推定差枚": "estimated_diff", "曜日": "day_of_week", "台番末尾": "unit_suffix",
    "出率": "payout_rate", "店舗名": "store_name",
}
df = df.rename(columns=COLUMN_MAP)

if "store_name" not in df.columns:
    df["store_name"] = "マルハン月寒店"
else:
    df["store_name"] = df["store_name"].fillna("マルハン月寒店").replace("", "マルハン月寒店")

for col in ["estimated_setting", "total_games", "bb_count", "rb_count",
            "unit_number", "estimated_diff", "day_of_week", "unit_suffix"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

# --- 店舗セレクター ---
store_list = sorted(df["store_name"].unique())
selected_store = st.selectbox("🏪 店舗", store_list)
df = df[df["store_name"] == selected_store]

st.title("📱 モバイルビュー")
st.caption(f"{selected_store}")

latest_date = df["play_date"].max()
st.markdown(f"**最新データ: {latest_date}**")

# --- 1. 今日座るべき台 TOP5 ---
st.markdown("---")
st.subheader("🎯 狙い台 TOP5")
st.caption("直近の高設定出現回数が多い台番号")

# 直近7日分のデータで高設定回数をカウント
dates_sorted = sorted(df["play_date"].unique(), reverse=True)
recent_dates = dates_sorted[:7]
recent_df = df[df["play_date"].isin(recent_dates)]

high_setting = recent_df[recent_df["estimated_setting"] >= 4]
if not high_setting.empty:
    top_units = (
        high_setting.groupby(["machine_name", "unit_number"])
        .agg(
            high_count=("estimated_setting", "count"),
            avg_setting=("estimated_setting", "mean"),
        )
        .sort_values("high_count", ascending=False)
        .head(5)
        .reset_index()
    )
    for _, row in top_units.iterrows():
        unit = int(row["unit_number"])
        st.markdown(
            f"### 🔥 {row['machine_name']} **{unit}番台**\n"
            f"高設定 **{int(row['high_count'])}回** / 7日間　"
            f"平均設定 **{row['avg_setting']:.1f}**"
        )
else:
    st.info("直近7日間に高設定データがありません")

# --- 2. 今日の狙い末尾 ---
st.markdown("---")
st.subheader("🔢 狙い末尾")

from datetime import datetime
today_dow = datetime.now().weekday()
dow_data = df[df["day_of_week"] == today_dow]
if not dow_data.empty:
    high_dow = dow_data[dow_data["estimated_setting"] >= 4]
    if not high_dow.empty:
        suffix_counts = high_dow["unit_suffix"].value_counts().head(3)
        day_name = DAY_NAMES[today_dow]
        st.markdown(f"**{day_name}曜日** に高設定が多い末尾:")
        for suffix, count in suffix_counts.items():
            total = len(dow_data[dow_data["unit_suffix"] == suffix])
            rate = count / total * 100 if total > 0 else 0
            st.markdown(f"### 末尾 **{int(suffix)}** → 高設定率 **{rate:.0f}%** ({int(count)}/{total})")
    else:
        st.info(f"{DAY_NAMES[today_dow]}曜日の高設定データが不足しています")
else:
    st.info(f"{DAY_NAMES[today_dow]}曜日のデータがありません")

# --- 3. 据え置き候補（前日高設定台） ---
st.markdown("---")
st.subheader("📌 据え置き候補")
st.caption("前日に高設定だった台（据え置きの可能性）")

if len(dates_sorted) >= 1:
    prev_date = dates_sorted[0]
    prev_data = df[(df["play_date"] == prev_date) & (df["estimated_setting"] >= 4)]
    if not prev_data.empty:
        prev_data = prev_data.sort_values("estimated_setting", ascending=False)
        st.markdown(f"**{prev_date}** の高設定台:")
        for _, row in prev_data.head(8).iterrows():
            unit = int(row["unit_number"])
            setting = int(row["estimated_setting"])
            games = int(row["total_games"]) if pd.notna(row["total_games"]) else 0
            st.markdown(
                f"- {row['machine_name']} **{unit}番台** "
                f"(設定{setting}, {games:,}G)"
            )
    else:
        st.info(f"{prev_date}: 高設定台なし")
else:
    st.info("データがありません")
