# GitHub Release 發佈與下載

TokenPet 的完整測試版透過 GitHub Releases 發佈，不需要再把 ZIP 搬到 Google Drive。
Release 資產必須使用 `TokenPetIntegrated-...zip`；只有這個整合包同時包含 Unity
Player、Python bridge、右鍵選單及遊戲系統。

## 使用者下載

開啟：

```text
https://github.com/zai1245/token_pet/releases
```

選擇最新版本，在 **Assets** 下載 `TokenPetIntegrated-...zip`，解壓後雙擊
`run_unity_preview.cmd`。不要單獨啟動 `TokenPetUnity.exe`，否則不會有 Python
負責的完整功能。

若 Unity 小視窗出現後仍停留在 Canvas，先等待最多 45 秒。仍未切換時，雙擊
`collect_debug_logs.cmd`，桌面會產生 `TokenPet-debug-logs-....zip`；回報問題時
附上這個 ZIP。它包含 Python/IPC 診斷與 Unity Player log，不包含登入密碼。

## 維護者一鍵發佈

需求：Git、Python、GitHub CLI `gh`、Unity `6000.0.65f1`，且 `gh auth status`
顯示已登入。發佈前先調整 `TokenPetPocBootstrap.RendererVersion`、commit 並 push。

```powershell
python tools/publish_github_release.py
```

腳本會依序：

1. 確認 working tree 乾淨，而且目前 commit 已推到 `origin`。
2. 執行測試。
3. 用鎖定的 Unity 版本重建 Windows Player。
4. 建立完整整合 ZIP，並驗證 ZIP 完整性。
5. 建立 GitHub Release 與 tag，再上傳 ZIP；名稱含 `preview` 或 `dev` 時自動標成 prerelease。

若本機已有剛通過人工驗收的 ZIP，只要發佈、不重新建置：

```powershell
python tools/publish_github_release.py --publish-existing
```

Unity 不在預設位置時，先設定：

```powershell
$env:UNITY_EDITOR = "D:\path\to\Unity.exe"
```
