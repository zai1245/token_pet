# TokenPet Unity 模組化 Renderer PoC

這個 PoC 採用「Python 主程式 + Unity 顯示程序」架構，目標是降低手寫 Canvas
動畫與道具邏輯互相干擾造成的 bug，而不是追求寫實畫質。原本的
`EmojinokoPet`、Tkinter Canvas、物理迴圈、家具與存檔均完整保留，預設也仍然
啟用舊版 renderer。

## 安全回退原則

- 沒有 `--unity-poc` 時，行為與原本版本相同。
- 找不到 Unity build 時，不隱藏舊地瓜球。
- Unity 八秒內未連線時，自動維持／恢復舊地瓜球。
- Unity 程序退出或 IPC 中斷時，自動恢復舊地瓜球。
- Unity 正常啟動後，舊 pet object 與物理迴圈仍在背景運作，沒有被刪除。
- F7 會同步顯示／隱藏 Unity renderer 與既有輔助視窗。

## 目前完成的垂直切片

- 以「えもじの子（仮）」的簡潔表情語言為方向、但造型與配色原創的透明地瓜球資產
- `idle` 呼吸與果凍 secondary motion
- `walk` 彈跳與重心搖擺
- 點擊 `poke` 反應
- 拖曳 Unity 視窗、放手後 `fall / land`
- 動態 viewport safety clamp；旋轉、彈跳與配件不得超出 Player 邊界
- 道具控制器、JSON catalog 與 `Socket_Head`；皇冠是第一個可替換測試物件
- 無邊框、置頂、正式模式不顯示於工作列
- Windows 保留洋紅色色鍵透明與透明區域 hit testing
- Python ↔ Unity localhost TCP JSON protocol
- Unity 雙擊開啟既有 AI Chat、右鍵叫出既有選單

## Unity 安裝與建置

需要 Unity **6000.0.65f1 LTS** 與 Windows Build Support。用 Unity Hub 開啟
`unity_poc/`；第一次載入時，Editor script 會建立空場景並套用 Player
設定。

在 Unity 選擇：

```text
TokenPet > Build Windows PoC
```

輸出位置：

```text
unity_poc/Build/TokenPetUnity.exe
```

也可以用 batch mode：

```powershell
& "C:\Program Files\Unity\Hub\Editor\6000.0.65f1\Editor\Unity.exe" `
  -batchmode -quit `
  -projectPath "$PWD\unity_poc" `
  -executeMethod TokenPet.Editor.TokenPetPocBuilder.BuildWindows `
  -logFile "$PWD\unity-build.log"
```

## 啟動

```powershell
python emojinoko_monitor.py --standalone --unity-poc
```

如 build 放在別處：

```powershell
$env:TOKENPET_UNITY_RENDERER = "D:\path\to\TokenPetUnity.exe"
python emojinoko_monitor.py --standalone --unity-poc
```

也能在既有設定檔加入：

```json
{
  "renderer_backend": "unity",
  "unity_renderer_path": "D:\\path\\to\\TokenPetUnity.exe"
}
```

## PoC 邊界

目前透明方案刻意先使用 Windows color key，以便快速驗證桌寵流程與 IPC。
它把素材未使用的保留洋紅色設為透明，但半透明抗鋸齒邊緣在部分 GPU／縮放設定
上可能出現細微色邊。進入正式版前，應將這層替換成原生 per-pixel-alpha
swapchain／layered-window plugin，並在 Windows 10、Windows 11、混合顯卡與
多螢幕 DPI 環境測試。

Unity build 也不是單一 EXE；正式部署時，現有 updater 必須升級成下載、驗證並
解壓完整 renderer package。PoC 階段不修改目前的正式更新流程。

## 擴充道具

角色動畫只操作 rig，不直接畫帽子或手持物。`TokenPetEquipmentController` 依照
`Assets/TokenPet/Resources/accessory_catalog.json` 的 `id` 與 `slot` 找到道具，
再掛到已註冊的 socket。新的正式道具可做成 Unity Prefab 放進 `Resources`，並在
catalog 填入 prefab resource path；不需要改角色的動畫或 IPC 程式。

目前先有 `head`，後續可用相同方式加上 `face`、`left_hand`、`right_hand`、
`back` 等 socket。表情與手腳 pose 也應沿用同樣原則拆成獨立 layer／controller，
避免再做成一個大型繪圖函式。

## IPC 摘要

Unity 以 `--tokenpet-port=<port>` 連回 Python，只監聽 localhost。

Python → Unity：

- `snapshot`
- `trigger`
- `equip`
- `set_visible`
- `shutdown`

Unity → Python：

- `hello` / `ready`
- `poke`
- `double_click`
- `context_menu`
- `drag_released`
- `action_finished`
- `renderer_closed`
