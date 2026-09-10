# 🍠 TokenPet (地瓜球桌面 AI 監控寵物)

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue.svg" alt="Python Version">
  <img src="https://img.shields.io/badge/GUI-Tkinter%20Canvas-orange.svg" alt="GUI Framework">
  <img src="https://img.shields.io/badge/AI-DeepSeek--V4%20%2F%20GLM--5-purple.svg" alt="AI Model">
  <img src="https://img.shields.io/badge/OS-Windows-success.svg" alt="OS Support">
  <img src="https://img.shields.io/badge/Version-2.9.4-brightgreen.svg" alt="App Version">
</p>

**TokenPet（地瓜球）** 是一隻運行在 Windows 桌面上的軟萌 Q 彈 2.5D 電子寵物與 API Token 即時用量監控助理！它不僅能即時監控 API 費用與用量，還擁有完整的果凍物理彈性引擎、動態 360° 轉身渲染、AI 智慧尬聊、日式和風便利貼、家具互動以及豐富的休閒小遊戲！

## 📥 下載 Unity 整合測試版

前往 [GitHub Releases](https://github.com/zai1245/token_pet/releases)，在最新版本的
**Assets** 下載 `TokenPetIntegrated-...zip`，解壓後執行 `run_unity_preview.cmd`。
請勿單獨啟動 `TokenPetUnity.exe`；完整右鍵選單與遊戲系統需要 Python bridge。
維護者發佈流程見 [`GITHUB_RELEASES.md`](GITHUB_RELEASES.md)。

---

## ✨ 核心特色與功能亮點

### 1. 🎨 向量 2.5D 動態物理與視覺渲染
- **純程式碼 Canvas 向量繪製**：無須任何外部 PNG/GIF 圖檔依賴，極度輕量、高幀率且支援任意解析度縮放防鋸齒。
- **果凍彈力物理引擎**：具備拖曳甩動、自由落體重力加速度、落地擠壓彈跳、空中 360 度後空翻與滾動物理。
- **360° 連續轉身與視線跟隨**：支援平滑的視線跟隨，以及面向背面時的完整垂直居中對稱。

### 2. ☄️ 經典神作夏亞（Char Aznable）造型全套還原
- **官方 1:1 像素級還原**：純白三叉立體鋼角冠、經典六邊形全白立體面甲、純白冷光眼部目鏡槽與軍官全覆式白色鋼盔。
- **三倍速性能提升**：裝備夏亞面具後，地瓜球移動速度與反應力提升 3 倍！

### 3. 🤖 智慧 AI 尬聊與主動碎碎念
- **內網 LLM / AI Nexus 智慧對接**：支援 DeepSeek-V4 與 GLM-5 雙模型秒級 Fallback。
- **即時狀態感知**：地瓜球能感知主人的稱呼、等級、金幣、飽食度與花費，並以軟萌元氣的日系語氣陪伴主人上班。
- **桌面自發搭話**：定時主動彈出關心氣泡，提醒主人喝水、休息與放鬆。

### 4. 📝 日式和風便利貼系統 (Sticky Memos)
- 支援自由拖曳、自由拉伸縮放（Resizable）的半透明和紙便利貼。
- 點擊便利貼關閉按鈕時，地瓜球會主動邁著小短腿走過去把便利貼**「Amu Amu」大口吃掉**並獎勵地瓜幣！
- 具備防誤刪「回收桶恢復」機制。

### 5. 🏠 豐富的互動家具與休閒小遊戲
- **家具互動**：日式溫馨地舖（晚安睡覺）、寫扣筆電（敲鍵盤加班產幣）、柔軟懶人沙發、被爐暖桌、彈簧蹦蹦床（彈跳特技翻滾）、像素電視（4大動態頻道輪播）、蘑菇小夜燈、多肉盆栽。
- **休閒小遊戲**：
  - 🏀 **投籃小遊戲 (Basketball Hoop)**：真實物理投籃與進球七彩碎紙特效。
  - 🍎 **接水果小遊戲 (Catch Fruits)**：接蘋果/草莓避開炸彈。
  - 🎰 **幸運拉霸機 (Lucky Slots)**：連線贏取大獎與豐厚經驗。
  - ✌️ **猜拳對決 (Rock Paper Scissors)**：與地瓜球互動猜拳贏取獎勵。

---

## 🚀 快速開始

### 必備環境
- **作業系統**：Windows 10 / 11
- **Python 版本**：Python 3.10 或更高版本

### 安裝依賴
```bash
pip install requests pyinstaller
```

### 啟動地瓜球
```bash
# 單機獨立模式 (無需 LDAP 聯網)
python emojinoko_monitor.py --standalone

# 完整監控模式 (包含用量對帳與登入)
python emojinoko_monitor.py
```

---

## 📦 打包成單一獨立 EXE 執行檔

使用 PyInstaller 進行單一可執行檔打包：

```powershell
pyinstaller --noconsole --onefile --clean --name="TokenPet" emojinoko_monitor.py
```

編譯完成後，二進制執行檔將生成於 `dist/TokenPet.exe`，可直接雙擊在任何 Windows 電腦上運行。

### Unity 模組化 Renderer PoC（選用）

專案另含一個完全 opt-in 的 Unity 6 renderer PoC，方向是保留簡潔可愛的角色
語言，並把動作、互動與道具掛載模組化。舊 Tkinter／Canvas 地瓜球保持預設，
Unity 缺檔、連線失敗或崩潰時會自動 fallback。建置與執行方式請見
[`UNITY_POC.md`](UNITY_POC.md)；新電腦的完整環境還原、依賴與驗證流程請見
[`DEVELOPMENT.md`](DEVELOPMENT.md)。

---

## 🛠️ 專案結構

```
token_monitor/
├── emojinoko_monitor.py    # 主進程：視窗管理、狀態時鐘、AI通訊、經濟與物理循環
├── emojinoko_game.py       # 繪圖引擎：向量 Canvas 繪製、各類配件、商店與彈窗 UI
├── usage_widget.py         # 用量統計組件與設定管理
├── standalone_pet.py       # 獨立桌寵啟動腳本
├── .gitignore              # Git 安全排除規則 (防護帳密與編譯快取)
└── README.md               # 專案說明文件
```

---

## 📄 開源許可證

本專案遵循 MIT License 規範開源。歡迎自由 Fork、提交 PR 或提出 Issue 一起讓地瓜球變得更可愛！🍠✨
