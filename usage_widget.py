import tkinter as tk
import requests
import threading
import time
import json
import base64
import os
import sys
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# 設定 matplotlib 使用微軟正黑體，避免中文亂碼
matplotlib.rcParams['font.family'] = 'Microsoft JhengHei'
matplotlib.rcParams['axes.unicode_minus'] = False

# ===================== 設定區 =====================
OPENWEBUI_BASE_URL = "http://chatbot.phison.com:8080"  # Open WebUI 伺服器網址
REFRESH_INTERVAL = 60       # 自動刷新間隔（秒）
WINDOW_ALPHA = 0.92         # 視窗預設透明度（0.0~1.0）
WINDOW_BG = "#1e1e2e"       # 主背景色
TEXT_COLOR = "#cdd6f4"      # 主要文字色
ACCENT_COLOR = "#89b4fa"    # 強調色（藍）
GREEN_COLOR = "#a6e3a1"     # 數值色（綠）
YELLOW_COLOR = "#f9e2af"    # 費用色（黃）
PINK_COLOR = "#f38ba8"      # 警告/API色（粉紅）
TITLE_COLOR = "#f38ba8"     # 標題色
CHART_BG = "#181825"        # 圖表背景色

# 取得配置儲存目錄
def get_config_dir():
    """取得配置儲存目錄：若為 exe 打包模式，回傳 exe 所在目錄；否則回傳腳本目錄；若無寫入權限， fallback 到家目錄"""
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 檢查該目錄是否具備寫入權限
    if not os.access(base_dir, os.W_OK):
        base_dir = os.path.join(os.path.expanduser("~"), ".token_monitor")
        os.makedirs(base_dir, exist_ok=True)
    return base_dir

# 儲存帳號密碼與配置的檔案路徑（與程式同目錄或 fallback 目錄）
CRED_FILE = os.path.join(get_config_dir(), ".credentials")
# ==================================================

# 網路請求重試次數與間隔（應付公司內網/VPN 短暫抖動造成的連線失敗）
REQUEST_RETRY_COUNT = 2
REQUEST_RETRY_DELAY = 1.5  # 秒


DEBUG_LOG_FILE = os.path.join(get_config_dir(), "debug.log")


def _debug_log(msg):
    """將除錯訊息附加寫入 debug.log，附上時間戳記，方便排查間歇性逾時問題"""
    try:
        with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def _request_with_retry(method, url, **kwargs):
    """
    對單次 HTTP 請求做簡單重試，只針對連線類錯誤（ConnectionError/Timeout）重試，
    HTTP 狀態碼錯誤（如 401/500）不重試，直接回傳讓呼叫端處理。
    """
    last_exc = None
    for attempt in range(REQUEST_RETRY_COUNT + 1):
        start = time.time()
        try:
            r = requests.request(method, url, **kwargs)
            elapsed = time.time() - start
            _debug_log(f"{method.upper()} {url} -> {r.status_code} ({elapsed:.1f}s, attempt {attempt + 1})")
            return r
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            elapsed = time.time() - start
            _debug_log(f"{method.upper()} {url} -> {e.__class__.__name__} ({elapsed:.1f}s, attempt {attempt + 1})")
            last_exc = e
            if attempt < REQUEST_RETRY_COUNT:
                time.sleep(REQUEST_RETRY_DELAY)
    raise last_exc


# ──────────────────────────────────────────────────
# 帳號密碼與配置管理工具函式
# 使用 base64 做簡單編碼，避免明文儲存
# ──────────────────────────────────────────────────
def _encode(text):
    """將字串 base64 編碼"""
    return base64.b64encode(text.encode()).decode()

def _decode(text):
    """將 base64 字串解碼"""
    return base64.b64decode(text.encode()).decode()

def load_config():
    """讀取完整配置字典"""
    try:
        if os.path.exists(CRED_FILE):
            with open(CRED_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def save_config(config_dict):
    """更新並儲存配置字典"""
    try:
        data = load_config()
        data.update(config_dict)
        with open(CRED_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def save_credentials(email, password):
    """將帳號密碼編碼後儲存至配置"""
    save_config({"email": _encode(email), "password": _encode(password)})

def load_credentials():
    """從配置讀取並解碼帳號密碼，若無則回傳空字串"""
    data = load_config()
    if "email" in data and "password" in data:
        try:
            return _decode(data["email"]), _decode(data["password"])
        except Exception:
            pass
    return "", ""

def delete_credentials():
    """刪除儲存的帳號密碼（但保留其他視窗位置、快捷鍵設定）"""
    data = load_config()
    data.pop("email", None)
    data.pop("password", None)
    try:
        with open(CRED_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


# ===================== 全域快捷鍵管理 (Windows API) =====================
IS_WINDOWS = sys.platform == "win32"
if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

WM_HOTKEY = 0x0312
WM_USER = 0x0400
UM_REGISTER = WM_USER + 1
UM_UNREGISTER = WM_USER + 2
UM_QUIT = WM_USER + 3

# Modifiers
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

class HotkeyManager:
    def __init__(self, on_hotkey_pressed):
        self.on_hotkey_pressed = on_hotkey_pressed
        self.thread = None
        self.thread_id = None
        self.hotkey_id = 1
        if IS_WINDOWS:
            self.user32 = ctypes.windll.user32
            self.kernel32 = ctypes.windll.kernel32

    def start(self):
        if not IS_WINDOWS:
            return
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        while self.thread_id is None:
            time.sleep(0.01)

    def _run(self):
        msg = wintypes.MSG()
        # 強制系統為此執行緒建立訊息佇列
        self.user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 0)
        self.thread_id = self.kernel32.GetCurrentThreadId()

        while self.user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) != 0:
            if msg.message == WM_HOTKEY:
                if self.on_hotkey_pressed:
                    self.on_hotkey_pressed()
            elif msg.message == UM_REGISTER:
                self.user32.UnregisterHotKey(0, self.hotkey_id)
                modifiers = msg.wParam
                vk = msg.lParam
                self.user32.RegisterHotKey(0, self.hotkey_id, modifiers, vk)
            elif msg.message == UM_UNREGISTER:
                self.user32.UnregisterHotKey(0, self.hotkey_id)
            elif msg.message == UM_QUIT:
                self.user32.UnregisterHotKey(0, self.hotkey_id)
                break
            self.user32.TranslateMessage(ctypes.byref(msg))
            self.user32.DispatchMessageW(ctypes.byref(msg))

    def register(self, modifiers, vk):
        if IS_WINDOWS and self.thread_id:
            self.user32.PostThreadMessageW(self.thread_id, UM_REGISTER, modifiers, vk)

    def unregister(self):
        if IS_WINDOWS and self.thread_id:
            self.user32.PostThreadMessageW(self.thread_id, UM_UNREGISTER, 0, 0)

    def stop(self):
        if IS_WINDOWS and self.thread_id:
            self.user32.PostThreadMessageW(self.thread_id, UM_QUIT, 0, 0)
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=1.0)


# ──────────────────────────────────────────────────
# 登入視窗
# ──────────────────────────────────────────────────
class LoginWindow:
    def __init__(self, root, on_login_success):
        """
        root: tkinter 根視窗
        on_login_success: 登入成功後的 callback 函式
        """
        self.root = root
        self.on_login_success = on_login_success

        # 無邊框、永遠置頂、設定背景色
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=WINDOW_BG)

        # 置中顯示
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        self.root.geometry(f"300x260+{screen_w//2 - 150}+{screen_h//2 - 130}")

        # 拖曳用變數
        self._drag_x = 0
        self._drag_y = 0

        self._build_ui()
        self._try_auto_login()  # 嘗試自動登入（若有儲存帳密）

    def _build_ui(self):
        """建立登入視窗 UI"""

        # 標題列（可拖曳）
        title_bar = tk.Frame(self.root, bg="#313244", height=32)
        title_bar.pack(fill=tk.X)
        title_bar.pack_propagate(False)
        title_bar.bind("<ButtonPress-1>", self._on_drag_start)
        title_bar.bind("<B1-Motion>", self._on_drag_motion)

        tk.Label(title_bar, text="🔐 登入 Open WebUI",
                 bg="#313244", fg=TITLE_COLOR,
                 font=("微軟正黑體", 11, "bold")).pack(side=tk.LEFT, padx=10, pady=4)

        # 關閉按鈕
        close = tk.Label(title_bar, text=" ✕ ", bg="#313244", fg=PINK_COLOR,
                         font=("Arial", 12, "bold"), cursor="hand2")
        close.pack(side=tk.RIGHT, padx=6)
        close.bind("<Button-1>", lambda e: self.root.destroy())

        # 表單區域
        form = tk.Frame(self.root, bg=WINDOW_BG, padx=20, pady=16)
        form.pack(fill=tk.BOTH, expand=True)

        # Email 輸入欄
        tk.Label(form, text="帳號（Email）", bg=WINDOW_BG, fg=TEXT_COLOR,
                 font=("微軟正黑體", 9)).pack(anchor="w")
        self.email_var = tk.StringVar()
        self.email_entry = tk.Entry(form, textvariable=self.email_var,
                                    bg="#313244", fg=TEXT_COLOR,
                                    insertbackground=TEXT_COLOR,
                                    relief=tk.FLAT, font=("微軟正黑體", 10))
        self.email_entry.pack(fill=tk.X, pady=(2, 10), ipady=4)

        # 密碼輸入欄（顯示 •）
        tk.Label(form, text="密碼", bg=WINDOW_BG, fg=TEXT_COLOR,
                 font=("微軟正黑體", 9)).pack(anchor="w")
        self.password_var = tk.StringVar()
        pw_entry = tk.Entry(form, textvariable=self.password_var,
                            show="•", bg="#313244", fg=TEXT_COLOR,
                            insertbackground=TEXT_COLOR,
                            relief=tk.FLAT, font=("微軟正黑體", 10))
        pw_entry.pack(fill=tk.X, pady=(2, 8), ipady=4)
        pw_entry.bind("<Return>", lambda e: self._do_login())  # 按 Enter 登入

        # 記住帳號密碼 checkbox
        self.remember_var = tk.BooleanVar(value=False)
        tk.Checkbutton(form, text="記住帳號密碼",
                       variable=self.remember_var,
                       bg=WINDOW_BG, fg=TEXT_COLOR,
                       selectcolor="#313244",
                       activebackground=WINDOW_BG,
                       activeforeground=ACCENT_COLOR,
                       font=("微軟正黑體", 9)).pack(anchor="w", pady=(0, 6))

        # 錯誤訊息標籤
        self.error_label = tk.Label(form, text="", bg=WINDOW_BG, fg=PINK_COLOR,
                                    font=("微軟正黑體", 8))
        self.error_label.pack(anchor="w")

        # 登入按鈕
        self.login_btn = tk.Button(form, text="登入",
                                   bg=ACCENT_COLOR, fg=WINDOW_BG,
                                   font=("微軟正黑體", 10, "bold"),
                                   relief=tk.FLAT, cursor="hand2",
                                   command=self._do_login)
        self.login_btn.pack(fill=tk.X, ipady=5)

        # 若有儲存帳密則自動填入
        saved_email, saved_password = load_credentials()
        if saved_email and saved_password:
            self.email_var.set(saved_email)
            self.password_var.set(saved_password)
            self.remember_var.set(True)
        else:
            self.email_entry.focus()

    def _try_auto_login(self):
        """若有儲存帳密則自動嘗試登入"""
        saved_email, saved_password = load_credentials()
        if saved_email and saved_password:
            self.error_label.config(text="⏳ 自動登入中...", fg=ACCENT_COLOR)
            self.login_btn.config(text="登入中...", state=tk.DISABLED)
            threading.Thread(target=self._try_login,
                             args=(saved_email, saved_password), daemon=True).start()

    def _do_login(self):
        """使用者按下登入按鈕時觸發"""
        email = self.email_var.get().strip()
        password = self.password_var.get()
        if not email or not password:
            self.error_label.config(text="請輸入帳號和密碼！", fg=PINK_COLOR)
            return
        self.login_btn.config(text="登入中...", state=tk.DISABLED)
        self.error_label.config(text="")
        # 背景執行登入，避免 UI 卡住
        threading.Thread(target=self._try_login,
                         args=(email, password), daemon=True).start()

    def _try_login(self, email, password):
        """實際呼叫 LDAP 登入 API"""
        try:
            r = _request_with_retry(
                "post",
                f"{OPENWEBUI_BASE_URL}/api/v1/auths/ldap",
                json={"user": email, "password": password},
                timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                # 依據 checkbox 決定是否儲存帳密
                if self.remember_var.get():
                    save_credentials(email, password)
                else:
                    delete_credentials()
                # 登入成功，回傳 token、phison_token、姓名、帳密
                self.root.after(0, self.on_login_success,
                                data.get("token", ""),
                                data.get("phison_token", ""),
                                data.get("name", ""),
                                email, password)
            else:
                msg = r.json().get("detail", "登入失敗！")
                self.root.after(0, self._login_failed, msg)
        except Exception as e:
            self.root.after(0, self._login_failed, str(e))

    def _login_failed(self, msg):
        """登入失敗時顯示錯誤訊息並恢復按鈕"""
        self.error_label.config(text=f"❌ {msg[:50]}", fg=PINK_COLOR)
        self.login_btn.config(text="登入", state=tk.NORMAL)

    def _on_drag_start(self, event):
        """記錄拖曳起始位置"""
        self._drag_x = event.x
        self._drag_y = event.y

    def _on_drag_motion(self, event):
        """拖曳視窗移動"""
        x = self.root.winfo_x() + (event.x - self._drag_x)
        y = self.root.winfo_y() + (event.y - self._drag_y)
        self.root.geometry(f"+{x}+{y}")


# ──────────────────────────────────────────────────
# 主要用量統計便利貼視窗
# ──────────────────────────────────────────────────
class UsageWidget:
    def __init__(self, root, token, phison_token, name, email, password):
        """
        root: tkinter 根視窗
        token: Open WebUI session token
        phison_token: 公司客製 API 用的 token
        name: 使用者姓名
        email/password: 用於 token 過期時自動重新登入
        """
        self.root = root
        self.TOKEN = token
        self.PHISON_TOKEN = phison_token
        self.user_name = name
        self.email = email
        self.password = password

        # 視窗基本設定
        self.root.overrideredirect(True)        # 無邊框
        self.root.attributes("-topmost", True)  # 預設置頂
        self.root.attributes("-alpha", WINDOW_ALPHA)
        self.root.configure(bg=WINDOW_BG)
        self.root.minsize(320, 100)

        # 讀取上次視窗位置與大小，若無則預設右下角
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        default_x = screen_w - 370
        default_y = screen_h - 560
        default_w = 340
        default_h = 520

        config = load_config()
        try:
            w = int(config.get("width", default_w))
            h = int(config.get("height", default_h))
            x = int(config.get("x", default_x))
            y = int(config.get("y", default_y))
        except Exception:
            w, h, x, y = default_w, default_h, default_x, default_y

        # 確保視窗位置不會完全在螢幕外（例如解析度切換）
        if x < -50 or x > screen_w - 50:
            x = default_x
        if y < -50 or y > screen_h - 50:
            y = default_y

        self.root.geometry(f"{w}x{h}+{x}+{y}")

        # 拖曳與調整大小用的變數
        self._drag_x = 0
        self._drag_y = 0
        self._minimized = False         # 是否最小化
        self._normal_height = h         # 最小化前記錄高度
        self._resize_start_x = 0
        self._resize_start_y = 0
        self._resize_start_w = 0
        self._resize_start_h = 0

        # 資料快取
        self._usage_data = []
        self._auth_data = {}

        # UI 狀態變數
        self._show_pie = tk.BooleanVar(value=False)     # 圓餅圖開關
        self._show_settings = False                      # 設定面板是否展開
        self._topmost = tk.BooleanVar(value=True)        # 視窗置頂開關

        # 各區塊折疊狀態（False = 展開，True = 收合）
        self._collapsed = {"費用": False, "明細": False}

        # 初始化全域快捷鍵管理器 (僅 Windows 支援)
        self.hotkey_manager = None
        if IS_WINDOWS:
            self.hotkey_manager = HotkeyManager(on_hotkey_pressed=self._on_hotkey_pressed)
            self.hotkey_manager.start()

        # 載入儲存的快捷鍵 (第一次開啟預設為 F7)
        if "hotkey" in config:
            self.hotkey_config = config["hotkey"]
        else:
            self.hotkey_config = {
                "modifiers": [],
                "vk": 118,
                "display": "F7"
            }
        if self.hotkey_config and self.hotkey_manager:
            self._register_saved_hotkey()

        self._build_ui()
        self._start_auto_refresh()

        # 綁定焦點事件，用於判斷視窗是否處於作用中
        self._window_focused = True  # 初始啟動時為 True
        self.root.bind("<FocusIn>", self._on_focus_in)
        self.root.bind("<FocusOut>", self._on_focus_out)

        # 綁定視窗銷毀事件，用於釋放快捷鍵資源
        self.root.bind("<Destroy>", self._on_destroy)

    def _build_ui(self):
        """建立主視窗 UI"""

        # ── 標題列 ──
        self.title_bar = tk.Frame(self.root, bg="#313244", height=32)
        self.title_bar.pack(fill=tk.X)
        self.title_bar.pack_propagate(False)
        self.title_bar.bind("<ButtonPress-1>", self._on_drag_start)
        self.title_bar.bind("<B1-Motion>", self._on_drag_motion)
        self.title_bar.bind("<ButtonRelease-1>", self._on_drag_end)  # 拖曳結束儲存位置
        self.title_bar.bind("<Double-Button-1>", self._toggle_minimize)  # 雙擊最小化

        title_label = tk.Label(self.title_bar, text="📊 本月用量統計",
                               bg="#313244", fg=TITLE_COLOR,
                               font=("微軟正黑體", 11, "bold"))
        title_label.pack(side=tk.LEFT, padx=10, pady=4)
        title_label.bind("<ButtonPress-1>", self._on_drag_start)
        title_label.bind("<B1-Motion>", self._on_drag_motion)
        title_label.bind("<ButtonRelease-1>", self._on_drag_end)  # 拖曳結束儲存位置
        title_label.bind("<Double-Button-1>", self._toggle_minimize)

        # 右側按鈕群組
        btn_frame = tk.Frame(self.title_bar, bg="#313244")
        btn_frame.pack(side=tk.RIGHT, padx=6)

        # 最小化按鈕
        self.min_btn = tk.Label(btn_frame, text=" ─ ", bg="#313244", fg="#cdd6f4",
                                font=("Arial", 12, "bold"), cursor="hand2")
        self.min_btn.pack(side=tk.LEFT)
        self.min_btn.bind("<Button-1>", lambda e: self._toggle_minimize())

        # 設定按鈕
        settings_btn = tk.Label(btn_frame, text=" ⚙ ", bg="#313244", fg="#cdd6f4",
                                font=("Arial", 11), cursor="hand2")
        settings_btn.pack(side=tk.LEFT)
        settings_btn.bind("<Button-1>", lambda e: self._toggle_settings())

        # 登出按鈕
        logout_btn = tk.Label(btn_frame, text=" ⏏ ", bg="#313244", fg="#cdd6f4",
                              font=("Arial", 11), cursor="hand2")
        logout_btn.pack(side=tk.LEFT)
        logout_btn.bind("<Button-1>", lambda e: self._logout())

        # 關閉按鈕
        close_btn = tk.Label(btn_frame, text=" ✕ ", bg="#313244", fg=PINK_COLOR,
                             font=("Arial", 12, "bold"), cursor="hand2")
        close_btn.pack(side=tk.LEFT)
        close_btn.bind("<Button-1>", lambda e: self.root.destroy())

        # ── 設定面板（預設隱藏，點 ⚙ 展開）──
        self.settings_frame = tk.Frame(self.root, bg="#252535", padx=14, pady=8)

        # 置頂開關
        topmost_row = tk.Frame(self.settings_frame, bg="#252535")
        topmost_row.pack(fill=tk.X, pady=2)
        tk.Label(topmost_row, text="📌 視窗置頂", bg="#252535", fg=TEXT_COLOR,
                 font=("微軟正黑體", 9)).pack(side=tk.LEFT)
        tk.Checkbutton(topmost_row, variable=self._topmost,
                       bg="#252535", fg=TEXT_COLOR, selectcolor="#313244",
                       activebackground="#252535",
                       command=self._apply_topmost).pack(side=tk.RIGHT)

        # 透明度滑桿
        alpha_row = tk.Frame(self.settings_frame, bg="#252535")
        alpha_row.pack(fill=tk.X, pady=2)
        tk.Label(alpha_row, text="🌫️ 透明度", bg="#252535", fg=TEXT_COLOR,
                 font=("微軟正黑體", 9)).pack(side=tk.LEFT)
        self.alpha_label = tk.Label(alpha_row, text=f"{int(WINDOW_ALPHA * 100)}%",
                                    bg="#252535", fg=ACCENT_COLOR,
                                    font=("微軟正黑體", 9))
        self.alpha_label.pack(side=tk.RIGHT)

        tk.Scale(self.settings_frame, from_=20, to=100, orient=tk.HORIZONTAL,
                 variable=tk.IntVar(value=int(WINDOW_ALPHA * 100)),
                 bg="#252535", fg=TEXT_COLOR, troughcolor="#313244",
                 highlightthickness=0, showvalue=False,
                 command=self._apply_alpha).pack(fill=tk.X, pady=(0, 4))

        # 快速鍵設定列
        hotkey_row = tk.Frame(self.settings_frame, bg="#252535")
        hotkey_row.pack(fill=tk.X, pady=(6, 2))
        tk.Label(hotkey_row, text="⌨️ 快速鍵", bg="#252535", fg=TEXT_COLOR,
                 font=("微軟正黑體", 9)).pack(side=tk.LEFT)

        self._recording_hotkey = False
        self._temp_modifiers = set()

        self.hotkey_btn = tk.Button(
            hotkey_row,
            text=self._get_hotkey_display_text(),
            bg="#313244", fg=ACCENT_COLOR,
            activebackground="#313244", activeforeground=ACCENT_COLOR,
            font=("微軟正黑體", 9), relief=tk.FLAT, cursor="hand2",
            command=self._toggle_recording_hotkey
        )
        self.hotkey_btn.pack(side=tk.RIGHT)

        # ── 主內容區 ──
        self.main_frame = tk.Frame(self.root, bg=WINDOW_BG)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # 狀態列（顯示更新狀態）
        status_frame = tk.Frame(self.main_frame, bg=WINDOW_BG, padx=16, pady=4)
        status_frame.pack(fill=tk.X)
        self.status_label = tk.Label(status_frame, text="⏳ 載入中...",
                                     bg=WINDOW_BG, fg="#6c7086",
                                     font=("微軟正黑體", 9))
        self.status_label.pack(side=tk.LEFT)

        # 圓餅圖 checkbox
        check_frame = tk.Frame(self.main_frame, bg=WINDOW_BG, padx=16, pady=2)
        check_frame.pack(fill=tk.X)
        tk.Checkbutton(check_frame, text="🥧 顯示模型占比圓餅圖",
                       variable=self._show_pie,
                       bg=WINDOW_BG, fg=TEXT_COLOR, selectcolor="#313244",
                       activebackground=WINDOW_BG, activeforeground=ACCENT_COLOR,
                       font=("微軟正黑體", 9),
                       command=self._refresh_charts).pack(side=tk.LEFT)

        # 捲動內容區
        content_frame = tk.Frame(self.main_frame, bg=WINDOW_BG, padx=16)
        content_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(content_frame, bg=WINDOW_BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(content_frame, orient="vertical",
                                 command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # data_frame 是實際放資料 widget 的容器
        self.data_frame = tk.Frame(self.canvas, bg=WINDOW_BG)
        self.canvas_window = self.canvas.create_window(
            (0, 0), window=self.data_frame, anchor="nw")
        self.data_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        # 滑鼠滾輪捲動
        self.canvas.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(
            int(-1*(e.delta/120)), "units"))

        # ── 底部工具列 ──
        bottom_bar = tk.Frame(self.root, bg="#313244", height=28)
        bottom_bar.pack(fill=tk.X, side=tk.BOTTOM)
        bottom_bar.pack_propagate(False)

        # 立即刷新按鈕
        refresh_btn = tk.Label(bottom_bar, text="🔄 立即刷新",
                               bg="#313244", fg=ACCENT_COLOR,
                               font=("微軟正黑體", 9), cursor="hand2")
        refresh_btn.pack(side=tk.LEFT, padx=10, pady=4)
        refresh_btn.bind("<Button-1>", lambda e: threading.Thread(
            target=self._fetch_and_update, daemon=True).start())

        # 上次更新時間
        self.last_update_label = tk.Label(bottom_bar, text="",
                                          bg="#313244", fg="#6c7086",
                                          font=("微軟正黑體", 8))
        self.last_update_label.pack(side=tk.RIGHT, padx=10)

        # 右下角調整大小的把手
        resize_grip = tk.Label(self.root, text="⠿", bg="#313244", fg="#6c7086",
                               font=("Arial", 10), cursor="size_nw_se")
        resize_grip.place(relx=1.0, rely=1.0, anchor="se")
        resize_grip.bind("<ButtonPress-1>", self._resize_start)
        resize_grip.bind("<B1-Motion>", self._resize_motion)
        resize_grip.bind("<ButtonRelease-1>", self._resize_end)  # 調整大小結束儲存大小

    def _make_collapsible_section(self, key, icon, title, build_fn):
        """
        建立可折疊區塊
        key: 折疊狀態的字典鍵值
        icon: 標題圖示
        title: 標題文字
        build_fn: 建立內容的函式，接受 parent frame 作為參數
        """
        is_collapsed = self._collapsed.get(key, False)

        # 點擊標題列可折疊/展開
        header = tk.Frame(self.data_frame, bg="#2a2a3e", cursor="hand2")
        header.pack(fill=tk.X, pady=(6, 0))

        # 箭頭指示展開/收合狀態
        arrow = "▶" if is_collapsed else "▼"
        header_label = tk.Label(
            header,
            text=f" {arrow} {icon} {title}",
            bg="#2a2a3e", fg=ACCENT_COLOR,
            font=("微軟正黑體", 9, "bold"), anchor="w", cursor="hand2"
        )
        header_label.pack(fill=tk.X, padx=6, pady=4)
        tk.Frame(self.data_frame, bg="#45475a", height=1).pack(fill=tk.X)

        # 內容區（展開時才建立）
        content = tk.Frame(self.data_frame, bg=WINDOW_BG)
        if not is_collapsed:
            content.pack(fill=tk.X)
            build_fn(content)

        def toggle(e=None):
            """切換折疊狀態並重新渲染"""
            self._collapsed[key] = not self._collapsed[key]
            self._refresh_charts()

        header.bind("<Button-1>", toggle)
        header_label.bind("<Button-1>", toggle)

    def _make_row_in(self, parent, label_text, value_text, value_color=None):
        """在指定 parent 中建立一行資料列（左側標籤、右側數值）"""
        if value_color is None:
            value_color = GREEN_COLOR
        row = tk.Frame(parent, bg=WINDOW_BG, pady=2)
        row.pack(fill=tk.X)
        tk.Label(row, text=label_text, bg=WINDOW_BG, fg=TEXT_COLOR,
                 font=("微軟正黑體", 9), anchor="w").pack(side=tk.LEFT)
        tk.Label(row, text=value_text, bg=WINDOW_BG, fg=value_color,
                 font=("微軟正黑體", 9, "bold"), anchor="e").pack(side=tk.RIGHT)

    def _toggle_settings(self):
        """展開或收合設定面板"""
        if self._show_settings:
            self.settings_frame.pack_forget()
            self._show_settings = False
        else:
            self.settings_frame.pack(fill=tk.X, after=self.title_bar)
            self._show_settings = True

    def _apply_topmost(self):
        """套用置頂設定"""
        self.root.attributes("-topmost", self._topmost.get())

    def _apply_alpha(self, val):
        """套用透明度設定並更新顯示數值"""
        self.root.attributes("-alpha", int(val) / 100)
        self.alpha_label.config(text=f"{int(val)}%")

    def _on_frame_configure(self, event):
        """data_frame 大小改變時更新捲動範圍"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        """canvas 大小改變時讓 data_frame 寬度跟著調整"""
        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def _toggle_minimize(self, event=None):
        """切換最小化/展開狀態"""
        if self._minimized:
            # 展開：恢復原本高度
            self.root.geometry(f"{self.root.winfo_width()}x{self._normal_height}+"
                               f"{self.root.winfo_x()}+{self.root.winfo_y()}")
            self.main_frame.pack(fill=tk.BOTH, expand=True)
            self.min_btn.config(text=" ─ ")
            self._minimized = False
        else:
            # 最小化：只剩標題列
            self._normal_height = self.root.winfo_height()
            self.main_frame.pack_forget()
            self.settings_frame.pack_forget()
            self._show_settings = False
            self.root.geometry(f"{self.root.winfo_width()}x32+"
                               f"{self.root.winfo_x()}+{self.root.winfo_y()}")
            self.min_btn.config(text=" ▢ ")
            self._minimized = True

    def _resize_start(self, event):
        """記錄調整大小的起始位置與視窗尺寸"""
        self._resize_start_x = event.x_root
        self._resize_start_y = event.y_root
        self._resize_start_w = self.root.winfo_width()
        self._resize_start_h = self.root.winfo_height()

    def _resize_motion(self, event):
        """拖曳右下角調整視窗大小"""
        if self._minimized:
            return
        new_w = max(300, self._resize_start_w + (event.x_root - self._resize_start_x))
        new_h = max(150, self._resize_start_h + (event.y_root - self._resize_start_y))
        self.root.geometry(f"{new_w}x{new_h}")

    def _logout(self):
        """登出：清除儲存的帳密並回到登入頁面"""
        delete_credentials()
        self.root.destroy()
        _start_app()

    def _auto_relogin(self):
        """Token 過期時在背景自動重新登入，使用者無感"""
        try:
            r = _request_with_retry(
                "post",
                f"{OPENWEBUI_BASE_URL}/api/v1/auths/ldap",
                json={"user": self.email, "password": self.password},
                timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                # 更新 token
                self.TOKEN = data.get("token", "")
                self.PHISON_TOKEN = data.get("phison_token", "")
                # 若有儲存帳密則同步更新
                if os.path.exists(CRED_FILE):
                    save_credentials(self.email, self.password)
                # 重新抓取資料
                self._fetch_and_update()
            else:
                self.root.after(0, self._show_error, "自動重新登入失敗")
                self.root.after(2000, self._logout)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            self.root.after(0, self._show_error, f"⚠️ 網路暫時不穩，將於下次自動重試\n({e.__class__.__name__})")
        except Exception as e:
            self.root.after(0, self._show_error, str(e))

    def _fetch_and_update(self):
        """從 API 抓取用量資料並更新 UI（在背景執行緒中呼叫）"""
        try:
            headers = {
                "Authorization": f"Bearer {self.TOKEN}",
                "Content-Type": "application/json",
            }
            cookies = {"token": self.TOKEN}

            # 先打 /api/usage 初始化（伺服器端需要先呼叫此 API 才能取得用量資料）
            # 這支 API 失敗不應中斷整個流程，只記錄即可
            try:
                _request_with_retry(
                    "get",
                    f"{OPENWEBUI_BASE_URL}/api/usage",
                    headers=headers,
                    cookies=cookies,
                    timeout=10
                )
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                pass

            # 呼叫公司客製的本月用量 API（此 API 實測回應時間約 12~15 秒，故 timeout 設寬鬆一些）
            r = _request_with_retry(
                "post",
                f"{OPENWEBUI_BASE_URL}/api/v1/phison/user/usage/monthly",
                headers=headers, cookies=cookies,
                json={"key": self.PHISON_TOKEN}, timeout=30
            )

            # Token 過期（401）→ 自動重新登入
            if r.status_code == 401:
                self.root.after(0, self.status_label.config,
                                {"text": "🔄 Token 過期，自動重新登入...", "fg": YELLOW_COLOR})
                threading.Thread(target=self._auto_relogin, daemon=True).start()
                return

            usage_data = r.json() if r.status_code == 200 else []

            # 抓取帳號資訊（取得姓名等）
            r2 = _request_with_retry(
                "get",
                f"{OPENWEBUI_BASE_URL}/api/v1/auths/",
                headers=headers, timeout=8
            )
            auth_data = r2.json() if r2.status_code == 200 else {}

            # 快取資料供圖表刷新使用
            self._usage_data = usage_data
            self._auth_data = auth_data

            # 切回主執行緒更新 UI
            self.root.after(0, self._update_ui, usage_data, auth_data)

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            self.root.after(0, self._show_error,
                             f"⚠️ 網路暫時不穩，將於下次自動重試\n({e.__class__.__name__})")
        except Exception as e:
            self.root.after(0, self._show_error, str(e))

    def _refresh_charts(self):
        """使用快取資料重新渲染 UI（checkbox 切換、折疊切換時使用）"""
        self._update_ui(self._usage_data, self._auth_data)

    def _update_ui(self, usage_data, auth_data):
        """清空並重新建立所有資料顯示 widget"""

        # 清除舊的 widget
        for widget in self.data_frame.winfo_children():
            widget.destroy()

        if not usage_data:
            self._show_error("無資料")
            return

        # 帳號與月份標題
        name = auth_data.get("name", self.user_name)
        month_str = datetime.now().strftime("%Y/%m")
        tk.Label(self.data_frame,
                 text=f"👤 {name} — {month_str}",
                 bg=WINDOW_BG, fg=ACCENT_COLOR,
                 font=("微軟正黑體", 9, "bold"), anchor="w").pack(fill=tk.X, pady=(8, 4))
        tk.Frame(self.data_frame, bg="#45475a", height=1).pack(fill=tk.X)

        # 計算各項總計
        total_price = sum(item.get("price", 0) for item in usage_data)
        total_requests = sum(item.get("request", 0) for item in usage_data)
        total_prompt = sum(item.get("prompt_tokens", 0) for item in usage_data)
        total_complete = sum(item.get("complete_tokens", 0) for item in usage_data)
        twd = total_price * 32  # 換算台幣（匯率可自行調整）

        # 💰 本月總費用（可折疊）
        def build_cost(parent):
            self._make_row_in(parent, "費用", f"${total_price:.2f} USD", YELLOW_COLOR)
            self._make_row_in(parent, "（約）", f"≈ NT${twd:.0f}", YELLOW_COLOR)
            self._make_row_in(parent, "總請求數", f"{total_requests:,} 次", ACCENT_COLOR)
            self._make_row_in(parent, "輸入 tokens", f"{total_prompt:,}")
            self._make_row_in(parent, "輸出 tokens", f"{total_complete:,}")

        self._make_collapsible_section("費用", "💰", "本月總費用", build_cost)

        # 📋 各模型明細（可折疊）
        def build_detail(parent):
            for item in usage_data:
                model = item.get("model", "?")
                # API 呼叫標示為粉紅色，UI 使用標示為綠色
                api_tag = " [API]" if item.get("api") == "yes" else " [UI]"
                price = item.get("price", 0)
                req = item.get("request", 0)
                color = PINK_COLOR if item.get("api") == "yes" else GREEN_COLOR
                self._make_row_in(parent,
                                  f"  {model}{api_tag}",
                                  f"${price:.2f} ({req}次)", color)

        self._make_collapsible_section("明細", "📋", "各模型明細", build_detail)

        # 🥧 圓餅圖（checkbox 打勾才顯示）
        if self._show_pie.get():
            self._draw_pie_chart(usage_data)

        # 更新狀態列
        now = time.strftime("%H:%M:%S")
        self.status_label.config(text="✅ 已更新", fg=GREEN_COLOR)
        self.last_update_label.config(text=now)

    def _draw_pie_chart(self, usage_data):
        """繪製各模型費用占比的圓餅圖"""
        tk.Frame(self.data_frame, bg="#45475a", height=1).pack(fill=tk.X, pady=(10, 0))
        tk.Label(self.data_frame, text="🥧 模型費用占比",
                 bg=WINDOW_BG, fg=ACCENT_COLOR,
                 font=("微軟正黑體", 9, "bold"), anchor="w").pack(fill=tk.X, pady=(4, 4))

        # 整理圓餅圖資料（只取有費用的項目）
        labels, sizes = [], []
        for item in usage_data:
            price = item.get("price", 0)
            if price > 0:
                api_tag = "[API]" if item.get("api") == "yes" else "[UI]"
                labels.append(f"{item.get('model', '?')} {api_tag}")
                sizes.append(price)

        if not sizes:
            return

        # 顏色循環
        colors = ["#f38ba8", "#89b4fa", "#a6e3a1", "#f9e2af",
                  "#cba6f7", "#94e2d5", "#fab387", "#89dceb"]

        fig, ax = plt.subplots(figsize=(3.2, 2.8), facecolor=CHART_BG)
        ax.set_facecolor(CHART_BG)

        wedges, _, autotexts = ax.pie(
            sizes, labels=None,
            autopct=lambda p: f'{p:.1f}%' if p > 5 else '',  # 小於5%不顯示標籤
            colors=colors[:len(sizes)], startangle=90,
            pctdistance=0.75,
            wedgeprops=dict(linewidth=1.5, edgecolor=WINDOW_BG)
        )
        for at in autotexts:
            at.set_color("white")
            at.set_fontsize(7)

        # 圖例顯示在下方
        ax.legend(wedges, [f"{l} ${s:.2f}" for l, s in zip(labels, sizes)],
                  loc="lower center", bbox_to_anchor=(0.5, -0.28),
                  ncol=2, fontsize=6, framealpha=0, labelcolor="white")

        plt.tight_layout(pad=0.5)

        # 嵌入圖表到 tkinter
        chart_frame = tk.Frame(self.data_frame, bg=CHART_BG)
        chart_frame.pack(fill=tk.X, pady=4)
        c = FigureCanvasTkAgg(fig, master=chart_frame)
        c.draw()
        c.get_tk_widget().pack(fill=tk.X)
        plt.close(fig)  # 釋放記憶體

    def _show_error(self, msg):
        """顯示錯誤訊息"""
        for widget in self.data_frame.winfo_children():
            widget.destroy()
        tk.Label(self.data_frame, text=f"❌ 錯誤\n{msg[:80]}",
                 bg=WINDOW_BG, fg=PINK_COLOR,
                 font=("微軟正黑體", 9), wraplength=260, justify="left").pack(pady=8)
        self.status_label.config(text="❌ 錯誤", fg=PINK_COLOR)

    def _start_auto_refresh(self):
        """啟動自動刷新：立即執行一次，之後每隔 REFRESH_INTERVAL 秒重複"""
        threading.Thread(target=self._fetch_and_update, daemon=True).start()
        self.root.after(REFRESH_INTERVAL * 1000, self._start_auto_refresh)

    def _on_drag_start(self, event):
        """記錄拖曳起始位置"""
        self._drag_x = event.x
        self._drag_y = event.y

    def _on_drag_motion(self, event):
        """拖曳標題列移動視窗"""
        x = self.root.winfo_x() + (event.x - self._drag_x)
        y = self.root.winfo_y() + (event.y - self._drag_y)
        self.root.geometry(f"+{x}+{y}")

    def _on_drag_end(self, event=None):
        """拖曳結束，儲存位置"""
        self._save_window_geometry()

    def _resize_end(self, event=None):
        """調整大小結束，儲存大小"""
        self._save_window_geometry()

    def _save_window_geometry(self):
        """儲存目前視窗的 X、Y、寬、高"""
        try:
            x = self.root.winfo_x()
            y = self.root.winfo_y()
            if self._minimized:
                save_config({"x": x, "y": y})
            else:
                w = self.root.winfo_width()
                h = self.root.winfo_height()
                save_config({
                    "width": w,
                    "height": h,
                    "x": x,
                    "y": y
                })
        except Exception:
            pass

    def _on_hotkey_pressed(self):
        """全域快捷鍵觸發回呼"""
        self.root.after(0, self._toggle_window_visibility)

    def _on_focus_in(self, event):
        """焦點進入事件"""
        if event.widget == self.root:
            self._window_focused = True

    def _on_focus_out(self, event):
        """焦點離開事件"""
        if event.widget == self.root:
            self._window_focused = False

    def _toggle_window_visibility(self):
        """切換視窗顯示/隱藏與焦點狀態"""
        is_withdrawn = (self.root.state() == "withdrawn")
        
        # 檢查視窗是否目前處於作用中 (Active Foreground)
        is_active = False
        if not is_withdrawn:
            if getattr(self, "_window_focused", False):
                is_active = True
            elif IS_WINDOWS:
                try:
                    hwnd = self.root.winfo_id()
                    foreground_hwnd = ctypes.windll.user32.GetForegroundWindow()
                    root_hwnd = ctypes.windll.user32.GetAncestor(hwnd, 2)  # GA_ROOT = 2
                    if hwnd == foreground_hwnd or root_hwnd == foreground_hwnd:
                        is_active = True
                except Exception:
                    pass

        if is_withdrawn or not is_active:
            # 顯示並置頂焦點
            self.root.deiconify()
            self.root.lift()
            if self._topmost.get():
                self.root.attributes("-topmost", True)
            else:
                self.root.attributes("-topmost", True)
                self.root.attributes("-topmost", False)
            self.root.focus_force()
        else:
            # 隱藏
            self.root.withdraw()

    def _register_saved_hotkey(self):
        """註冊儲存的快捷鍵"""
        if not self.hotkey_config or not self.hotkey_manager:
            return
        modifiers = self.hotkey_config.get("modifiers", [])
        vk = self.hotkey_config.get("vk", 0)
        if vk > 0:
            mask = MOD_NOREPEAT
            if "Ctrl" in modifiers:
                mask |= MOD_CONTROL
            if "Alt" in modifiers:
                mask |= MOD_ALT
            if "Shift" in modifiers:
                mask |= MOD_SHIFT
            self.hotkey_manager.register(mask, vk)

    def _on_destroy(self, event):
        """視窗銷毀時清理快捷鍵資源"""
        if event.widget == self.root:
            if self.hotkey_manager:
                self.hotkey_manager.stop()

    def _get_hotkey_display_text(self):
        """取得目前註冊的快捷鍵顯示字串"""
        if self.hotkey_config:
            display = self.hotkey_config.get("display", "")
            if display:
                return display
        return "無"

    def _toggle_recording_hotkey(self):
        """切換錄製快速鍵狀態"""
        if self._recording_hotkey:
            self._stop_recording(save=False)
        else:
            self._start_recording()

    def _start_recording(self):
        """開始錄製快速鍵"""
        self._recording_hotkey = True
        self._temp_modifiers = set()
        self.hotkey_btn.config(text="請按按鍵... (Esc取消/BS清除)", fg=YELLOW_COLOR)
        self.root.bind("<KeyPress>", self._on_key_press)
        self.root.bind("<KeyRelease>", self._on_key_release)
        self.root.focus_set()

    def _stop_recording(self, save=True, clear=False):
        """停止錄製快速鍵"""
        self._recording_hotkey = False
        self.root.unbind("<KeyPress>")
        self.root.unbind("<KeyRelease>")
        
        if clear:
            self.hotkey_config = None
            save_config({"hotkey": None})
            if self.hotkey_manager:
                self.hotkey_manager.unregister()
        
        self.hotkey_btn.config(text=self._get_hotkey_display_text(), fg=ACCENT_COLOR)

    def _on_key_press(self, event):
        """錄製中的按鍵按下事件處理"""
        if not self._recording_hotkey:
            return "break"

        keysym = event.keysym
        keycode = event.keycode

        # 判斷是否為修飾鍵 (16=Shift, 17=Ctrl, 18=Alt)
        if keycode == 16 or keysym in ('Shift_L', 'Shift_R'):
            self._temp_modifiers.add("Shift")
            self._update_recording_display()
            return "break"
        elif keycode == 17 or keysym in ('Control_L', 'Control_R'):
            self._temp_modifiers.add("Ctrl")
            self._update_recording_display()
            return "break"
        elif keycode == 18 or keysym in ('Alt_L', 'Alt_R'):
            self._temp_modifiers.add("Alt")
            self._update_recording_display()
            return "break"

        # 沒有修飾鍵時，特殊鍵(Esc/Backspace/Delete)的特別行為
        if not self._temp_modifiers:
            if keysym == "Escape":
                self._stop_recording(save=False)
                return "break"
            elif keysym in ("BackSpace", "Delete"):
                self._stop_recording(clear=True)
                return "break"

        # 錄製完成：按下非修飾鍵
        display_key = self._get_keysym_display(keysym)
        sorted_mods = []
        for m in ["Ctrl", "Alt", "Shift"]:
            if m in self._temp_modifiers:
                sorted_mods.append(m)

        if sorted_mods:
            display_str = "+".join(sorted_mods) + "+" + display_key
        else:
            display_str = display_key

        self.hotkey_config = {
            "modifiers": sorted_mods,
            "vk": keycode,
            "display": display_str
        }
        save_config({"hotkey": self.hotkey_config})

        if self.hotkey_manager:
            self._register_saved_hotkey()

        self._stop_recording(save=True)
        return "break"

    def _on_key_release(self, event):
        """錄製中的按鍵放開事件處理"""
        if not self._recording_hotkey:
            return "break"

        keysym = event.keysym
        keycode = event.keycode

        if keycode == 16 or keysym in ('Shift_L', 'Shift_R'):
            self._temp_modifiers.discard("Shift")
            self._update_recording_display()
        elif keycode == 17 or keysym in ('Control_L', 'Control_R'):
            self._temp_modifiers.discard("Ctrl")
            self._update_recording_display()
        elif keycode == 18 or keysym in ('Alt_L', 'Alt_R'):
            self._temp_modifiers.discard("Alt")
            self._update_recording_display()

        return "break"

    def _update_recording_display(self):
        """更新錄製中按鍵的狀態顯示"""
        sorted_mods = []
        for m in ["Ctrl", "Alt", "Shift"]:
            if m in self._temp_modifiers:
                sorted_mods.append(m)
        if sorted_mods:
            text = "+".join(sorted_mods) + " + ..."
        else:
            text = "請按按鍵... (Esc取消/BS清除)"
        self.hotkey_btn.config(text=text)

    def _get_keysym_display(self, keysym):
        """取得按鍵符號的優雅顯示文字"""
        special = {
            "space": "Space",
            "Return": "Enter",
            "escape": "Esc",
            "Prior": "PageUp",
            "Next": "PageDown",
            "BackSpace": "Backspace",
            "Delete": "Delete",
        }
        if keysym in special:
            return special[keysym]
        if len(keysym) == 1:
            return keysym.upper()
        return keysym.capitalize()


# ──────────────────────────────────────────────────
# 程式進入點
# ──────────────────────────────────────────────────
def _start_app():
    """建立登入視窗，登入成功後切換到主視窗"""
    root = tk.Tk()

    def on_login_success(token, phison_token, name, email, password):
        """登入成功 callback：關閉登入視窗，開啟主視窗"""
        root.destroy()
        main_root = tk.Tk()
        UsageWidget(main_root, token, phison_token, name, email, password)
        main_root.mainloop()

    LoginWindow(root, on_login_success)
    root.mainloop()


if __name__ == "__main__":
    _start_app()