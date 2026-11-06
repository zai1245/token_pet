# TokenPet Unity 模組化 Renderer PoC

這個 PoC 採用「Python 主程式 + Unity 顯示程序」架構，目標是降低手寫 Canvas
動畫與道具邏輯互相干擾造成的 bug，而不是追求寫實畫質。原本的
`EmojinokoPet`、Tkinter Canvas、物理迴圈、家具與存檔均完整保留，預設也仍然
啟用舊版 renderer。

## v0.8.13 preview：陪伴手帳

Python 主程式新增 `companion_journal.py` 與 `companion_window.py`。右鍵選單可開啟
陪伴手帳、免費打招呼與伸懶腰；揮手／伸展沿用現有 snapshot effects，不增加 IPC
協定或新的 Unity 場景資產。每日小事、6 枚累計徽章與最近 30 天回憶儲存在
`pet_game.companionship`；Canvas 與 Unity 的摸摸、猜拳、投籃、接水果與拉霸共用紀錄。

領獎旗標、地瓜幣與 XP 以同一次原子存檔保存；失敗則恢復領取前的狀態。
每日三份獎勵合計 45 地瓜幣／20 XP，全數領取另送 30 地瓜幣／15 XP。
沒有 Token 使用量目標，月費 HUD 尺寸與內容保持不變。

本機可執行 `python -m unittest discover -s tests -p test_companion_journal.py -v`，
涵蓋跨日、重開防重領、時鐘回撥、回憶保留期限與存檔失敗回復。

## v0.8.12 preview：透明合成與美術整理

Windows 10/11 顯示程序使用 DWM 直接合成 framebuffer alpha。Camera 清為透明黑，
保留半透明邊緣；不再用洋紅色鍵去背，避免角色、配件與家具外圍的亮圈。
維持 D3D11 blit-model swapchain（`PlayerSettings.useFlipModelSwapchain = false`），
並啟用 4× MSAA。合成初始化失敗時退出 Unity，讓 Python 恢復 Canvas。

角色四肢使用單次暖棕色著色；角色與家具加入柔和接觸陰影，家具陰影依實際不透明
輪廓定位。費用標籤、商店與家具選單統一為暖色圓角卡片。標籤維持 252×36 邏輯尺寸，
仍只顯示本月 USD 費用與同步狀態，不加入等級或輸入／輸出用量。

拋擲沿用 v0.8.11 的 Canvas 共用物理：相同速度採樣、重力、阻力、反彈與角度。
拖住角色時 Unity 控制位置，放手確認後再交回 Python。

美術回歸測試：`python -m unittest discover -s tests -p test_unity_art_runtime.py -v`。
有本機 Mono player 與 .NET SDK 時，會以隔離的測試程序在受控黑／白背景驗證真實桌面
透明合成，並將預覽保存至 `scratch/art-review/`；測試元件不會加入正式產物。

## v0.7.0 preview：透明桌面舞台與 Unity 家具實體

Unity Player 現在覆蓋 Windows 虛擬桌面作為透明舞台，但只有角色、家具和已開啟
面板的區域會接收滑鼠；其他透明區域會自動切換成 click-through。因此角色尺寸仍
維持原本約 104px，動作、配件與家具卻不再受 340×300 小視窗裁切，也能跨螢幕移動。

八種既有家具（futon、laptop、trampoline、night lamp、succulent pot、lazy sofa、
pixel TV、kotatsu）都有 Unity 實體、拖曳與 Unity 內右鍵收回選單。Python 繼續管理
存檔座標、商店、角色走向家具、吸附姿勢、計時獎勵與碰撞；`UnityFurnitureProxy`
維持舊物理介面，Unity 失效時則會在原位置重建 Tk 家具視窗。

早期 Unity 專用的速度上限與單次短回彈，已於 v0.8.11 被共用 Canvas 規則取代。
落點仍依角色所在螢幕的 Windows work area 計算。

## v0.6.0 preview：桌面物理與互動回饋橋接

Unity 拖曳放手後，現在會把視窗位置與甩動速度交回既有 Python 桌面物理。
因此角色會像原版一樣受重力下落、撞地回彈、碰到螢幕左右邊界反彈，也會沿用
彈簧床、籃球與完美落地獎勵等既有判定。Unity 只負責呈現落下時的伸展、翻轉與
落地 squash，桌面座標仍只有一套權威來源。

Unity 模式的物理迴圈會使用橋接器保存的桌面座標，不再讀取已隱藏的 Tk 視窗
座標。這可避免拖曳放手後每一幀都從同一個釋放點重新計算，造成角色看似沒有
下落的問題。

「道具與家具」目前會在同一個 Unity 表面內打開暖色商店面板，提供分類頁籤、
金幣、購買／裝備／使用／擺放狀態與捲動清單。交易與存檔仍由原本 Python 規則
處理，因此不會產生第二份經濟資料；關閉按鈕或 Escape 會回到角色畫面。

這一版也把原本隱藏 Canvas 後看不到的浮動提示搬進 Unity，並加入拖曳開始、
快速左右甩動、單擊反應與五連點 fever 的事件橋接。家具開始具備各自的輕動畫，
例如棉被呼吸、筆電游標、彈簧床壓縮、夜燈光暈、電視換台、盆栽擺動與茶杯熱氣。

## v0.5.0：Canvas 內容橋接

Python 仍是養成資料與規則的唯一來源；Unity 只負責呈現。每個 snapshot
除了 state、表情、飽食度、等級、XP 與金幣，現在也會同步食物種類、目前
互動家具、Buff 集合、舉牌文字與加班狀態。

- 表情：normal、happy、blink、dizzy、star、sleep、hungry、open mouth。
- 行為：idle、walk/chase/return、poke、drag、fall/roll/backflip、eat、drink、
  balloon、sleep、turn/back idle、memo 與所有家具專屬姿勢。
- Buff：coffee、candy、bubble tea、matcha、spicy、ice、fever、wave、doze、
  bubble、stretch、singing；包含相應身體變形、色調與粒子。
- 配件：char mask、sunglasses、scholar cap、cat ears、crown、rainbow、halo、
  gentleman hat、demon horns、star sunglasses、bowtie、sakura hairpin、
  gamer headset、wizard hat、clover sprout、bandage。
- 食物／玩具：matcha parfait、souffle pancake、pizza、lollipop、spicy ramen、
  popsicle、candy、bubble tea、ramen、balloon、balloon toy。
- 家具：futon、laptop、trampoline、night lamp、succulent pot，以及舊存檔仍可
  出現的 lazy sofa、pixel TV、kotatsu 和 memo 互動。

所有呈現物件都由 `TokenPetProceduralArt`、`TokenPetLegacyVisuals` 與
`TokenPetEquipmentController` 模組化產生；新增道具不需要修改角色本體貼圖。
Unity 啟動或連線失敗時，原本 Canvas renderer 仍會自動恢復。

## 安全回退原則

- 沒有 `--unity-poc` 時，行為與原本版本相同。
- 找不到 Unity build 時，不隱藏舊地瓜球。
- Unity 四十五秒內未就緒時，自動維持／恢復舊地瓜球。
- Unity 程序退出或 IPC 中斷時，自動恢復舊地瓜球。
- Unity 正常啟動後，舊 pet object 與物理迴圈仍在背景運作，沒有被刪除。
- F7 會同步顯示／隱藏 Unity renderer 與既有輔助視窗。

## 目前完成的垂直切片

- 以「えもじの子（仮）」的簡潔表情語言為方向、但造型與配色原創的透明地瓜球資產
- `idle` 呼吸、果凍 secondary motion、隨機探頭、慢速重心轉移與平滑注視
- `walk` 接地壓縮、離地伸展、彈跳與重心搖擺
- 點擊 `poke` 的預備、反衝與衰減餘震
- 拖曳依游標速度拉伸；放手後 `fall / land` 有速度形變與多段回彈
- `MotionRoot` 統一驅動身體與配件，動作參數由 `motion_profiles.json` 提供
- 身體與四肢已分層；短手短腳由 Unity 程序化骨架即時換 pose，原始完整貼圖仍保留為 fallback
- 五官已從身體分層；Unity 即時控制追視、隨機眨眼、眉毛與各動作的眼睛／嘴型
- 虛擬桌面大小的透明舞台搭配動態 click-through；不再用 viewport clamp 限制動作
- 地瓜球本體直徑仍約 104px，沿用原 Canvas 的 340×300 邏輯框與 (170, 205) 錨點
- Unity 底部只顯示本月 USD 費用；等級、XP、飽食度與地瓜幣可透過既有遊戲功能查看
- 八種家具由 Unity 程序化渲染，可在桌面拖曳與右鍵收回，舊 Tk 家具保留為 fallback
- 道具控制器、JSON catalog 與 head/face/neck/body sockets；完整舊配件皆可替換
- 無邊框、置頂、正式模式不顯示於工作列
- Windows 保留洋紅色色鍵透明與透明區域 hit testing
- Python ↔ Unity localhost TCP JSON protocol
- Unity 雙擊開啟既有 AI Chat；右鍵顯示同色系功能面板。「道具與家具」在 Unity
  表面內顯示，遊戲、便利貼與帳戶功能則繼續呼叫既有 Python 模組

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

`Build Windows PoC` 只建立預覽執行檔，方便先確認畫面。使用者確認版本後，
再於 Unity 選擇 `TokenPet > Package Approved Windows Build`，才會建立完整壓縮包：

```text
dist/TokenPetUnity-v<版本>-win-x64.zip
```

壓縮包會包含 Player 所需資料並排除 `BurstDebugInformation_DoNotShip`。命令列
也可在確認後使用
`-executeMethod TokenPet.Editor.TokenPetPocBuilder.PackageApprovedWindowsBuild`
單獨封裝目前預覽版。

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
python emojinoko_monitor.py --unity-poc
```

Windows 開發環境也可以直接雙擊 repo 根目錄的 `run_unity_preview.cmd`。請勿用
`TokenPetUnity.exe` 測試右鍵功能；該檔案是純 renderer，沒有 Python 選單與遊戲
邏輯。

預設啟動會登入公司 chatbot 並同步本月 Token 用量。需要純離線測試時，使用
`run_unity_preview.cmd offline`，或在 Python 指令加上 `--standalone`；
離線模式的模擬數字不代表公司實際用量。

正式測試請使用上述整合啟動方式。單獨執行 `TokenPetUnity.exe` 只有 renderer，
不包含原本由 Python 管理的功能面板、商店、便利貼與存檔。純 renderer 可按
`Esc` 關閉；整合模式可使用右鍵功能面板的「關閉地瓜球」同時關閉兩個程序。

如 build 放在別處：

```powershell
$env:TOKENPET_UNITY_RENDERER = "D:\path\to\TokenPetUnity.exe"
python emojinoko_monitor.py --unity-poc
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

目前有 `head`、`face`、`neck` 與 `body`；後續可用相同方式加上
`left_hand`、`right_hand`、`back` 等 socket。表情、手腳 pose、舊內容特效與
程序化圖形各自維持獨立 controller，避免再做成一個大型繪圖函式。

## 擴充動作

一般的節奏與幅度調整先修改
`Assets/TokenPet/Resources/motion_profiles.json`，不需要重新編譯狀態機。每個 profile
包含 `duration`、`frequency`、`bob`、`sway`、`tilt`、`squash`、`stretch` 與
`smoothing`。程式內仍保留相同的安全預設值，避免 JSON 缺漏讓 renderer 無法啟動。

角色的桌面座標只能由 `TokenPetWindowsOverlay` 更新；透明 Player 本身固定涵蓋虛擬
桌面，角色與家具再由桌面像素座標換算成 Unity world position。動畫仍只能操作
`MotionRoot`，因此全域位置、局部動作與裝備不會互相覆寫。

## IPC 摘要

Unity 以 `--tokenpet-port=<port>` 連回 Python，只監聽 localhost。

Python → Unity：

- `snapshot`
- `trigger`
- `equip`
- `move_window`
- `popup`
- `show_shop` / `hide_shop`
- `sync_furniture` / `trigger_furniture`
- `set_visible`
- `set_status_visible`
- `shutdown`

Unity → Python：

- `hello` / `ready`
- `poke`
- `double_click`
- `context_menu`
- `drag_started`
- `drag_released`
- `shake`
- `action_finished`
- `shop_action` / `shop_closed`
- `furniture_moved` / `furniture_despawn`
- `renderer_closed`
