"""
Streamlit ダッシュボード メインエントリ。

起動方法:
  set SPREADSHEET_ID=あなたのスプレッドシートID
  streamlit run dashboard/app.py
"""
import streamlit as st

st.set_page_config(
    page_title="マルハン月寒 パチスロ分析",
    page_icon="🎰",
    layout="wide",
)

st.title("マルハン月寒 パチスロ設定狙いツール")
st.markdown("""
Google Sheetsからデータを読み込み、設定推測・パターン分析を行います。

### ページ一覧
- **📊 ダッシュボード** — ヒートマップ・曜日別/末尾別パターン分析
- **📋 データ閲覧** — 日付・機種・台番号でフィルタ、CSV/Excelエクスポート
- **🔍 機種別分析** — 機種ごとの詳細分析・確率推移グラフ

### 使い方
1. 左のサイドバーからページを選択
2. Google Sheets認証情報が `config/credentials.json` に配置されていること
3. 環境変数 `SPREADSHEET_ID` が設定されていること
""")
