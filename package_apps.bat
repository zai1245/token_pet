@echo off
chcp 65001 > nul
echo ==================================================
echo         地瓜球桌寵與 Token 監控器打包工具
echo ==================================================
echo.
echo 正在確認必要套件是否安裝...
python -m pip install requests matplotlib pyinstaller

echo.
echo ──────────────────────────────────────────────────
echo 1. 正在打包：Token 統計統計統計監視統計 (TokenMonitor.exe)...
echo ──────────────────────────────────────────────────
pyinstaller --noconsole --onefile --clean --name="TokenMonitor" usage_widget.py

echo.
echo ──────────────────────────────────────────────────
echo 2. 正在打包：地瓜球桌面寵物 (TokenPet.exe)...
echo ──────────────────────────────────────────────────
pyinstaller --noconsole --onefile --clean --name="TokenPet" emojinoko_monitor.py

echo.
echo ──────────────────────────────────────────────────
echo 3. 正在打包：純萌寵單機版地瓜球 (PurePet.exe)...
echo ──────────────────────────────────────────────────
pyinstaller --noconsole --onefile --clean --name="PurePet" standalone_pet.py

echo.
echo ==================================================
echo 打包完成！請至 dist 資料夾取得以下檔案：
echo  - dist\TokenMonitor.exe (原本統計面板)
echo  - dist\TokenPet.exe (地瓜球桌寵 + API 對帳功能)
echo  - dist\PurePet.exe (純萌寵單機版)
echo ==================================================
pause
