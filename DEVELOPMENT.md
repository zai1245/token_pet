# TokenPet 開發環境

這份文件是新電腦的可重現環境清單。舊版 Tkinter/Canvas 是預設 renderer；
Unity 是 opt-in 顯示程序，兩者共用 Python 主程式、存檔與互動邏輯。

## 1. 必要工具

- Windows 10 或 Windows 11（Unity 透明桌寵目前只支援 Windows）
- Git
- Python 3.11 或 3.12（64-bit，安裝時勾選 `tcl/tk and IDLE`）
- Unity Hub
- Unity Editor **6000.0.65f1**
- Unity 模組：**Windows Build Support (Mono)**；需要 IL2CPP 發行版時再加裝
  **Windows Build Support (IL2CPP)**

Unity 精確 revision 是 `a18e2220bd50`，並記錄於
`unity_poc/ProjectSettings/ProjectVersion.txt`。Unity package 版本由
`unity_poc/Packages/manifest.json` 與 `packages-lock.json` 鎖定。

## 2. Clone 與 Python 環境

```powershell
git clone https://github.com/zai1245/token_pet.git
cd token_pet

py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

只執行應用程式、不打包時，可以改裝 `requirements.txt`。`.credentials`、
存檔、`.env` 與本機 log 都不得 commit。

## 3. 先驗證舊版 renderer

```powershell
python emojinoko_monitor.py --standalone
```

這一步不需要 Unity。若 Unity build 不存在或 IPC 中斷，正式流程也會自動回到
這個 Canvas renderer。

## 4. 開啟與建置 Unity renderer

在 Unity Hub 用上述 Editor 版本開啟 repo 內的 `unity_poc` 資料夾。第一次開啟會
依 lock file 還原 package，並由 Editor script 確認 PoC scene 與 Player 設定。

Editor 選單建置：

```text
TokenPet > Build Windows PoC
```

或使用 batch mode；請依安裝位置調整第一行：

```powershell
$UnityEditor = "C:\Program Files\Unity\Hub\Editor\6000.0.65f1\Editor\Unity.exe"
& $UnityEditor `
  -batchmode -quit `
  -projectPath "$PWD\unity_poc" `
  -executeMethod TokenPet.Editor.TokenPetPocBuilder.BuildWindows `
  -logFile "$PWD\unity-build.log"
if ($LASTEXITCODE -ne 0) { throw "Unity build failed: $LASTEXITCODE" }
```

如果 batch mode 顯示 `Access token unavailable`，先登入並保持 Unity Hub 開啟，
確認 Hub 的「設定 → 授權」中有有效的 Unity Personal，再重跑；不需要退還授權。

輸出是 `unity_poc/Build/TokenPetUnity.exe` 與同層的 Unity data/runtime 檔案。
`Build/`、`Library/`、`Logs/`、`UserSettings/` 都是本機產物，已由 `.gitignore`
排除；不要只複製 EXE，也不要 commit 這些目錄。

## 5. 整合啟動與驗證

```powershell
python emojinoko_monitor.py --standalone --unity-poc

python -m unittest discover -s tests -v
python -m py_compile emojinoko_monitor.py unity_renderer_bridge.py
git diff --check
```

若 Player 放在別處：

```powershell
$env:TOKENPET_UNITY_RENDERER = "D:\path\to\TokenPetUnity.exe"
python emojinoko_monitor.py --standalone --unity-poc
```

## 6. 必須提交與不得提交

Unity 功能變更至少應提交：

- `unity_poc/Assets/`（包含 `.meta`）
- `unity_poc/Packages/manifest.json`
- `unity_poc/Packages/packages-lock.json`
- `unity_poc/ProjectSettings/`
- Python bridge、tests 與相關文件

不得提交：

- `unity_poc/Library/`、`Temp/`、`Obj/`、`Logs/`、`UserSettings/`
- `unity_poc/Build/` 或單獨的 `TokenPetUnity.exe`
- `.credentials`、個人存檔、log 與機器專屬路徑

## 7. 目前架構邊界

- Python 是狀態、經濟、AI、家具與存檔的 source of truth。
- Unity 只負責角色顯示、動畫、點擊、拖曳與道具 socket。
- 原生 Windows 視窗負責桌面座標；Unity rig 必須留在 viewport 安全區，不能用
  `rigRoot.position` 模擬桌面移動。
- Unity renderer 必須維持 opt-in，且任何啟動／連線失敗都要保留 Canvas fallback。

## 8. GitHub Release

完整發佈與下載流程請見 `GITHUB_RELEASES.md`。完成預覽驗收、調整
`RendererVersion`、commit 並 push 後，可執行：

```powershell
python tools/publish_github_release.py
```

GitHub Release 只上傳 `TokenPetIntegrated-...zip`，避免使用者誤下載缺少右鍵選單與
Python 遊戲系統的 renderer-only 套件。
