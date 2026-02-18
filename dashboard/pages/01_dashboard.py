"""
分析ダッシュボード。
ヒートマップ・曜日別/末尾別パターン分析・旧イベント日分析・ホット台一覧。
"""
import sys
import os
from pathlib import Path

# パス設定
_root = Path(__file__).resolve().parent.parent.parent
_site_packages = _root.parent / "Lib" / "site-packages"
if _site_packages.exists():
    sys.path.insert(0, str(_site_packages))
sys.path.insert(0, str(_root))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from scraper.sheets import SheetsManager
from analysis.patterns import (
    analyze_suffix_patterns,
    analyze_day_of_week_patterns,
    analyze_machine_patterns,
    find_hot_units,
)
from analysis.visualize import create_setting_heatmap, create_suffix_chart, create_dow_chart

st.set_page_config(page_title="ダッシュボード", layout="wide")
st.title("📊 マルハン月寒 分析ダッシュボード")


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

# カラム名の互換対応（日本語ヘッダー/英語ヘッダーどちらでも動くように）
COLUMN_MAP = {
    "日付": "play_date", "機種名": "machine_name", "台番号": "unit_number",
    "総G数": "total_games", "BB回数": "bb_count", "RB回数": "rb_count",
    "合算確率": "combined_prob", "BB率": "bb_prob", "RB率": "rb_prob",
    "推定設定": "estimated_setting", "信頼度": "setting_confidence",
    "推定差枚": "estimated_diff", "曜日": "day_of_week", "台番末尾": "unit_suffix",
}
df = df.rename(columns=COLUMN_MAP)

# 数値型に変換
for col in ["estimated_setting", "total_games", "bb_count", "rb_count",
            "combined_prob", "bb_prob", "rb_prob", "unit_number",
            "setting_confidence", "estimated_diff", "day_of_week", "unit_suffix"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

# --- 概要 ---
st.markdown(f"**データ期間:** {df['play_date'].min()} 〜 {df['play_date'].max()}　|　**総レコード数:** {len(df):,}件　|　**日数:** {df['play_date'].nunique()}日")

# --- フィルタ ---
st.sidebar.header("フィルタ")
machines = sorted(df["machine_name"].unique())
selected_machine = st.sidebar.selectbox("機種", ["全機種"] + list(machines))

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

# --- 旧イベント日分析（7のつく日: 7日・17日・27日）---
st.subheader("🎯 旧イベント日分析（7のつく日: 7日・17日・27日）")

def is_event_day(date_str):
    """7のつく日かどうか判定"""
    try:
        day = int(date_str.split("-")[2])
        return day in (7, 17, 27)
    except Exception:
        return False

filtered_df = filtered_df.copy()
filtered_df["is_event"] = filtered_df["play_date"].apply(is_event_day)

event_df = filtered_df[filtered_df["is_event"]]
normal_df = filtered_df[~filtered_df["is_event"]]

col_ev1, col_ev2, col_ev3 = st.columns(3)

with col_ev1:
    event_high = event_df["estimated_setting"].dropna()
    event_rate = (event_high >= 4).mean() * 100 if len(event_high) > 0 else 0
    st.metric("旧イベント日 高設定率", f"{event_rate:.1f}%",
              help=f"対象日数: {event_df['play_date'].nunique()}日, データ数: {len(event_high)}")

with col_ev2:
    normal_high = normal_df["estimated_setting"].dropna()
    normal_rate = (normal_high >= 4).mean() * 100 if len(normal_high) > 0 else 0
    st.metric("通常日 高設定率", f"{normal_rate:.1f}%",
              help=f"対象日数: {normal_df['play_date'].nunique()}日, データ数: {len(normal_high)}")

with col_ev3:
    diff = event_rate - normal_rate
    st.metric("差分", f"{diff:+.1f}%",
              delta=f"{'旧イベント日が高い' if diff > 0 else '通常日が高い'}",
              delta_color="normal" if diff > 0 else "inverse")

# 旧イベント日の末尾傾向
if len(event_df) > 0:
    event_dicts = event_df.to_dict("records")
    event_suffix = analyze_suffix_patterns(event_dicts)
    st.markdown("**旧イベント日の末尾別 高設定率:**")
    suffix_items = []
    for s in range(10):
        info = event_suffix.get(s, {})
        rate = info.get("rate", 0) * 100
        total = info.get("total", 0)
        if total > 0:
            suffix_items.append(f"末尾{s}: {rate:.0f}% (n={total})")
    st.text("　".join(suffix_items))
else:
    st.info("旧イベント日のデータがまだありません。")

# --- ホット台一覧 ---
st.subheader("🔥 直近7日間のホット台（複数回高設定）")
all_dicts = df.to_dict("records")
hot_units = find_hot_units(all_dicts, days=7, min_high_count=2)
if hot_units:
    hot_df = pd.DataFrame(hot_units)
    hot_df.columns = ["機種名", "台番号", "高設定回数", "日付"]
    hot_df["日付"] = hot_df["日付"].apply(lambda x: ", ".join(x))
    st.dataframe(hot_df, use_container_width=True)
else:
    st.info("直近7日間で複数回高設定が入った台はありません。")

# --- 機種別サマリー ---
st.subheader("機種別 高設定出現率")
machine_data = analyze_machine_patterns(all_dicts)
machine_df = pd.DataFrame([
    {"機種": k, "総データ数": v["total"], "高設定数": v["high"],
     "出現率": f"{v['rate']*100:.1f}%"}
    for k, v in machine_data.items()
]).sort_values("出現率", ascending=False)
st.dataframe(machine_df, use_container_width=True)
