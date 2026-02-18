"""
設定推測ロジック。
REG確率と合算確率からベイズ的に最尤設定を推定する。
"""
import json
import os
import logging

logger = logging.getLogger(__name__)

# 機種データ読み込み
_MACHINES = None


def _load_machines():
    global _MACHINES
    if _MACHINES is None:
        machines_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "config", "machines.json"
        )
        with open(machines_path, "r", encoding="utf-8") as f:
            _MACHINES = json.load(f)["machines"]
    return _MACHINES


def estimate_setting(machine_name: str, total_games: int | None,
                     bb_count: int | None, rb_count: int | None) -> dict:
    """
    ボーナス確率から設定を推定する。

    Returns:
        dict: {"estimated_setting": int|None, "confidence": float, "reason": str}
    """
    machines = _load_machines()

    if not total_games or total_games < 2000:
        return {
            "estimated_setting": None,
            "confidence": 0.0,
            "reason": f"回転数不足（{total_games}G）",
        }

    bb = bb_count or 0
    rb = rb_count or 0
    total_bonus = bb + rb

    if total_bonus == 0:
        return {
            "estimated_setting": 1,
            "confidence": 0.1,
            "reason": "ボーナス0回",
        }

    actual_reg = total_games / rb if rb > 0 else 9999
    actual_combined = total_games / total_bonus

    # 対象機種を検索
    machine = next(
        (m for m in machines if m["machine_name"] == machine_name), None
    )
    if not machine:
        return {
            "estimated_setting": None,
            "confidence": 0.0,
            "reason": f"未登録機種: {machine_name}",
        }

    if machine["machine_type"] == "juggler":
        return _estimate_juggler(machine, total_games, actual_reg, actual_combined)
    elif machine["machine_type"] == "at":
        return _estimate_at(machine, total_games, total_bonus)

    return {"estimated_setting": None, "confidence": 0.0, "reason": "不明"}


def _estimate_juggler(machine: dict, total_games: int,
                      actual_reg: float, actual_combined: float) -> dict:
    """ジャグラー系: REG確率ベースで最も近い設定を推定"""
    best_setting = 1
    best_diff = float("inf")

    for setting_str, probs in machine["settings"].items():
        setting = int(setting_str)
        expected_reg = probs["reg"]
        diff = abs(actual_reg - expected_reg)
        if diff < best_diff:
            best_diff = diff
            best_setting = setting

    # 信頼度: G数が多いほど高い（8000Gで最大）
    confidence = min(1.0, total_games / 8000)
    # REG確率の乖離が大きい場合は信頼度低下
    if best_diff > 50:
        confidence *= 0.5

    return {
        "estimated_setting": best_setting,
        "confidence": round(confidence, 2),
        "reason": f"REG 1/{actual_reg:.0f}, 合算 1/{actual_combined:.0f}",
    }


def _estimate_at(machine: dict, total_games: int, total_bonus: int) -> dict:
    """AT機: 初当たり確率ベース"""
    if total_bonus == 0:
        return {
            "estimated_setting": None,
            "confidence": 0.0,
            "reason": "初当たりなし",
        }

    actual_hit = total_games / total_bonus
    best_setting = 1
    best_diff = float("inf")

    for setting_str, probs in machine["settings"].items():
        setting = int(setting_str)
        expected = probs.get("first_hit", 999)
        diff = abs(actual_hit - expected)
        if diff < best_diff:
            best_diff = diff
            best_setting = setting

    # AT機は判別精度が低い
    confidence = min(1.0, total_games / 8000) * 0.7
    return {
        "estimated_setting": best_setting,
        "confidence": round(confidence, 2),
        "reason": f"初当たり 1/{actual_hit:.0f}",
    }
