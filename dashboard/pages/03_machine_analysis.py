"""
機種別分析ページ。
機種ごとの設定分布・台別確率推移グラフ。
"""
import sys
import os
import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from scraper.sheets import SheetsManager
from analysis.visualize import create_setting_heatmap, create_reg_trend

st.set_page_config(page_title="機種別分析", layout="wide")
st.title("🔍 機種別分析")


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

# --- 機種選択 ---
machines = sorted(df["machine_name"].unique())
selected_machine = st.selectbox("機種を選択", machines)

machine_df = df[df["machine_name"] == selected_machine]

# --- 基本統計 ---
st.subheader(f"{selected_machine} - 基本統計")
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("データ日数", machine_df["play_date"].nunique())
with col2:
    st.metric("台数", machine_df["unit_number"].nunique())
with col3:
    avg_games = machine_df["total_games"].mean()
    st.metric("平均G数", f"{avg_games:,.0f}" if pd.notna(avg_games) else "-")
with col4:
    high_rate = (
        machine_df["estimated_setting"].dropna() >= 4
    ).mean() * 100
    st.metric("高設定率", f"{high_rate:.1f}%")

# --- 設定ヒートマップ ---
st.subheader("設定ヒートマップ")
fig_heatmap = create_setting_heatmap(machine_df, selected_machine)
st.plotly_chart(fig_heatmap, use_container_width=True)

# --- 設定分布 ---
st.subheader("設定分布")
setting_counts = machine_df["estimated_setting"].dropna().value_counts().sort_index()
st.bar_chart(setting_counts)

# --- 台別詳細 ---
st.subheader("台別 ボーナス確率推移")
units = sorted(machine_df["unit_number"].dropna().unique().astype(int))
selected_unit = st.selectbox("台番号", units)

if selected_unit:
    fig_trend = create_reg_trend(machine_df, selected_machine, selected_unit)
    st.plotly_chart(fig_trend, use_container_width=True)

    # 選択した台のデータ一覧
    unit_data = machine_df[machine_df["unit_number"] == selected_unit].sort_values(
        "play_date", ascending=False
    )
    st.dataframe(unit_data[
        ["play_date", "total_games", "bb_count", "rb_count",
         "combined_prob", "bb_prob", "rb_prob", "estimated_setting",
         "setting_confidence"]
    ], use_container_width=True)
