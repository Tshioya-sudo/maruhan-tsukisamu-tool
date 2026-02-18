"""
分析ダッシュボード（狙い目特化版）
一番上に「今日の狙い目」、下に根拠データを表示。
"""
import sys
from pathlib import Path
from datetime import datetime

_root = Path(__file__).resolve().parent.parent.parent
_site_packages = _root.parent / "Lib" / "site-packages"
if _site_packages.exists():
    sys.path.insert(0, str(_site_packages))
sys.path.insert(0, str(_root))

import streamlit as st
import pandas as pd

from scraper.sheets import SheetsManager
from analysis.patterns import (
    analyze_suffix_patterns,
    analyze_day_of_week_patterns,
    analyze_machine_patterns,
    find_hot_units,
)

st.set_page_config(page_title="マルハン月寒 狙い目", layout="wide")


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
    st.warning("データがありません。スクレイパーを実行してください。")
    st.stop()

# カラム名の互換対応
COLUMN_MAP = {
    "日付": "play_date", "機種名": "machine_name", "台番号": "unit_number",
    "総G数": "total_games", "BB回数": "bb_count", "RB回数": "rb_count",
    "合算確率": "combined_prob", "BB率": "bb_prob", "RB率": "rb_prob",
    "推定設定": "estimated_setting", "信頼度": "setting_confidence",
    "推定差枚": "estimated_diff", "曜日": "day_of_week", "台番末尾": "unit_suffix",
}
df = df.rename(columns=COLUMN_MAP)

for col in ["estimated_setting", "total_games", "bb_count", "rb_count",
            "combined_prob", "bb_prob", "rb_prob", "unit_number",
            "setting_confidence", "estimated_diff", "day_of_week", "unit_suffix"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

DAY_NAMES = ["月", "火", "水", "木", "金", "土", "日"]


def is_event_day(date_str):
    try:
        return int(date_str.split("-")[2]) in (7, 17, 27)
    except Exception:
        return False


# =============================================
# ヘッダー
# =============================================
st.title("🎰 マルハン月寒 狙い目ダッシュボード")

latest_date = df["play_date"].max()
total_days = df["play_date"].nunique()
st.caption(f"データ: {df['play_date'].min()} 〜 {latest_date}（{total_days}日分）")

# =============================================
# 1. 今日の狙い目（一番目立つ場所）
# =============================================
st.markdown("---")
st.header("🔥 狙い目まとめ")

all_dicts = df.to_dict("records")

# 曜日分析
dow_data = analyze_day_of_week_patterns(all_dicts)
today_dow = datetime.now().weekday()
today_name = DAY_NAMES[today_dow]
today_info = dow_data.get(today_name, {})
today_rate = today_info.get("rate", 0) * 100

# 末尾分析
suffix_data = analyze_suffix_patterns(all_dicts)
hot_suffixes = sorted(
    [(s, d) for s, d in suffix_data.items() if d["total"] >= 5],
    key=lambda x: x[1]["rate"], reverse=True
)

# 機種分析
machine_data = analyze_machine_patterns(all_dicts)
hot_machines = sorted(
    machine_data.items(),
    key=lambda x: x[1]["rate"], reverse=True
)

# ホット台
hot_units = find_hot_units(all_dicts, days=7, min_high_count=2)

# --- 狙い目カード ---
col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("### 📅 狙い目の曜日")
    # 全曜日をランク付け
    dow_ranked = sorted(dow_data.items(), key=lambda x: x[1]["rate"], reverse=True)
    for i, (day, info) in enumerate(dow_ranked):
        rate = info["rate"] * 100
        n = info["total"]
        if n == 0:
            continue
        if i == 0:
            st.markdown(f"**🥇 {day}曜日 → {rate:.1f}%** (n={n})")
        elif i == 1:
            st.markdown(f"**🥈 {day}曜日 → {rate:.1f}%** (n={n})")
        elif i == 2:
            st.markdown(f"🥉 {day}曜日 → {rate:.1f}% (n={n})")
        else:
            st.caption(f"　{day}曜日 → {rate:.1f}% (n={n})")

    if today_rate > 0:
        st.info(f"今日は **{today_name}曜日** → 高設定率 **{today_rate:.1f}%**")

with col2:
    st.markdown("### 🔢 狙い目の末尾")
    for i, (suffix, info) in enumerate(hot_suffixes[:5]):
        rate = info["rate"] * 100
        n = info["total"]
        if i == 0:
            st.markdown(f"**🥇 末尾{suffix} → {rate:.1f}%** (n={n})")
        elif i == 1:
            st.markdown(f"**🥈 末尾{suffix} → {rate:.1f}%** (n={n})")
        elif i == 2:
            st.markdown(f"🥉 末尾{suffix} → {rate:.1f}% (n={n})")
        else:
            st.caption(f"　末尾{suffix} → {rate:.1f}% (n={n})")

with col3:
    st.markdown("### 🎰 狙い目の機種")
    for i, (machine, info) in enumerate(hot_machines):
        rate = info["rate"] * 100
        n = info["total"]
        if n == 0:
            continue
        short_name = machine[:10] + "..." if len(machine) > 10 else machine
        if i == 0:
            st.markdown(f"**🥇 {short_name} → {rate:.1f}%** (n={n})")
        elif i == 1:
            st.markdown(f"**🥈 {short_name} → {rate:.1f}%** (n={n})")
        elif i == 2:
            st.markdown(f"🥉 {short_name} → {rate:.1f}% (n={n})")
        else:
            st.caption(f"　{short_name} → {rate:.1f}% (n={n})")

# =============================================
# 2. リピート高設定台（ピンポイント狙い）
# =============================================
st.markdown("---")
st.header("🎯 リピート高設定台（直近7日で2回以上）")

if hot_units:
    for unit in hot_units[:10]:
        machine = unit["machine_name"]
        num = unit["unit_number"]
        count = unit["high_count"]
        dates = ", ".join(unit["dates"])
        st.markdown(
            f"**{machine} 台番{num}** → 高設定 **{count}回** （{dates}）"
        )
else:
    st.info("直近7日間でリピート高設定台はありません。データが溜まると表示されます。")

# =============================================
# 3. 旧イベント日分析（7のつく日）
# =============================================
st.markdown("---")
st.header("📆 旧イベント日（7のつく日: 7日・17日・27日）")

df_copy = df.copy()
df_copy["is_event"] = df_copy["play_date"].apply(is_event_day)
event_df = df_copy[df_copy["is_event"]]
normal_df = df_copy[~df_copy["is_event"]]

col_a, col_b = st.columns(2)

with col_a:
    event_settings = event_df["estimated_setting"].dropna()
    if len(event_settings) > 0:
        event_rate = (event_settings >= 4).mean() * 100
        event_days = event_df["play_date"].nunique()
        st.metric("旧イベント日の高設定率",
                  f"{event_rate:.1f}%",
                  help=f"{event_days}日分のデータ")
    else:
        st.metric("旧イベント日の高設定率", "データなし")

with col_b:
    normal_settings = normal_df["estimated_setting"].dropna()
    if len(normal_settings) > 0:
        normal_rate = (normal_settings >= 4).mean() * 100
        normal_days = normal_df["play_date"].nunique()
        st.metric("通常日の高設定率",
                  f"{normal_rate:.1f}%",
                  help=f"{normal_days}日分のデータ")
    else:
        st.metric("通常日の高設定率", "データなし")

if len(event_settings) > 0 and len(normal_settings) > 0:
    diff = event_rate - normal_rate
    if diff > 3:
        st.success(f"旧イベント日は通常日より **+{diff:.1f}%** 高設定が多い → **狙い目！**")
    elif diff > 0:
        st.info(f"旧イベント日は通常日より +{diff:.1f}% 高い（微差）")
    else:
        st.warning(f"旧イベント日は通常日より {diff:.1f}%（差なし or 通常日の方が高い）")

    # 旧イベント日に強い末尾
    if len(event_df) > 0:
        event_suffix = analyze_suffix_patterns(event_df.to_dict("records"))
        hot_event_suffix = sorted(
            [(s, d) for s, d in event_suffix.items() if d["total"] >= 3],
            key=lambda x: x[1]["rate"], reverse=True
        )
        if hot_event_suffix:
            top = hot_event_suffix[0]
            st.markdown(f"旧イベント日に最も強い末尾: **末尾{top[0]}**（{top[1]['rate']*100:.0f}%）")

# =============================================
# 4. 直近データ一覧（高設定台だけ）
# =============================================
st.markdown("---")
st.header("📊 直近の高設定台一覧")

recent_high = df[df["estimated_setting"] >= 4].sort_values(
    ["play_date", "estimated_setting"], ascending=[False, False]
).head(30)

if not recent_high.empty:
    display_df = recent_high[["play_date", "machine_name", "unit_number",
                              "total_games", "bb_count", "rb_count",
                              "combined_prob", "estimated_setting", "setting_confidence"]].copy()
    display_df.columns = ["日付", "機種", "台番", "G数", "BB", "RB", "合算", "推定設定", "信頼度"]
    display_df["合算"] = display_df["合算"].apply(lambda x: f"1/{x:.0f}" if pd.notna(x) else "-")
    display_df["信頼度"] = display_df["信頼度"].apply(lambda x: f"{x:.0%}" if pd.notna(x) else "-")
    st.dataframe(display_df, use_container_width=True, hide_index=True)
else:
    st.info("高設定（設定4以上）と推定された台はまだありません。")

st.caption("※ 高設定率 = 推定設定4以上の割合。データが多いほど信頼性が上がります。")
