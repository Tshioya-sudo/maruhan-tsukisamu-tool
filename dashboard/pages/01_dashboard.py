"""
分析ダッシュボード。
ヒートマップ・曜日別/末尾別パターン分析・ホット台一覧。
"""
import sys
import os
import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from scraper.sheets import SheetsManager
from analysis.patterns import (
    analyze_suffix_patterns,
    analyze_day_of_week_patterns,
    analyze_machine_patterns,
    find_hot_units,
)
from analysis.visualize import create_setting_heatmap, create_suffix_chart, create_dow_chart

st.set_page_config(page_title="ダッシュボード", layout="wide")
st.title("📊 ダッシュボード")


@st.cache_data(ttl=300)
def load_data():
    sheets = SheetsManager()
    records = sheets.read_all_daily_data()
    return pd.DataFrame(records)


try:
    df = load_data()
except Exception as e:
    st.error(f"データ読み込みエラー: {e}")
    st.info("Google Sheets認証情報とSPREADSHEET_IDを確認してください。")
    st.stop()

if df.empty:
    st.warning("データがありません。スクレイパーを実行してデータを取得してください。")
    st.stop()

# 数値型に変換
for col in ["estimated_setting", "total_games", "bb_count", "rb_count",
            "combined_prob", "bb_prob", "rb_prob", "unit_number",
            "setting_confidence", "estimated_diff", "day_of_week", "unit_suffix"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

# --- フィルタ ---
st.sidebar.header("フィルタ")
machines = sorted(df["machine_name"].unique())
selected_machine = st.sidebar.selectbox("機種", ["全機種"] + machines)

if selected_machine != "全機種":
    filtered_df = df[df["machine_name"] == selected_machine]
else:
    filtered_df = df

# --- ヒートマップ ---
st.subheader("設定ヒートマップ")
machine_for_heatmap = selected_machine if selected_machine != "全機種" else None
fig_heatmap = create_setting_heatmap(filtered_df, machine_for_heatmap)
st.plotly_chart(fig_heatmap, use_container_width=True)

# --- パターン分析 ---
data_dicts = filtered_df.to_dict("records")

col1, col2 = st.columns(2)

with col1:
    st.subheader("末尾別 高設定出現率")
    suffix_data = analyze_suffix_patterns(data_dicts)
    fig_suffix = create_suffix_chart(suffix_data)
    st.plotly_chart(fig_suffix, use_container_width=True)

with col2:
    st.subheader("曜日別 高設定出現率")
    dow_data = analyze_day_of_week_patterns(data_dicts)
    fig_dow = create_dow_chart(dow_data)
    st.plotly_chart(fig_dow, use_container_width=True)

# --- ホット台一覧 ---
st.subheader("🔥 直近7日間のホット台（複数回高設定）")
hot_units = find_hot_units(data_dicts, days=7, min_high_count=2)
if hot_units:
    hot_df = pd.DataFrame(hot_units)
    hot_df["dates"] = hot_df["dates"].apply(lambda x: ", ".join(x))
    st.dataframe(hot_df, use_container_width=True)
else:
    st.info("直近7日間で複数回高設定が入った台はありません。")

# --- 機種別サマリー ---
st.subheader("機種別 高設定出現率")
machine_data = analyze_machine_patterns(data_dicts)
machine_df = pd.DataFrame([
    {"機種": k, "総データ数": v["total"], "高設定数": v["high"],
     "出現率": f"{v['rate']*100:.1f}%"}
    for k, v in machine_data.items()
]).sort_values("出現率", ascending=False)
st.dataframe(machine_df, use_container_width=True)
