@echo off
chcp 65001 >nul
echo ==========================================
echo   マルハン月寒 分析ダッシュボード 起動中...
echo ==========================================
echo.

set SPREADSHEET_ID=1vZ285mSvemUid8qkQ3e6ynCUfQD6pNjw3_jFnQTFhhY
set PYTHONPATH=d:\Downloads\HTML修了課題\HTML修了課題\ポートフォリオ\Lib\site-packages

cd /d "d:\Downloads\HTML修了課題\HTML修了課題\ポートフォリオ\maruhan-tsukisamu-tool"

echo ブラウザで http://localhost:8501 を開いてください
echo 終了するにはこのウィンドウを閉じてください
echo.

C:\Python314\python.exe -c "import sys; sys.path.insert(0, r'd:\Downloads\HTML修了課題\HTML修了課題\ポートフォリオ\Lib\site-packages'); from streamlit.web.cli import main; sys.argv=['streamlit', 'run', 'dashboard/app.py', '--server.headless=true']; main()"

pause
