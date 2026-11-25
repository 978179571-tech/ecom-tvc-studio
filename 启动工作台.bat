@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动 ecom-tvc-studio 电商主图视频工作台...
start "" "http://127.0.0.1:18765"
"d:\CCJ\github\rea-video\.venv\Scripts\python.exe" "d:\CCJ\github\ecom-tvc-studio\app.py"
pause
