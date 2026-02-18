"""
グラフ生成モジュール。
Plotlyを使用してダッシュボード用のグラフを生成する。
"""
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd


def create_setting_heatmap(df: pd.DataFrame, machine_name: str = None) -> go.Figure:
    """
    台番号 × 日付 のヒートマップ（推定設定の色分け）。

    Args:
        df: daily_data DataFrame
        machine_name: フィルタする機種名（Noneなら全機種）
    """
    if machine_name:
        df = df[df["machine_name"] == machine_name]

    if df.empty:
        return go.Figure().update_layout(title="データなし")

    pivot = df.pivot_table(
        index="unit_number",
        columns="play_date",
        values="estimated_setting",
        aggfunc="first",
    )
    pivot = pivot.sort_index()

    fig = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=pivot.columns.tolist(),
        y=pivot.index.tolist(),
        colorscale=[
            [0, "#2c3e50"],      # 設定1: 暗い
            [0.2, "#3498db"],    # 設定2: 青
            [0.4, "#2ecc71"],    # 設定3: 緑
            [0.6, "#f1c40f"],    # 設定4: 黄
            [0.8, "#e67e22"],    # 設定5: オレンジ
            [1.0, "#e74c3c"],    # 設定6: 赤
        ],
        zmin=1,
        zmax=6,
        colorbar=dict(title="推定設定"),
        hoverongaps=False,
    ))
    title = f"設定ヒートマップ - {machine_name}" if machine_name else "設定ヒートマップ（全機種）"
    fig.update_layout(
        title=title,
        xaxis_title="日付",
        yaxis_title="台番号",
        yaxis=dict(type="category"),
    )
    return fig


def create_suffix_chart(suffix_data: dict) -> go.Figure:
    """末尾別 高設定出現率の棒グラフ"""
    suffixes = list(range(10))
    rates = [suffix_data.get(s, {}).get("rate", 0) * 100 for s in suffixes]
    totals = [suffix_data.get(s, {}).get("total", 0) for s in suffixes]

    fig = go.Figure(data=go.Bar(
        x=[str(s) for s in suffixes],
        y=rates,
        text=[f"{r:.1f}%<br>(n={t})" for r, t in zip(rates, totals)],
        textposition="outside",
        marker_color=["#e74c3c" if r > 15 else "#3498db" for r in rates],
    ))
    fig.update_layout(
        title="末尾別 高設定出現率（設定4以上）",
        xaxis_title="台番号末尾",
        yaxis_title="出現率 (%)",
        yaxis=dict(range=[0, max(rates) * 1.3 if rates else 30]),
    )
    return fig


def create_dow_chart(dow_data: dict) -> go.Figure:
    """曜日別 高設定出現率の棒グラフ"""
    days = ["月", "火", "水", "木", "金", "土", "日"]
    rates = [dow_data.get(d, {}).get("rate", 0) * 100 for d in days]
    totals = [dow_data.get(d, {}).get("total", 0) for d in days]

    fig = go.Figure(data=go.Bar(
        x=days,
        y=rates,
        text=[f"{r:.1f}%<br>(n={t})" for r, t in zip(rates, totals)],
        textposition="outside",
        marker_color=["#e74c3c" if d in ("土", "日") else "#3498db" for d in days],
    ))
    fig.update_layout(
        title="曜日別 高設定出現率（設定4以上）",
        xaxis_title="曜日",
        yaxis_title="出現率 (%)",
        yaxis=dict(range=[0, max(rates) * 1.3 if rates else 30]),
    )
    return fig


def create_reg_trend(df: pd.DataFrame, machine_name: str,
                     unit_number: int) -> go.Figure:
    """特定台のREG確率推移グラフ"""
    filtered = df[
        (df["machine_name"] == machine_name) & (df["unit_number"] == unit_number)
    ].sort_values("play_date")

    if filtered.empty:
        return go.Figure().update_layout(title="データなし")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=filtered["play_date"],
        y=filtered["rb_prob"],
        mode="lines+markers",
        name="RB率（分母）",
        line=dict(color="#e74c3c"),
    ))
    fig.add_trace(go.Scatter(
        x=filtered["play_date"],
        y=filtered["combined_prob"],
        mode="lines+markers",
        name="合算確率（分母）",
        line=dict(color="#3498db"),
    ))
    fig.update_layout(
        title=f"{machine_name} 台番{unit_number} - ボーナス確率推移",
        xaxis_title="日付",
        yaxis_title="確率（分母）",
        yaxis=dict(autorange="reversed"),  # 分母が小さい＝良い → 上に表示
    )
    return fig
