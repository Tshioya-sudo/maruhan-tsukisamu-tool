"""
分析ダッシュボード（狙い目特化版）
具体的な台番号・日付・機種を提案する。
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

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
    st.warning("データがありません。スクレイパーを実行してください。")
    st.stop()

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


def is_event_day_date(d):
    return d.day in (7, 17, 27)


def next_event_day():
    today = datetime.now().date()
    for i in range(1, 31):
        d = today + timedelta(days=i)
        if d.day in (7, 17, 27):
            return d
    return None


# =============================================
st.title("🎰 マルハン月寒 狙い目ダッシュボード")
latest_date = df["play_date"].max()
total_days = df["play_date"].nunique()
st.caption(f"データ: {df['play_date'].min()} 〜 {latest_date}（{total_days}日分）")

all_dicts = df.to_dict("records")

# =============================================
# ★★★ 具体的な狙い台リスト ★★★
# =============================================
st.markdown("---")
st.header("🎯 次に座るべき台（具体的な台番号）")

# 各台の高設定回数と直近の実績を計算
unit_stats = defaultdict(lambda: {"high_count": 0, "total": 0, "dates": [], "machine": ""})
for row in all_dicts:
    machine = row.get("machine_name", "")
    unit = row.get("unit_number")
    setting = row.get("estimated_setting")
    date = row.get("play_date", "")
    if unit is None or setting is None:
        continue
    try:
        key = (machine, int(unit))
    except (ValueError, TypeError):
        continue
    unit_stats[key]["total"] += 1
    unit_stats[key]["machine"] = machine
    if setting >= 4:
        unit_stats[key]["high_count"] += 1
        unit_stats[key]["dates"].append(date)

# 高設定率が高い台をランキング（最低3回以上データがある台）
unit_ranking = []
for (machine, unit), stats in unit_stats.items():
    if stats["total"] >= 3 and stats["high_count"] >= 1:
        rate = stats["high_count"] / stats["total"]
        unit_ranking.append({
            "機種": machine,
            "台番号": unit,
            "高設定回数": stats["high_count"],
            "データ日数": stats["total"],
            "高設定率": rate,
            "直近の高設定日": ", ".join(sorted(stats["dates"])[-3:]),
        })

unit_ranking.sort(key=lambda x: (-x["高設定率"], -x["高設定回数"]))

if unit_ranking:
    st.markdown("**過去データから高設定が入りやすい台番号（高設定率順）:**")
    top_units = unit_ranking[:15]
    display = pd.DataFrame(top_units)
    display["高設定率"] = display["高設定率"].apply(lambda x: f"{x:.0%}")
    st.dataframe(display, use_container_width=True, hide_index=True)

    # トップ3を目立たせる
    st.markdown("### 特に狙い目の台")
    for i, u in enumerate(top_units[:3]):
        medal = ["🥇", "🥈", "🥉"][i]
        st.success(
            f"{medal} **{u['機種']} 台番{u['台番号']}** — "
            f"高設定率 {u['高設定率']} "
            f"（{u['データ日数']}日中 {u['高設定回数']}回）"
        )
else:
    st.info("データが溜まると具体的な台番号の推薦が表示されます（最低3日分必要）。")

# =============================================
# ★★★ 次に行くべき日 ★★★
# =============================================
st.markdown("---")
st.header("📅 次に行くべき日")

today = datetime.now()
today_name = DAY_NAMES[today.weekday()]

# 曜日別分析
dow_data = analyze_day_of_week_patterns(all_dicts)
dow_ranked = sorted(
    [(d, info) for d, info in dow_data.items() if info["total"] > 0],
    key=lambda x: x[1]["rate"], reverse=True
)

# 次の旧イベント日
next_event = next_event_day()

col1, col2 = st.columns(2)

with col1:
    st.markdown("### 曜日別ランキング")
    for i, (day, info) in enumerate(dow_ranked):
        rate = info["rate"] * 100
        n = info["total"]
        medal = ["🥇", "🥈", "🥉"][i] if i < 3 else "　"
        marker = " ← **今日**" if day == today_name else ""
        st.markdown(f"{medal} **{day}曜日** → 高設定率 **{rate:.1f}%** (n={n}){marker}")

    if dow_ranked:
        best_day = dow_ranked[0][0]
        # 次にその曜日が来る日付を計算
        best_dow_idx = DAY_NAMES.index(best_day)
        days_ahead = (best_dow_idx - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7  # 今日がその曜日なら来週
        next_best = today + timedelta(days=days_ahead)
        st.info(f"次の{best_day}曜日 → **{next_best.strftime('%m/%d')}（{best_day}）**")

with col2:
    st.markdown("### 旧イベント日（7のつく日）")

    df_copy = df.copy()
    def _is_event(x):
        try:
            parts = str(x).split("-")
            return int(parts[2]) in (7, 17, 27) if len(parts) >= 3 else False
        except (ValueError, IndexError):
            return False

    df_copy["is_event"] = df_copy["play_date"].apply(_is_event)
    event_settings = df_copy[df_copy["is_event"]]["estimated_setting"].dropna()
    normal_settings = df_copy[~df_copy["is_event"]]["estimated_setting"].dropna()

    if len(event_settings) > 0:
        event_rate = (event_settings >= 4).mean() * 100
        normal_rate = (normal_settings >= 4).mean() * 100 if len(normal_settings) > 0 else 0
        diff = event_rate - normal_rate

        st.metric("旧イベント日の高設定率", f"{event_rate:.1f}%")
        st.metric("通常日の高設定率", f"{normal_rate:.1f}%")

        if diff > 3:
            st.success(f"旧イベント日は **+{diff:.1f}%** → 狙い目！")
        elif diff > 0:
            st.info(f"旧イベント日は +{diff:.1f}%（微差）")
        else:
            st.warning(f"差なし or 通常日が高い（{diff:+.1f}%）")
    else:
        st.info("旧イベント日のデータがまだありません。")

    if next_event:
        event_dow = DAY_NAMES[next_event.weekday()]
        st.markdown(f"次の旧イベント日 → **{next_event.strftime('%m/%d')}（{event_dow}）**")

# =============================================
# ★★★ 曜日×末尾クロス分析 ★★★
# =============================================
st.markdown("---")
st.header("🔢 曜日×末尾 クロス分析（どの曜日にどの末尾が熱いか）")

# クロス集計
cross = defaultdict(lambda: {"total": 0, "high": 0})
for row in all_dicts:
    dow = row.get("day_of_week")
    suffix = row.get("unit_suffix")
    setting = row.get("estimated_setting")
    if dow is None or suffix is None or setting is None:
        continue
    try:
        key = (int(dow), int(suffix))
    except (ValueError, TypeError):
        continue
    cross[key]["total"] += 1
    if setting >= 4:
        cross[key]["high"] += 1

# テーブル作成
cross_data = []
for dow_idx, day_name in enumerate(DAY_NAMES):
    row_data = {"曜日": day_name}
    for suffix in range(10):
        info = cross.get((dow_idx, suffix), {"total": 0, "high": 0})
        if info["total"] >= 3:
            rate = info["high"] / info["total"] * 100
            row_data[f"末尾{suffix}"] = f"{rate:.0f}%"
        else:
            row_data[f"末尾{suffix}"] = "-"
    cross_data.append(row_data)

cross_df = pd.DataFrame(cross_data)
st.dataframe(cross_df, use_container_width=True, hide_index=True)

# 最強の曜日×末尾コンボを抽出
best_combos = []
for (dow_idx, suffix), info in cross.items():
    if info["total"] >= 3:
        rate = info["high"] / info["total"]
        best_combos.append({
            "曜日": DAY_NAMES[dow_idx],
            "末尾": suffix,
            "rate": rate,
            "total": info["total"],
            "high": info["high"],
        })

best_combos.sort(key=lambda x: -x["rate"])

if best_combos:
    st.markdown("### 最強コンボ TOP5")
    for i, combo in enumerate(best_combos[:5]):
        rate = combo["rate"] * 100
        medal = ["🥇", "🥈", "🥉", "4.", "5."][i]
        st.markdown(
            f"{medal} **{combo['曜日']}曜日 × 末尾{combo['末尾']}** → "
            f"高設定率 **{rate:.0f}%**（{combo['total']}回中{combo['high']}回）"
        )

    # 今日のコンボ
    today_combos = [c for c in best_combos if c["曜日"] == today_name]
    if today_combos:
        best_today = today_combos[0]
        st.info(
            f"今日（{today_name}曜日）の最強末尾 → **末尾{best_today['末尾']}** "
            f"（高設定率 {best_today['rate']*100:.0f}%）"
        )

# =============================================
# ★★★ 機種別 狙い目サマリー ★★★
# =============================================
st.markdown("---")
st.header("🎰 機種別 狙い目")

machine_data = analyze_machine_patterns(all_dicts)
for machine, info in sorted(machine_data.items(), key=lambda x: -x[1]["rate"]):
    rate = info["rate"] * 100
    if info["total"] == 0:
        continue

    # この機種の狙い台を抽出
    machine_units = [u for u in unit_ranking if u["機種"] == machine][:3]

    with st.expander(f"{'🔥' if rate >= 15 else '　'} {machine} — 高設定率 {rate:.1f}%（{info['total']}台中{info['high']}台）"):
        if machine_units:
            st.markdown("**狙い台番号:**")
            for u in machine_units:
                st.markdown(f"- 台番**{u['台番号']}** — 高設定率 {u['高設定率']}（{u['データ日数']}日中{u['高設定回数']}回）")
        else:
            st.caption("まだ狙い台の特定に十分なデータがありません。")

        # この機種の末尾傾向
        machine_rows = [r for r in all_dicts if r.get("machine_name") == machine]
        if machine_rows:
            m_suffix = analyze_suffix_patterns(machine_rows)
            hot = [(s, d) for s, d in m_suffix.items() if d["total"] >= 3 and d["rate"] > 0]
            hot.sort(key=lambda x: -x[1]["rate"])
            if hot:
                suffix_text = " / ".join([f"末尾{s}({d['rate']*100:.0f}%)" for s, d in hot[:3]])
                st.markdown(f"**狙い末尾:** {suffix_text}")

st.markdown("---")
st.caption("※ 高設定 = 推定設定4以上。n数が少ない場合は信頼性が低いので注意。データが2〜3週間溜まると精度が上がります。")
