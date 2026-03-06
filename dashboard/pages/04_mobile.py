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
from datetime import datetime

from scraper.sheets import SheetsManager

st.set_page_config(page_title="モバイルビュー", layout="centered")

# モバイル向けCSS
st.markdown("""
<style>
    /* 全体のフォントサイズを大きく */
    .block-container { padding-top: 1rem; padding-bottom: 1rem; }
    /* カード風スタイル */
    .target-card {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 12px;
        border-left: 4px solid #e94560;
        color: #ffffff;
    }
    .target-card h4 { margin: 0 0 4px 0; color: #e94560; font-size: 1.1rem; }
    .target-card .unit-num { font-size: 1.8rem; font-weight: bold; color: #ffffff; }
    .target-card .detail { color: #a0a0b0; font-size: 0.85rem; }
    .suffix-badge {
        display: inline-block;
        background: #e94560;
        color: white;
        border-radius: 50%;
        width: 48px;
        height: 48px;
        line-height: 48px;
        text-align: center;
        font-size: 1.4rem;
        font-weight: bold;
        margin: 4px 8px 4px 0;
    }
    .section-header {
        background: #0a3d62;
        color: white;
        padding: 8px 12px;
        border-radius: 8px;
        margin: 16px 0 8px 0;
        font-size: 1.1rem;
    }
    .hold-card {
        background: linear-gradient(135deg, #1a1a2e 0%, #0a3d62 100%);
        border-radius: 12px;
        padding: 12px 16px;
        margin-bottom: 8px;
        border-left: 4px solid #38ada9;
        color: #ffffff;
    }
    .hold-card .machine { color: #38ada9; font-size: 0.9rem; }
    .hold-card .unit-num { font-size: 1.3rem; font-weight: bold; }
    .hold-card .detail { color: #a0a0b0; font-size: 0.85rem; }
</style>
""", unsafe_allow_html=True)

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

# --- ヘッダー ---
today_dow = datetime.now().weekday()
day_name = DAY_NAMES[today_dow]
latest_date = df["play_date"].max()

st.markdown(f"## 📱 {day_name}曜日の狙い目")
st.caption(f"最新データ: {latest_date}")

# --- 1. 狙い台 TOP5 ---
st.markdown('<div class="section-header">🎯 狙い台 TOP5（直近7日）</div>', unsafe_allow_html=True)

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
            max_setting=("estimated_setting", "max"),
        )
        .sort_values("high_count", ascending=False)
        .head(5)
        .reset_index()
    )
    for i, row in top_units.iterrows():
        unit = int(row["unit_number"])
        count = int(row["high_count"])
        avg = row["avg_setting"]
        st.markdown(
            f'<div class="target-card">'
            f'<h4>{row["machine_name"]}</h4>'
            f'<span class="unit-num">{unit}番台</span><br>'
            f'<span class="detail">高設定 {count}回/7日 ｜ 平均設定 {avg:.1f}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
else:
    st.info("直近7日間に高設定データがありません")

# --- 2. 今日の狙い末尾 ---
st.markdown(f'<div class="section-header">🔢 {day_name}曜日の狙い末尾</div>', unsafe_allow_html=True)

dow_data = df[df["day_of_week"] == today_dow]
if not dow_data.empty:
    high_dow = dow_data[dow_data["estimated_setting"] >= 4]
    if not high_dow.empty:
        suffix_counts = high_dow["unit_suffix"].value_counts().head(3)
        badges_html = ""
        for suffix, count in suffix_counts.items():
            total = len(dow_data[dow_data["unit_suffix"] == suffix])
            rate = count / total * 100 if total > 0 else 0
            badges_html += (
                f'<span class="suffix-badge">{int(suffix)}</span>'
            )
        st.markdown(badges_html, unsafe_allow_html=True)
        for suffix, count in suffix_counts.items():
            total = len(dow_data[dow_data["unit_suffix"] == suffix])
            rate = count / total * 100 if total > 0 else 0
            st.markdown(f"末尾 **{int(suffix)}** → 高設定率 **{rate:.0f}%**（{int(count)}/{total}）")
    else:
        st.info(f"{day_name}曜日の高設定データが不足しています")
else:
    st.info(f"{day_name}曜日のデータがありません")

# --- 3. 据え置き候補（前日高設定台） ---
st.markdown('<div class="section-header">📌 据え置き候補（前日の高設定台）</div>', unsafe_allow_html=True)

if len(dates_sorted) >= 1:
    prev_date = dates_sorted[0]
    prev_data = df[(df["play_date"] == prev_date) & (df["estimated_setting"] >= 4)]
    if not prev_data.empty:
        prev_data = prev_data.sort_values("estimated_setting", ascending=False)
        st.caption(f"{prev_date} の高設定台")
        for _, row in prev_data.head(8).iterrows():
            unit = int(row["unit_number"])
            setting = int(row["estimated_setting"])
            games = int(row["total_games"]) if pd.notna(row["total_games"]) else 0
            st.markdown(
                f'<div class="hold-card">'
                f'<span class="machine">{row["machine_name"]}</span><br>'
                f'<span class="unit-num">{unit}番台</span>'
                f'<span class="detail">（設定{setting} / {games:,}G）</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
    else:
        st.info(f"{prev_date}: 高設定台なし")
else:
    st.info("データがありません")
