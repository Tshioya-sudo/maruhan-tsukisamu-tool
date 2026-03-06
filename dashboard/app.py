"""
Streamlit ダッシュボード メインエントリ。

起動方法（ローカル）:
  set SPREADSHEET_ID=あなたのスプレッドシートID
  streamlit run dashboard/app.py

Streamlit Cloud:
  Secretsに PASSWORD, SPREADSHEET_ID, GOOGLE_SHEETS_CREDENTIALS を設定
"""
import streamlit as st

st.set_page_config(
    page_title="マルハン月寒 パチスロ分析",
    page_icon="🎰",
    layout="wide",
)


def check_password():
    """パスワード認証。Streamlit Cloud用。"""
    # パスワードが設定されていなければ認証スキップ（ローカル開発用）
    try:
        correct_pw = st.secrets["PASSWORD"]
    except (FileNotFoundError, KeyError):
        return True

    if st.session_state.get("authenticated"):
        return True

    # 5回失敗でロックアウト
    fail_count = st.session_state.get("login_fail_count", 0)
    if fail_count >= 5:
        st.error("ログイン試行回数が上限（5回）に達しました。ブラウザを再起動してください。")
        return False

    st.title("🔐 ログイン")
    password = st.text_input("パスワードを入力", type="password")
    if st.button("ログイン"):
        if password == correct_pw:
            st.session_state["authenticated"] = True
            st.session_state["login_fail_count"] = 0
            st.rerun()
        else:
            st.session_state["login_fail_count"] = fail_count + 1
            remaining = 5 - st.session_state["login_fail_count"]
            if remaining > 0:
                st.error(f"パスワードが違います（残り{remaining}回）")
            else:
                st.error("ログイン試行回数が上限に達しました。ブラウザを再起動してください。")
    return False


if not check_password():
    st.stop()

st.title("マルハン月寒 パチスロ設定狙いツール")
st.markdown("""
Google Sheetsからデータを読み込み、設定推測・パターン分析を行います。

### ページ一覧
- **🎯 狙い目ダッシュボード** — 具体的な台番号・日付・機種の推薦
- **📋 データ閲覧** — 日付・機種・台番号でフィルタ、CSV/Excelエクスポート
- **🔍 機種別分析** — 機種ごとの詳細分析・確率推移グラフ

左のサイドバーからページを選択してください。
""")
