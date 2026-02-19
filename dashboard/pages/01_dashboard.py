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

import json
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
    "出率": "payout_rate",
}
df = df.rename(columns=COLUMN_MAP)

# シートのヘッダーにO列(payout_rate/出率)が未設定の場合でもエラーにならないよう保護
if "payout_rate" not in df.columns:
    df["payout_rate"] = None

for col in ["estimated_setting", "total_games", "bb_count", "rb_count",
            "combined_prob", "bb_prob", "rb_prob", "unit_number",
            "setting_confidence", "estimated_diff", "day_of_week", "unit_suffix",
            "payout_rate"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

# 差枚修正: 出率がある場合はそこから正確に再計算
# 出率がない旧データは旧式が壊れているので、ボーナス+小役の概算で補正
if "payout_rate" in df.columns:
    mask_rate = df["payout_rate"].notna() & df["total_games"].notna()
    df.loc[mask_rate, "estimated_diff"] = (
        (df.loc[mask_rate, "payout_rate"] / 100 - 1) * df.loc[mask_rate, "total_games"] * 3
    ).round(0)

# 出率がない旧データの差枚を補正（ジャグラー小役払出≒G数×2.1枚を加算）
mask_old = df["estimated_diff"].notna() & df["total_games"].notna()
if "payout_rate" in df.columns:
    mask_old = mask_old & df["payout_rate"].isna()
# 旧式: BB*312+RB*104-G*3 → 正しくは小役(ぶどう等)の払出が抜けている
# 補正: G数*2.1を加算（ジャグラーの通常時小役期待値≒約2.1枚/G）
if mask_old.any():
    df.loc[mask_old, "estimated_diff"] = (
        df.loc[mask_old, "estimated_diff"] + df.loc[mask_old, "total_games"] * 2.1
    ).round(0)

# AT機種名セット（台ランキングから除外）
_machines_path = _root / "config" / "machines.json"
with open(_machines_path, "r", encoding="utf-8") as _f:
    _machines_data = json.load(_f)
AT_MACHINES = {m["machine_name"] for m in _machines_data["machines"] if m["machine_type"] == "at"}


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

today = datetime.now()
today_name = DAY_NAMES[today.weekday()]
today_date = today.strftime("%Y-%m-%d")
today_day = today.day
sorted_dates = sorted(df["play_date"].dropna().unique())

# =============================================
# ★★★ 今日のアクションプラン ★★★
# =============================================
st.markdown("---")
st.header("🚀 今日のアクションプラン")
st.caption(f"{today.strftime('%m/%d')}（{today_name}）— ページを開いたらまずここを見る")

# --- 事前計算: 今日の曜日の高設定率 ---
dow_data_pre = analyze_day_of_week_patterns(all_dicts)
today_dow_info = dow_data_pre.get(today_name, {"total": 0, "rate": 0})
today_dow_rate = today_dow_info["rate"] * 100
dow_ranked_pre = sorted(
    [(d, info) for d, info in dow_data_pre.items() if info["total"] > 0],
    key=lambda x: x[1]["rate"], reverse=True
)
today_dow_rank = next((i + 1 for i, (d, _) in enumerate(dow_ranked_pre) if d == today_name), None)

# --- 事前計算: 今日がイベント日か ---
is_today_event = today_day in (7, 17, 27)

# --- 事前計算: 今日の最強末尾 ---
cross_pre = defaultdict(lambda: {"total": 0, "high": 0})
for row in all_dicts:
    _dow = row.get("day_of_week")
    _suf = row.get("unit_suffix")
    _set = row.get("estimated_setting")
    if _dow is None or _suf is None or _set is None:
        continue
    try:
        cross_pre[(int(_dow), int(_suf))]["total"] += 1
        if _set >= 4:
            cross_pre[(int(_dow), int(_suf))]["high"] += 1
    except (ValueError, TypeError):
        pass

today_suffix_ranked = []
for suffix in range(10):
    info = cross_pre.get((today.weekday(), suffix), {"total": 0, "high": 0})
    if info["total"] >= 2 and info["high"] > 0:
        today_suffix_ranked.append((suffix, info["high"] / info["total"] * 100, info["total"]))
today_suffix_ranked.sort(key=lambda x: -x[1])

# --- 事前計算: 高設定台ランキング（直近重み付き）--- AT機は除外 ---
unit_stats_pre = defaultdict(lambda: {"high": 0, "total": 0, "recent_high": 0, "machine": "", "dates": []})
recent_cutoff = sorted_dates[-7:] if len(sorted_dates) >= 7 else sorted_dates
for row in all_dicts:
    machine = row.get("machine_name", "")
    unit = row.get("unit_number")
    setting = row.get("estimated_setting")
    date = row.get("play_date", "")
    if unit is None or setting is None:
        continue
    if machine in AT_MACHINES:
        continue
    try:
        key = (machine, int(unit))
    except (ValueError, TypeError):
        continue
    unit_stats_pre[key]["total"] += 1
    unit_stats_pre[key]["machine"] = machine
    if setting >= 4:
        unit_stats_pre[key]["high"] += 1
        unit_stats_pre[key]["dates"].append(date)
        if date in recent_cutoff:
            unit_stats_pre[key]["recent_high"] += 1

# 直近重み付きスコア（直近高設定×2 + 全期間高設定）
top_units_action = []
for (machine, unit), stats in unit_stats_pre.items():
    if stats["total"] >= 3 and stats["high"] >= 1:
        score = stats["recent_high"] * 2 + stats["high"]
        rate = stats["high"] / stats["total"]
        top_units_action.append({
            "machine": machine, "unit": unit, "score": score,
            "rate": rate, "high": stats["high"], "total": stats["total"],
            "recent": stats["recent_high"],
        })
top_units_action.sort(key=lambda x: (-x["score"], -x["rate"]))

# --- 事前計算: 据え置き候補（前日高設定台） ---
sueoki_candidates = []
if sorted_dates:
    last_date = sorted_dates[-1]
    last_day_high = df[
        (df["play_date"] == last_date) & (df["estimated_setting"] >= 4)
    ][["machine_name", "unit_number", "estimated_setting"]].dropna()
    for _, row in last_day_high.iterrows():
        sueoki_candidates.append({
            "machine": row["machine_name"],
            "unit": int(row["unit_number"]),
            "setting": int(row["estimated_setting"]),
        })

# --- 事前計算: 店のトレンド ---
trend_direction = "不明"
if len(sorted_dates) >= 5:
    recent_rates = []
    older_rates = []
    for i, date in enumerate(sorted_dates):
        day_settings = df[df["play_date"] == date]["estimated_setting"].dropna()
        if len(day_settings) == 0:
            continue
        rate = (day_settings >= 4).mean() * 100
        if i >= len(sorted_dates) - 5:
            recent_rates.append(rate)
        else:
            older_rates.append(rate)
    if recent_rates and older_rates:
        diff_t = sum(recent_rates) / len(recent_rates) - sum(older_rates) / len(older_rates)
        if diff_t > 3:
            trend_direction = "上昇"
        elif diff_t < -3:
            trend_direction = "下降"
        else:
            trend_direction = "安定"

# --- アクションプラン表示 ---
# 総合判定
go_score = 0
reasons_go = []
reasons_wait = []

if today_dow_rank and today_dow_rank <= 3:
    go_score += 2
    reasons_go.append(f"{today_name}曜日は高設定率ランキング**{today_dow_rank}位**（{today_dow_rate:.1f}%）")
elif today_dow_rank and today_dow_rank >= 5:
    go_score -= 1
    reasons_wait.append(f"{today_name}曜日は高設定率ランキング{today_dow_rank}位（低め）")

if is_today_event:
    go_score += 2
    reasons_go.append("今日は**旧イベント日（7のつく日）**")

if trend_direction == "上昇":
    go_score += 1
    reasons_go.append("直近の店全体トレンドが**上昇中**")
elif trend_direction == "下降":
    go_score -= 1
    reasons_wait.append("直近の店全体トレンドが下降中")

if top_units_action:
    go_score += 1
    reasons_go.append(f"狙える高設定候補台が**{len(top_units_action[:5])}台**ある")

# 判定結果
if go_score >= 3:
    verdict = "🟢 今日は行くべき！"
    verdict_color = "success"
elif go_score >= 1:
    verdict = "🟡 行ってもいい（条件付き）"
    verdict_color = "info"
else:
    verdict = "🔴 今日は様子見が無難"
    verdict_color = "warning"

getattr(st, verdict_color)(f"### {verdict}")

col_go, col_wait = st.columns(2)
with col_go:
    if reasons_go:
        st.markdown("**行くべき理由:**")
        for r in reasons_go:
            st.markdown(f"- ✅ {r}")
with col_wait:
    if reasons_wait:
        st.markdown("**注意点:**")
        for r in reasons_wait:
            st.markdown(f"- ⚠️ {r}")

# 狙い台の具体的指示
st.markdown("---")
st.markdown("### 🎯 今日座るならこの台")

if top_units_action:
    action_cols = st.columns(min(len(top_units_action[:3]), 3))
    for i, u in enumerate(top_units_action[:3]):
        with action_cols[i]:
            medal = ["🥇", "🥈", "🥉"][i]
            st.markdown(f"#### {medal} 第{i+1}候補")
            st.markdown(f"**{u['machine']}**")
            st.markdown(f"台番号: **{u['unit']}**")
            st.markdown(f"高設定率: {u['rate']:.0%}（{u['total']}日中{u['high']}回）")
            if u["recent"] > 0:
                st.markdown(f"直近7日: **{u['recent']}回** 高設定 🔥")

if today_suffix_ranked:
    top_suffixes = today_suffix_ranked[:3]
    suffix_text = "、".join([f"**末尾{s}**({r:.0f}%)" for s, r, _ in top_suffixes])
    st.info(f"今日（{today_name}曜日）の狙い末尾: {suffix_text}")

if sueoki_candidates:
    with st.expander(f"📋 据え置き候補（前日 {sorted_dates[-1]} の高設定台）— {len(sueoki_candidates)}台"):
        for c in sueoki_candidates[:10]:
            st.markdown(f"- {c['machine']} 台番**{c['unit']}** （前日推定設定{c['setting']}）")

# =============================================
# ★★★ 具体的な狙い台リスト ★★★
# =============================================
st.markdown("---")
st.header("🎯 次に座るべき台（具体的な台番号）")

# 各台の高設定回数と直近の実績を計算（AT機は除外: 台番号での設定判別が困難なため）
unit_stats = defaultdict(lambda: {"high_count": 0, "total": 0, "dates": [], "machine": ""})
for row in all_dicts:
    machine = row.get("machine_name", "")
    unit = row.get("unit_number")
    setting = row.get("estimated_setting")
    date = row.get("play_date", "")
    if unit is None or setting is None:
        continue
    if machine in AT_MACHINES:
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
# ★★★ 沖ドキ!DUO 専用分析 ★★★
# =============================================
st.markdown("---")
st.header("🌺 スマスロ 沖ドキ!DUO アンコール 専用")
st.caption("出率ベースで設定を推定。107%以上 → 設定4相当、110%以上 → 設定5相当、112%以上 → 設定6相当")

OKIDOKI_NAME = "スマスロ 沖ドキ!DUO アンコール"
df_oki = df[df["machine_name"] == OKIDOKI_NAME].copy()

if df_oki.empty:
    st.info("沖ドキ!DUOのデータがありません。")
else:
    # 最新日の全台データ
    oki_latest_date = df_oki["play_date"].max()
    df_oki_latest = df_oki[df_oki["play_date"] == oki_latest_date].sort_values("unit_number")

    st.markdown(f"### 最新日（{oki_latest_date}）の全台出率")
    if not df_oki_latest.empty:
        oki_display = df_oki_latest[
            ["unit_number", "total_games", "payout_rate", "estimated_setting", "estimated_diff"]
        ].copy()
        oki_display.columns = ["台番号", "G数", "出率(%)", "推定設定", "推定差枚"]
        st.dataframe(oki_display, use_container_width=True, hide_index=True)

        # 高設定台ハイライト
        oki_high = df_oki_latest[df_oki_latest["payout_rate"] >= 107].sort_values(
            "payout_rate", ascending=False
        )
        if not oki_high.empty:
            for _, r in oki_high.iterrows():
                rate_val = r["payout_rate"]
                if rate_val >= 112:
                    label = "設定6相当"
                elif rate_val >= 110:
                    label = "設定5相当"
                else:
                    label = "設定4相当"
                games_val = int(r["total_games"]) if pd.notna(r["total_games"]) else 0
                st.success(
                    f"🔥 **台番{int(r['unit_number'])}** "
                    f"出率 {rate_val:.1f}% → **{label}**（{games_val:,}G）"
                )
        else:
            st.info(f"{oki_latest_date} は出率107%以上の台なし（高設定不在 or データ不足）")

    # 台番号別の高出率実績
    st.markdown("### 台番号別 高設定（出率107%以上）実績")
    oki_unit_stats = defaultdict(lambda: {"total": 0, "high": 0, "rates": []})
    for _, r in df_oki.iterrows():
        unit = r.get("unit_number")
        rate = r.get("payout_rate")
        if pd.isna(unit) or pd.isna(rate):
            continue
        try:
            u = int(unit)
        except (ValueError, TypeError):
            continue
        oki_unit_stats[u]["total"] += 1
        oki_unit_stats[u]["rates"].append(float(rate))
        if float(rate) >= 107:
            oki_unit_stats[u]["high"] += 1

    oki_ranking = []
    for unit, stats in oki_unit_stats.items():
        if stats["total"] >= 2:
            avg_rate = sum(stats["rates"]) / len(stats["rates"])
            high_rate = stats["high"] / stats["total"]
            oki_ranking.append({
                "台番号": unit,
                "出率107%以上回数": stats["high"],
                "データ日数": stats["total"],
                "高設定率": high_rate,
                "平均出率(%)": round(avg_rate, 1),
            })

    oki_ranking.sort(key=lambda x: (-x["高設定率"], -x["平均出率(%)"]))

    if oki_ranking:
        oki_rank_df = pd.DataFrame(oki_ranking)
        oki_rank_df["高設定率"] = oki_rank_df["高設定率"].apply(lambda x: f"{x:.0%}")
        st.dataframe(oki_rank_df, use_container_width=True, hide_index=True)

        top_oki = oki_ranking[0]
        st.info(
            f"沖ドキ最有力台: **台番{top_oki['台番号']}** — "
            f"高設定率 {top_oki['高設定率']}（{top_oki['データ日数']}日中{top_oki['出率107%以上回数']}回） "
            f"平均出率 {top_oki['平均出率(%)']}%"
        )
    else:
        st.info("データが溜まると台番号別の高設定実績が表示されます（最低2日分必要）。")

# =============================================
# ★★★ 次に行くべき日 ★★★
# =============================================
st.markdown("---")
st.header("📅 次に行くべき日")

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

# =============================================
# ★★★ 据え置き・設定変更パターン ★★★
# =============================================
st.markdown("---")
st.header("🔄 据え置き・設定変更パターン")
st.caption("前日高設定だった台が翌日どうなったか → 据え置き狙いの判断材料")

sueoki_data = []
for i in range(len(sorted_dates) - 1):
    date_prev = sorted_dates[i]
    date_next = sorted_dates[i + 1]
    prev_df = df[df["play_date"] == date_prev]
    next_df = df[df["play_date"] == date_next]

    # 前日に高設定だった台
    high_prev = prev_df[prev_df["estimated_setting"] >= 4]
    for _, row in high_prev.iterrows():
        machine = row.get("machine_name")
        unit = row.get("unit_number")
        if pd.isna(unit):
            continue
        # 翌日の同じ台を探す
        next_same = next_df[
            (next_df["machine_name"] == machine) &
            (next_df["unit_number"] == unit)
        ]
        if not next_same.empty:
            next_setting = next_same.iloc[0].get("estimated_setting")
            if pd.notna(next_setting):
                sueoki_data.append({
                    "前日": date_prev,
                    "翌日": date_next,
                    "機種": machine,
                    "台番号": int(unit),
                    "前日設定": int(row["estimated_setting"]),
                    "翌日設定": int(next_setting),
                    "据え置き": "○" if next_setting >= 4 else "✕",
                })

if sueoki_data:
    sueoki_df = pd.DataFrame(sueoki_data)
    total_pairs = len(sueoki_df)
    sueoki_count = len(sueoki_df[sueoki_df["据え置き"] == "○"])
    sueoki_rate = sueoki_count / total_pairs * 100 if total_pairs > 0 else 0

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("据え置き率", f"{sueoki_rate:.1f}%")
    with col2:
        st.metric("据え置き回数", f"{sueoki_count}/{total_pairs}")
    with col3:
        if sueoki_rate >= 30:
            st.success("据え置き傾向あり → 前日高設定台を狙え！")
        elif sueoki_rate >= 15:
            st.info("据え置きは時々ある")
        else:
            st.warning("据え置き少ない → 前日高設定台は避けるべき")

    # 機種別据え置き率
    st.markdown("#### 機種別 据え置き率")
    machine_sueoki = sueoki_df.groupby("機種").agg(
        件数=("据え置き", "count"),
        据え置き=("据え置き", lambda x: (x == "○").sum()),
    ).reset_index()
    machine_sueoki["据え置き率"] = (machine_sueoki["据え置き"] / machine_sueoki["件数"] * 100).apply(lambda x: f"{x:.0f}%")
    st.dataframe(machine_sueoki, use_container_width=True, hide_index=True)
else:
    st.info("連続日のデータが溜まると据え置き分析が表示されます。")

# =============================================
# ★★★ 隣接台分析（並び狙い） ★★★
# =============================================
st.markdown("---")
st.header("🏗️ 並び・固まり傾向（高設定が隣接するか）")
st.caption("同じ日に高設定が隣り合って入る傾向があるか → 並び狙いの判断材料")

adjacent_count = 0
adjacent_total = 0
for date in sorted_dates:
    for machine in df["machine_name"].unique():
        day_machine = df[
            (df["play_date"] == date) &
            (df["machine_name"] == machine) &
            (df["estimated_setting"] >= 4)
        ]["unit_number"].dropna().sort_values().tolist()

        if len(day_machine) < 2:
            continue

        for i in range(len(day_machine) - 1):
            adjacent_total += 1
            try:
                if abs(int(day_machine[i+1]) - int(day_machine[i])) == 1:
                    adjacent_count += 1
            except (ValueError, TypeError):
                pass

if adjacent_total > 0:
    adj_rate = adjacent_count / adjacent_total * 100
    col1, col2 = st.columns(2)
    with col1:
        st.metric("高設定の隣接率", f"{adj_rate:.1f}%",
                   help="高設定台同士が台番号で隣り合っている割合")
    with col2:
        if adj_rate >= 30:
            st.success("並び傾向あり！高設定台の隣も狙い目")
        elif adj_rate >= 15:
            st.info("並びは時々ある")
        else:
            st.caption("並び傾向は薄い → バラけて入る店")
else:
    st.info("データが溜まると並び分析が表示されます。")

# =============================================
# ★★★ 角台・端台分析 ★★★
# =============================================
st.markdown("---")
st.header("📐 角台（端台）の優遇傾向")
st.caption("各機種の一番端の台（角台）は高設定が入りやすいか")

kado_stats = {"角台": {"total": 0, "high": 0}, "中間台": {"total": 0, "high": 0}}
for date in sorted_dates:
    for machine in df["machine_name"].unique():
        day_machine = df[
            (df["play_date"] == date) &
            (df["machine_name"] == machine)
        ].dropna(subset=["unit_number", "estimated_setting"])

        if len(day_machine) < 3:
            continue

        units_sorted = day_machine.sort_values("unit_number")
        min_unit = units_sorted["unit_number"].min()
        max_unit = units_sorted["unit_number"].max()

        for _, row in units_sorted.iterrows():
            unit = row["unit_number"]
            setting = row["estimated_setting"]
            is_kado = (unit == min_unit or unit == max_unit)
            key = "角台" if is_kado else "中間台"
            kado_stats[key]["total"] += 1
            if setting >= 4:
                kado_stats[key]["high"] += 1

if kado_stats["角台"]["total"] > 0 and kado_stats["中間台"]["total"] > 0:
    kado_rate = kado_stats["角台"]["high"] / kado_stats["角台"]["total"] * 100
    naka_rate = kado_stats["中間台"]["high"] / kado_stats["中間台"]["total"] * 100
    diff_kado = kado_rate - naka_rate

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("角台の高設定率", f"{kado_rate:.1f}%",
                   delta=f"{diff_kado:+.1f}%")
    with col2:
        st.metric("中間台の高設定率", f"{naka_rate:.1f}%")
    with col3:
        if diff_kado > 5:
            st.success("角台が優遇されている！")
        elif diff_kado > 0:
            st.info("角台がやや有利")
        else:
            st.warning("角台の優遇なし")
else:
    st.info("データが溜まると角台分析が表示されます。")

# =============================================
# ★★★ 店の出玉傾向（全体トレンド） ★★★
# =============================================
st.markdown("---")
st.header("📈 店全体の出玉トレンド")
st.caption("日ごとの高設定投入率の推移 → 店が出す時期・渋い時期を見極める")

daily_trend = []
for date in sorted_dates:
    day_df = df[df["play_date"] == date]
    settings = day_df["estimated_setting"].dropna()
    if len(settings) == 0:
        continue
    high_rate = (settings >= 4).mean() * 100
    avg_diff = day_df["estimated_diff"].dropna().mean()
    daily_trend.append({
        "日付": date,
        "高設定率": round(high_rate, 1),
        "平均差枚": round(avg_diff) if pd.notna(avg_diff) else 0,
        "台数": len(settings),
    })

if daily_trend:
    trend_df = pd.DataFrame(daily_trend)
    st.line_chart(trend_df.set_index("日付")["高設定率"], use_container_width=True)

    # 直近の傾向
    if len(daily_trend) >= 5:
        recent_5 = trend_df.tail(5)["高設定率"].mean()
        older = trend_df.head(len(trend_df) - 5)["高設定率"].mean()
        diff_trend = recent_5 - older

        if diff_trend > 3:
            st.success(f"直近5日間の高設定率が上昇傾向（+{diff_trend:.1f}%）→ 今が攻め時！")
        elif diff_trend < -3:
            st.warning(f"直近5日間の高設定率が下降傾向（{diff_trend:.1f}%）→ 様子見推奨")
        else:
            st.info(f"直近5日間は安定推移（{diff_trend:+.1f}%）")

    # 差枚トレンド
    st.markdown("#### 日別 平均差枚推移")
    st.bar_chart(trend_df.set_index("日付")["平均差枚"], use_container_width=True)
else:
    st.info("データが溜まるとトレンドが表示されます。")

# =============================================
# ★★★ 期待収支シミュレーション ★★★
# =============================================
st.markdown("---")
st.header("💰 期待収支シミュレーション")
st.caption("狙い台に座れた場合の期待収支（過去の差枚データから算出）")

if unit_ranking:
    top_target = unit_ranking[:5]
    sim_data = []
    for u in top_target:
        machine = u["機種"]
        unit = u["台番号"]
        target_data = df[
            (df["machine_name"] == machine) &
            (df["unit_number"] == unit) &
            (df["estimated_setting"] >= 4)
        ]["estimated_diff"].dropna()

        if len(target_data) > 0:
            avg_diff = target_data.mean()
            sim_data.append({
                "機種": machine,
                "台番号": unit,
                "高設定時の平均差枚": f"{avg_diff:+,.0f}枚",
                "期待収支(20円換算)": f"¥{avg_diff * 20:+,.0f}",
                "高設定回数": len(target_data),
            })

    if sim_data:
        st.dataframe(pd.DataFrame(sim_data), use_container_width=True, hide_index=True)

        total_avg = df[df["estimated_setting"] >= 4]["estimated_diff"].dropna().mean()
        if pd.notna(total_avg):
            st.info(f"高設定台全体の平均差枚: **{total_avg:+,.0f}枚**（20円換算: **¥{total_avg*20:+,.0f}**）")

# =============================================
# ★★★ G数（回転数）と設定の相関 ★★★
# =============================================
st.markdown("---")
st.header("🎮 回転数（G数）と高設定の関係")
st.caption("G数が多い台＝客が粘っている＝出ている可能性。何G以上なら高設定の確率が高いか")

games_thresholds = [3000, 4000, 5000, 6000, 7000, 8000]
games_analysis = []
valid_games = df.dropna(subset=["total_games", "estimated_setting"])

for threshold in games_thresholds:
    above = valid_games[valid_games["total_games"] >= threshold]
    below = valid_games[valid_games["total_games"] < threshold]
    if len(above) > 0:
        above_rate = (above["estimated_setting"] >= 4).mean() * 100
        below_rate = (below["estimated_setting"] >= 4).mean() * 100 if len(below) > 0 else 0
        games_analysis.append({
            "G数閾値": f"{threshold:,}G以上",
            "該当台数": len(above),
            "高設定率": f"{above_rate:.1f}%",
            "それ以下の高設定率": f"{below_rate:.1f}%",
            "差": f"+{above_rate - below_rate:.1f}%",
        })

if games_analysis:
    st.dataframe(pd.DataFrame(games_analysis), use_container_width=True, hide_index=True)

    # 最も差が大きい閾値を推薦
    best_threshold = None
    best_diff = 0
    for threshold in games_thresholds:
        above = valid_games[valid_games["total_games"] >= threshold]
        below = valid_games[valid_games["total_games"] < threshold]
        if len(above) >= 10:
            above_rate = (above["estimated_setting"] >= 4).mean() * 100
            below_rate = (below["estimated_setting"] >= 4).mean() * 100 if len(below) > 0 else 0
            d = above_rate - below_rate
            if d > best_diff:
                best_diff = d
                best_threshold = threshold

    if best_threshold and best_diff > 3:
        st.success(
            f"**{best_threshold:,}G以上** の台は高設定率が **+{best_diff:.1f}%** 高い → "
            f"夕方から打つなら{best_threshold:,}G以上回っている台を狙え！"
        )
else:
    st.info("データが溜まるとG数分析が表示されます。")

# =============================================
# ★★★ 月初・月末・給料日傾向 ★★★
# =============================================
st.markdown("---")
st.header("📆 月の時期による傾向")
st.caption("月初（1〜10日）・中旬（11〜20日）・月末（21〜末日）で高設定率に差があるか")

period_stats = {"月初(1-10日)": {"total": 0, "high": 0},
                "中旬(11-20日)": {"total": 0, "high": 0},
                "月末(21-末日)": {"total": 0, "high": 0}}

for _, row in df.dropna(subset=["estimated_setting"]).iterrows():
    try:
        day_num = int(str(row["play_date"]).split("-")[2])
    except (ValueError, IndexError):
        continue
    if day_num <= 10:
        period = "月初(1-10日)"
    elif day_num <= 20:
        period = "中旬(11-20日)"
    else:
        period = "月末(21-末日)"
    period_stats[period]["total"] += 1
    if row["estimated_setting"] >= 4:
        period_stats[period]["high"] += 1

period_data = []
for period, stats in period_stats.items():
    if stats["total"] > 0:
        rate = stats["high"] / stats["total"] * 100
        period_data.append({"時期": period, "高設定率": f"{rate:.1f}%", "データ数": stats["total"]})

if period_data:
    pcols = st.columns(len(period_data))
    for i, pd_item in enumerate(period_data):
        with pcols[i]:
            st.metric(pd_item["時期"], pd_item["高設定率"], help=f"n={pd_item['データ数']}")

    # 最も高い時期を強調
    best_period = max(period_stats.items(), key=lambda x: x[1]["high"] / x[1]["total"] if x[1]["total"] > 0 else 0)
    if best_period[1]["total"] > 0:
        best_rate = best_period[1]["high"] / best_period[1]["total"] * 100
        st.info(f"最も高設定が入りやすい時期: **{best_period[0]}**（高設定率 {best_rate:.1f}%）")

st.markdown("---")
st.caption("※ 高設定 = 推定設定4以上。n数が少ない場合は信頼性が低いので注意。データが2〜3週間溜まると精度が上がります。")
