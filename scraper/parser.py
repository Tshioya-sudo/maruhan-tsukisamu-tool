"""
HTMLパース補助モジュール。
みんレポのHTML構造に合わせたパーサー群。

実際のHTML構造（2026/2/17確認）:
- テーブルにはclass/idがないことが多い
- <thead>/<tbody>は不使用。全て<tr>がフラットに並ぶ
- 機種別テーブルは15行ごとにヘッダー行(<th>)が再挿入される
- 最終行は<tr class="avg_row">で平均値行
- 機種別テーブルの列: 台番|差枚|G数|出率|BB|RB|合成|BB率|RB率 (9列)
"""
import re
import logging
from urllib.parse import unquote_plus

logger = logging.getLogger(__name__)


def parse_int(text: str) -> int | None:
    """'5,743' → 5743, '-1,200' → -1200"""
    if text is None:
        return None
    try:
        cleaned = text.strip().replace(",", "").replace(" ", "").replace("\u3000", "")
        if cleaned in ("", "-"):
            return None
        return int(cleaned)
    except (ValueError, AttributeError):
        return None


def parse_payout_rate(text: str) -> float | None:
    """'109.5%' → 109.5, '-' → None"""
    if text is None:
        return None
    try:
        cleaned = text.strip().replace("%", "").replace(",", "")
        if cleaned in ("", "-"):
            return None
        return float(cleaned)
    except (ValueError, AttributeError):
        return None


def parse_prob(text: str) -> float | None:
    """'1/221' → 221.0, '-' → None"""
    if text is None:
        return None
    try:
        text = text.strip()
        if text in ("", "-"):
            return None
        parts = text.split("/")
        if len(parts) == 2:
            return float(parts[1].replace(",", ""))
        return None
    except (ValueError, AttributeError):
        return None


def parse_date_text(text: str, reference_year: int = None) -> str:
    """
    '2/16(月)' → '2026-02-16' (年を推定)
    年またぎ対策付き。
    """
    from datetime import datetime

    try:
        match = re.match(r"(\d{1,2})/(\d{1,2})", text)
        if match:
            month, day = int(match.group(1)), int(match.group(2))
            now = datetime.now()
            year = reference_year or now.year

            # 年またぎ対策
            if now.month >= 11 and month <= 2:
                year = now.year + 1
            elif now.month <= 2 and month >= 11:
                year = now.year - 1

            return f"{year}-{month:02d}-{day:02d}"
    except Exception:
        pass
    return text


def extract_article_id(url: str) -> str | None:
    """
    URLからarticle_idを抽出する。
    'https://min-repo.com/2924707/' → '2924707'
    '/2924707/' → '2924707'
    """
    match = re.search(r"/(\d{5,8})/", url)
    if match:
        return match.group(1)
    return None


def extract_kishu_name(href: str) -> str | None:
    """
    ?kishu=パラメータから機種名を抽出する。
    '?kishu=%E3%83%9E%E3%82%A4...' → 'マイジャグラーV'
    末尾番号（?kishu=0）やall（?kishu=all）は除外。
    """
    match = re.search(r"[?&]kishu=([^&]+)", href)
    if match:
        raw = match.group(1)
        # 末尾番号やallは除外
        if raw in ("all",) or re.match(r"^\d$", raw) or raw == "z":
            return None
        return unquote_plus(raw)
    return None
