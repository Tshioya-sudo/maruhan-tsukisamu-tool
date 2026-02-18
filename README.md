# マルハン月寒 パチスロ設定狙いツール

マルハン月寒店（札幌市豊平区）に特化したパチスロ設定狙い支援ツール。

- GitHub Actions + Playwright でみんレポから毎日自動でデータを取得
- Google Sheets にデータを蓄積し、スマホ・PCどこからでも閲覧可能
- ローカルの Streamlit ダッシュボードで高度な分析・パターン検出

## セットアップ手順

### 1. リポジトリのクローン

```bash
git clone https://github.com/YOUR_USERNAME/maruhan-tsukisamu-tool.git
cd maruhan-tsukisamu-tool
pip install -r requirements.txt
playwright install chromium
```

### 2. Google Cloud設定

1. [Google Cloud Console](https://console.cloud.google.com/) でプロジェクト作成
2. 「APIとサービス」→ Google Sheets API を有効化
3. 「認証情報」→ サービスアカウント作成 → JSONキーダウンロード
4. Google Sheetsで新規スプレッドシート作成
   - スプレッドシート名: `マルハン月寒_パチスロデータ`
5. スプレッドシートの共有設定でサービスアカウントのメールアドレスに「編集者」権限を付与

### 3. スプレッドシート初期セットアップ

```bash
# ローカル: config/credentials.json にサービスアカウントJSONキーを配置
set SPREADSHEET_ID=あなたのスプレッドシートID
python scripts/setup_sheets.py
```

4つのシート（daily_data, daily_summary, scrape_log, machines）が自動作成されます。

### 4. GitHub Secrets設定

リポジトリの Settings → Secrets and variables → Actions で以下を登録:
- `GOOGLE_SHEETS_CREDENTIALS`: サービスアカウントJSONキーの中身をそのまま貼り付け
- `SPREADSHEET_ID`: スプレッドシートのURL中のID部分

### 5. 初回テスト実行

GitHubリポジトリの Actions タブ → 「Daily Maruhan Tsukisamu Data Scraper」→ 「Run workflow」で手動実行。

### 6. ローカルダッシュボード起動（任意）

```bash
set SPREADSHEET_ID=あなたのスプレッドシートID
streamlit run dashboard/app.py
```

## 対象機種（Phase 1）

| 機種 | 台数 | タイプ |
|------|------|--------|
| マイジャグラーV | 40台 | ジャグラー |
| スマスロ 沖ドキ!DUO アンコール | 36台 | AT |
| ネオアイムジャグラーEX | 24台 | ジャグラー |
| ゴーゴージャグラー３ | 22台 | ジャグラー |
| SアイムジャグラーＥＸ | 12台 | ジャグラー |
| ウルトラミラクルジャグラー | 6台 | ジャグラー |

## 運用コスト

全て無料（GitHub Actions無料枠 + Google Sheets API無料枠）。
