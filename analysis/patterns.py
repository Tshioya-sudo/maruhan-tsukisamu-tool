"""
パターン検出モジュール。
曜日別・末尾別の高設定出現パターンを分析する。
"""
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

# 曜日名
DAY_NAMES = ["月", "火", "水", "木", "金", "土", "日"]


def analyze_suffix_patterns(data: list[dict], min_setting: int = 4) -> dict:
    """
    台番号末尾別の高設定出現率を分析する。

    Args:
        data: daily_dataレコードのリスト
        min_setting: 高設定の閾値（デフォルト4以上）

    Returns:
        dict: {末尾: {"total": 件数, "high": 高設定数, "rate": 出現率}, ...}
    """
    suffix_stats = defaultdict(lambda: {"total": 0, "high": 0})

    for row in data:
        suffix = row.get("unit_suffix")
        setting = row.get("estimated_setting")
        if suffix is None or setting is None:
            continue
        suffix_stats[suffix]["total"] += 1
        if setting >= min_setting:
            suffix_stats[suffix]["high"] += 1

    result = {}
    for suffix in range(10):
        stats = suffix_stats[suffix]
        total = stats["total"]
        high = stats["high"]
        rate = high / total if total > 0 else 0.0
        result[suffix] = {"total": total, "high": high, "rate": round(rate, 3)}

    return result


def analyze_day_of_week_patterns(data: list[dict], min_setting: int = 4) -> dict:
    """
    曜日別の高設定出現率を分析する。

    Returns:
        dict: {"月": {"total": 件数, "high": 高設定数, "rate": 出現率}, ...}
    """
    dow_stats = defaultdict(lambda: {"total": 0, "high": 0})

    for row in data:
        dow = row.get("day_of_week")
        setting = row.get("estimated_setting")
        if dow is None or setting is None:
            continue
        dow_stats[dow]["total"] += 1
        if setting >= min_setting:
            dow_stats[dow]["high"] += 1

    result = {}
    for i, name in enumerate(DAY_NAMES):
        stats = dow_stats[i]
        total = stats["total"]
        high = stats["high"]
        rate = high / total if total > 0 else 0.0
        result[name] = {"total": total, "high": high, "rate": round(rate, 3)}

    return result


def analyze_machine_patterns(data: list[dict], min_setting: int = 4) -> dict:
    """
    機種別の高設定出現率を分析する。

    Returns:
        dict: {機種名: {"total": 件数, "high": 高設定数, "rate": 出現率}, ...}
    """
    machine_stats = defaultdict(lambda: {"total": 0, "high": 0})

    for row in data:
        machine = row.get("machine_name")
        setting = row.get("estimated_setting")
        if not machine or setting is None:
            continue
        machine_stats[machine]["total"] += 1
        if setting >= min_setting:
            machine_stats[machine]["high"] += 1

    result = {}
    for machine, stats in machine_stats.items():
        total = stats["total"]
        high = stats["high"]
        rate = high / total if total > 0 else 0.0
        result[machine] = {"total": total, "high": high, "rate": round(rate, 3)}

    return result


def find_hot_units(data: list[dict], days: int = 7, min_high_count: int = 2) -> list[dict]:
    """
    直近N日間で複数回高設定が入った台番号を検出する。

    Returns:
        list[dict]: [{"machine_name": ..., "unit_number": ...,
                       "high_count": N, "dates": [...]}, ...]
    """
    # 日付でソートして直近N日を取得
    dates = sorted(set(row.get("play_date", "") for row in data))
    recent_dates = set(dates[-days:]) if len(dates) >= days else set(dates)

    # 台ごとの高設定日を集計
    unit_highs = defaultdict(list)
    for row in data:
        if row.get("play_date") not in recent_dates:
            continue
        setting = row.get("estimated_setting")
        if setting and setting >= 4:
            key = (row.get("machine_name"), row.get("unit_number"))
            unit_highs[key].append(row["play_date"])

    # 複数回高設定の台を抽出
    hot_units = []
    for (machine, unit), dates_list in unit_highs.items():
        if len(dates_list) >= min_high_count:
            hot_units.append({
                "machine_name": machine,
                "unit_number": unit,
                "high_count": len(dates_list),
                "dates": sorted(dates_list),
            })

    hot_units.sort(key=lambda x: x["high_count"], reverse=True)
    return hot_units
