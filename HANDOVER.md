# 🍠 地瓜球桌面監控寵物 (TokenPet) 開發交接與維護指南 (Handover Guide)

歡迎接手 **地瓜球桌面監控寵物** 專案！本專案是一個集成了 **LLM API Token 額度監控** 與 **桌面電子寵物互動** 的高質感 Windows 桌面小玩具。
本指南旨在幫助您快速熟悉架構、開發環境、編譯部署流程，以及開發過程中所有踩過的雷與設計 Knowhow，以便您順利遷移至新電腦或公司內網環境中進行後續測試。

---

## 📂 1. 專案架構與核心檔案介紹

專案採用 **Tkinter + 物理引擎** 的 Windows 無邊框去背景架構，檔案結構簡潔清晰：

* **emojinoko_game.py** (地瓜球物理與動畫核心)：
  * 負責地瓜球的**果凍感呼吸起伏、跳躍、重力下墜、物理碰撞（地面與家具彈性碰撞）**。
  * 管理所有表情狀態（開心、驚嚇、發呆、受傷、睡覺）與動作序列（寫扣、散步、後空翻、唱歌、大口咬下便利貼）。
  * 採用局部 Canvas 像素級重繪，內建**側臉 3D 水平透視收縮機制**。
* **emojinoko_monitor.py** (系統整合、監控與互動核心 - `TokenPet.exe` 入口)：
  * 整合網絡對帳邏輯，定期向 API 伺服器拉取 Token 使用數據，換算成地瓜幣（Coins）並提供視覺反饋（大喊 `TOKEN! 🪙` 與灑幣）。
  * 管理獨立的**貼地影子視窗**（動態縮放與淡出）、**HUD 資訊看板**、**道具商店**以及**便利貼視窗**。
  * 實作**雙螢幕無邊界通行**與**系統級置頂守護 (Topmost Guard)**。
  * 內建雙進程熱更新機制。
* **usage_widget.py** (詳細統計面板 - `TokenMonitor.exe` 入口)：
  * 當用戶點擊「詳細 Token 統計」時啟動的獨立視窗，以直觀的 `matplotlib` 圖表展示每日 Token 用量、API 請求次數與累積費用折線圖。
* **standalone_pet.py** (純寵物本地版入口 - `PurePet.exe` 入口)：
  * 用於無網路、無對帳需求的本地純娛樂模式，僅保留本地投餵、猜拳與商店交互。
* **package_apps.bat**：
  * 用於一鍵編譯打包 `TokenPet.exe`、`TokenMonitor.exe` 與 `PurePet.exe` 的 Windows 批次檔。
* **.agents/AGENTS.md** (專案開發規則)：
  * 定義了編譯完成後，自動更新伺服器 `version.json` 與覆蓋 EXE 的工作流規則。

---

## 🛠️ 2. 開發環境與依賴套件

本專案運行於 **Python 3.12+ (Windows 64-bit)**。

### 依賴套件安裝：
```bash
pip install requests pillow matplotlib numpy keyboard pyinstaller
```
* **注意**：`keyboard` 庫需要管理員權限才能註冊全局快捷鍵，因此在調試與運行時，請確保以管理員權限執行終端或編譯產物。

---

## 🚀 3. 編譯打包與自動部署流程

### A. 本地一鍵編譯
專案目錄下已撰寫 `package_apps.bat`，直接在終端運行即可編譯所有執行檔：
```cmd
package_apps.bat
```
它底層使用的是 `PyInstaller` 指令（以無控制台 `--noconsole` 和單一檔案 `--onefile` 打包）：
```bash
# 編譯主程式 (TokenPet.exe)
python -m PyInstaller --noconsole --onefile --clean --name="TokenPet" emojinoko_monitor.py

# 編譯統計面板 (TokenMonitor.exe)
python -m PyInstaller --noconsole --onefile --clean --name="TokenMonitor" usage_widget.py

# 編譯純寵物本地版 (PurePet.exe)
python -m PyInstaller --noconsole --onefile --clean --name="PurePet" standalone_pet.py
```
編譯完成的 EXE 檔案將輸出至 `D:\token_monitor\dist\` 目錄。

### B. 伺服器更新與自動部署規則 (重要)
為了讓內網其他電腦可以透過「自動檢查更新」取得最新版本，每次編譯新版本時，必須執行以下部署工作：
1. **更新內網版控 JSON**：
   * 修改 `\\power2\RD Share\EdwinLuo\Another Token Bites the Dust\version.json`，將 `version` 改為最新版（如 `2.2.4`），並撰寫對應的 `changelog`（更新日誌）與下載路徑。
2. **覆蓋伺服器執行檔**：
   * 將本地 `D:\token_monitor\dist\TokenPet.exe` 覆蓋複製到 `\\power2\RD Share\EdwinLuo\Another Token Bites the Dust\TokenPet.exe`。

---

## 💾 4. 本地存檔（資料庫）規格說明

地瓜球的存檔儲存在本地的 `.credentials` 檔案中（實質上是一個加密/未加密的 JSON 存檔，由 `save_pet_savegame()` 負責讀寫），欄位規格如下：

```json
{
  "pet_game": {
    "coins": 150,           // 目前地瓜幣餘額
    "level": 3,             // 寵物等級 (累計 XP 升級)
    "xp": 45.0,             // 當前等級的累積經驗值
    "satiety": 85.2,        // 飽食度 (0.0% ~ 100.0%)，每分鐘隨機下降
    "purchased_items": ["futon", "trampoline", "work_laptop"], // 已購買的家具清單
    "spawned_furniture": ["work_laptop"],                      // 目前擺設在桌面上的家具
    "memos": [              // 當前畫面上所有活躍便利貼的清單
      {
        "id": "memo_1781684477", 
        "x": 450, 
        "y": 200, 
        "text": "今天下班要買地瓜球！"
      }
    ],
    "deleted_memos": [     // 便利貼回收桶 (最多保留最近 15 筆)
      {
        "id": "memo_1781684310",
        "x": 300,
        "y": 150,
        "text": "舊的備忘錄 (已被吃掉)",
        "deleted_at": 1781685320.0
      }
    ]
  }
}
```

---

## ⚡ 5. 關鍵踩坑與修復記錄 (技術 Knowhow)

在接手維護或在新電腦上調試時，請務必注意以下歷史 Bug 及其修復機制，防止代碼重構時覆蓋出錯：

### 1️⃣ 數字鍵盤 (NumPad) 小數點變 Delete 的相容性 Bug (v2.2.1)
* **現象**：在 Windows 系統下，Tkinter 的 `Text` 框在 NumLock 開啟時，按數字鍵盤上的小數點（`.`）會產生 `KP_Decimal` 事件，但 Tkinter 預設卻將其綁定為與 `Delete` 鍵相同的行為，導致輸入小數點時卻刪除了前方文字。
* **修復**：在 `MemoWindow` 創立時，顯式遍歷綁定 `<KP_Decimal>`, `<KP_Separator>` 及 `<KP_0>`~`<KP_9>` 到自定義的 `_handle_kp_input` 函數中，手動於游標處插入 `.` 或數字，並返回 `"break"` 阻斷 Tkinter 的預設不相容事件。

### 2️⃣ 影子與地瓜球 X/Y 軸動態物理失聯 Bug (v2.2.3)
* **現象**：地瓜球走路（`walk`）或追逐滑鼠時，改變的是 Canvas 內部的相對座標 `cx`（主視窗螢幕座標固定）。原本影子位置寫死在主視窗中央 `170` 處，導致地瓜球走開時影子仍留在中間；在彈簧床上彈跳時，高度差只判定主視窗 Y 坐標，導致影子無法感應彈跳起伏。
* **修復**：重構 `update_shadow_position`，將影子的 X 座標對接 `self.pet.cx`，並將底部高度對接 `self.pet.cy + 58`。這使影子能完美平移跟隨，且能實時響應彈簧床彈跳的收縮淡出。

### 3️⃣ 視窗失去置頂 (Topmost) 的 Bug (v2.2.4)
* **現象**：Windows 在用戶點擊管理員權限程式（如工作管理員）或高強度焦點切換時，會強制重置普通視窗的 z-order，導致地瓜球與便利貼被壓在底下。
* **修復**：在 `tick_physics` 中引入 **Topmost Guard 守護機制**。每 60 幀（約 1 秒），定時重新申明 `-topmost` 屬性並調用 `lift()`，且在隱藏（`withdrawn`）狀態下自動暫停守護以防被誤喚醒。

### 4️⃣ 重啟進程環境變數污染 Bug (v1.7.2)
* **現象**：點擊更新或更換帳號重啟時，PyInstaller 打包產物會報出 `failed to start embedded python interpreter` 閃退。這是因為新進程繼承了舊進程被刪除的臨時解壓目錄 `_MEIPASS` 等環境變數。
* **修復**：在啟動新進程前，手動自 `os.environ` 中刪除 `PYTHONPATH`、`PYTHONHOME` 與 `PYTHONNOUSERSITE`。

---

## 🏢 6. 遷移至公司內網進行 Token 測試指引

當您將專案搬移到公司內網時，可能需要進行以下設定以對接內網的 API 量與 Token 統計：

1. **調整 API 對帳端點**：
   * 在 `emojinoko_monitor.py` 的對帳請求部分，將向外網伺服器請求的 URL 改為您公司內網的 API 對帳服務端點。
2. **模擬內網 Token 使用量**：
   * 您可以點擊地瓜球右鍵選單的「🟢 模擬用量增加 (Simulate)」，這會模擬本地 Token 的增長，並在桌面觸發產幣與灑落動畫，是離線測試或內網調試對帳視覺反饋的最佳手段。
3. **數據本地保存路徑**：
   * 存檔預設保存在使用者目錄下的 `AppData\Local\Programs` 或專案根目錄 `.credentials` 中，搬移電腦時，只需將專案根目錄下的 `.credentials` 與圖檔資源一併複製到新電腦，即可無縫繼承原本的金幣、等級與便利貼數據！

祝您維護愉快！有任何問題，地瓜球隨時在桌面上陪伴您！
