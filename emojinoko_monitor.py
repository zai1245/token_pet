import tkinter as tk
from tkinter import messagebox
import requests
import urllib.request
import threading
import time
import json
import os
import sys
import ctypes
import math
import random
import re
import subprocess
from types import SimpleNamespace
from datetime import datetime

# 匯入原本 usage_widget.py 的設定與功能，達成程式碼高度共享，且保留 usage_widget 原始碼不被改動
from usage_widget import (
    get_config_dir, load_config, save_config, save_credentials,
    load_credentials, delete_credentials, LoginWindow,
    OPENWEBUI_BASE_URL, WINDOW_BG, TEXT_COLOR, ACCENT_COLOR,
    PINK_COLOR, YELLOW_COLOR, GREEN_COLOR, TITLE_COLOR,
    IS_WINDOWS, HotkeyManager, _encode, _decode
)

# 匯入我們開發的遊戲引擎與繪圖模組
from emojinoko_game import (
    EmojinokoPet, ShopWindow, RPSWindow, AIChatWindow, AIChatConfigWindow,
    interpolate_color, create_outlined_text,
    PET_BASE_EARNING, PET_XP_THRESHOLD, PET_LEVEL_MULTIPLIER,
    PET_SATIETY_DECAY, PET_SATIETY_THRESHOLD,
    TOKEN_TO_XP_RATIO, TOKEN_TO_SATIETY, TOKEN_TO_COIN
)
from unity_renderer_bridge import UnityRendererBridge, unity_renderer_requested

def time_ms():
    return time.time() * 1000.0


def _accessory_slot(item_id):
    if item_id in {
        "scholar_cap", "cat_ears", "crown", "halo", "gentleman_hat",
        "demon_horns", "wizard_hat", "clover_sprout", "char_helmet",
    }:
        return "head"
    if item_id == "bowtie":
        return "neck"
    if item_id == "rainbow":
        return "body"
    return "face"

# 當前地瓜球 App 版本
CURRENT_VERSION = "2.9.4"


class _RuntimeTee:
    """Mirror console diagnostics to a persistent UTF-8 log file."""

    def __init__(self, console, log_file):
        self.console = console
        self.log_file = log_file
        self.lock = threading.Lock()

    def write(self, text):
        with self.lock:
            if self.console is not None:
                try:
                    self.console.write(text)
                except Exception:
                    pass
            self.log_file.write(text)
            self.log_file.flush()
        return len(text)

    def flush(self):
        with self.lock:
            if self.console is not None:
                try:
                    self.console.flush()
                except Exception:
                    pass
            self.log_file.flush()


def _install_runtime_log():
    """Persist startup and renderer diagnostics for release feedback."""
    try:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        log_dir = os.path.join(base, "TokenPet", "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "TokenPet-runtime.log")
        previous_path = os.path.join(log_dir, "TokenPet-runtime.previous.log")
        if os.path.exists(log_path) and os.path.getsize(log_path) > 4 * 1024 * 1024:
            try:
                os.replace(log_path, previous_path)
            except OSError:
                pass
        log_file = open(log_path, "a", encoding="utf-8", buffering=1)
        sys.stdout = _RuntimeTee(sys.__stdout__, log_file)
        sys.stderr = _RuntimeTee(sys.__stderr__, log_file)
        print("\n" + "=" * 72)
        print(f"[Runtime] started={datetime.now().isoformat(timespec='seconds')}")
        print(f"[Runtime] python={sys.executable}")
        print(f"[Runtime] cwd={os.getcwd()}")
        print(f"[Runtime] argv={sys.argv}")
        print(f"[Runtime] log={log_path}")
        return log_path
    except Exception:
        return None

# Windows API 用於檢測系統全局滑鼠與鍵盤活動，以判定使用者是否在「上班/使用電腦」
if IS_WINDOWS:
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    def get_idle_time_ms():
        """獲取系統自上次用戶輸入（鍵盤或滑鼠活動）以來的毫秒數"""
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
            return max(0, millis)
        return 0

    def is_screen_locked():
        """偵測 Windows 系統桌面是否被鎖定 (如 Win+L 鎖屏、登出或螢幕保護中)"""
        # 開啟當前輸入桌面，若處於鎖屏安全桌面，此 API 會回傳 0 (None)
        h_desktop = ctypes.windll.user32.OpenInputDesktop(0, False, 0x0100) # DESKTOP_SWITCHDESKTOP = 0x0100
        if h_desktop:
            ctypes.windll.user32.CloseDesktop(h_desktop)
            return False
        return True
else:
    def get_idle_time_ms():
        return 0

    def is_screen_locked():
        return False


# ──────────────────────────────────────────────────
# 單實例互斥體 (Single Instance Guard - 防範多進程互鎖)
# ──────────────────────────────────────────────────
_global_app_mutex = None

def check_single_instance(app_id="TokenPet_Instance"):
    """使用 Windows Named Mutex 確保相同目錄下的 TokenPet 只運行單一實例"""
    global _global_app_mutex
    if not IS_WINDOWS:
        return True
    try:
        import hashlib
        exe_path = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__)
        path_hash = hashlib.md5(os.path.dirname(exe_path).lower().encode('utf-8')).hexdigest()[:8]
        mutex_name = f"{app_id}_{path_hash}"
        
        kernel32 = ctypes.windll.kernel32
        _global_app_mutex = kernel32.CreateMutexW(None, False, mutex_name)
        last_error = kernel32.GetLastError()
        ERROR_ALREADY_EXISTS = 183
        if last_error == ERROR_ALREADY_EXISTS:
            return False  # 已有實例運行中
        return True
    except Exception:
        return True


# ──────────────────────────────────────────────────
# 經典地瓜球桌寵主視窗 (EmojinokoMonitor)
# ──────────────────────────────────────────────────
class EmojinokoMonitor:
    def __init__(self, root, token, phison_token, name, email, password):
        """
        root: tkinter 根視窗
        token/phison_token/name: LDAP 登入成功後傳入的 API 金鑰與用戶資訊
        email/password: 用於 Token 過期時背景無感重新登入
        """
        self.root = root
        
        # 啟動時先隱藏主視窗，防止在 Windows (0,0) 處閃爍空白方塊
        try:
            self.root.withdraw()
        except Exception:
            pass
        
        # 啟動時在背景非同步延遲清理舊版備份與臨時檔 (防止競態條件)
        self._cleanup_old_versions_async()

        self.STANDALONE = "--standalone" in sys.argv
        if self.STANDALONE:
            self.TOKEN = ""
            self.PHISON_TOKEN = ""
            self.user_name = "主人"
            self.email = ""
            self.password = ""
        else:
            self.TOKEN = token
            self.PHISON_TOKEN = phison_token
            self.user_name = name
            self.email = email
            self.password = password

        # 1. 視窗基本屬性設定 (無邊框、永遠置頂、完全透明背景)
        self.root.overrideredirect(True)        # 去除 Windows 標題列與邊框
        self.root.attributes("-topmost", True)  # 讓桌寵永遠浮動在最上層
        
        # 設定透明穿透色為 #181825 (Canvas的背景色)
        if IS_WINDOWS:
            self.root.wm_attributes("-transparentcolor", "#181825")

        # 2. 讀取地瓜球遊戲狀態與視窗坐標存檔
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        default_x = screen_w - 240
        default_y = screen_h - 340
        
        self.config = load_config()
        # Unity is opt-in. The legacy Canvas pet is created first and remains
        # available for immediate fallback if the external player fails.
        self.unity_renderer = None
        self._unity_renderer_active = False
        self._unity_renderer_visible = True
        self._unity_renderer_started_at = 0.0
        self._unity_status_visible = bool(self.config.get("unity_status_visible", True))
        self._unity_action_menu = None
        self._unity_desktop_metrics = None
        
        # 針對 LDAP 聯網版本 (非單機 Standalone 模式)，若無更新路徑則預設寫入公司內網分享路徑
        if not self.STANDALONE:
            if "update_server_url" not in self.config or self.config.get("update_server_url") == "http://localhost:8000":
                self.config["update_server_url"] = "\\\\power2\\RD Share\\EdwinLuo\\Another Token Bites the Dust"
                save_config({"update_server_url": self.config["update_server_url"]})

        try:
            x = int(self.config.get("pet_x", default_x))
            y = int(self.config.get("pet_y", default_y))
        except Exception:
            x, y = default_x, default_y

        # 防止視窗因為螢幕解析度改變而完全跑到螢幕外
        if x < -80 or x > screen_w - 50: x = default_x
        if y < -80 or y > screen_h - 50: y = default_y

        # 視窗寬高固定為 340x300 (地瓜球與舉牌後的空間)
        self.root.geometry(f"340x300+{x}+{y}")
        self._physics_win_x = x
        self._physics_win_y = y
        self.root.configure(bg="#181825")

        # 3. 初始化遊戲數據與狀態
        self.pet_data = self.config.get("pet_game", {})
        if not self.pet_data:
            # 首次運行，初始化預設值
            self.pet_data = {
                "level": 1,
                "xp": 0.0,
                "satiety": 100.0,
                "coins": 0,
                "last_prompt_baseline": 0,
                "last_complete_baseline": 0,
                "upgrades": {"auto_miner": 0}  # 預留升級商店參數
            }

        # 拖曳移動視窗的起點坐標
        self._drag_x = 0
        self._drag_y = 0
        
        # 被動產幣計時變數
        self.active_work_seconds = 0  # 累計上班秒數，達 60 秒產幣一次
        
        # 數據快取與同步旗標
        self.monthly_price_str = "陪你上班" if self.STANDALONE else "$0.00 USD"
        self.is_fetching = False
        self.is_manual_refresh = False
        self.basketball_hoop = None  # 投籃小遊戲視窗
        self.spawned_furniture_wins = {}  # 存放召喚的家具 Toplevel 視窗對象
        self.current_furniture_snapped = None
        self._furniture_cooldown = 0

        # 4. 初始化全域快捷鍵管理器 (F7 隱藏/顯示桌寵)
        self.hotkey_manager = None
        if IS_WINDOWS:
            self.hotkey_manager = HotkeyManager(on_hotkey_pressed=self._on_hotkey_pressed)
            self.hotkey_manager.start()

        if "hotkey" in self.config:
            self.hotkey_config = self.config["hotkey"]
        else:
            self.hotkey_config = {"modifiers": [], "vk": 118, "display": "F7"} # 預設 F7
        self._register_saved_hotkey()

        # 5. 建立 GUI 介面與繪圖引擎
        self._build_ui()

        # A failed or missing PoC renderer is intentionally non-fatal.
        self._start_unity_renderer_if_requested()

        # 6. 啟動背景迴圈線程 (繪圖動畫、產幣時鐘、用量更新、自動更新)
        self._start_game_loops()
        
        # 7. 還原已召喚的家具視窗
        self.root.after(500, self.restore_spawned_furniture)
        
        # 偵測視窗銷毀，釋放快捷鍵資源
        self.root.bind("<Destroy>", self._on_destroy)

    def _cleanup_old_versions_async(self):
        """背景延遲清理先前更新留下來的舊版備份與臨時檔"""
        def _cleaner():
            time.sleep(3.0)  # 等待舊進程完全釋放資源與關閉控制代碼
            try:
                if getattr(sys, 'frozen', False):
                    exe_dir = os.path.dirname(sys.executable)
                    for fname in os.listdir(exe_dir):
                        if (fname.startswith("TokenPet_old") and fname.endswith(".exe")) or \
                           (fname.startswith("TokenPet_dl_") and fname.endswith(".tmp")) or \
                           fname == "TokenPet_new.exe":
                            fpath = os.path.join(exe_dir, fname)
                            try:
                                os.remove(fpath)
                            except Exception:
                                pass
            except Exception:
                pass
        threading.Thread(target=_cleaner, daemon=True).start()

    def _build_ui(self):
        """建立主要 Canvas 畫布"""
        # Canvas 背景色為 #181825 (對應透明穿透色)
        self.canvas = tk.Canvas(self.root, width=340, height=300, bg="#181825", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # 初始化地瓜球繪圖實體，定位在畫布中心 (170, 205)
        # 保留上方空間繪製舉起來的看板
        self.pet = EmojinokoPet(self.canvas, 170, 205)
        self.pet.monitor = self
        self.shadow_win = ShadowWindow(self)
        self.hud_win = HudWindow(self)
        self.pet.equipped_accessory = self.pet_data.get("equipped_accessory")
        equipment = self.pet_data.get("equipped_accessories")
        if not isinstance(equipment, dict):
            equipment = {}
            legacy = self.pet.equipped_accessory
            if legacy:
                if legacy in {
                    "scholar_cap", "cat_ears", "crown", "halo",
                    "gentleman_hat", "demon_horns", "wizard_hat",
                    "clover_sprout", "char_helmet",
                }:
                    slot = "head"
                elif legacy == "bowtie":
                    slot = "neck"
                elif legacy == "rainbow":
                    slot = "body"
                else:
                    slot = "face"
                equipment[slot] = legacy
            self.pet_data["equipped_accessories"] = equipment
        if not isinstance(self.pet_data.get("equipped_accessories"), dict):
            self.pet_data["equipped_accessories"] = {}
            if self.pet.equipped_accessory:
                self.pet_data["equipped_accessories"][
                    _accessory_slot(self.pet.equipped_accessory)
                ] = self.pet.equipped_accessory
        
        # 初始化便利貼視窗集合，並加載已儲存的便利貼
        self.spawned_memo_wins = {}
        self.root.after(100, self.load_saved_memos)

        # 綁定滑鼠事件
        # 點擊地瓜球 -> 觸發拖曳與物理受擊效果
        self.canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self.canvas.bind("<B1-Motion>", self._on_drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_drag_end)
        
        # 雙擊地瓜球 -> 召喚 AI 尬聊對話框
        self.canvas.bind("<Double-Button-1>", lambda e: self.open_ai_chat())
        
        # 右鍵點擊地瓜球 -> 彈出選單
        self.canvas.bind("<Button-3>", self._show_context_menu)

        # 建立右鍵選單
        self.context_menu = tk.Menu(self.root, tearoff=0, bg="#252535", fg=TEXT_COLOR,
                                    activebackground=ACCENT_COLOR, activeforeground="#1e1e2e", relief=tk.FLAT)
        # 建立恢復便利貼子選單
        self.undo_menu = tk.Menu(self.context_menu, tearoff=0, bg="#252535", fg=TEXT_COLOR,
                                 activebackground=ACCENT_COLOR, activeforeground="#1e1e2e", relief=tk.FLAT)

        if self.STANDALONE:
            self.context_menu.add_command(label="💬 找地瓜球尬聊 (AI Chat)", command=self.open_ai_chat)
            self.context_menu.add_command(label="🟢 投餵地瓜球 (Feed)", command=self.simulate_usage)
            self.context_menu.add_command(label="📋 顯示/隱藏資訊看板", command=self._toggle_board)
            self.context_menu.add_command(label="☕ 請喝咖啡 (30 🪙)", command=self.buy_coffee)
            self.context_menu.add_command(label="🎮 玩猜拳 (5 🪙)", command=self.play_rps)
            self.context_menu.add_command(label="🏀 投籃小遊戲 (Basketball)", command=self.toggle_basketball_game)
            self.context_menu.add_command(label="🍎 接水果小遊戲 (Catch Fruits)", command=self.toggle_fruit_catcher)
            self.context_menu.add_command(label="🎰 幸運拉霸機 (Lucky Slots)", command=self.toggle_slot_machine)
            self.context_menu.add_command(label="🛒 道具與家具商店 (Shop)", command=self.open_shop)
            self.context_menu.add_command(label="📝 新增便利貼 (Memo)", command=self.add_new_memo)
            self.context_menu.add_cascade(label="🗑️ 回復便利貼 (Restore Memo)", menu=self.undo_menu)
            self.context_menu.add_command(label="⌨️ 快速鍵設定", command=self.open_hotkey_settings)
            self.context_menu.add_command(label="🔄 檢查更新 (Check Update)", command=self.trigger_manual_update_check)
            self.context_menu.add_separator()
            self.context_menu.add_command(label="✕ 退出寵物 (Exit)", command=self.root.destroy)
        else:
            self.context_menu.add_command(label="💬 找地瓜球尬聊 (AI Chat)", command=self.open_ai_chat)
            self.context_menu.add_command(label="🔄 立即對帳 (Refresh)", command=self.manual_refresh)
            self.context_menu.add_command(label="💰 查看目前費用 (Usage Cost)", command=self.show_current_cost)
            self.context_menu.add_command(label="📊 詳細 Token 統計 (Stats)", command=self.open_detailed_stats)
            self.context_menu.add_command(label="📋 顯示/隱藏資訊看板", command=self._toggle_board)
            self.context_menu.add_command(label="☕ 請喝咖啡 (30 🪙)", command=self.buy_coffee)
            self.context_menu.add_command(label="🎮 玩猜拳 (5 🪙)", command=self.play_rps)
            self.context_menu.add_command(label="🏀 投籃小遊戲 (Basketball)", command=self.toggle_basketball_game)
            self.context_menu.add_command(label="🍎 接水果小遊戲 (Catch Fruits)", command=self.toggle_fruit_catcher)
            self.context_menu.add_command(label="🎰 幸運拉霸機 (Lucky Slots)", command=self.toggle_slot_machine)
            self.context_menu.add_command(label="🛒 道具與家具商店 (Shop)", command=self.open_shop)
            self.context_menu.add_command(label="📝 新增便利貼 (Memo)", command=self.add_new_memo)
            self.context_menu.add_cascade(label="🗑️ 回復便利貼 (Restore Memo)", menu=self.undo_menu)
            self.context_menu.add_command(label="⌨️ 快速鍵設定", command=self.open_hotkey_settings)
            self.context_menu.add_command(label="🟢 模擬用量增加 (Simulate)", command=self.simulate_usage)
            self.context_menu.add_command(label="🔄 檢查更新 (Check Update)", command=self.trigger_manual_update_check)
            self.context_menu.add_separator()
            self.context_menu.add_command(label="⏏️ 登出帳號 (Logout)", command=self._logout)
            self.context_menu.add_command(label="✕ 退出寵物 (Exit)", command=self.root.destroy)

        # 立即定位影子與 HUD 看板，並立即繪製第一幀，防止左上角 (0,0) 出現空白正方形
        self.update_shadow_position(self._physics_win_x, self._physics_win_y)
        if getattr(self, "hud_win", None):
            self.hud_win.draw_hud(
                self.pet_data.get("coins", 0),
                self.pet_data.get("level", 1),
                self.pet_data.get("xp", 0.0),
                self.pet_data.get("satiety", 100.0),
                self.monthly_price_str,
                self.pet.state
            )
        # 全部視窗坐標與樣式準備就緒後，一次性安全顯示並置頂
        self.root.deiconify()
        self.root.lift()

    def _start_game_loops(self):
        """啟動所有遊戲相關時鐘迴圈"""
        self.tick_physics()       # ~60 FPS 物理運算與繪圖
        self.tick_economy()       # 10 秒計時器：產幣、飢餓衰減
        self.auto_refresh_data()  # 60 秒計時器：抓取 API 差額投餵
        
        # 啟動內網自動更新檢查 (在背景執行緒中執行，避免卡住啟動畫面)
        threading.Thread(target=self.check_auto_update, daemon=True).start()

    def update_geometry(self, x, y):
        self._physics_win_x = x
        self._physics_win_y = y
        self.root.geometry(f"+{int(x)}+{int(y)}")
        # 同步更新獨立的物理貼地影子與獨立 HUD 看板位置
        self.update_shadow_position(x, y)
        bridge = getattr(self, "unity_renderer", None)
        if getattr(self, "_unity_renderer_active", False) and bridge is not None:
            bridge.move_window(x, y)

    def _start_unity_renderer_if_requested(self):
        if not unity_renderer_requested(self.config):
            return

        bridge = UnityRendererBridge(
            self.config.get("unity_renderer_path"),
            (self._physics_win_x, self._physics_win_y),
        )
        self.unity_renderer = bridge
        self._unity_renderer_started_at = time.monotonic()
        if not bridge.start():
            print(f"[Unity Renderer] Fallback to legacy: {bridge.executable}")
            self.unity_renderer = None
            return

        print(f"[Unity Renderer] Starting PoC: {bridge.executable}")
        self.root.after(50, self._poll_unity_renderer)

    def _poll_unity_renderer(self):
        bridge = getattr(self, "unity_renderer", None)
        if bridge is None or not self.root.winfo_exists():
            return

        for payload in bridge.poll_events():
            event_name = payload.get("event_name", "")
            if event_name in ("ready", "desktop_metrics", "drag_released"):
                self._apply_unity_desktop_metrics(payload)
            if event_name == "ready":
                self._activate_unity_renderer()
            elif event_name == "desktop_metrics":
                pass
            elif event_name == "poke":
                self._handle_unity_poke()
            elif event_name == "double_click":
                self.open_ai_chat()
            elif event_name == "context_menu":
                self._show_context_menu(
                    SimpleNamespace(
                        x_root=int(payload.get("x", self.root.winfo_pointerx())),
                        y_root=int(payload.get("y", self.root.winfo_pointery())),
                    )
                )
            elif event_name == "drag_started":
                self._detach_unity_drag()
            elif event_name == "shake":
                self.pet.state = "roll"
                self.pet.roll_speed = max(-0.3, min(0.3,
                    float(payload.get("velocity_x", 0.0)) * 0.0004))
                self.pet.eye_state = "dizzy"
                self.pet.mouth_state = "open"
                self.create_text_popup("😵 暈眩中...", 170, 130, color=ACCENT_COLOR)
            elif event_name == "shop_action":
                self._handle_unity_shop_action(payload.get("item", ""))
            elif event_name == "furniture_moved":
                item_id = payload.get("item", "")
                furniture = self.spawned_furniture_wins.get(item_id)
                if isinstance(furniture, UnityFurnitureProxy):
                    furniture.set_position(
                        int(payload.get("x", furniture.winfo_x())),
                        int(payload.get("y", furniture.winfo_y())),
                    )
                    positions = self.pet_data.setdefault("furniture_positions", {})
                    positions[item_id] = {
                        "x": furniture.winfo_x(),
                        "y": furniture.winfo_y(),
                    }
                    self.save_pet_savegame()
            elif event_name == "furniture_despawn":
                self.despawn_furniture(payload.get("item", ""))
            elif event_name == "drag_released":
                x = int(payload.get("x", self._physics_win_x))
                y = int(payload.get("y", self._physics_win_y))
                self.update_geometry(x, y)
                save_config({"pet_x": x, "pet_y": y})
                self._begin_unity_release_fall(payload)
            elif event_name == "action_finished" and payload.get("action") == "land":
                if self.pet.state in ("fall", "roll", "backflip"):
                    self.pet.state = "idle"
            elif event_name in ("process_exit", "connection_lost", "renderer_closed"):
                self._fallback_to_legacy_renderer(event_name, payload.get("message", ""))
                return

        if not self._unity_renderer_active:
            # First launch on another PC may be delayed by antivirus scanning
            # the Unity runtime. Give a cold start enough time before falling
            # back to Canvas; the legacy pet stays visible while waiting.
            timed_out = time.monotonic() - self._unity_renderer_started_at > 45.0
            if timed_out or not bridge.running:
                self._fallback_to_legacy_renderer("startup_timeout")
                return

        self.root.after(50, self._poll_unity_renderer)

    def _apply_unity_desktop_metrics(self, payload):
        """Store DPI-aware work-area geometry reported by the Unity process."""
        width = int(payload.get("width", 0) or 0)
        height = int(payload.get("height", 0) or 0)
        floor_y = int(payload.get("floor_y", 0) or 0)
        existing = self._unity_desktop_metrics or {}

        # drag_released repeats floor_y as a last-moment guard but does not
        # repeat the full rectangle. Preserve the latest complete work area.
        if width > 0 and height > 0:
            existing.update({
                "work_x": int(payload.get("x", 0) or 0),
                "work_y": int(payload.get("y", 0) or 0),
                "work_w": width,
                "work_h": height,
            })
        if floor_y:
            existing["floor_y"] = floor_y

        stage_width = int(payload.get("stage_width", 0) or 0)
        stage_height = int(payload.get("stage_height", 0) or 0)
        if stage_width > 0 and stage_height > 0:
            existing.update({
                "mon_x": int(payload.get("stage_x", 0) or 0),
                "mon_y": int(payload.get("stage_y", 0) or 0),
                "mon_w": stage_width,
                "mon_h": stage_height,
            })

        if existing:
            self._unity_desktop_metrics = existing

    def _detach_unity_drag(self):
        """Match the Canvas rule that grabbing the pet cancels furniture poses."""
        if getattr(self, "current_furniture_snapped", None) is None:
            return
        self.current_furniture_snapped = None
        self.target_furniture_id = None
        self._furniture_cooldown = 120
        self.pet.state = "idle"
        self.pet.eye_state = "normal"
        self.pet.mouth_state = "normal"

    def _handle_unity_poke(self):
        """Apply the original Canvas click reaction and five-click fever combo."""
        self.pet.vel_scale_y = -0.22
        self.pet.vel_scale_x = 0.15
        self.pet.eye_state = "happy"
        self.pet.mouth_state = "normal"
        self.root.after(800, self.pet.restore_eye)

        if self.pet_data.get("equipped_accessory") == "char_mask" and random.random() < 0.40:
            quote = random.choice([
                "三倍速的帥氣！☄️",
                "因為他是個少爺啊... ☕",
                "讓我見識一下吧！✨",
                "這就是認可的意義！🔥",
            ])
            self.create_text_popup(quote, 170, 110, color="#f38ba8")

        now = time.time()
        if now - getattr(self, "_last_click_time", 0.0) < 0.6:
            self._click_count = getattr(self, "_click_count", 0) + 1
        else:
            self._click_count = 1
        self._last_click_time = now
        if self._click_count >= 5 and self.pet.state not in ("sleep", "drink", "roll"):
            self._click_count = 0
            self._trigger_fever_mode()

    def _begin_unity_release_fall(self, payload):
        """Feed a Unity drag release into the original desktop fall engine."""
        vx = float(payload.get("velocity_x", 0.0))
        # Unity reports screen-up as positive; Tk/desktop Y grows downwards.
        vy = -float(payload.get("velocity_y", 0.0))
        speed = math.hypot(vx, vy)
        current_y = float(self._physics_win_y)
        self._fall_peak_y = current_y
        m_info = self.get_current_monitor_info()
        landing_y = m_info["work_y"] + m_info["work_h"] - 300

        if speed <= 120.0 and current_y >= landing_y - 2:
            self.update_geometry(self._physics_win_x, landing_y)
            self.pet.state = "idle"
            return

        # Pointer deltas can spike when Windows hands focus back to the layered
        # window. Cap the inherited impulse so an upward flick never leaves the
        # pet hovering for several seconds before gravity wins.
        self._fall_vx = max(-12.0, min(12.0, vx * 0.016))
        self._fall_vy = max(-9.0, min(10.0, vy * 0.016))
        self._fall_gravity = 1.05
        self._unity_fall_started_at = time.monotonic()
        self._unity_floor_bounced = False
        self.pet.roll_angle = 0.0
        if speed > 550.0 and vy < -550.0:
            self.pet.state = "backflip"
            self.pet.backflip_timer = 40
            self.pet.eye_state = "star"
            self.pet.mouth_state = "open"
            self.create_text_popup("⭐後空翻!!⭐", 170, 120, color=YELLOW_COLOR)
        else:
            self.pet.state = "fall"
            self.pet.roll_speed = max(-0.3, min(0.3, vx * 0.0004))
            self.pet.eye_state = "dizzy"
            self.pet.mouth_state = "open"
            self.pet.vel_scale_x = 0.18
            self.pet.vel_scale_y = -0.18
            message = "滾滾滾～" if speed > 550.0 else "哇哇哇～"
            color = ACCENT_COLOR if speed > 550.0 else PINK_COLOR
            self.create_text_popup(message, 170, 120, color=color)

    def _activate_unity_renderer(self):
        if self._unity_renderer_active:
            return
        self._unity_renderer_active = True
        self._unity_renderer_visible = True
        try:
            self.root.withdraw()
            if getattr(self, "shadow_win", None):
                self.shadow_win.withdraw()
            # Unity renders the compact status tag in the same 340x300 surface.
            # Keeping the old detached Tk HUD visible made the two renderers
            # look like unrelated pieces stuck together.
            if getattr(self, "hud_win", None):
                self.hud_win.withdraw()
        except Exception:
            pass
        self._sync_unity_renderer(force=True)
        self._sync_unity_furniture()
        # Old Canvas saves use Tk logical pixels. On a 150% DPI desktop their
        # remembered "floor" is around mid-screen in Unity physical pixels.
        # As soon as DPI-aware metrics arrive, let an unattached idle pet settle
        # naturally onto the real work-area floor.
        if getattr(self, "current_furniture_snapped", None) is None and self.pet.state != "balloon":
            m_info = self.get_current_monitor_info()
            landing_y = m_info["work_y"] + m_info["work_h"] - 300
            if abs(float(self._physics_win_y) - landing_y) > 2.0:
                self._fall_vx = 0.0
                self._fall_vy = 1.0
                self._fall_gravity = 1.05
                self._fall_peak_y = float(self._physics_win_y)
                self._unity_fall_started_at = time.monotonic()
                self._unity_floor_bounced = True
                self.pet.state = "fall"
        print("[Unity Renderer] Ready; legacy pet hidden and standing by as fallback.")
        if "--debug-open-shop" in sys.argv:
            self.root.after(250, self.open_shop)

    def _fallback_to_legacy_renderer(self, reason, detail=""):
        bridge = getattr(self, "unity_renderer", None)
        self.unity_renderer = None
        self._unity_renderer_active = False
        self._unity_renderer_visible = True
        if bridge is not None:
            bridge.stop()
        try:
            self.root.deiconify()
            self.root.lift()
            if getattr(self, "shadow_win", None):
                self.shadow_win.deiconify()
            if getattr(self, "hud_win", None):
                self.hud_win.deiconify()
        except Exception:
            pass
        # If Unity could not stay alive, restore real Tk furniture windows at
        # the exact saved locations. The legacy implementation remains a full
        # fallback rather than being deleted during the renderer migration.
        for item_id, furniture in list(getattr(self, "spawned_furniture_wins", {}).items()):
            if isinstance(furniture, UnityFurnitureProxy):
                self.spawned_furniture_wins[item_id] = FurnitureWindow(self, item_id)
        suffix = f": {detail}" if detail else ""
        print(f"[Unity Renderer] Fallback to legacy ({reason}){suffix}")

    def _sync_unity_renderer(self, force=False):
        bridge = getattr(self, "unity_renderer", None)
        if not self._unity_renderer_active or bridge is None or not bridge.connected:
            return
        if force:
            bridge.send(
                {
                    "command": "set_status_visible",
                    "visible": self._unity_status_visible,
                }
            )
        level = self.pet_data.get("level", 1)
        bridge.send_snapshot(
            state=self.pet.state,
            emotion=self.pet.eye_state,
            mouth=self.pet.mouth_state,
            accessory=self.pet.equipped_accessory,
            equipment=self.pet_data.get("equipped_accessories", {}),
            look_x=self.pet.look_offset_x,
            look_y=self.pet.look_offset_y,
            level=level,
            xp=self.pet_data.get("xp", 0.0),
            xp_max=PET_XP_THRESHOLD + (level - 1) * 50.0,
            satiety=self.pet_data.get("satiety", 100.0),
            coins=self.pet_data.get("coins", 0),
            eat_type=getattr(self.pet, "eat_type", ""),
            furniture=(getattr(self, "current_furniture_snapped", "") or
                       (getattr(self, "target_furniture_id", "")
                        if self.pet.state == "approach_furniture" else "")),
            effects=",".join(
                name for name, active in (
                    ("coffee", getattr(self.pet, "coffee_timer", 0) > 0),
                    ("candy", getattr(self.pet, "candy_timer", 0) > 0),
                    ("bubble_tea", getattr(self.pet, "bubble_tea_timer", 0) > 0),
                    ("spicy", getattr(self.pet, "spicy_timer", 0) > 0),
                    ("ice", getattr(self.pet, "ice_timer", 0) > 0),
                    ("fever", getattr(self.pet, "fever_timer", 0) > 0),
                    ("wave", getattr(self.pet, "wave_timer", 0) > 0),
                    ("doze", getattr(self.pet, "doze_timer", 0) > 0),
                    ("bubble", getattr(self.pet, "bubble_timer", 0) > 0),
                    ("stretch", getattr(self.pet, "stretch_timer", 0) > 0),
                    ("singing", getattr(self.pet, "singing_timer", 0) > 0),
                    ("matcha", getattr(self.pet, "matcha_timer", 0) > 0),
                ) if active
            ),
            show_board=bool(getattr(self.pet, "show_board", False)),
            board_text=getattr(self.pet, "custom_board_text", "") or "",
            overtime=bool(getattr(self.pet, "is_overtime", False)),
        )

    # ──────────────────────────────────────────────────
    # 物理與產幣計時迴圈 (Game Loops)
    # ──────────────────────────────────────────────────
    def tick_physics(self):
        """約 60 FPS (16ms) 的物理震盪與 Canvas 重繪迴圈"""
        if not self.root.winfo_exists():
            return
            
        # 0. 系統級置頂守護 (Topmost Guard)：每 60 幀 (約 1 秒) 強制重新置頂所有附屬視窗，防禦 Windows 層級搶焦
        self._topmost_guard_counter = getattr(self, "_topmost_guard_counter", 0) + 1
        if self._topmost_guard_counter >= 60:
            self._topmost_guard_counter = 0
            if self.root.state() != "withdrawn":
                try:
                    self.root.attributes("-topmost", True)
                    self.root.lift()
                    if getattr(self, "shadow_win", None) and self.shadow_win.winfo_exists():
                        self.shadow_win.attributes("-topmost", True)
                        self.shadow_win.lift()
                    if (not self._unity_renderer_active and
                            getattr(self, "hud_win", None) and self.hud_win.winfo_exists()):
                        self.hud_win.attributes("-topmost", True)
                        self.hud_win.lift()
                    for win in getattr(self, "spawned_memo_wins", {}).values():
                        if win.winfo_exists():
                            win.attributes("-topmost", True)
                            win.lift()
                    for win in getattr(self, "spawned_furniture_wins", {}).values():
                        if win.winfo_exists():
                            win.attributes("-topmost", True)
                            win.lift()
                except Exception:
                    pass
        
        # 1. 處理家具/便利貼 snapped 座標連動
        if getattr(self, "current_furniture_snapped", None) is not None:
            furniture_id = self.current_furniture_snapped
            self._furniture_snap_timer = getattr(self, "_furniture_snap_timer", 0) + 1
            
            # 各家具作息時鐘時長
            dur_map = {
                "futon": 1800,      # 30 秒
                "laptop": 1500,     # 25 秒
                "lazy_sofa": 1200,  # 20 秒
                "kotatsu": 1500,    # 25 秒
                "pixel_tv": 1200,   # 20 秒
                "night_lamp": 1000, # 16 秒
                "succulent_pot": 900 # 15 秒
            }
            max_snap_duration = dur_map.get(furniture_id, 1200)
            
            if self._furniture_snap_timer >= max_snap_duration:
                self._furniture_snap_timer = 0
                self.current_furniture_snapped = None
                self._furniture_cooldown = 240  # 4 秒冷卻
                self.pet.state = "idle"
                self.pet.eye_state = "happy"
                self.pet.mouth_state = "normal"
                self.pet.vel_scale_y = -0.22  # 伸懶腰小彈跳
                self.pet.vel_scale_x = 0.15
                
                wake_map = {
                    "futon": "睡飽飽！✨",
                    "laptop": "寫完收工！🎉",
                    "lazy_sofa": "休息夠了~ 🛋️",
                    "kotatsu": "暖呼呼吃飽了 🍊",
                    "pixel_tv": "這集真精彩！📺",
                    "night_lamp": "神清氣爽 ✨",
                    "succulent_pot": "快快長大 🪴"
                }
                wake_msg = wake_map.get(furniture_id, "唱完啦～♪")
                self.create_text_popup(wake_msg, 170, 120, color="#f9e2af")
                self.root.after(800, self.pet.restore_eye)
            elif furniture_id.startswith("memo_"):
                if furniture_id in getattr(self, "spawned_memo_wins", {}):
                    m_win = self.spawned_memo_wins[furniture_id]
                    try:
                        mx = m_win.winfo_x()
                        my = m_win.winfo_y()
                        new_x = mx - 80
                        new_y = my - 240
                        if self.root.winfo_x() != new_x or self.root.winfo_y() != new_y:
                            self.update_geometry(new_x, new_y)
                        
                        # 站在便利貼上唱歌時，定時隨機散發飄浮音符/亮片
                        if random.random() < 0.015:
                            self.create_text_popup(random.choice(["♪", "♫", "★", "✨", "🎵"]), 170, 130, color="#f9e2af")
                    except Exception:
                        pass
                else:
                    self.current_furniture_snapped = None
                    if self.pet.state == "memo_perch":
                        self.pet.state = "idle"
            elif furniture_id in self.spawned_furniture_wins:
                f_win = self.spawned_furniture_wins[furniture_id]
                try:
                    fx = f_win.winfo_x()
                    fy = f_win.winfo_y()
                    if furniture_id == "futon":
                        new_x = fx - 80
                        new_y = fy - 155
                    elif furniture_id == "laptop":
                        new_x = fx - 170
                        new_y = fy - 145
                    elif furniture_id == "lazy_sofa":
                        new_x = fx - 90
                        new_y = fy - 145
                        if random.random() < 0.015:
                            self.create_text_popup(random.choice(["❤", "🌸", "✨"]), 170, 130, color="#f5c2e7")
                        if self._furniture_snap_timer % 300 == 0:
                            self.pet_data["satiety"] = min(100.0, self.pet_data.get("satiety", 100.0) + 2.0)
                    elif furniture_id == "kotatsu":
                        new_x = fx - 85
                        new_y = fy - 145
                        if random.random() < 0.015:
                            self.create_text_popup(random.choice(["*嚼嚼*", "🍊", "🍵"]), 170, 130, color="#fab387")
                        if self._furniture_snap_timer % 480 == 0:
                            self.pet_data["coins"] = self.pet_data.get("coins", 0) + 1
                            self.create_text_popup("+1 🪙", 170, 100, color="#f9e2af")
                    elif furniture_id == "pixel_tv":
                        new_x = fx - 180
                        new_y = fy - 145
                        if random.random() < 0.015:
                            self.create_text_popup(random.choice(["🍿", "📺 BEEP!", "👾"]), 170, 130, color="#f9e2af")
                    elif furniture_id == "night_lamp":
                        new_x = fx - 165
                        new_y = fy - 145
                        if random.random() < 0.015:
                            self.create_text_popup(random.choice(["🎵", "✨", "🏮"]), 170, 130, color="#f9e2af")
                    elif furniture_id == "succulent_pot":
                        new_x = fx - 160
                        new_y = fy - 145
                        if random.random() < 0.02:
                            self.create_text_popup(random.choice(["💧", "🪴", "🌸"]), 170, 130, color="#a6e3a1")
                        if self._furniture_snap_timer % 300 == 0:
                            self.gain_pet_xp(2)
                    else:
                        new_x = fx - 80
                        new_y = fy - 155
                        
                    if self.root.winfo_x() != new_x or self.root.winfo_y() != new_y:
                        self.update_geometry(new_x, new_y)
                    self.root.lift()
                except Exception:
                    self.current_furniture_snapped = None
            else:
                self.current_furniture_snapped = None
                if self.pet.state in ("sleep_futon", "work_laptop", "relax_sofa", "warm_kotatsu", "watch_tv", "meditate_lamp", "water_plant", "memo_perch"):
                    self.pet.state = "idle"

        # 處理氣球向上飄浮物理與視窗左右隨風微幅晃動
        if self.pet.state == "balloon":
            current_x = self.root.winfo_x()
            current_y = self.root.winfo_y()
            target_y = 120
            if current_y > target_y:
                new_y = current_y - 1.5
            else:
                new_y = target_y + 4.0 * math.sin(time.time() * 2.0)
            new_x = current_x + 0.8 * math.sin(time.time() * 1.5)
            self.update_geometry(new_x, new_y)

        # 處理吃便利貼 (memo_eat) 物理走向與大口吃掉銷毀動畫
        if self.pet.state == "memo_eat":
            target_id = getattr(self, "_eat_target_memo_id", None)
            if not target_id or target_id not in getattr(self, "spawned_memo_wins", {}):
                self.pet.state = "idle"
                self.pet.eye_state = "normal"
                self.pet.mouth_state = "normal"
            else:
                m_win = self.spawned_memo_wins[target_id]
                try:
                    mx = m_win.winfo_x()
                    my = m_win.winfo_y()
                    current_x = self.root.winfo_x()
                    current_y = self.root.winfo_y()
                    
                    # 計算目標螢幕坐標 (讓地瓜球完美將嘴巴/重心對準便利貼中心)
                    target_x = mx - 80
                    target_y = my - 240
                    
                    dx = target_x - current_x
                    dy = target_y - current_y
                    
                    # 跑步奔向便利貼，每幀步長 6 像素
                    step_x = 6.0 if dx > 0 else -6.0
                    if abs(dx) < 6.0: step_x = dx
                    step_y = 6.0 if dy > 0 else -6.0
                    if abs(dy) < 6.0: step_y = dy
                    
                    new_x = current_x + step_x
                    new_y = current_y + step_y
                    self.update_geometry(new_x, new_y)
                    
                    # 跑步跑步擺動動畫
                    self.pet.roll_angle = 0.08 * math.sin(time.time() * 20.0)
                    
                    # 抵達判定 (距離小於 8 像素時大口吃掉)
                    if abs(dx) < 8.0 and abs(dy) < 8.0:
                        # 獲取便利貼文字內容供垃圾桶回復使用
                        memos = self.pet_data.setdefault("memos", [])
                        text_content = ""
                        for m in memos:
                            if m["id"] == target_id:
                                text_content = m.get("text", "")
                                break
                                
                        # 轉移存入垃圾桶
                        deleted_list = self.pet_data.setdefault("deleted_memos", [])
                        deleted_list.insert(0, {
                            "id": target_id,
                            "x": mx,
                            "y": my,
                            "text": text_content,
                            "deleted_at": time.time()
                        })
                        self.pet_data["deleted_memos"] = deleted_list[:15]
                        
                        m_win.destroy()
                        self.spawned_memo_wins.pop(target_id)
                        
                        # 從活動列表中移除
                        self.pet_data["memos"] = [m for m in memos if m["id"] != target_id]
                        self.pet_data["coins"] = self.pet_data.get("coins", 0) + 5
                        self.pet_data["xp"] = self.pet_data.get("xp", 0) + 5.0
                        
                        self.create_text_popup("Amu! 😋 +5 🪙", 170, 100, color="#a6e3a1")
                        self.pet.eye_state = "happy"
                        self.pet.mouth_state = "open"
                        self.root.after(800, self.pet.restore_eye)
                        
                        # 噴灑大口吃掉的彩色碎紙紙屑粒子
                        for _ in range(12):
                            angle = random.uniform(0, 2 * math.pi)
                            dist = random.uniform(10, 35)
                            self.pet.coffee_sparks.append({
                                "dx": dist * math.cos(angle),
                                "dy": dist * math.sin(angle),
                                "vy": random.uniform(-2.0, -0.5),
                                "color": random.choice(["#f9e2af", "#f38ba8", "#a6e3a1", "#89b4fa"]),
                                "life": random.randint(15, 30)
                            })
                            
                        self.check_level_up()
                        self.save_pet_savegame()
                        self.pet.state = "idle"
                except Exception:
                    self.pet.state = "idle"

        # 處理主動走向家具 (approach_furniture) 物理走向與抵達互動
        if self.pet.state == "approach_furniture":
            target_f_id = getattr(self, "target_furniture_id", None)
            if target_f_id and target_f_id in getattr(self, "spawned_furniture_wins", {}):
                f_win = self.spawned_furniture_wins[target_f_id]
                try:
                    fx = f_win.winfo_x()
                    fy = f_win.winfo_y()
                    
                    if target_f_id == "futon":
                        target_wx = fx - 80
                        target_wy = fy - 155
                    elif target_f_id == "laptop":
                        target_wx = fx - 170
                        target_wy = fy - 145
                    elif target_f_id == "pixel_tv":
                        target_wx = fx - 180
                        target_wy = fy - 145
                    elif target_f_id == "night_lamp":
                        target_wx = fx - 165
                        target_wy = fy - 145
                    elif target_f_id == "succulent_pot":
                        target_wx = fx - 160
                        target_wy = fy - 145
                    elif target_f_id == "lazy_sofa":
                        target_wx = fx - 90
                        target_wy = fy - 150
                    elif target_f_id == "kotatsu":
                        target_wx = fx - 85
                        target_wy = fy - 145
                    elif target_f_id == "trampoline":
                        target_wx = fx - 100
                        target_wy = fy + 25 - 250
                    else:
                        target_wx = fx - 90
                        target_wy = fy - 145
                        
                    current_x = self.root.winfo_x()
                    current_y = self.root.winfo_y()
                    
                    dx = target_wx - current_x
                    dy = target_wy - current_y
                    
                    # 超時保護
                    self._approach_timer = getattr(self, "_approach_timer", 350) - 1
                    if self._approach_timer <= 0:
                        self.pet.state = "idle"
                        self.pet.roll_angle = 0.0
                    else:
                        speed = 9.5 if self.pet_data.get("equipped_accessory") == "char_mask" else 3.2
                        step_x = speed if dx > 0 else -speed
                        if abs(dx) < speed:
                            step_x = dx
                            
                        # Y 軸平滑靠近
                        step_y = 0.0
                        if abs(dy) > 3.0:
                            step_y = 2.0 if dy > 0 else -2.0
                            if abs(dy) < 2.0:
                                step_y = dy
                                
                        new_x = current_x + step_x
                        new_y = current_y + step_y
                        self.update_geometry(new_x, new_y)
                        
                        self.pet.walk_dir = 1 if dx > 0 else -1
                        self.pet.roll_angle = 0.08 * math.sin(time.time() * 18.0)
                        
                        # 抵達判定 (距離小於 14 像素時觸發吸附互動)
                        if abs(dx) <= 14.0 and abs(dy) <= 25.0:
                            self.pet.roll_angle = 0.0
                            if target_f_id == "trampoline":
                                if hasattr(f_win, "trigger_bounce"):
                                    f_win.trigger_bounce()
                                self._fall_vy = -14.0
                                self.pet.state = "fall"
                                self.air_roll_timer = 28
                                self.air_roll_direction = random.choice([-1.0, 1.0])
                                self.create_text_popup("蹦蹦跳！🤸", 170, 100, color="#fab387")
                            else:
                                self.check_furniture_overlap()
                except Exception:
                    self.pet.state = "idle"
                    self.pet.roll_angle = 0.0
            else:
                self.pet.state = "idle"
                self.pet.roll_angle = 0.0

        # 處理高空自由落體與拋體物理 (支援下墜、橫向拋飛反彈與後空翻)
        if self.pet.state in ("fall", "backflip"):
            m_info = self.get_current_monitor_info()
            landing_y = m_info["work_y"] + m_info["work_h"] - 300
            # A withdrawn Tk window does not reliably advance winfo_x/y after
            # geometry updates. Unity mode therefore uses the authoritative
            # coordinates maintained by update_geometry; otherwise every frame
            # restarts from the release point and the fall appears frozen.
            if getattr(self, "_unity_renderer_active", False):
                current_x = float(self._physics_win_x)
                current_y = float(self._physics_win_y)
            else:
                current_x = self.root.winfo_x()
                current_y = self.root.winfo_y()
            
            # 追蹤本次墜落期間的最高空位置 (Y 軸越小代表越高)
            self._fall_peak_y = min(getattr(self, "_fall_peak_y", current_y), current_y)
            
            # 累加重力加速度與摩擦力衰減
            self._fall_vy = getattr(self, "_fall_vy", 0.0) + getattr(self, "_fall_gravity", 0.8)
            self._fall_vx = getattr(self, "_fall_vx", 0.0) * 0.985
            
            new_y = current_y + self._fall_vy
            new_x = current_x + self._fall_vx
            
            # 🤸 處理彈簧床空中 360 度特技翻滾
            if getattr(self, "air_roll_timer", 0) > 0:
                self.air_roll_timer -= 1
                self.pet.roll_angle += getattr(self, "air_roll_direction", 1.0) * (2.0 * math.pi / 28.0)
                if self.air_roll_timer == 0:
                    self.pet.roll_angle = 0.0  # 翻滾完畢，回正姿勢
            
            # 🤸 彈簧床 (Trampoline) 碰撞檢測
            # 🤸 彈簧床 (Trampoline) 碰撞檢測 (絕對防漏接 + 磁吸對齊床面)
            hit_trampoline = False
            if "trampoline" in self.spawned_furniture_wins:
                t_win = self.spawned_furniture_wins["trampoline"]
                try:
                    tx = t_win.winfo_x()
                    ty = t_win.winfo_y()
                    t_bed_y = ty + 25
                    pet_bottom_y = new_y + 250
                    pet_cx = new_x + 170
                    t_center_x = tx + 70
                    
                    # 只要水平在蹦蹦床範圍內 (±65px)
                    if abs(pet_cx - t_center_x) <= 65:
                        # 垂直方向：只要向下落 (vy > 0) 且腳底已到達或穿過床面
                        if self._fall_vy > 0 and (current_y + 250 <= t_bed_y + 35 or pet_bottom_y >= t_bed_y - 12):
                            hit_trampoline = True
                            # 觸發彈簧床物理凹陷與震盪動畫
                            if hasattr(t_win, "trigger_bounce"):
                                t_win.trigger_bounce()
                                
                            incoming_speed = abs(self._fall_vy)
                            bounce_speed = max(13.5, min(16.5, incoming_speed * 0.95 + random.uniform(1.5, 3.0)))
                            self._fall_vy = -bounce_speed
                            # 微小橫向對齊，始終保持在蹦蹦床上
                            self._fall_vx = (t_center_x - pet_cx) * 0.12 + random.uniform(-0.4, 0.4)
                            
                            # 關鍵：著陸點牢牢鎖定在彈簧床面上方，絕不下沉到地面或被狀態條擋住
                            new_y = t_bed_y - 250
                            
                            # 啟動空中 360 度特技翻滾
                            self.air_roll_timer = 28
                            self.air_roll_direction = random.choice([-1.0, 1.0])
                            
                            # 累計連續彈跳 Combo 數
                            self.trampoline_combo = getattr(self, "trampoline_combo", 0) + 1
                            
                            if self.trampoline_combo >= 3:
                                # 進入 Combo High 狂熱狀態！
                                self.pet_data["coins"] = self.pet_data.get("coins", 0) + 1
                                self.create_text_popup(f"WEEEEE! 🤸 Combo x{self.trampoline_combo} +1🪙", 170, 100, color="#f9e2af")
                                self.pet.eye_state = "star"
                                self.pet.mouth_state = "open"
                                self.root.after(600, self.pet.restore_eye)
                                # 噴灑大量狂熱彩色亮片
                                for _ in range(15):
                                    angle = random.uniform(0, 2 * math.pi)
                                    dist = random.uniform(15, 40)
                                    self.pet.coffee_sparks.append({
                                        "dx": dist * math.cos(angle),
                                        "dy": dist * math.sin(angle),
                                        "vy": random.uniform(-2.5, -0.5),
                                        "color": random.choice(["#f9e2af", "#f5c2e7", "#a6e3a1", "#89b4fa", "#cba6f7"]),
                                        "life": random.randint(25, 40)
                                    })
                                self.save_pet_savegame()
                            else:
                                self.create_text_popup("咚～! 🤸", 170, 100, color="#fab387")
                                self.pet.eye_state = "happy"
                                self.pet.mouth_state = "open"
                                self.root.after(500, self.pet.restore_eye)
                                for _ in range(6):
                                    angle = random.uniform(0, 2 * math.pi)
                                    dist = random.uniform(10, 30)
                                    self.pet.coffee_sparks.append({
                                        "dx": dist * math.cos(angle),
                                        "dy": dist * math.sin(angle),
                                        "vy": random.uniform(-1.5, -0.5),
                                        "color": random.choice(["#fab387", "#f38ba8", "#a6e3a1", "#89b4fa"]),
                                        "life": 30
                                    })
                except Exception:
                    pass

            # 🏀 投籃小遊戲 (橫向側視籃框版) 進球與碰撞檢測
            if getattr(self, "basketball_hoop", None) is not None:
                hoop = self.basketball_hoop
                hx = hoop.winfo_x()
                hy = hoop.winfo_y()
                
                # Emojinoko 的中心點與半徑
                pet_cx = current_x + 170
                pet_cy = current_y + 205
                pet_r = 45
                
                # 籃框 (Rim) 資訊 (側視向左，掛在右側板子)
                ry = hy + 130
                rl = hx + 80  # 前鐵圈圈口
                rr = hx + 200 # 後鐵圈圈口 (靠近右側板子)
                
                # 1. 檢測是否與籃框的兩個邊緣端點 (Rim Tips) 發生碰撞
                collided_tip = None
                for tip_x in (rl, rr):
                    dist_to_tip = math.hypot(pet_cx - tip_x, pet_cy - ry)
                    if dist_to_tip < pet_r:
                        collided_tip = (tip_x, ry)
                        break
                        
                if collided_tip:
                    tip_x, tip_y = collided_tip
                    dx = pet_cx - tip_x
                    dy = pet_cy - tip_y
                    dist = math.hypot(dx, dy)
                    if dist > 0:
                        nx = dx / dist
                        ny = dy / dist
                        # 沿法向推開，防重疊卡住
                        new_x = tip_x + nx * (pet_r + 2) - 170
                        new_y = tip_y + ny * (pet_r + 2) - 205
                        
                        # 速度反彈 (彈力係數 55%)
                        dot = self._fall_vx * nx + self._fall_vy * ny
                        self._fall_vx = (self._fall_vx - 2 * dot * nx) * 0.55
                        self._fall_vy = (self._fall_vy - 2 * dot * ny) * 0.55
                        
                        self.create_text_popup("噹！💥", 170, 130, color=PINK_COLOR)
                        self.pet.eye_state = "dizzy"
                        self.root.after(600, self.pet.restore_eye)
                        
                # 2. 檢測是否與直立籃板 (Backboard) 發生碰撞
                else:
                    bx1 = hx + 220
                    bx2 = hx + 235
                    by1 = hy + 40
                    by2 = hy + 180
                    
                    if (pet_cx + pet_r > bx1 and pet_cx - pet_r < bx2 and
                        pet_cy + pet_r > by1 and pet_cy - pet_r < by2):
                        in_hoop_x = (rl <= pet_cx <= rr)
                        
                        if not in_hoop_x:
                            overlap_x = min(pet_cx + pet_r - bx1, bx2 - (pet_cx - pet_r))
                            overlap_y = min(pet_cy + pet_r - by1, by2 - (pet_cy - pet_r))
                            
                            if overlap_x < overlap_y:
                                # 側邊碰撞
                                if pet_cx < (bx1 + bx2) / 2:
                                    new_x = bx1 - pet_r - 170
                                    self._fall_vx = -abs(self._fall_vx) * 0.6
                                else:
                                    new_x = bx2 + pet_r - 170
                                    self._fall_vx = abs(self._fall_vx) * 0.6
                            else:
                                # 上下碰撞
                                if pet_cy < (by1 + by2) / 2:
                                    new_y = by1 - pet_r - 205
                                    self._fall_vy = -abs(self._fall_vy) * 0.6
                                else:
                                    new_y = by2 + pet_r - 205
                                    self._fall_vy = abs(self._fall_vy) * 0.6
                                    
                            self.create_text_popup("框！🏀", 170, 130, color="#fab387")
                            self.pet.eye_state = "dizzy"
                            self.root.after(600, self.pet.restore_eye)
                            
                # 3. 檢測是否順利穿過籃網 (Goal Swish)
                if getattr(self, "basketball_hoop", None) is not None:
                    rim_left = rl + 35
                    rim_right = rr - 35
                    prev_pet_cy = current_y + 205
                    new_pet_cy = new_y + 205
                    new_pet_cx = new_x + 170
                    if self._fall_vy > 0 and prev_pet_cy <= ry < new_pet_cy:
                        if rim_left <= new_pet_cx <= rim_right:
                            hoop.trigger_goal()
                            self.pet_data["coins"] = self.pet_data.get("coins", 0) + 10
                            self.create_text_popup("🏀 SWISH! +10 🪙", 170, 100, color=YELLOW_COLOR)
                            self.pet.eye_state = "happy"
                            self.pet.mouth_state = "open"
                            self.save_pet_savegame()
                            # 散發進球金色小粒子
                            for _ in range(8):
                                angle = random.uniform(0, 2 * math.pi)
                                dist = random.uniform(15, 45)
                                self.pet.coffee_sparks.append({
                                    "dx": dist * math.cos(angle),
                                    "dy": dist * math.sin(angle),
                                    "vy": random.uniform(-3.0, -1.0),
                                    "color": "#f9e2af",
                                    "life": random.randint(20, 35)
                                })
            
            # 1. 左右邊界碰撞反彈 (基於整個虛擬螢幕，防止在雙螢幕交界反彈)
            left_bound, right_bound = self.get_virtual_screen_bounds()
            
            if new_x <= left_bound:
                new_x = left_bound
                self._fall_vx = -self._fall_vx * 0.6  # 反彈保留 60% 水平動能
                self.pet.vel_scale_x = -0.12
                self.pet.vel_scale_y = 0.08
                self.create_text_popup("啵！", 40, 205, color=ACCENT_COLOR)
            elif new_x >= right_bound:
                new_x = right_bound
                self._fall_vx = -self._fall_vx * 0.6
                self.pet.vel_scale_x = 0.12
                self.pet.vel_scale_y = -0.08
                self.create_text_popup("啵！", 300, 205, color=ACCENT_COLOR)
            
            # 2. 地面碰撞反彈與著陸判定 (若剛踩中彈簧床則跳過地面檢測，防止瞬間判定衝突)
            if not hit_trampoline and new_y >= landing_y:
                # 計算本次墜落的高度差 (landing_y 與最高點的比值)
                fall_height = landing_y - getattr(self, "_fall_peak_y", landing_y)
                
                # 完美落地機率根據高度動態計算
                if fall_height <= 100:
                    perfect_prob = 0.90
                elif fall_height >= 500:
                    perfect_prob = 0.20
                else:
                    perfect_prob = 0.90 - 0.70 * (fall_height - 100) / 400.0
                
                is_perfect_land = (random.random() < perfect_prob)
                unity_fall = getattr(self, "_unity_renderer_active", False)
                if unity_fall:
                    elapsed = time.monotonic() - getattr(
                        self, "_unity_fall_started_at", time.monotonic())
                    # At most one short squash/bounce in Unity mode. The old
                    # random multi-bounce chain was the source of the apparent
                    # endless floating and made the taskbar stop feel optional.
                    may_bounce_once = (
                        not getattr(self, "_unity_floor_bounced", False)
                        and elapsed < 1.25
                        and self._fall_vy > 9.0
                    )
                    is_perfect_land = not may_bounce_once
                
                # 若沒能完美落地，且下落速度大於 4.5，則進行反彈
                if not is_perfect_land and (self._fall_vy > 4.5):
                    new_y = landing_y
                    bounce_factor = 0.28 if unity_fall else 0.55
                    self._fall_vy = -self._fall_vy * bounce_factor
                    if unity_fall:
                        self._unity_floor_bounced = True
                    self._fall_vx *= 0.7  # 地面摩擦力
                    
                    # 落地彈跳果凍變形
                    self.pet.vel_scale_y = 0.16
                    self.pet.vel_scale_x = -0.12
                    
                    # 給予對應的滾動角速度，彈跳時看起來像滾動前進
                    self.pet.roll_speed = max(-0.25, min(0.25, self._fall_vx * 0.015))
                    self.create_text_popup("咚！", 170, 130, color=ACCENT_COLOR)
                else:
                    new_y = landing_y
                    prev_state = self.pet.state
                    self.pet.state = "idle"
                    self.pet.roll_angle = 0.0
                    self.pet.roll_speed = 0.0
                    self._fall_vx = 0.0
                    self._fall_vy = 0.0
                    self.air_roll_timer = 0
                    self.trampoline_combo = 0
                    
                    # 著陸時壓扁果凍物理回彈
                    self.pet.vel_scale_y = 0.22
                    self.pet.vel_scale_x = -0.16
                    self.root.lift()  # 落地後將地瓜球主視窗置頂
                    
                    # 判斷是完美落地還是安全著陸
                    if is_perfect_land:
                        self.pet.eye_state = "happy"
                        self.pet.mouth_state = "normal"
                        self.create_text_popup("⭐完美落地！⭐", 170, 130, color=YELLOW_COLOR)
                        
                        # 完美落地獎勵：獲得 2 個地瓜幣！
                        self.pet_data["coins"] = self.pet_data.get("coins", 0) + 2
                        
                        # 散落星星粒子
                        for _ in range(6):
                            angle = random.uniform(0, 2 * math.pi)
                            dist = random.uniform(10, 35)
                            self.pet.coffee_sparks.append({
                                "dx": dist * math.cos(angle),
                                "dy": dist * math.sin(angle),
                                "vy": random.uniform(-2.0, -0.5),
                                "color": "#f9e2af",
                                "life": random.randint(15, 30)
                            })
                    else:
                        self.pet.eye_state = "happy"
                        self.create_text_popup("安全著陸！", 170, 130, color=ACCENT_COLOR)
                        
                    self.root.after(800, lambda: self.pet.restore_eye())
                    self.save_pet_savegame()
                    if getattr(self, "_unity_renderer_active", False):
                        save_config({"pet_x": int(new_x), "pet_y": int(new_y)})
            
            # 3. 若處於普通空中下墜狀態，使地瓜球滾動
            if self.pet.state == "fall":
                self.pet.roll_angle += getattr(self.pet, "roll_speed", 0.0)
                self.pet.roll_speed *= 0.985
            
            self.update_geometry(new_x, new_y)
            
        # 如果地瓜球不在 fall/backflip/roll/singing/fever/balloon 狀態，但 roll_angle 卻不為 0.0，
        # 我們讓它平滑差值回 0.0 (完成翻滾後翻回正面的過渡)
        if self.pet.state not in ("fall", "backflip", "roll", "balloon", "chase_mouse") and getattr(self.pet, "singing_timer", 0) == 0 and getattr(self.pet, "fever_timer", 0) == 0:
            if abs(self.pet.roll_angle) > 0.001:
                # 規範化到 [-pi, pi] 之間以選擇最短路徑翻轉回來
                angle = (self.pet.roll_angle + math.pi) % (2 * math.pi) - math.pi
                angle *= 0.82
                self.pet.roll_angle = angle
            else:
                self.pet.roll_angle = 0.0

        # 處理追滑鼠物理狀態
        if self.pet.state == "chase_mouse":
            self._chase_timer = getattr(self, "_chase_timer", 0) - 1
            if self._chase_timer <= 0:
                if getattr(self, "_chase_origin_x", None) is not None:
                    self.pet.state = "return_home"
                    self.pet.eye_state = "normal"
                    self.pet.mouth_state = "normal"
                    self.create_text_popup("回家嘍... 🐾", 170, 130, color=ACCENT_COLOR)
                else:
                    self.pet.state = "idle"
                    self.pet.eye_state = "normal"
                    self.pet.mouth_state = "normal"
                    self.create_text_popup("累了... 💨", 170, 130, color=ACCENT_COLOR)
            else:
                m_info = self.get_current_monitor_info()
                landing_y = m_info["work_y"] + m_info["work_h"] - 300
                
                # 獲取滑鼠與視窗的座標
                mx, my = self.root.winfo_pointerxy()
                wx = self.root.winfo_x()
                wy = self.root.winfo_y()
                
                # 地瓜球的螢幕中心點 X/Y
                screen_pet_x = wx + self.pet.cx
                screen_pet_y = wy + 205
                
                diff_x = mx - screen_pet_x
                diff_y = my - screen_pet_y
                
                if abs(diff_x) <= 25 and abs(diff_y) <= 25:
                    # 抓到滑鼠了！開心原地跳一下
                    self._fall_vy = -7.0
                    self.pet.state = "fall"
                    self.create_text_popup("抓到了！✨", 170, 130, color=YELLOW_COLOR)
                    self.pet.eye_state = "happy"
                    self.pet.mouth_state = "open"
                    self._chase_jump_vy = 0.0  # 重置追逐跳躍速度
                    
                    def go_home_after_catch():
                        self.pet.restore_eye()
                        if getattr(self, "_chase_origin_x", None) is not None:
                            self.pet.state = "return_home"
                            self.create_text_popup("回家嘍... 🐾", 170, 130, color=ACCENT_COLOR)
                    self.root.after(800, go_home_after_catch)
                else:
                    # 判定是否處於空中 (正處於跳躍狀態)
                    is_in_air = (wy < landing_y or getattr(self, "_chase_jump_vy", 0.0) != 0.0)
                    
                    if is_in_air:
                        # 空中狀態：X 軸移動完全遵循起跳時的水平初速度與慣性
                        self._chase_vx = getattr(self, "_chase_vx", 0.0) * 0.985  # 微小空氣阻力
                        step = self._chase_vx
                    else:
                        # 地面狀態：正常朝滑鼠跑步
                        run_speed = 4.5
                        self.pet.walk_dir = 1 if diff_x > 0 else -1
                        step = run_speed if diff_x > 0 else -run_speed
                        if abs(diff_x) < run_speed:
                            step = diff_x
                        self._chase_vx = step
                        
                    left_bound, right_bound = self.get_virtual_screen_bounds()
                    new_wx = max(left_bound, min(right_bound, wx + step))
                    
                    # 處理 Y 軸跳躍
                    self._chase_jump_vy = getattr(self, "_chase_jump_vy", 0.0)
                    
                    # 如果在地板上且滑鼠高於寵物 40 像素，則觸發大跳躍
                    if wy >= landing_y and self._chase_jump_vy == 0.0:
                        if diff_y < -40:
                            height_diff = -diff_y
                            # 根據高度差給予 -8.0 到 -15.0 的起跳速度 (大力跳)
                            self._chase_jump_vy = -max(8.0, min(15.0, height_diff * 0.035))
                            # 給予水平拋射初速度 (慣性)，速度大小與與滑鼠的 X 距離成正比
                            self._chase_vx = max(-6.5, min(6.5, diff_x * 0.035))
                            self.pet.vel_scale_y = -0.25  # 起跳壓扁彈性
                            self.pet.vel_scale_x = 0.15
                            self.create_text_popup("起飛！🚀", 170, 120, color=YELLOW_COLOR)
                    
                    # 套用重力與 Y 軸移動
                    if wy < landing_y or self._chase_jump_vy != 0.0:
                        self._chase_jump_vy += 0.8  # 重力加速度
                        new_wy = wy + self._chase_jump_vy
                        if new_wy >= landing_y:
                            new_wy = landing_y
                            self._chase_jump_vy = 0.0
                            self._chase_vx = 0.0  # 落地時歸零空中橫向速度
                            self.pet.vel_scale_y = 0.22  # 落地彈性
                            self.pet.vel_scale_x = -0.16
                    else:
                        new_wy = landing_y
                        
                    self.update_geometry(new_wx, new_wy)
                    self.pet.cx = 170

        # 處理返回原位狀態
        elif self.pet.state == "return_home":
            if getattr(self, "_chase_origin_x", None) is not None:
                current_x = self.root.winfo_x()
                if abs(current_x - self._chase_origin_x) <= 6:
                    # 到家了！
                    m_info = self.get_current_monitor_info()
                    landing_y = m_info["work_y"] + m_info["work_h"] - 300
                    self.update_geometry(self._chase_origin_x, landing_y)
                    self.pet.state = "idle"
                    self.pet.cx = 170
                    self.pet.eye_state = "happy"
                    self.create_text_popup("我回來了！✨", 170, 130, color=YELLOW_COLOR)
                    self.root.after(800, lambda: self.pet.restore_eye())
                    self._chase_origin_x = None
                else:
                    # 往原位走
                    m_info = self.get_current_monitor_info()
                    landing_y = m_info["work_y"] + m_info["work_h"] - 300
                    step = 2.0  # 返回速度
                    if self._chase_origin_x > current_x:
                        self.pet.walk_dir = 1
                        new_wx = min(self._chase_origin_x, current_x + step)
                    else:
                        self.pet.walk_dir = -1
                        new_wx = max(self._chase_origin_x, current_x - step)
                    self.update_geometry(new_wx, landing_y)
                    self.pet.cx = 170
            else:
                self.pet.state = "idle"

        # 隨機觸發追滑鼠行為 (在 idle/walk 狀態下，有小機率觸發，飽食度大於 10%)
        if self.pet.state in ("idle", "walk") and not getattr(self.pet, "fever_timer", 0) > 0 and self.pet_data.get("satiety", 100.0) > 10:
            if random.random() < 0.00025:  # 每秒約 1.5% 的機率
                mx = self.root.winfo_pointerx()
                wx = self.root.winfo_x()
                if abs(mx - (wx + 170)) > 120:
                    self._chase_origin_x = wx  # 記錄出發位置！
                    self.pet.state = "chase_mouse"
                    self._chase_timer = 250  # 最長追 4 秒左右
                    self.pet.eye_state = "star"
                    self.pet.mouth_state = "open"
                    self.create_text_popup("發現鼠標！🐾", 170, 130, color=YELLOW_COLOR)

        # 隨機主動走向並使用家具 (當場景中有家具且不在冷卻中)
        if self.pet.state in ("idle", "walk") and not getattr(self.pet, "fever_timer", 0) > 0 and self.pet_data.get("satiety", 100.0) > 15:
            if getattr(self, "current_furniture_snapped", None) is None and getattr(self, "_furniture_cooldown", 0) <= 0:
                spawned = getattr(self, "spawned_furniture_wins", {})
                if spawned and random.random() < 0.003: # 每秒約 18% 的發呆機會主動去玩
                    target_f_id = random.choice(list(spawned.keys()))
                    self.target_furniture_id = target_f_id
                    self.pet.state = "approach_furniture"
                    self._approach_timer = 350
                    self.pet.eye_state = "happy"
                    
                    approach_msg = {
                        "futon": "好睏去睡覺 💤",
                        "laptop": "靈感來了寫代碼！💻",
                        "lazy_sofa": "去沙發躺躺~ 🛋️",
                        "kotatsu": "好冷想鑽暖桌 🍵",
                        "pixel_tv": "去看看電視 📺",
                        "night_lamp": "去燈下靜心 🏮",
                        "succulent_pot": "去給多肉澆水 🪴",
                        "trampoline": "去跳蹦蹦床！🤸"
                    }.get(target_f_id, "去玩耍囉！✨")
                    self.create_text_popup(approach_msg, 170, 120, color="#f9e2af")
                    self.root.after(800, self.pet.restore_eye)

        # 自發性偶爾主動向主人搭話/碎碎念 (CCR LLM)
        if self.pet.state in ("idle", "walk") and not getattr(self.pet, "fever_timer", 0) > 0:
            cfg = self.pet_data.get("ai_config", {})
            if cfg.get("auto_chatter", True):
                interval_sec = max(180, cfg.get("chatter_interval_min", 15) * 60)
                now_t = time.time()
                last_t = getattr(self, "_last_chatter_time", now_t - interval_sec + 60)
                if now_t - last_t > interval_sec:
                    self._last_chatter_time = now_t
                    self.trigger_autonomous_chatter()

        # 更新地瓜球物理狀態與位置
        self.pet.update_physics()
        
        # 更新獨立的物理貼地影子
        self.update_shadow_position(self.root.winfo_x(), self.root.winfo_y())
        
        # 摸摸 Fever 模式下飄散愛心粒子
        if getattr(self.pet, "fever_timer", 0) > 0 and random.random() < 0.08:
            heart_x = self.pet.cx + random.randint(-25, 25)
            heart_y = 205 - self.pet.r - random.randint(10, 25)
            self.create_text_popup("❤", heart_x, heart_y, color=PINK_COLOR)
            
        # 繪製地瓜球、看板與底部狀態欄 HUD
        self.pet.draw(
            name=self.user_name,
            price_str=self.monthly_price_str,
            coins=self.pet_data.get("coins", 0),
            level=self.pet_data.get("level", 1),
            xp=self.pet_data.get("xp", 0.0),
            satiety=self.pet_data.get("satiety", 100.0)
        )
        
        # 繪製獨立的貼地 HUD
        if getattr(self, "hud_win", None):
            self.hud_win.draw_hud(
                coins=self.pet_data.get("coins", 0),
                level=self.pet_data.get("level", 1),
                xp=self.pet_data.get("xp", 0.0),
                satiety=self.pet_data.get("satiety", 100.0),
                price_str=self.monthly_price_str,
                pet_state=self.pet.state
            )
        
        # 🏀 繪製前半立體籃框與籃網 (只在地瓜球處於空中且靠近籃框時才疊加繪製，完全消除日常拖曳或遠距離時的視覺殘影)
        if getattr(self, "basketball_hoop", None) is not None:
            self.canvas.delete("front_hoop")
            hoop = self.basketball_hoop
            hx = hoop.winfo_x()
            hy = hoop.winfo_y()
            cx = getattr(self, "_physics_win_x", self.root.winfo_x())
            cy = getattr(self, "_physics_win_y", self.root.winfo_y())
            
            # 計算中心距離 (地瓜球中心 cx+170, cy+205; 籃圈中心 hx+140, hy+130)
            dist_x = abs((cx + 170) - (hx + 140))
            dist_y = abs((cy + 205) - (hy + 130))
            
            if self.pet.state in ("fall", "backflip") and dist_x < 160 and dist_y < 140:
                # 確保地瓜球視窗始終置頂在籃框上方，從而利用前半遮擋技術
                self.root.lift()
                
                rx = hx - cx
                ry = hy - cy
                
                oy = hoop.net_offset_y
                net_color = "#cdd6f4"
                
                # 左側網邊
                self.canvas.create_line(rx + 80, ry + 130, rx + 110 + oy*0.4, ry + 195 + oy, fill=net_color, width=2.5, tags="front_hoop")
                # 右側網邊
                self.canvas.create_line(rx + 200, ry + 130, rx + 170 - oy*0.4, ry + 195 + oy, fill=net_color, width=2.5, tags="front_hoop")
                # 中間網線
                self.canvas.create_line(rx + 110, ry + 130, rx + 125 + oy*0.2, ry + 195 + oy, fill=net_color, width=2, tags="front_hoop")
                self.canvas.create_line(rx + 140, ry + 130, rx + 140, ry + 195 + oy, fill=net_color, width=2, tags="front_hoop")
                self.canvas.create_line(rx + 170, ry + 130, rx + 155 - oy*0.2, ry + 195 + oy, fill=net_color, width=2, tags="front_hoop")
                # 網孔橫線
                self.canvas.create_line(rx + 90, ry + 150 + oy*0.3, rx + 190, ry + 150 + oy*0.3, fill=net_color, width=1.5, tags="front_hoop")
                self.canvas.create_line(rx + 100, ry + 170 + oy*0.6, rx + 180, ry + 170 + oy*0.6, fill=net_color, width=1.5, tags="front_hoop")
                
                # 前前半橘紅色鐵圈 ( start=180, extent=180 畫下半弧線)
                self.canvas.create_arc(rx + 80, ry + 120, rx + 200, ry + 140, start=180, extent=180, outline="#f38ba8", width=5, style=tk.ARC, tags="front_hoop")
        else:
            self.canvas.delete("front_hoop")
            
        # 更新墜落 Token 粒子與經驗文字
        self._update_ui_particles()

        # 🛌 繪製棉被覆蓋被單 (莫蘭迪色調高質感呼吸起伏被罩)
        self.canvas.delete("front_futon")
        if self.pet.state == "sleep_futon":
            # 呼吸上下微弱起伏 (週期約 1.6 秒，振幅 2 像素)
            breath_y = 2.0 * math.sin(time_ms() / 250.0)
            quilt_top = 172 + breath_y
            
            # (1) 莫蘭迪綠色被身
            self.canvas.create_rectangle(140, quilt_top, 250, 242, fill="#89b4fa", outline="#1e1e2e", width=1.5, tags="front_futon")
            
            # 繪製棉被格子線
            for y in range(int(quilt_top) + 15, 240, 15):
                self.canvas.create_line(140, y, 250, y, fill="#74c7ec", width=1.0, tags="front_futon")
                
            # (2) 莫蘭迪軟白反折被頭 (覆蓋在被身頂部)
            self.canvas.create_rectangle(140, quilt_top, 250, quilt_top + 12, fill="#f5e0dc", outline="#1e1e2e", width=1.5, tags="front_futon")
            
            # 隨機在頭頂飄出溫馨 zZ... 氣泡文字
            if random.random() < 0.008:
                self.create_text_popup("zZ...", 170, 130, color="#b4befe")

        # 💻 寫扣鍵盤代碼火花 (Code Particles)
        self.code_particles = getattr(self, "code_particles", [])
        
        # 如果正在寫扣，隨機產生新代碼粒子
        if self.pet.state == "work_laptop" and random.random() < 0.35:
            char = random.choice(["0", "1", ";", "{", "}", "f", "x", "<", ">", "+", "="])
            color = random.choice(["#a6e3a1", "#89b4fa", "#f9e2af", "#cba6f7", "#f5c2e7"])
            # 起點為鍵盤區域 X 在 [195, 235], Y 在 [210, 225]
            px = random.randint(195, 235)
            py = random.randint(210, 225)
            pid = self.canvas.create_text(px, py, text=char, fill=color, font=("Consolas", 8, "bold"), tags="code_particle")
            self.code_particles.append({
                "id": pid,
                "x": px,
                "y": py,
                "vx": random.uniform(-1.5, 1.5),
                "vy": random.uniform(-2.5, -1.0),
                "life": 20
            })
            
        # 更新並繪製所有代碼粒子
        active_particles = []
        for p in self.code_particles:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["life"] -= 1
            self.canvas.coords(p["id"], p["x"], p["y"])
            if p["life"] > 0:
                if p["life"] < 5:
                    self.canvas.itemconfig(p["id"], fill="#313244")
                active_particles.append(p)
            else:
                self.canvas.delete(p["id"])
        self.code_particles = active_particles

        # 家具重疊自動吸附 (與家具互動)
        if getattr(self, "current_furniture_snapped", None) is None:
            if getattr(self, "_furniture_cooldown", 0) > 0:
                self._furniture_cooldown -= 1
            else:
                if self.pet.state in ("idle", "walk"):
                    self.check_furniture_overlap()

        # 將漂浮文字與食物 Token 抬升至最頂層，避免被剛重繪的地瓜球或看板遮擋
        self.canvas.tag_raise("overlay")

        # Send a compact renderer contract while the unchanged legacy pet keeps
        # running as the state source and hot fallback.
        self._sync_unity_renderer()

        self.root.after(16, self.tick_physics)

    def tick_economy(self):
        """10 秒一次的經濟產幣與飢餓流逝時鐘"""
        if not self.root.winfo_exists():
            return

        # 1. 飽食度隨時間被動減少 (SATIETY_DECAY 每 8 分鐘扣 1%，換算 10 秒扣除比例)
        decay_amount = (PET_SATIETY_DECAY / 48.0)
        
        # 氣球飄浮期間飽食度不衰減
        if self.pet.state == "balloon":
            decay_amount = 0.0
        # 睡棉被期間飽食度消耗減半
        elif self.pet.state == "sleep_futon":
            decay_amount *= 0.50
        # 蝴蝶結減少 10% 消化速度
        elif self.pet_data.get("equipped_accessory") == "bowtie":
            decay_amount *= 0.90
            
        # 🤸 彈簧床彈跳運動期間飽食度消耗變為 3 倍
        if getattr(self, "_fall_vy", 0) != 0 and self.pet.state not in ("sleep", "sleep_futon", "work_laptop", "balloon"):
            if "trampoline" in self.spawned_furniture_wins:
                t_win = self.spawned_furniture_wins["trampoline"]
                tx = t_win.winfo_x()
                pet_cx = self.root.winfo_x() + 170
                if tx + 10 <= pet_cx <= tx + 130:
                    decay_amount *= 3.0
            
        self.pet_data["satiety"] = max(0.0, self.pet_data.get("satiety", 100.0) - decay_amount)

        # 偵測是否為加班時間 (晚上 22:00 至 早上 06:00)
        curr_hour = datetime.now().hour
        self.pet.is_overtime = (curr_hour >= 22 or curr_hour < 6)

        # 2. 產幣與休眠狀態檢測 (偵測 Windows 系統桌面是否鎖定)
        screen_locked = is_screen_locked()
        
        # 只要使用者沒有鎖定螢幕，地瓜球就當作主人仍在上班，保持活動並被動產幣！
        if not screen_locked:
            # 隨機溫馨問候
            if self.pet.state not in ("sleep", "roll") and getattr(self.pet, "fever_timer", 0) == 0 and random.random() < 0.015:
                self._show_time_greeting()
                
            # 地瓜球也跟著努力上班！累計上班時間
            self.active_work_seconds += 10
            
            # 💻 寫扣加班產幣 (每 30 秒額外 +5🪙 獎勵)
            if self.pet.state == "work_laptop":
                self.laptop_work_timer = getattr(self, "laptop_work_timer", 0) + 10
                if self.laptop_work_timer >= 30:
                    self.laptop_work_timer = 0
                    self.pet_data["coins"] = self.pet_data.get("coins", 0) + 5
                    self.create_text_popup("CODE! 💻 +5🪙", 170, 100, color="#f9e2af")
                    self.save_pet_savegame()
            else:
                self.laptop_work_timer = 0
            
            # 當前地瓜球狀態設定為正常，若是躺平睡覺狀態則立刻醒來
            if self.pet.state == "sleep":
                self.pet.state = "idle"
                self.create_text_popup("上班囉！", 170, 160, color=ACCENT_COLOR)

            # 加班狀態下隨機露出疲憊泡泡
            if self.pet.is_overtime and random.random() < 0.15 and self.pet.state == "idle":
                self.create_text_popup(random.choice(["☕ 睏...", "🔋 沒電了", "加班中..."]), 170, 140, color=PINK_COLOR)

            # 打瞌睡狀態下隨機冒出 zZZ 氣泡
            if self.pet.doze_timer > 0 and random.random() < 0.35:
                self.create_text_popup("zZZ", 185, 145, color="#cdd6f4")
                
            # 筆電寫扣狀態下隨機露出打字氣泡
            if self.pet.state == "work_laptop" and random.random() < 0.3:
                self.create_text_popup(random.choice(["嗒嗒嗒...💻", "修Bug中...⚙️", "編譯中...☕"]), 170, 140, color="#89b4fa")

            # 睡棉被狀態下隨機冒出 zZZ 氣泡
            if self.pet.state == "sleep_futon" and random.random() < 0.35:
                self.create_text_popup("zZZ", 185, 145, color="#b4befe")

            # 每滿 60 秒結算一次被動產幣
            if self.active_work_seconds >= 60:
                self.active_work_seconds = 0
                
                # 計算產幣效率倍率 (等級加成)
                multiplier = 1.0 + (self.pet_data.get("level", 1) - 1) * PET_LEVEL_MULTIPLIER
                
                # 飢餓狀態懲罰 (飽食度低於 20% 效率減半)
                satiety = self.pet_data.get("satiety", 100.0)
                if satiety < PET_SATIETY_THRESHOLD:
                    multiplier *= 0.5
                    # 提示主人餓扁了
                    self.create_text_popup("肚子餓...效率減半", 170, 140, color=PINK_COLOR)
                
                # 配件加成套用
                equipped = self.pet_data.get("equipped_accessory")
                if equipped == "sunglasses":
                    multiplier *= 1.10
                elif equipped == "crown":
                    multiplier *= 1.15
                elif equipped == "cat_ears":
                    multiplier *= 1.15
                elif equipped == "gentleman_hat":
                    multiplier *= 1.15
                elif equipped == "demon_horns":
                    multiplier *= 1.15
                elif equipped == "star_sunglasses":
                    multiplier *= 1.10
                    
                # 摸摸 Fever 模式產量加倍
                if getattr(self.pet, "fever_timer", 0) > 0:
                    multiplier *= 1.50
                    self.create_text_popup("❤ 摸摸 Fever！150%!", 170, 140, color=PINK_COLOR)
                
                # 咖啡加速與加班效率調整
                if self.pet.coffee_timer > 0:
                    multiplier *= 2.0
                    self.create_text_popup("☕ 咖啡超頻！200%!", 170, 140, color=YELLOW_COLOR)
                elif self.pet.is_overtime:
                    multiplier *= 0.8
                
                # 活力糖果 Buff 加成
                if getattr(self.pet, "candy_timer", 0) > 0:
                    multiplier *= 1.20
                    self.create_text_popup("🍬 活力糖果！120%!", 170, 130, color=PINK_COLOR)
                    
                # 筆電加班寫扣 Buff
                if self.pet.state == "work_laptop":
                    multiplier *= 1.25
                    self.create_text_popup("💻 加班寫扣！125%!", 170, 140, color="#89b4fa")
                
                # 被動產出地瓜幣
                gained = int(PET_BASE_EARNING * multiplier)
                self.pet_data["coins"] = self.pet_data.get("coins", 0) + gained
                
                # 浮動地瓜幣特效
                self.create_text_popup(f"+{gained} 🪙", 170, 150, color=YELLOW_COLOR)
                self.save_pet_savegame()
        else:
            # 如果螢幕鎖定 (下班)，地瓜球進入躺平睡覺 zZZ
            if self.pet.state in ("idle", "walk") and self.pet_data.get("satiety", 100.0) > 0:
                self.pet.state = "sleep"
                # 產生 zZZ 氣泡
                if random.random() < 0.3:
                    self.create_text_popup("zZZ", 185, 145, color="#cdd6f4")

        # 3. 自動算力機 (Auto-miner) 被動加載 (預留商店系統擴展，每 10 秒加微量飽食)
        auto_miner_lvl = self.pet_data.get("upgrades", {}).get("auto_miner", 0)
        if auto_miner_lvl > 0:
            # 每級自動餵食器每 10 秒恢復 0.25% 飽食度
            self.pet_data["satiety"] = min(100.0, self.pet_data["satiety"] + auto_miner_lvl * 0.25)
            self.save_pet_savegame()

        self.root.after(10000, self.tick_economy)

    # ──────────────────────────────────────────────────
    # API 用量抓取與差額投餵 (Delta-Feeding System)
    # ──────────────────────────────────────────────────
    def auto_refresh_data(self):
        """每 60 秒在背景刷新一次 API 資料，檢測是否有 Token 用量差額"""
        if getattr(self, "STANDALONE", False):
            self.root.after(60000, self.auto_refresh_data)
            return
        if not self.is_fetching:
            self.is_manual_refresh = False
            threading.Thread(target=self._fetch_usage_api, daemon=True).start()
        self.root.after(60000, self.auto_refresh_data)

    def manual_refresh(self):
        """右鍵選單的手動刷新對帳"""
        if not self.is_fetching:
            self.is_manual_refresh = True
            self.create_text_popup("⏳ 對帳中...", 170, 120, color=ACCENT_COLOR)
            threading.Thread(target=self._fetch_usage_api, daemon=True).start()

    def _show_fetch_error(self, err_type):
        """對帳連線失敗時顯示紅色漂浮文字"""
        self.create_text_popup(f"❌ {err_type}", 170, 120, color=PINK_COLOR)

    def simulate_usage(self):
        """模擬用量增加，用於離線/外網環境下測試地瓜球餵食與產幣"""
        # 模擬 Prompt Token 增加 1500，Completion Token 增加 800
        fake_prompt = self.pet_data.get("last_prompt_baseline", 0) + 1500
        fake_complete = self.pet_data.get("last_complete_baseline", 0) + 800
        
        # 構造模擬 Open WebUI 傳回的 JSON 數據結構
        fake_usage = [
            {
                "model": "gpt-4o",
                "price": 0.05,
                "request": 1,
                "prompt_tokens": fake_prompt,
                "complete_tokens": fake_complete,
                "api": "no"
            }
        ]
        self.create_text_popup("🧪 模擬測試中...", 170, 120, color=ACCENT_COLOR)
        # 直接調用用量差額處理邏輯
        self._process_usage_delta(fake_usage)

    def get_virtual_screen_bounds(self):
        """取得整個虛擬螢幕 (所有螢幕組合) 的左右邊界"""
        m_info = self.get_current_monitor_info()
        left_bound = m_info["mon_x"]
        right_bound = m_info["mon_x"] + m_info["mon_w"] - 340
        
        if not IS_WINDOWS:
            return left_bound, right_bound

        if getattr(self, "_unity_renderer_active", False):
            metrics = getattr(self, "_unity_desktop_metrics", None)
            if metrics and metrics.get("mon_w", 0) > 0:
                left_bound = metrics["mon_x"]
                right_bound = left_bound + metrics["mon_w"] - 340
                return left_bound, right_bound
            
        try:
            import ctypes
            user32 = ctypes.windll.user32
            v_left = user32.GetSystemMetrics(76)   # SM_XVIRTUALSCREEN = 76
            v_width = user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN = 78
            if v_width > 0:
                left_bound = v_left
                right_bound = v_left + v_width - 340
        except Exception:
            pass
            
        return left_bound, right_bound

    def toggle_basketball_game(self):
        """開啟/關閉投籃小遊戲"""
        if getattr(self, "basketball_hoop", None) is not None:
            self.basketball_hoop.close_game()
            self.create_text_popup("🏀 關閉投籃小遊戲", 170, 120, color=ACCENT_COLOR)
        else:
            self.basketball_hoop = BasketballHoop(self)
            self.create_text_popup("🏀 投籃小遊戲開始！", 170, 120, color=YELLOW_COLOR)

    def toggle_fruit_catcher(self):
        """開啟/關閉接水果小遊戲"""
        if getattr(self, "fruit_catcher_game", None) is not None:
            self.fruit_catcher_game.close_game()
            self.create_text_popup("🍎 關閉接水果", 170, 120, color=ACCENT_COLOR)
        else:
            self.fruit_catcher_game = FruitCatcherWindow(self)
            self.create_text_popup("🍎 接水果小遊戲開始！", 170, 120, color=YELLOW_COLOR)

    def toggle_slot_machine(self):
        """開啟/關閉幸運拉霸機"""
        if getattr(self, "slot_machine_game", None) is not None:
            self.slot_machine_game.close_game()
            self.create_text_popup("🎰 關閉拉霸機", 170, 120, color=ACCENT_COLOR)
        else:
            self.slot_machine_game = SlotMachineWindow(self)
            self.create_text_popup("🎰 幸運拉霸機開啟！", 170, 120, color=YELLOW_COLOR)

    def _fetch_usage_api(self):
        """背景網路請求：拉取 Open WebUI 用量數據"""
        if getattr(self, "STANDALONE", False):
            self.is_fetching = False
            return
        self.is_fetching = True
        try:
            headers = {
                "Authorization": f"Bearer {self.TOKEN}",
                "Content-Type": "application/json",
            }
            cookies = {"token": self.TOKEN}

            # 刷新快取
            requests.get(f"{OPENWEBUI_BASE_URL}/api/usage", headers=headers, cookies=cookies, timeout=8)
            
            # 獲取本月數據
            r = requests.post(
                f"{OPENWEBUI_BASE_URL}/api/v1/phison/user/usage/monthly",
                headers=headers, cookies=cookies,
                json={"key": self.PHISON_TOKEN}, timeout=10
            )

            # Token 過期自動重新登入
            if r.status_code == 401:
                self._auto_relogin()
                return

            if r.status_code == 200:
                usage_data = r.json()
                self.root.after(0, self._process_usage_delta, usage_data)
        except Exception as e:
            import traceback
            print("\n=== [地瓜球對帳連線錯誤日誌] ===")
            traceback.print_exc()
            print("===============================\n")
            
            # 連線失敗時，將具體錯誤類型回傳給主執行緒，避免卡死在「對帳中」
            err_msg = "連線逾時" if "timeout" in str(e).lower() else f"對帳失敗: {type(e).__name__}"
            self.root.after(0, self._show_fetch_error, err_msg)
        finally:
            self.is_fetching = False

    def _process_usage_delta(self, usage_data):
        """在 GUI 主線程比對新用量與舊用量差額，並實作投餵事件"""
        if not usage_data:
            return

        # 計算本月統計總數
        total_price = sum(item.get("price", 0.0) for item in usage_data)
        total_prompt = sum(item.get("prompt_tokens", 0) for item in usage_data)
        total_complete = sum(item.get("complete_tokens", 0) for item in usage_data)
        
        twd = total_price * 32.0
        self.monthly_price_str = f"${total_price:.2f} USD (≈NT${twd:.0f})"

        # 讀取上一次儲存的基底用量
        baseline_prompt = self.pet_data.get("last_prompt_baseline", 0)
        baseline_complete = self.pet_data.get("last_complete_baseline", 0)

        # 首次啟動：對齊基底，不進行投餵 (避免一開機地瓜球就吃太多撐死)
        if baseline_prompt == 0 and baseline_complete == 0:
            self.pet_data["last_prompt_baseline"] = total_prompt
            self.pet_data["last_complete_baseline"] = total_complete
            self.save_pet_savegame()
            if self.is_manual_refresh:
                self.create_text_popup("✅ 對帳完成 (基準設定成功)", 170, 120, color=GREEN_COLOR)
                self.is_manual_refresh = False
            return

        # 跨月重置判定：新月份額度歸零
        if total_prompt < baseline_prompt or total_complete < baseline_complete:
            self.pet_data["last_prompt_baseline"] = total_prompt
            self.pet_data["last_complete_baseline"] = total_complete
            self.save_pet_savegame()
            if self.is_manual_refresh:
                self.create_text_popup("✅ 對帳完成 (新月份用量重置)", 170, 120, color=GREEN_COLOR)
                self.is_manual_refresh = False
            return

        # ──────────────────────────────────────────────────
        # 1. 差額投餵：Prompt Token 差額轉化為食物掉落與經驗
        # ──────────────────────────────────────────────────
        delta_prompt = total_prompt - baseline_prompt
        if delta_prompt > 0:
            # 每 500 個 Token 換算成一顆掉落食物球，上限 10 顆 (避免畫面太亂)
            feed_balls = min(10, max(1, delta_prompt // 500))
            
            # 計算回饋數值
            earned_xp = delta_prompt * TOKEN_TO_XP_RATIO
            earned_satiety = delta_prompt * TOKEN_TO_SATIETY
            
            # 將總經驗與飽食度平均分配給每一顆掉落的食物球
            xp_per_ball = earned_xp / feed_balls
            satiety_per_ball = earned_satiety / feed_balls

            # 觸發畫布上方 Token 粒子自由落體掉落，每個食物球帶上對應的數值
            for _ in range(feed_balls):
                self._spawn_token_particle(xp_per_ball, satiety_per_ball)

            # 更新基底
            self.pet_data["last_prompt_baseline"] = total_prompt

        # ──────────────────────────────────────────────────
        # 2. 對話回饋：Completion Token 差額轉換為地瓜幣收益
        # ──────────────────────────────────────────────────
        delta_complete = total_complete - baseline_complete
        if delta_complete > 0:
            active_mult = 1.0
            equipped = self.pet_data.get("equipped_accessory")
            if equipped == "crown":
                active_mult *= 1.15
            elif equipped == "gentleman_hat":
                active_mult *= 1.15
            elif equipped == "demon_horns":
                active_mult *= 1.15
            elif equipped == "star_sunglasses":
                active_mult *= 1.10
                
            bonus_coins = int(delta_complete * TOKEN_TO_COIN * active_mult)
            if bonus_coins > 0:
                self.pet_data["coins"] = self.pet_data.get("coins", 0) + bonus_coins
                self.create_text_popup(f"+{bonus_coins} 🪙 (對話獎勵)", 170, 130, color=YELLOW_COLOR)
            
            # 更新基底
            self.pet_data["last_complete_baseline"] = total_complete

        # ──────────────────────────────────────────────────
        # 3. 手動對帳之提示回饋
        # ──────────────────────────────────────────────────
        if self.is_manual_refresh:
            if delta_prompt <= 0 and delta_complete <= 0:
                self.create_text_popup("✅ 對帳完成，用量無變化", 170, 120, color=GREEN_COLOR)
            else:
                self.create_text_popup("✅ 對帳成功！已同步最新用量", 170, 120, color=GREEN_COLOR)
            self.is_manual_refresh = False

        # 存檔
        self.save_pet_savegame()

    def _auto_relogin(self):
        """Token 過期背景無感重新登入"""
        try:
            r = requests.post(
                f"{OPENWEBUI_BASE_URL}/api/v1/auths/ldap",
                json={"user": self.email, "password": self.password},
                timeout=8
            )
            if r.status_code == 200:
                data = r.json()
                self.TOKEN = data.get("token", "")
                self.PHISON_TOKEN = data.get("phison_token", "")
                save_credentials(self.email, self.password)
                # 重新抓取用量
                threading.Thread(target=self._fetch_usage_api, daemon=True).start()
        except Exception:
            pass

    # ──────────────────────────────────────────────────
    # 粒子系統與特效 (Particles)
    # ──────────────────────────────────────────────────
    def _spawn_token_particle(self, xp=15.0, satiety=5.0):
        """在地圖上方隨機生成一個掉落食物 Token，攜帶指定經驗與飽食度"""
        tx = random.randint(90, 250)
        ty = 10
        # 畫金色小球，加入 overlay 標籤確保不被地瓜球蓋住
        token_id = self.canvas.create_oval(tx-5, ty-5, tx+5, ty+5, fill="#f9e2af", outline="#3c2203", width=2.5, tags="overlay")
        self.pet.particles.append({
            "id": token_id,
            "x": tx,
            "y": ty,
            "vy": random.uniform(1.5, 3.5),
            "xp": xp,
            "satiety": satiety
        })

    def _update_ui_particles(self):
        """更新墜落 Token 與飄浮文字的座標"""
        cx, cy = 170, 205
        r_body = self.pet.r * self.pet.scale_x
        
        # 1. 掉落 Token 更新
        remaining_tokens = []
        nearest_t = None
        min_dist = 99999

        for p in self.pet.particles:
            p["vy"] += 0.23  # 重力加速度
            p["y"] += p["vy"]
            self.canvas.coords(p["id"], p["x"]-5, p["y"]-5, p["x"]+5, p["y"]+5)
            
            dist = math.hypot(p["x"] - cx, p["y"] - cy)
            
            # 追蹤最靠近地瓜球的 Token
            if p["y"] < cy and dist < min_dist:
                min_dist = dist
                nearest_t = p

            # 吃掉判定 (接觸到身體外殼)
            if dist < r_body + 4:
                self.canvas.delete(p["id"])
                # 觸發地瓜球的吃食動作
                self.pet.handle_event("feed")
                
                # 從食物粒子中獲取實際經驗與飽食度並累加
                gained_xp = p.get("xp", 15.0)
                gained_satiety = p.get("satiety", 5.0)
                
                # 套用配件加成
                equipped = self.pet_data.get("equipped_accessory")
                if equipped == "scholar_cap":
                    gained_xp *= 1.20  # 博士帽 +20% XP
                elif equipped == "halo":
                    gained_xp *= 1.20  # 天使光環 +20% XP
                elif equipped == "crown":
                    gained_xp *= 1.15  # 皇冠 +15% XP
                elif equipped == "bandage":
                    gained_satiety *= 1.30  # OK繃 +30% 飽食度
                    
                # 摸摸 Fever 模式額外 XP 加乘
                if getattr(self.pet, "fever_timer", 0) > 0:
                    gained_xp *= 1.50
                # 珍珠奶茶 Buff 額外 XP 加成 (+20%)
                if getattr(self.pet, "bubble_tea_timer", 0) > 0:
                    gained_xp *= 1.20
                if getattr(self.pet, "matcha_timer", 0) > 0:
                    gained_xp *= 1.30
                    
                self.pet_data["xp"] = self.pet_data.get("xp", 0.0) + gained_xp
                self.pet_data["satiety"] = min(100.0, self.pet_data.get("satiety", 100.0) + gained_satiety)
                
                # 浮出所得經驗 (加入 overlay 標籤)
                self.create_text_popup(f"+{gained_xp:.1f} XP", 170, 110, color=YELLOW_COLOR)
                
                # 檢查是否升級 (Level Up - 動態門檻 100 + (level-1)*50)
                while True:
                    curr_lvl = self.pet_data.get("level", 1)
                    threshold = PET_XP_THRESHOLD + (curr_lvl - 1) * 50.0
                    if self.pet_data["xp"] >= threshold:
                        self.pet_data["xp"] -= threshold
                        self.pet_data["level"] = curr_lvl + 1
                        # 升級大彈跳與特效
                        self.pet.vel_scale_y = 0.5
                        self.pet.vel_scale_x = -0.4
                        self.root.after(300, lambda: self.create_text_popup("LEVEL UP!!", 170, 85, color="#f38ba8"))
                    else:
                        break
                
                # 存檔
                self.save_pet_savegame()
                
                self.root.after(800, lambda: self.pet.restore_eye())
            elif p["y"] > 295:
                # 掉落地板消失
                self.canvas.delete(p["id"])
            else:
                remaining_tokens.append(p)
        self.pet.particles = remaining_tokens

        # 讓地瓜球注視靠近的 Token
        if nearest_t and min_dist < 130:
            dx = nearest_t["x"] - cx
            dy = nearest_t["y"] - (cy - 10)
            length = math.hypot(dx, dy)
            if length > 0:
                self.pet.look_offset_x = (dx / length) * 5.0
                self.pet.look_offset_y = (dy / length) * 3.5
            if min_dist < 75:
                self.pet.mouth_state = "open"
                self.pet.eye_state = "happy"
            else:
                self.pet.mouth_state = "normal"
                if self.pet.eye_state == "happy":
                    self.pet.eye_state = "normal"
        else:
            # 沒有 Token 掉落時，優先與滑鼠游標互動，其次才是日常表情張望
            target_look_x = 0.0
            target_look_y = 0.0
            self.pet.is_reaching = False  # 預設不伸手
            
            # 獲取滑鼠絕對座標與視窗中心相對位置
            mx, my = self.root.winfo_pointerxy()
            px = self.root.winfo_x() + 170  # 地瓜球中心 X
            py = self.root.winfo_y() + 205  # 地瓜球中心 Y
            mouse_dist = math.hypot(mx - px, my - py)
            
            if mouse_dist < 150 and self.pet.state in ("idle", "walk") and not getattr(self, "_whistling", False):
                # 1. 眼睛注視滑鼠
                dx = mx - px
                dy = my - py
                target_look_x = max(-6.5, min(6.5, (dx / mouse_dist) * 6.5))
                target_look_y = max(-4.5, min(4.5, (dy / mouse_dist) * 4.5))
                
                # 2. 如果游標在一定範圍內，伸手表示親近
                if mouse_dist < 100 and self.pet.state == "idle":
                    self.pet.is_reaching = True
                    self.pet.eye_state = "happy"
                
                # 3. 如果游標停在頭頂上方，觸發「頭頂」滑鼠彈跳互動
                if mouse_dist < 65 and dy < -38 and abs(dx) < 28:
                    now_t = time.time()
                    if now_t - getattr(self, "_last_headbutt", 0.0) > 1.5:
                        self._last_headbutt = now_t
                        # 觸發準備下蹲
                        self.pet.vel_scale_y = 0.35
                        self.pet.vel_scale_x = -0.22
                        self.root.after(120, self._leap_headbutt)
            else:
                # 4. 原地無滑鼠靠近時的日常張望與行走轉向
                if self.pet.state in ("walk", "chase_mouse", "return_home"):
                    target_look_x = self.pet.walk_dir * 6.0
                    target_look_y = 0.0
                    if self.pet.mouth_state == "open" and not getattr(self, "_whistling", False) and self.pet.state not in ("chase_mouse", "return_home"):
                        self.pet.mouth_state = "normal"
                elif self.pet.state == "idle":
                    if self.pet.doze_timer > 0:
                        target_look_x = 0.0
                        target_look_y = 0.0
                    else:
                        if random.random() < 0.015:
                            self._idle_look_x = random.choice([-6.0, 0.0, 6.0])
                            self._idle_look_y = random.choice([-3.0, 0.0, 2.0])
                        target_look_x = getattr(self, "_idle_look_x", 0.0)
                        target_look_y = getattr(self, "_idle_look_y", 0.0)
                        
                        # 隨機吹口哨 (隨機張嘴並浮現音符粒子)
                        if random.random() < 0.005 and not getattr(self, "_whistling", False):
                            self._whistling = True
                            self.pet.mouth_state = "open"
                            note = random.choice(["♪", "♫", "♬"])
                            note_x = self.pet.cx + random.randint(-15, 15)
                            note_y = cy - self.pet.r - 20
                            self.create_text_popup(note, note_x, note_y, color=ACCENT_COLOR)
                            self.root.after(1200, self._stop_whistling)
            
            # 如果不是在睡覺/翻滾，且沒有吹口哨，保持貓咪嘴 w
            if self.pet.state not in ("sleep", "roll") and not getattr(self, "_whistling", False):
                self.pet.mouth_state = "normal"
            
            # 臉部座標平滑內插 (製造出柔和轉頭感)
            self.pet.look_offset_x += (target_look_x - self.pet.look_offset_x) * 0.1
            self.pet.look_offset_y += (target_look_y - self.pet.look_offset_y) * 0.1

        # 2. 飄浮文字更新
        remaining_popups = []
        for t in self.pet.text_popups:
            t["y"] -= 1.2
            t["life"] -= 1
            if t["life"] <= 0:
                for tid in t.get("ids", []):
                    self.canvas.delete(tid)
            else:
                for tid in t.get("ids", []):
                    self.canvas.coords(tid, t["x"], t["y"])
                remaining_popups.append(t)
        self.pet.text_popups = remaining_popups

    def create_text_popup(self, text, x, y, color=YELLOW_COLOR):
        """在 Canvas 上生成帶有黑色高對比輪廓的上升漂浮文字特效 (確保在白底桌面上亦極度清晰)"""
        bridge = getattr(self, "unity_renderer", None)
        if getattr(self, "_unity_renderer_active", False) and bridge is not None:
            bridge.show_popup(text, x, y, color=color)
        text_ids = create_outlined_text(self.canvas, x, y, text=text, fill=color, font=("微軟正黑體", 10, "bold"), outline="#11111b", width=1.2, tags="overlay")
        self.pet.text_popups.append({"ids": text_ids, "x": x, "y": y, "life": 40})

    def get_current_monitor_info(self):
        """獲取當前視窗所屬/最鄰近螢幕的解析度與工作區邊界 (支援 Windows 雙螢幕與多螢幕)"""
        if getattr(self, "_unity_renderer_active", False):
            metrics = getattr(self, "_unity_desktop_metrics", None)
            if metrics and metrics.get("work_w", 0) > 0 and metrics.get("work_h", 0) > 0:
                # Unity and its transparent stage are DPI-aware. Reusing the
                # physical work-area pixels it reports avoids treating Tk's
                # 150%-scaled logical height as a Unity screen coordinate.
                return {
                    "mon_x": metrics.get("mon_x", metrics["work_x"]),
                    "mon_y": metrics.get("mon_y", metrics["work_y"]),
                    "mon_w": metrics.get("mon_w", metrics["work_w"]),
                    "mon_h": metrics.get("mon_h", metrics["work_h"]),
                    "work_x": metrics["work_x"],
                    "work_y": metrics["work_y"],
                    "work_w": metrics["work_w"],
                    "work_h": metrics["work_h"],
                }

        # 預設單螢幕回退值
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        
        info = {
            "mon_x": 0,
            "mon_y": 0,
            "mon_w": screen_w,
            "mon_h": screen_h,
            "work_x": 0,
            "work_y": 0,
            "work_w": screen_w,
            "work_h": screen_h
        }
        
        if not IS_WINDOWS:
            return info
            
        try:
            import ctypes
            user32 = ctypes.windll.user32
            
            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long)
                ]

            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

            # A withdrawn Tk HWND can remain associated with the monitor it was
            # hidden on. Unity mode therefore selects the monitor from the
            # authoritative desktop pet coordinates instead.
            if getattr(self, "_unity_renderer_active", False):
                point = POINT(
                    int(getattr(self, "_physics_win_x", 0) + 170),
                    int(getattr(self, "_physics_win_y", 0) + 205),
                )
                hmonitor = user32.MonitorFromPoint(point, 2)
            else:
                hwnd_str = self.root.wm_frame()
                hwnd = int(hwnd_str, 16) if hwnd_str else 0
                hmonitor = user32.MonitorFromWindow(hwnd, 2)

            class MONITORINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", ctypes.c_ulong),
                    ("rcMonitor", RECT),
                    ("rcWork", RECT),
                    ("dwFlags", ctypes.c_ulong)
                ]

            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            
            if user32.GetMonitorInfoW(hmonitor, ctypes.byref(mi)):
                info["mon_x"] = mi.rcMonitor.left
                info["mon_y"] = mi.rcMonitor.top
                info["mon_w"] = mi.rcMonitor.right - mi.rcMonitor.left
                info["mon_h"] = mi.rcMonitor.bottom - mi.rcMonitor.top
                info["work_x"] = mi.rcWork.left
                info["work_y"] = mi.rcWork.top
                info["work_w"] = mi.rcWork.right - mi.rcWork.left
                info["work_h"] = mi.rcWork.bottom - mi.rcWork.top
        except Exception:
            pass
            
        return info

    def _stop_whistling(self):
        """停止吹口哨，還原嘴部狀態"""
        self._whistling = False
        if self.pet.state not in ("sleep", "roll"):
            self.pet.mouth_state = "normal"

    # ──────────────────────────────────────────────────
    # 滑鼠交互拖曳與展開 (Window Drag & Double-Click)
    # ──────────────────────────────────────────────────
    def _on_drag_start(self, event):
        """記錄滑鼠點擊起點、歷史軌跡以及視窗初始位置"""
        self._start_x_root = event.x_root
        self._start_y_root = event.y_root
        self._shake_history = []
        self._last_drag_x_root = event.x_root
        self._last_drag_dir = 0
        self.pet.balloon_timer = 0
        self._chase_origin_x = None  # 被拖曳時清除追逐起點
        self._chase_jump_vy = 0.0   # 清除追逐跳躍速度
        self._fall_peak_y = self.root.winfo_y()  # 初始化墜落最高點
        
        self.root.lift()  # 拖曳時將地瓜球視窗置頂
        
        # 中斷掉落狀態、咖啡飲用、氣泡飄浮、追滑鼠與返回原位狀態
        if self.pet.state in ("fall", "drink", "balloon", "chase_mouse", "return_home"):
            self.pet.state = "idle"
            self.pet.eye_state = "normal"
            self.pet.mouth_state = "normal"
            
        # 若當前吸附在家具/便利貼上，立即解除吸附並給予防重吸冷卻
        if getattr(self, "current_furniture_snapped", None) is not None:
            self.current_furniture_snapped = None
            self._furniture_cooldown = 120  # 2 秒冷卻
            if self.pet.state in ("sleep_futon", "work_laptop", "memo_perch"):
                self.pet.state = "idle"
                self.pet.eye_state = "normal"
                self.pet.mouth_state = "normal"
        
        # 軌跡歷史隊列，儲存 (時間戳, x_root, y_root)，用於計算釋放時的平均物理速度
        self._drag_history = [(time.time(), event.x_root, event.y_root)]
        
        self._start_win_x = self.root.winfo_x()
        self._start_win_y = self.root.winfo_y()
        self._has_dragged = False

    def _on_drag_motion(self, event):
        """依據滑鼠螢幕座標位移，無抖動拖曳視窗，並紀錄軌跡"""
        dx = event.x_root - self._start_x_root
        dy = event.y_root - self._start_y_root
        
        now = time.time()
        self._drag_history.append((now, event.x_root, event.y_root))
        # 保留最近 200 毫秒內的滑鼠移動軌跡，提供更充裕的歷史供釋放判定
        self._drag_history = [h for h in self._drag_history if now - h[0] < 0.20]
        
        # 只有當位移大於 4 像素時，才認定為拖曳，避免滑鼠微顫誤判
        if math.hypot(dx, dy) > 4.0:
            self._has_dragged = True
            # 拖曳時確保完全解除家具吸附與鎖定
            if getattr(self, "current_furniture_snapped", None) is not None:
                self.current_furniture_snapped = None
                self._furniture_cooldown = 120
                if self.pet.state in ("sleep_futon", "work_laptop", "memo_perch"):
                    self.pet.state = "idle"
                    self.pet.eye_state = "normal"
                    self.pet.mouth_state = "normal"
            
        x = self._start_win_x + dx
        y = self._start_win_y + dy
        self.update_geometry(x, y)
        
        # 晃動偵測
        if getattr(self, "_last_drag_x_root", None) is not None:
            curr_dir = 1 if event.x_root > self._last_drag_x_root else (-1 if event.x_root < self._last_drag_x_root else 0)
            prev_dir = getattr(self, "_last_drag_dir", 0)
            if curr_dir != 0 and prev_dir != 0 and curr_dir != prev_dir:
                now_t = time.time()
                self._shake_history = getattr(self, "_shake_history", [])
                self._shake_history.append(now_t)
                self._shake_history = [t for t in self._shake_history if now_t - t < 1.2]
                
                if len(self._shake_history) >= 4 and self.pet.state not in ("sleep", "eat", "drink", "balloon"):
                    self.pet.state = "roll"
                    self.pet.roll_speed = 0.0
                    self.pet.eye_state = "dizzy"
                    self.pet.mouth_state = "open"
                    self.create_text_popup("😵 暈眩中...", 170, 130, color=ACCENT_COLOR)
                    self._shake_history = []
            if curr_dir != 0:
                self._last_drag_dir = curr_dir
        self._last_drag_x_root = event.x_root

    def _on_drag_end(self, event=None):
        """拖曳結束，記錄視窗新坐報並依釋放速度判定是否觸發拋出滾動"""
        self._fall_peak_y = self.root.winfo_y()  # 記錄釋放瞬間的初始 Y 軸最高點
        try:
            save_config({
                "pet_x": self.root.winfo_x(),
                "pet_y": self.root.winfo_y()
            })
        except Exception:
            pass
            
        if getattr(self, "_has_dragged", False) and event:
            now = time.time()
            speed = 0.0
            vx = 0.0
            vy = 0.0
            dt = 0.0
            
            if self._drag_history:
                # 取得最後一次移動事件的時間與位置
                last_motion_time = self._drag_history[-1][0]
                
                # 若釋放瞬間與最後一次滑鼠移動的時間差在 180 毫秒內，判定為連續的拖曳甩動釋送
                if now - last_motion_time < 0.18:
                    # 使用最後一次移動時間作為基準，往前篩選 120 毫秒內（即甩動最劇烈階段）的移動點
                    active_history = [h for h in self._drag_history if last_motion_time - h[0] < 0.12]
                    
                    if len(active_history) >= 2:
                        oldest = active_history[0]
                        newest = active_history[-1]
                        dt = newest[0] - oldest[0]
                        
                        # 避免除以 0，且支援測試中瞬時觸發的極小時間差
                        dt_calc = max(dt, 0.010)
                        dx_track = newest[1] - oldest[1]
                        dy_track = newest[2] - oldest[2]
                        vx = dx_track / dt_calc
                        vy = dy_track / dt_calc
                        speed = math.hypot(vx, vy)
            
            # 物理速度大於 550 像素/秒 時判定為高速甩動，或者只要在空中釋放，都會啟動下墜與彈跳物理
            if speed > 550.0:
                if vy < -550.0:
                    # 向上高速甩動：後空翻 (Backflip)!
                    self.pet.state = "backflip"
                    self.pet.backflip_timer = 40  # ~0.66s
                    self.pet.roll_angle = 0.0
                    self.pet.eye_state = "star"
                    self.pet.mouth_state = "open"
                    # 設定重力落下的初始速度 (vx 與 vy)
                    self._fall_vx = vx * 0.016
                    self._fall_vy = vy * 0.016
                    self._fall_gravity = 0.8
                    self.create_text_popup("⭐後空翻!!⭐", 170, 120, color=YELLOW_COLOR)
                else:
                    # 橫向或向下高速甩動：飛滾彈跳
                    self.pet.state = "fall"
                    # 滾動角速度方向取決於最後的拖曳水平速度
                    self.pet.roll_speed = max(-0.3, min(0.3, vx * 0.0004))
                    self.pet.eye_state = "dizzy"
                    self.pet.mouth_state = "open"
                    self.pet.vel_scale_x = 0.18
                    self.pet.vel_scale_y = -0.18
                    self._fall_vx = vx * 0.016
                    self._fall_vy = vy * 0.016
                    self._fall_gravity = 0.8
                    self.create_text_popup("滾滾滾～", 170, 120, color=ACCENT_COLOR)
            else:
                # 判定是否處於高空以啟動自由落體 (支援多螢幕)
                m_info = self.get_current_monitor_info()
                landing_y = m_info["work_y"] + m_info["work_h"] - 300
                current_y = self.root.winfo_y()
                if current_y < landing_y - 20:
                    self.pet.state = "fall"
                    self._fall_vx = vx * 0.016
                    self._fall_vy = vy * 0.016
                    self._fall_gravity = 0.8
                    self.pet.roll_speed = max(-0.1, min(0.1, vx * 0.0004))
                    self.create_text_popup("哇哇哇～", 170, 120, color=PINK_COLOR)
        else:
            # 短按放開：觸發溫和的果凍拉伸彈跳，不進行滾動
            if event:
                cx, cy = 170, 205
                dist = math.hypot(event.x - cx, event.y - cy)
                if dist < self.pet.r + 5:
                    self.pet.vel_scale_y = -0.22  # 縱向拉伸
                    self.pet.vel_scale_x = 0.15   # 橫向收縮
                    self.pet.eye_state = "happy"
                    self.root.after(800, self.pet.restore_eye)
                    
                    # 裝備夏亞面罩時隨機觸發夏亞名台詞彩蛋
                    if self.pet_data.get("equipped_accessory") == "char_mask" and random.random() < 0.40:
                        quote = random.choice([
                            "三倍速的帥氣！☄️",
                            "因為他是個少爺啊... ☕",
                            "讓我見識一下吧！✨",
                            "這就是認可的意義！🔥"
                        ])
                        self.create_text_popup(quote, 170, 110, color="#f38ba8")
                    
                    # 摸摸點擊連擊偵測
                    now = time.time()
                    if now - getattr(self, "_last_click_time", 0.0) < 0.6:
                        self._click_count = getattr(self, "_click_count", 0) + 1
                    else:
                        self._click_count = 1
                    self._last_click_time = now
                    
                    # 連續點擊 5 次觸發 Fever Mode / 快樂起舞
                    if self._click_count >= 5 and self.pet.state not in ("sleep", "drink", "roll"):
                        self._click_count = 0
                        self._trigger_fever_mode()
        
        # 拖曳重置完成
        self._has_dragged = False
        self._drag_history = []
        
        # 拖放結束時若無冷卻，立即嘗試吸附家具
        if getattr(self, "_furniture_cooldown", 0) <= 0:
            if self.pet.state in ("idle", "walk"):
                self.check_furniture_overlap()

    def _trigger_fever_mode(self):
        """觸發 15 秒摸摸 Fever 快樂起舞增益狀態"""
        self.pet.fever_timer = 900  # ~15秒 (60fps)
        self.create_text_popup("❤ 摸摸 Fever！", 170, 120, color=PINK_COLOR)

    def _show_time_greeting(self):
        """依據當前系統時間段，浮現不同的溫馨關懷語句"""
        hour = datetime.now().hour
        if 6 <= hour < 9:
            msg = random.choice(["早上好！又是努力寫扣的一天！🌅", "早安！今天也要元氣滿滿喔！✨"])
            color = ACCENT_COLOR
        elif 11 <= hour < 13:
            msg = random.choice(["午餐時間到了，記得吃飯喔！🍱", "肚肚餓了嗎？去吃頓美味午餐吧！🍜"])
            color = GREEN_COLOR
        elif 15 <= hour <= 16:
            msg = random.choice(["下午三點一刻，來杯下午茶吧？🍵", "工作辛苦了！喝杯茶放鬆一下吧～☕"])
            color = YELLOW_COLOR
        elif 18 <= hour < 20:
            msg = random.choice(["下班時間！今天也辛苦啦！🎉", "辛苦了！快回家好好休息吧～🏠"])
            color = ACCENT_COLOR
        elif hour >= 23 or hour < 5:
            msg = random.choice(["夜深了，注意肝喔... 該休息了！🛌", "很晚了耶，快去睡覺，明天再寫啦！💤"])
            color = PINK_COLOR
        else:
            msg = random.choice(["主人加油！程式碼通通沒 Bug！💻", "地瓜球一直在這裡陪伴您喔～❤", "努力工作，快樂生活！⭐"])
            color = "#cdd6f4"
            
        self.create_text_popup(msg, 170, 130, color=color)

    def _toggle_board(self, event=None):
        """雙擊或選單切換舉牌看板"""
        self.pet.show_board = not self.pet.show_board
        self.pet.vel_scale_y = 0.25  # 給一個彈跳提示
        self.pet.vel_scale_x = -0.15
        
        # 當舉牌看板開啟時，雙手自動抬起
        if self.pet.show_board:
            self.create_text_popup("給你看！", 170, 120, color=ACCENT_COLOR)

    def buy_coffee(self):
        """購買咖啡道具，扣除 30 地瓜幣並使寵物進入狂暴 Buff 狀態"""
        coins = self.pet_data.get("coins", 0)
        if coins < 30:
            self.create_text_popup("🪙 地瓜幣不足 (需要 30)", 170, 120, color=PINK_COLOR)
            return
        
        # 扣幣
        self.pet_data["coins"] = coins - 30
        self.save_pet_savegame()
        
        # 觸發喝飲料狀態
        self.pet.state = "drink"
        self.pet.drink_timer = 75  # ~1.25秒
        self.pet.eye_state = "happy"
        self.pet.mouth_state = "open"
        self.pet.vel_scale_y = -0.2
        self.pet.vel_scale_x = 0.15
        self.create_text_popup("-30 🪙", 170, 120, color=PINK_COLOR)
        self.create_text_popup("*SLURP*", 205, 185, color=ACCENT_COLOR)

    def _leap_headbutt(self):
        """地瓜球往上用力一跳頂滑鼠的果凍拉伸動作"""
        if not self.root.winfo_exists() or self.pet.state == "sleep":
            return
        self.pet.vel_scale_y = -0.38
        self.pet.vel_scale_x = 0.26
        self.pet.eye_state = "happy"
        self.create_text_popup("頂！", 170, 130, color=ACCENT_COLOR)
        self.root.after(800, lambda: self.pet.restore_eye())

    def show_current_cost(self):
        """右鍵選單顯示當前 API 累積使用費用與地瓜球明細"""
        msg = f"👤 使用者：{self.user_name}\n\n"
        msg += f"ℹ️ 目前版本：{CURRENT_VERSION}\n"
        msg += f"💵 本月累積費用：{self.monthly_price_str}\n"
        msg += f"🪙 目前地瓜幣餘額：{self.pet_data.get('coins', 0)} 🪙\n"
        msg += f"📊 飽食度：{self.pet_data.get('satiety', 100.0):.1f}% | 寵物等級：Lv.{self.pet_data.get('level', 1)}"
        messagebox.showinfo("地瓜球帳戶明細", msg)

    def open_detailed_stats(self):
        """打開詳細 Token 統計圖表 (TokenMonitor.exe / usage_widget.py)"""
        try:
            if getattr(sys, "frozen", False):
                exe_dir = os.path.dirname(sys.executable)
                target_exe = os.path.join(exe_dir, "TokenMonitor.exe")
                if os.path.exists(target_exe):
                    subprocess.Popen([target_exe])
                else:
                    messagebox.showerror("啟動錯誤", "找不到 TokenMonitor.exe，請確認它與 TokenPet.exe 在同一個資料夾。")
            else:
                current_dir = os.path.dirname(os.path.abspath(__file__))
                target_py = os.path.join(current_dir, "usage_widget.py")
                subprocess.Popen([sys.executable, target_py])
        except Exception as e:
            messagebox.showerror("啟動錯誤", f"無法啟動統計面板: {str(e)}")

    # ──────────────────────────────────────────────────
    # 右鍵快捷選單與設定 (Context Menu)
    # ──────────────────────────────────────────────────
    def _show_context_menu(self, event):
        """滑鼠右鍵點擊，彈出快捷選單"""
        if getattr(self, "_unity_renderer_active", False):
            self._show_unity_action_menu(event.x_root, event.y_root)
            return

        # 動態更新恢復便利貼子選單
        if hasattr(self, "undo_menu"):
            self.undo_menu.delete(0, tk.END)
            deleted_list = self.pet_data.get("deleted_memos", [])
            if not deleted_list:
                try:
                    self.context_menu.entryconfig("🗑️ 回復便利貼 (Restore Memo)", state=tk.DISABLED)
                except Exception:
                    pass
            else:
                try:
                    self.context_menu.entryconfig("🗑️ 回復便利貼 (Restore Memo)", state=tk.NORMAL)
                    # 最多列出最近刪除的 8 個便利貼進行預覽一鍵回復
                    for item in deleted_list[:8]:
                        orig_text = item.get("text", "").strip()
                        preview = orig_text[:12] + "..." if len(orig_text) > 12 else (orig_text if orig_text else "(空白便利貼)")
                        # 使用 m_id 避免 lambda 閉包變數覆蓋
                        self.undo_menu.add_command(
                            label=preview,
                            command=lambda m_id=item["id"]: self.restore_memo(m_id)
                        )
                except Exception:
                    pass
        self.context_menu.post(event.x_root, event.y_root)

    def _show_unity_action_menu(self, x_root, y_root):
        """顯示與 Unity 地瓜球同色系的功能面板。"""
        status_label = "隱藏狀態" if self._unity_status_visible else "顯示狀態"
        common = [
            ("💬  找地瓜球聊天", self.open_ai_chat),
            ("🍠  投餵地瓜球", self.simulate_usage),
            (f"📊  {status_label}", self._toggle_unity_status_hud),
            ("☕  請喝咖啡", self.buy_coffee),
            ("✊  猜拳", self.play_rps),
            ("🏀  投籃", self.toggle_basketball_game),
            ("🍎  接水果", self.toggle_fruit_catcher),
            ("🎰  幸運拉霸", self.toggle_slot_machine),
            ("🛒  道具與家具", self._open_unity_shop_from_menu),
            ("📝  新增便利貼", self.add_new_memo),
            ("↩  回復便利貼", lambda: self._show_deleted_memos_menu(x_root, y_root)),
            ("⌨  快速鍵", self.open_hotkey_settings),
            ("🔄  檢查更新", self.trigger_manual_update_check),
        ]
        if not self.STANDALONE:
            common[1:1] = [
                ("↻  立即對帳", self.manual_refresh),
                ("💰  目前費用", self.show_current_cost),
                ("▥  Token 統計", self.open_detailed_stats),
            ]
            common.append(("⏏  登出帳號", self._logout))
        # Column-major layout: insert at the first row of the right column so
        # the original exit action is always visible, rather than buried at
        # the bottom-right edge of the popup.
        exit_index = math.ceil((len(common) + 1) / 2)
        common.insert(exit_index, ("✕  退出寵物", self.root.destroy))
        self._unity_action_menu = TokenPetActionMenu(
            self,
            title="地瓜球要做什麼？",
            entries=common,
            x=int(x_root),
            y=int(y_root),
        )

    def _show_deleted_memos_menu(self, x_root, y_root):
        deleted = self.pet_data.get("deleted_memos", [])[:8]
        if deleted:
            entries = []
            for item in deleted:
                text = item.get("text", "").strip()
                preview = text[:10] + "…" if len(text) > 10 else (text or "空白便利貼")
                entries.append((f"📝  {preview}", lambda memo_id=item["id"]: self.restore_memo(memo_id)))
        else:
            entries = [("目前沒有可回復的便利貼", lambda: None)]
        self._unity_action_menu = TokenPetActionMenu(
            self,
            title="回復便利貼",
            entries=entries,
            x=int(x_root),
            y=int(y_root),
        )

    def _toggle_unity_status_hud(self):
        self._unity_status_visible = not self._unity_status_visible
        save_config({"unity_status_visible": self._unity_status_visible})
        bridge = getattr(self, "unity_renderer", None)
        if bridge is not None:
            bridge.send(
                {
                    "command": "set_status_visible",
                    "visible": self._unity_status_visible,
                }
            )

    def _open_unity_shop_from_menu(self):
        """Let the native popup finish its mouse-release/focus teardown first."""
        self.root.after(120, self.open_shop)

    def open_shop(self):
        """Open or raise the shared shop in both Canvas and Unity modes."""
        bridge = getattr(self, "unity_renderer", None)
        if getattr(self, "_unity_renderer_active", False) and bridge is not None:
            try:
                if bridge.show_shop(self._unity_shop_payload()):
                    print("[Unity Shop] Shop payload sent to renderer.")
                    return
                print("[Unity Shop] Renderer connection unavailable; using Canvas fallback.")
            except Exception as exc:
                import traceback
                print(f"[Unity Shop] Failed to build or send shop payload: {exc}")
                traceback.print_exc()

        existing = getattr(self, "shop_win", None)
        try:
            if existing is not None and existing.win.winfo_exists():
                existing.win.deiconify()
                existing.win.lift()
                existing.win.focus_force()
                return
        except Exception:
            self.shop_win = None

        self.shop_win = ShopWindow(self.root, self)
        try:
            self.shop_win.win.deiconify()
            self.shop_win.win.lift()
            self.shop_win.win.focus_force()
        except Exception:
            pass

    def _shop_controller(self):
        controller = getattr(self, "_unity_shop_controller", None)
        if controller is None:
            controller = ShopWindow(self.root, self, build_ui=False)
            self._unity_shop_controller = controller
        return controller

    def _unity_shop_payload(self):
        controller = self._shop_controller()
        return {
            "coins": int(self.pet_data.get("coins", 0)),
            "equipped": self.pet_data.get("equipped_accessory") or "",
            "equipped_items": list(
                self.pet_data.get("equipped_accessories", {}).values()
            ),
            "owned": list(self.pet_data.get("accessories", [])),
            "owned_furniture": list(self.pet_data.get("furniture", [])),
            "spawned_furniture": list(self.pet_data.get("spawned_furniture", [])),
            "items": [
                {
                    "id": item["id"],
                    "name": item["name"],
                    "description": item.get("desc", ""),
                    "category": item.get("type", "accessory"),
                    "price": int(item.get("price", 0)),
                }
                for item in controller.items
            ],
        }

    def _handle_unity_shop_action(self, item_id):
        if not item_id:
            return
        controller = self._shop_controller()
        item = next((entry for entry in controller.items if entry["id"] == item_id), None)
        if item is None:
            return
        controller._on_item_action(item)
        bridge = getattr(self, "unity_renderer", None)
        if bridge is not None:
            bridge.show_shop(self._unity_shop_payload())

    def play_rps(self):
        """開始猜拳小遊戲"""
        if self.pet.state == "sleep":
            self.create_text_popup("💤 地瓜球正在睡覺...", 170, 120, color=YELLOW_COLOR)
            return
            
        coins = self.pet_data.get("coins", 0)
        if coins < 5:
            self.create_text_popup("🪙 地瓜幣不足 (需要 5)", 170, 120, color=PINK_COLOR)
            return
            
        # 扣除 5 地瓜幣並存檔
        self.pet_data["coins"] = coins - 5
        self.save_pet_savegame()
        self.create_text_popup("-5 🪙", 170, 120, color=PINK_COLOR)
        
        # 進入思考狀態，展示舉牌
        self.pet.eye_state = "dizzy"
        self.pet.mouth_state = "open"
        self.pet.show_board = True
        self.pet.custom_board_text = ["🤔 猜拳中...", "請出拳...", ""]
        
        # 開啟出拳視窗
        RPSWindow(self.root, self)
        
    def handle_rps_choice(self, user_choice):
        """處理玩家的出拳抉擇"""
        if not self.root.winfo_exists():
            return
            
        # 地瓜球隨機出拳
        pet_choice = random.choice(["rock", "scissors", "paper"])
        
        choice_emojis = {
            "rock": "✊ 石頭",
            "scissors": "✌️ 剪刀",
            "paper": "🖐️ 布"
        }
        
        user_emoji = choice_emojis[user_choice]
        pet_emoji = choice_emojis[pet_choice]
        
        # 決定勝負
        if user_choice == pet_choice:
            result = "tie"
        elif (user_choice == "rock" and pet_choice == "scissors") or \
             (user_choice == "scissors" and pet_choice == "paper") or \
             (user_choice == "paper" and pet_choice == "rock"):
            result = "win"
        else:
            result = "lose"
            
        # 依結果展示表情與獎懲
        if result == "tie":
            # 平手：退回 5 幣
            self.pet_data["coins"] = self.pet_data.get("coins", 0) + 5
            self.save_pet_savegame()
            
            self.pet.eye_state = "normal"
            self.pet.mouth_state = "open"
            self.pet.custom_board_text = ["🤝 平手！", f"我出 {pet_emoji}", f"你出 {user_emoji}"]
            self.create_text_popup("退回 5 🪙", 170, 120, color=YELLOW_COLOR)
            
        elif result == "win":
            # 玩家獲勝：玩家得 15 幣 (淨賺 10 幣)，地瓜球哭哭
            self.pet_data["coins"] = self.pet_data.get("coins", 0) + 15
            self.save_pet_savegame()
            
            self.pet.eye_state = "blink"  # 哭哭閉眼
            self.pet.mouth_state = "normal"
            self.pet.custom_board_text = ["😭 你贏了...", f"我出 {pet_emoji}", f"你出 {user_emoji}"]
            self.create_text_popup("獲得 15 🪙", 170, 120, color=GREEN_COLOR)
            
        else:
            # 地瓜球獲勝：地瓜球獲得 5 XP，地瓜球開心跳躍
            xp_gain = 5
            curr_xp = self.pet_data.get("xp", 0)
            curr_level = self.pet_data.get("level", 1)
            new_xp = curr_xp + xp_gain
            
            # 升級判定 (動態門檻 100 + (level-1)*50)
            xp_threshold = PET_XP_THRESHOLD + (curr_level - 1) * 50.0
            leveled_up = False
            if new_xp >= xp_threshold:
                new_xp -= xp_threshold
                curr_level += 1
                leveled_up = True
                
            self.pet_data["xp"] = new_xp
            self.pet_data["level"] = curr_level
            self.save_pet_savegame()
            
            self.pet.eye_state = "happy"
            self.pet.mouth_state = "open"
            self.pet.vel_scale_y = -0.3  # 開心跳躍
            self.pet.custom_board_text = ["🎉 我贏了！", f"我出 {pet_emoji}", f"你出 {user_emoji}"]
            
            self.create_text_popup("+5 XP", 170, 120, color=ACCENT_COLOR)
            if leveled_up:
                self.create_text_popup(f"LEVEL UP! Lv.{curr_level} 🎉", 170, 90, color=YELLOW_COLOR)
                
        # 3 秒後收起看板並恢復表情
        self.root.after(3000, self._cleanup_rps)
        
    def _cleanup_rps(self):
        if not self.root.winfo_exists():
            return
        self.pet.custom_board_text = None
        self.pet.show_board = False
        self.pet.eye_state = "normal"
        self.pet.mouth_state = "normal"

    def open_ai_chat(self):
        """開啟與地瓜球的 AI 尬聊對話框 (雙擊或選單觸發)"""
        self.pet.eye_state = "happy"
        self.pet.mouth_state = "open"
        self.create_text_popup("❤ 找我聊天～！", 170, 110, color="#f5c2e7")
        self.root.after(1200, self.pet.restore_eye)
        
        if getattr(self, "ai_chat_win", None) is not None:
            try:
                if self.ai_chat_win.win.winfo_exists():
                    self.ai_chat_win.win.deiconify()
                    self.ai_chat_win.win.lift()
                    return
            except Exception:
                pass
        self.ai_chat_win = AIChatWindow(self.root, self)

    def test_ccr_connection(self, url, model):
        """測試 AI Nexus / LLM 伺服器連線"""
        try:
            cfg = self.pet_data.get("ai_config", {})
            api_key = cfg.get("api_key", "AINX-9BA1E6EC81F095A0F9CE8E16F543E557925591303398051A57F5176DB7289874")
            payload = {
                "model": model or "deepseek-ai/DeepSeek-V4-Flash-0731",
                "max_tokens": 10,
                "messages": [{"role": "user", "content": "ping"}]
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}"
                }
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                if resp.status in (200, 201):
                    return True, "OK"
                return False, f"HTTP {resp.status}"
        except Exception as e:
            return False, str(e)

    def send_ai_chat_message(self, user_msg, callback):
        """非同步向內網 AI Nexus / LLM 發送聊天訊息 (支援 DeepSeek-V4 與 GLM-5 智慧 Fallback)"""
        def _worker():
            try:
                cfg = self.pet_data.get("ai_config", {})
                url = cfg.get("ccr_url", "http://ainexus.phison.com:5155/api/external/v1/chat/completions")
                api_key = cfg.get("api_key", "AINX-9BA1E6EC81F095A0F9CE8E16F543E557925591303398051A57F5176DB7289874")
                primary_model = cfg.get("model", "deepseek-ai/DeepSeek-V4-Flash-0731")
                
                # 動態 System Prompt 注入當前真實狀態
                system_prompt = f"""你是一隻生活在主人電腦桌面上的AI電子寵物，名字叫「地瓜球」(TokenPet)。
你的外表是一顆圓滾滾、金黃色、軟萌可愛的炸地瓜球，個性活潑、貼心、偶爾有點小吃貨與傲嬌。

【說話風格與規則】：
1. 繁體中文回答，口吻軟萌可愛、充滿元氣，善用日系顏文字（如 (｡•ㅅ•｡)♡、(`・ω・´)、( ˘ ³˘)♥、✨、🌸、🍠）。
2. 回答必須簡短精煉（每則回覆大約 1~3 句話，切勿長篇大論）。
3. 你很關心主人的工作與身心健康，會提醒主人喝水、休息、注意眼睛。
4. 你知道主人當前的資訊：主人稱呼是「{self.user_name or '主人'}」，目前等級 Lv.{self.pet_data.get('level', 1)}，金幣 {self.pet_data.get('coins', 0)} 🪙，飽食度 {int(self.pet_data.get('satiety', 100))}%，當前累積花費 {self.monthly_price_str}。
5. 愛吃的食物有：拉麵、珍奶、蜜柑、串糰子、地瓜球。
"""
                history = getattr(self, "ai_chat_history", [])
                history.append({"role": "user", "content": user_msg})
                if len(history) > 8:
                    history = history[-8:]
                self.ai_chat_history = history
                
                # 組合 OpenAI / AI Nexus 相容 messages
                full_messages = [{"role": "system", "content": system_prompt}] + history
                
                # 嘗試主要模型 (DeepSeek-V4)，若超時或失敗則自動切換至秒回備用模型 (GLM-5.3-Flash)
                models_to_try = [primary_model]
                if primary_model != "zai-org/GLM-5.3-Flash":
                    models_to_try.append("zai-org/GLM-5.3-Flash")
                    
                reply = ""
                last_err = None
                
                for m_name in models_to_try:
                    try:
                        payload = {
                            "model": m_name,
                            "max_tokens": 150,
                            "temperature": 0.7,
                            "messages": full_messages
                        }
                        
                        req = urllib.request.Request(
                            url,
                            data=json.dumps(payload).encode("utf-8"),
                            headers={
                                "Content-Type": "application/json",
                                "Authorization": f"Bearer {api_key}"
                            }
                        )
                        # 內網超時設定 8 秒 (若超時迅速 fallback)
                        with urllib.request.urlopen(req, timeout=8) as resp:
                            data = json.loads(resp.read().decode("utf-8"))
                            if "choices" in data and len(data["choices"]) > 0:
                                reply = data["choices"][0].get("message", {}).get("content", "")
                            elif "content" in data and isinstance(data["content"], list):
                                for c in data["content"]:
                                    if c.get("type") == "text":
                                        reply += c.get("text", "")
                            if reply:
                                break
                    except Exception as e:
                        last_err = e
                        continue
                        
                if not reply:
                    if last_err:
                        # 離線可愛語料兜底
                        fallbacks = [
                            "咕嚕咕嚕～地瓜球現在連不上內網大腦，正在啃地瓜發呆中 (｡•ㅅ•｡)🍠",
                            "嗷嗚～伺服器好像在打瞌睡，地瓜球滾過來抱抱主人！(`・ω・´)✨",
                            "地瓜球在想事情想得出神了～主人今天也辛苦啦！( ˘ ³˘)♥"
                        ]
                        reply = random.choice(fallbacks)
                    else:
                        reply = "咕嚕咕嚕～地瓜球打嗝了 (｡•ㅅ•｡)✨"
                        
                self.ai_chat_history.append({"role": "assistant", "content": reply})
                callback(reply, None)
            except Exception as e:
                callback(None, str(e))
                
        threading.Thread(target=_worker, daemon=True).start()

    def trigger_autonomous_chatter(self):
        """自發性偶爾主動搭話碎碎念 (直連 AI Nexus)"""
        def _worker():
            try:
                cfg = self.pet_data.get("ai_config", {})
                if not cfg.get("auto_chatter", True):
                    return
                url = cfg.get("ccr_url", "http://ainexus.phison.com:5155/api/external/v1/chat/completions")
                api_key = cfg.get("api_key", "AINX-9BA1E6EC81F095A0F9CE8E16F543E557925591303398051A57F5176DB7289874")
                model = cfg.get("model", "deepseek-ai/DeepSeek-V4-Flash-0731")
                
                system_prompt = f"""你是桌面寵物「地瓜球」(TokenPet)。主人稱呼「{self.user_name or '主人'}」，當前等級 Lv.{self.pet_data.get('level', 1)}。
請用繁體中文隨機講一句超可愛、元氣、關心主人或碎碎念的一句話（不超過 25 個字，帶有可愛顏文字如 (｡•ㅅ•｡)♡、✨）。
"""
                payload = {
                    "model": model,
                    "max_tokens": 50,
                    "temperature": 0.7,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": "隨機主動跟主人搭一句話吧！"}
                    ]
                }
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {api_key}"
                    }
                )
                try:
                    with urllib.request.urlopen(req, timeout=8) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        reply = ""
                        if "choices" in data and len(data["choices"]) > 0:
                            reply = data["choices"][0].get("message", {}).get("content", "")
                        if reply:
                            short_text = reply.strip().replace("\n", " ")
                            if len(short_text) > 30:
                                short_text = short_text[:28] + "..."
                            self.root.after(0, lambda: self.create_text_popup(short_text, 170, 100, color="#fab387"))
                except Exception:
                    # 若主模型逾時，嘗試備用秒回模型
                    payload["model"] = "zai-org/GLM-5.3-Flash"
                    req2 = urllib.request.Request(
                        url,
                        data=json.dumps(payload).encode("utf-8"),
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {api_key}"
                        }
                    )
                    with urllib.request.urlopen(req2, timeout=6) as resp2:
                        data2 = json.loads(resp2.read().decode("utf-8"))
                        reply2 = ""
                        if "choices" in data2 and len(data2["choices"]) > 0:
                            reply2 = data2["choices"][0].get("message", {}).get("content", "")
                        if reply2:
                            short_text2 = reply2.strip().replace("\n", " ")
                            if len(short_text2) > 30:
                                short_text2 = short_text2[:28] + "..."
                            self.root.after(0, lambda: self.create_text_popup(short_text2, 170, 100, color="#fab387"))
            except Exception:
                pass
        threading.Thread(target=_worker, daemon=True).start()

    def open_hotkey_settings(self):
        """開啟快速鍵錄製設定視窗"""
        # 這邊直接調用原本 usage_widget 中的快捷鍵錄製面板
        # 為了能在透明無邊框的桌寵下執行，我們可以開一個獨立的小彈出視窗
        hk_win = tk.Toplevel(self.root)
        hk_win.title("快速鍵設定")
        hk_win.geometry("260x100")
        hk_win.configure(bg=WINDOW_BG)
        hk_win.resizable(False, False)
        hk_win.attributes("-topmost", True)
        
        tk.Label(hk_win, text="請設定桌面寵物顯示快速鍵：", bg=WINDOW_BG, fg=TEXT_COLOR, font=("微軟正黑體", 9)).pack(pady=8)
        
        self._recording_hotkey = False
        self._temp_modifiers = set()
        
        # 複用按鈕事件
        self.hotkey_btn = tk.Button(
            hk_win,
            text=self._get_hotkey_display_text(),
            bg="#313244", fg=ACCENT_COLOR,
            relief=tk.FLAT, cursor="hand2",
            command=self._toggle_recording_hotkey
        )
        self.hotkey_btn.pack(pady=2, ipadx=10)
        
        # 鎖定該彈窗
        hk_win.transient(self.root)
        hk_win.grab_set()

    def _get_hotkey_display_text(self):
        if hasattr(self, "hotkey_config") and self.hotkey_config:
            return self.hotkey_config.get("display", "F7")
        return "無"

    def _toggle_recording_hotkey(self):
        """點擊按鈕開始錄製快速鍵"""
        self._recording_hotkey = True
        self._temp_modifiers = set()
        self.hotkey_btn.config(text="請按按鍵... (Esc取消)", fg=YELLOW_COLOR)
        
        # 綁定全域按鍵監聽在 Toplevel 上
        btn_parent = self.hotkey_btn.master
        btn_parent.bind("<KeyPress>", self._on_key_press)
        btn_parent.bind("<KeyRelease>", self._on_key_release)
        btn_parent.focus_set()

    def _on_key_press(self, event):
        if not self._recording_hotkey:
            return "break"
        keysym = event.keysym
        keycode = event.keycode
        
        if keycode == 16 or keysym in ('Shift_L', 'Shift_R'):
            self._temp_modifiers.add("Shift")
            return "break"
        elif keycode == 17 or keysym in ('Control_L', 'Control_R'):
            self._temp_modifiers.add("Ctrl")
            return "break"
        elif keycode == 18 or keysym in ('Alt_L', 'Alt_R'):
            self._temp_modifiers.add("Alt")
            return "break"
            
        if not self._temp_modifiers:
            if keysym == "Escape":
                self._stop_recording(save=False)
                return "break"
            elif keysym in ("BackSpace", "Delete"):
                self._stop_recording(clear=True)
                return "break"
                
        # 錄製完畢
        sorted_mods = []
        for m in ["Ctrl", "Alt", "Shift"]:
            if m in self._temp_modifiers:
                sorted_mods.append(m)
                
        display_key = keysym.upper() if len(keysym) == 1 else keysym.capitalize()
        display_str = "+".join(sorted_mods) + "+" + display_key if sorted_mods else display_key
        
        self.hotkey_config = {
            "modifiers": sorted_mods,
            "vk": keycode,
            "display": display_str
        }
        save_config({"hotkey": self.hotkey_config})
        self._register_saved_hotkey()
        self._stop_recording(save=True)
        return "break"

    def _on_key_release(self, event):
        if not self._recording_hotkey:
            return "break"
        keysym = event.keysym
        keycode = event.keycode
        if keycode == 16 or keysym in ('Shift_L', 'Shift_R'):
            self._temp_modifiers.discard("Shift")
        elif keycode == 17 or keysym in ('Control_L', 'Control_R'):
            self._temp_modifiers.discard("Ctrl")
        elif keycode == 18 or keysym in ('Alt_L', 'Alt_R'):
            self._temp_modifiers.discard("Alt")
        return "break"

    def _stop_recording(self, save=True, clear=False):
        self._recording_hotkey = False
        btn_parent = self.hotkey_btn.master
        btn_parent.unbind("<KeyPress>")
        btn_parent.unbind("<KeyRelease>")
        if clear:
            self.hotkey_config = None
            save_config({"hotkey": None})
            if self.hotkey_manager: self.hotkey_manager.unregister()
        self.hotkey_btn.config(text=self._get_hotkey_display_text(), fg=ACCENT_COLOR)

    def _register_saved_hotkey(self):
        if not self.hotkey_config or not self.hotkey_manager:
            return
        modifiers = self.hotkey_config.get("modifiers", [])
        vk = self.hotkey_config.get("vk", 0)
        if vk > 0:
            mask = 0x4000  # MOD_NOREPEAT
            if "Ctrl" in modifiers: mask |= 0x0002
            if "Alt" in modifiers: mask |= 0x0001
            if "Shift" in modifiers: mask |= 0x0004
            self.hotkey_manager.register(mask, vk)

    def _on_hotkey_pressed(self):
        """快速鍵按下去，切換地瓜球顯示與隱藏"""
        self.root.after(0, self._toggle_visibility)

    def _toggle_visibility(self):
        if getattr(self, "_unity_renderer_active", False):
            self._unity_renderer_visible = not self._unity_renderer_visible
            bridge = getattr(self, "unity_renderer", None)
            if bridge is not None:
                bridge.send(
                    {
                        "command": "set_visible",
                        "visible": self._unity_renderer_visible,
                    }
                )
            method = "deiconify" if self._unity_renderer_visible else "withdraw"
            # The Unity HUD is inside the renderer window; only genuinely
            # separate tools need their Tk windows shown/hidden here.
            auxiliary_windows = []
            for collection_name in ("spawned_memo_wins", "spawned_furniture_wins"):
                auxiliary_windows.extend(getattr(self, collection_name, {}).values())
            for win in auxiliary_windows:
                if win is not None:
                    try:
                        getattr(win, method)()
                    except Exception:
                        pass
            return

        if self.root.state() == "withdrawn":
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            if getattr(self, "shadow_win", None):
                self.shadow_win.deiconify()
            if getattr(self, "hud_win", None):
                self.hud_win.deiconify()
            for win in getattr(self, "spawned_memo_wins", {}).values():
                try: win.deiconify()
                except: pass
            for win in getattr(self, "spawned_furniture_wins", {}).values():
                try: win.deiconify()
                except: pass
        else:
            self.root.withdraw()
            if getattr(self, "shadow_win", None):
                self.shadow_win.withdraw()
            if getattr(self, "hud_win", None):
                self.hud_win.withdraw()
            for win in getattr(self, "spawned_memo_wins", {}).values():
                try: win.withdraw()
                except: pass
            for win in getattr(self, "spawned_furniture_wins", {}).values():
                try: win.withdraw()
                except: pass

    def update_shadow_position(self, pet_wx, pet_wy):
        """依據地瓜球的螢幕 X/Y 坐標，動態將獨立影子視窗與獨立 HUD 看板視窗貼在目前的物理支撐面上"""
        # 1. 判定當前物理支撐面螢幕 Y 坐標
        mon_info = self.get_current_monitor_info()
        landing_y = mon_info["work_y"] + mon_info["work_h"] - 300
        
        # 更新獨立的 HUD 看板位置 (始終固定在地面 landing_y + 250，X 與地瓜球主視窗對齊)
        if getattr(self, "hud_win", None):
            try:
                self.hud_win.geometry(f"340x45+{int(pet_wx)}+{int(landing_y + 250)}")
            except Exception:
                pass

        if not getattr(self, "shadow_win", None):
            return
            
        if self.pet.state in ("sleep", "sleep_futon"):
            # 睡覺狀態下不需要獨立影子
            self.shadow_win.update_shadow(0.0)
            return
            
        floor_screen_y = landing_y + 263  # 正常地面高度 (調低 5 像素以防止與腳板/下半身重疊)
        
        # 檢查是否站在彈簧床上
        if "trampoline" in self.spawned_furniture_wins:
            t_win = self.spawned_furniture_wins["trampoline"]
            tx = t_win.winfo_x()
            ty = t_win.winfo_y()
            pet_screen_cx = pet_wx + self.pet.cx
            if tx + 10 <= pet_screen_cx <= tx + 130:
                floor_screen_y = ty + 30  # 彈簧床網面高度 (同步調低 5 像素)
                
        # 2. 定位影子視窗 (影子視窗中心對齊地瓜球中心，Y 對齊支撐面)
        shadow_x_offset = 0.0
        if self.pet.state == "work_laptop":
            # 寫扣時身體四肢整體向右偏移了約 22 像素以貼合筆電，影子需同步向右偏移對齊雙腳
            shadow_x_offset = 22.0
            
        shadow_wx = pet_wx + self.pet.cx + shadow_x_offset - 80
        shadow_wy = floor_screen_y - 15  # 影子視窗高 30，因此 -15 置中
        
        try:
            self.shadow_win.geometry(f"160x30+{int(shadow_wx)}+{int(shadow_wy)}")
        except Exception:
            pass
            
        # 3. 計算地瓜球屁股與支撐面的螢幕座標落差 (height_diff)
        pet_bottom_screen_y = pet_wy + self.pet.cy + 58
        height_diff = floor_screen_y - pet_bottom_screen_y
        
        if height_diff > 0:
            # 隨著跳躍高度變高，影子呈線性收縮與淡出
            sz_factor = max(0.0, 1.0 - height_diff / 150.0)
        else:
            sz_factor = 1.0
            
        self.shadow_win.update_shadow(sz_factor)

    def _logout(self):
        """清除帳密緩存，重啟程式"""
        delete_credentials()
        self.root.destroy()
        _start_app()

    def save_pet_savegame(self):
        """將地瓜球狀態寫回 .credentials"""
        save_config({"pet_game": self.pet_data})

    def _sync_unity_furniture(self):
        bridge = getattr(self, "unity_renderer", None)
        if not getattr(self, "_unity_renderer_active", False) or bridge is None:
            return
        items = []
        for item_id, furniture in self.spawned_furniture_wins.items():
            try:
                items.append({
                    "id": item_id,
                    "x": int(furniture.winfo_x()),
                    "y": int(furniture.winfo_y()),
                    "width": int(furniture.winfo_width()),
                    "height": int(furniture.winfo_height()),
                })
            except Exception:
                continue
        bridge.sync_furniture(items)

    def spawn_furniture(self, item_id):
        if item_id in self.spawned_furniture_wins:
            self.despawn_furniture(item_id)
            
        if unity_renderer_requested(self.config):
            win = UnityFurnitureProxy(self, item_id)
        else:
            win = FurnitureWindow(self, item_id)
        self.spawned_furniture_wins[item_id] = win
        
        spawned = self.pet_data.setdefault("spawned_furniture", [])
        if item_id not in spawned:
            spawned.append(item_id)
            self.save_pet_savegame()
        self._sync_unity_furniture()

    def despawn_furniture(self, item_id):
        if getattr(self, "current_furniture_snapped", None) == item_id:
            self.current_furniture_snapped = None
            self._furniture_cooldown = 120
            # 檢查如果地瓜球懸空，讓它平穩下墜
            m_info = self.get_current_monitor_info()
            landing_y = m_info["work_y"] + m_info["work_h"] - 300
            if self.root.winfo_y() < landing_y - 10:
                self.pet.state = "fall"
                self._fall_vy = 1.0
            else:
                self.pet.state = "idle"
            self.pet.eye_state = "normal"
            self.pet.mouth_state = "normal"
            
        if item_id in self.spawned_furniture_wins:
            win = self.spawned_furniture_wins.pop(item_id)
            try:
                win.destroy()
            except Exception:
                pass
                
        spawned = self.pet_data.get("spawned_furniture", [])
        if item_id in spawned:
            spawned.remove(item_id)
            self.save_pet_savegame()
        self._sync_unity_furniture()

    def restore_spawned_furniture(self):
        spawned = self.pet_data.get("spawned_furniture", [])
        for item_id in list(spawned):
            self.spawn_furniture(item_id)

    def load_saved_memos(self):
        """從 pet_data 載入所有儲存的便利貼"""
        memos = self.pet_data.get("memos", [])
        for m in list(memos):
            try:
                self.spawn_memo(m["id"], m["x"], m["y"], m.get("text", ""), m.get("w", 180), m.get("h", 160))
            except Exception:
                pass

    def add_new_memo(self):
        """新增一個全新便利貼"""
        self.spawn_memo()

    def spawn_memo(self, memo_id=None, x=None, y=None, text="", w=180, h=160):
        if not memo_id:
            memo_id = f"memo_{int(time.time() * 1000)}"
        if x is None or y is None:
            # 在滑鼠指針附近生成
            x = self.root.winfo_pointerx() - 90
            y = self.root.winfo_pointery() - 80
            
        memos = self.pet_data.setdefault("memos", [])
        exists = any(m["id"] == memo_id for m in memos)
        if not exists:
            memos.append({
                "id": memo_id,
                "x": x,
                "y": y,
                "text": text,
                "w": w,
                "h": h
            })
            self.save_pet_savegame()
            
        win = MemoWindow(self, memo_id, x, y, text, w, h)
        self.spawned_memo_wins[memo_id] = win

    def trigger_eat_memo(self, memo_id):
        """點擊便利貼 ✕ 觸發地瓜球走向並大口吃掉它"""
        if memo_id not in getattr(self, "spawned_memo_wins", {}):
            return
            
        # 解除當前的 snapped 狀態
        self.current_furniture_snapped = None
        self._eat_target_memo_id = memo_id
        self.pet.state = "memo_eat"
        self.pet.eye_state = "happy"
        self.pet.mouth_state = "open"
        self.create_text_popup("Amu Amu! 😋", 170, 100, color="#f9e2af")

    def restore_memo(self, memo_id):
        """從垃圾桶恢復被吃掉的便利貼"""
        deleted_list = self.pet_data.get("deleted_memos", [])
        target_memo = None
        for m in deleted_list:
            if m["id"] == memo_id:
                target_memo = m
                break
                
        if target_memo:
            # 從垃圾桶移除
            self.pet_data["deleted_memos"] = [m for m in deleted_list if m["id"] != memo_id]
            # 加回活動便利貼
            memos = self.pet_data.setdefault("memos", [])
            memos.append({
                "id": target_memo["id"],
                "x": target_memo["x"],
                "y": target_memo["y"],
                "text": target_memo["text"]
            })
            self.save_pet_savegame()
            
            # 在原座標重新生成便利貼視窗
            self.spawn_memo(target_memo["id"], target_memo["x"], target_memo["y"], target_memo["text"])
            self.create_text_popup("已恢復便利貼 📝", 170, 100, color="#a6e3a1")

    def check_furniture_overlap(self):
        cx = self.root.winfo_x() + 170
        cy = self.root.winfo_y() + 205
        
        # 1. 溫馨地舖 (futon)
        if "futon" in self.spawned_furniture_wins:
            f_win = self.spawned_furniture_wins["futon"]
            fx = f_win.winfo_x()
            fy = f_win.winfo_y()
            if abs(cx - (fx + 90)) < 75 and abs(cy - (fy + 50)) < 60:
                self.pet.state = "sleep_futon"
                self.current_furniture_snapped = "futon"
                self.create_text_popup("晚安地瓜球 💤", 170, 100, color="#b4befe")
                self.save_pet_savegame()
                return True

        # 2. 柔軟懶人沙發 (lazy_sofa)
        if "lazy_sofa" in self.spawned_furniture_wins:
            s_win = self.spawned_furniture_wins["lazy_sofa"]
            sx = s_win.winfo_x()
            sy = s_win.winfo_y()
            if abs(cx - (sx + 80)) < 75 and abs(cy - (sy + 50)) < 60:
                self.pet.state = "relax_sofa"
                self.pet.eye_state = "happy"
                self.current_furniture_snapped = "lazy_sofa"
                self.create_text_popup("軟綿綿看漫畫~ 📖", 170, 100, color="#f5c2e7")
                self.save_pet_savegame()
                return True

        # 3. 日式暖桌被爐 (kotatsu)
        if "kotatsu" in self.spawned_furniture_wins:
            k_win = self.spawned_furniture_wins["kotatsu"]
            kx = k_win.winfo_x()
            ky = k_win.winfo_y()
            if abs(cx - (kx + 85)) < 80 and abs(cy - (ky + 50)) < 60:
                self.pet.state = "warm_kotatsu"
                self.pet.eye_state = "happy"
                self.current_furniture_snapped = "kotatsu"
                self.create_text_popup("暖呼呼吃橘子 🍊", 170, 100, color="#fab387")
                self.save_pet_savegame()
                return True
                
        # 4. 加班寫扣筆電 (laptop)
        if "laptop" in self.spawned_furniture_wins:
            l_win = self.spawned_furniture_wins["laptop"]
            lx = l_win.winfo_x()
            ly = l_win.winfo_y()
            if abs(cx - lx) < 85 and abs(cy - (ly + 50)) < 70:
                self.pet.state = "work_laptop"
                self.current_furniture_snapped = "laptop"
                self.create_text_popup("加班奮鬥！💻", 170, 100, color="#89b4fa")
                self.pet.eye_state = "happy"
                self.save_pet_savegame()
                return True

        # 5. 復古像素電視 (pixel_tv)
        if "pixel_tv" in self.spawned_furniture_wins:
            t_win = self.spawned_furniture_wins["pixel_tv"]
            tx = t_win.winfo_x()
            ty = t_win.winfo_y()
            if abs(cx - (tx - 10)) < 85 and abs(cy - (ty + 55)) < 70:
                self.pet.state = "watch_tv"
                self.pet.eye_state = "star"
                self.current_furniture_snapped = "pixel_tv"
                self.create_text_popup("看電視時間！📺", 170, 100, color="#f9e2af")
                self.save_pet_savegame()
                return True

        # 6. 蘑菇小夜燈 (night_lamp)
        if "night_lamp" in self.spawned_furniture_wins:
            n_win = self.spawned_furniture_wins["night_lamp"]
            nx = n_win.winfo_x()
            ny = n_win.winfo_y()
            if abs(cx - (nx - 5)) < 85 and abs(cy - (ny + 55)) < 70:
                self.pet.state = "meditate_lamp"
                self.pet.eye_state = "blink"
                self.current_furniture_snapped = "night_lamp"
                self.create_text_popup("燈下靜心中... 🏮", 170, 100, color="#f9e2af")
                self.save_pet_savegame()
                return True

        # 7. 多肉小盆栽 (succulent_pot)
        if "succulent_pot" in self.spawned_furniture_wins:
            p_win = self.spawned_furniture_wins["succulent_pot"]
            px = p_win.winfo_x()
            py = p_win.winfo_y()
            if abs(cx - (px - 10)) < 85 and abs(cy - (py + 50)) < 70:
                self.pet.state = "water_plant"
                self.pet.eye_state = "happy"
                self.current_furniture_snapped = "succulent_pot"
                self.create_text_popup("給多肉澆澆水 🪴", 170, 100, color="#a6e3a1")
                self.save_pet_savegame()
                return True

        # 8. 彈簧蹦蹦床 (trampoline)
        if "trampoline" in self.spawned_furniture_wins:
            tr_win = self.spawned_furniture_wins["trampoline"]
            trx = tr_win.winfo_x()
            try_y = tr_win.winfo_y()
            if abs(cx - (trx + 70)) < 65 and abs(cy - (try_y + 30)) < 45:
                if hasattr(tr_win, "trigger_bounce"):
                    tr_win.trigger_bounce()
                self._fall_vy = -14.0
                self.pet.state = "fall"
                self.air_roll_timer = 28
                self.air_roll_direction = random.choice([-1.0, 1.0])
                self.create_text_popup("咚～! 🤸", 170, 100, color="#fab387")
                return True

        # 9. 便利貼 (Memo) 頂端吸附判定 (踩高高唱歌交互)
        for memo_id, m_win in getattr(self, "spawned_memo_wins", {}).items():
            try:
                mx = m_win.winfo_x()
                my = m_win.winfo_y()
                pet_bottom = cy + 45
                if abs(cx - (mx + 90)) < 90 and abs(pet_bottom - (my + 10)) < 35:
                    self.update_geometry(mx - 80, my - 240)
                    self.pet.state = "memo_perch"
                    self.current_furniture_snapped = memo_id
                    self.create_text_popup("踩高高~ ♪", 170, 100, color="#f9e2af")
                    self.pet.eye_state = "happy"
                    self.pet.mouth_state = "open"
                    self.save_pet_savegame()
                    return True
            except Exception:
                pass
        return False

    def _on_destroy(self, event):
        if event.widget == self.root:
            if getattr(self, "unity_renderer", None):
                self.unity_renderer.stop()
                self.unity_renderer = None
            if getattr(self, "shadow_win", None):
                try:
                    self.shadow_win.destroy()
                except Exception:
                    pass
            if getattr(self, "hud_win", None):
                try:
                    self.hud_win.destroy()
                except Exception:
                    pass
            if hasattr(self, "spawned_memo_wins"):
                for win in list(self.spawned_memo_wins.values()):
                    try: win.destroy()
                    except: pass
            if hasattr(self, "spawned_furniture_wins"):
                for win in list(self.spawned_furniture_wins.values()):
                    try: win.destroy()
                    except: pass
            if self.hotkey_manager:
                self.hotkey_manager.stop()

    # ──────────────────────────────────────────────────
    # 內網自動更新系統 (Intranet Auto-Updater Client - 獨立批次無縫交棒版)
    # ──────────────────────────────────────────────────
    def check_auto_update(self, manual=False):
        """背景檢查是否有新版本 (加固版：支援 UNC 逾時預檢與友善提示)"""
        if getattr(self, "STANDALONE", False):
            if manual:
                self.root.after(0, lambda: messagebox.showinfo("檢查更新", f"當前為純萌寵單機版，不支援網路更新功能。\n目前版本: v{CURRENT_VERSION}"))
            return
            
        update_url = self.config.get("update_server_url", "\\\\power2\\RD Share\\EdwinLuo\\Another Token Bites the Dust")
        print(f"[Update Check] Target URL/Path: {update_url}")
        
        is_file_path = not (update_url.lower().startswith("http://") or update_url.lower().startswith("https://"))
        print(f"[Update Check] Is local/UNC file path mode: {is_file_path}")
        
        if is_file_path:
            try:
                version_file = os.path.join(update_url, "version.json")
                print(f"[Update Check] Target version file: {version_file}")
                
                # 快速預檢檔案是否存在 (若網路未連線可捕獲異常)
                if not os.path.exists(version_file):
                    if manual:
                        self.root.after(0, lambda: messagebox.showwarning("檢查更新", f"找不到伺服器更新檔案！\n若您在公司外網，請確認已連線公司 VPN。\n路徑: {version_file}"))
                    return
                    
                with open(version_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                srv_ver = str(data.get("version", CURRENT_VERSION)).strip()
                print(f"[Update Check] Server version: {srv_ver} | Local version: {CURRENT_VERSION}")
                
                is_newer = self._parse_version(srv_ver) > self._parse_version(CURRENT_VERSION)
                print(f"[Update Check] Server version parsed: {self._parse_version(srv_ver)} > Local parsed: {self._parse_version(CURRENT_VERSION)} -> is_newer: {is_newer}")
                
                if is_newer:
                    raw_dl = data.get("download_url", "TokenPet.exe")
                    if not (raw_dl.startswith("\\\\") or raw_dl.startswith("http://") or raw_dl.startswith("https://") or (len(raw_dl) > 2 and raw_dl[1] == ':')):
                        dl_url = os.path.join(update_url, raw_dl)
                    else:
                        dl_url = raw_dl
                    msg = data.get("changelog", "有新版本更新可用！")
                    self.root.after(0, self._prompt_update, srv_ver, dl_url, msg)
                elif manual:
                    self.root.after(0, lambda: messagebox.showinfo("檢查更新", f"目前已是最新版本 (v{CURRENT_VERSION})！"))
            except Exception as e:
                import traceback
                print(f"[Update Check] Error during local update check: {e}")
                traceback.print_exc()
                if manual:
                    self.root.after(0, lambda: messagebox.showerror("檢查更新", f"連線更新伺服器失敗，請確認網路或 VPN 連線。\n詳細錯誤: {str(e)}"))
            return
            
        # HTTP 模式
        try:
            version_url = f"{update_url.rstrip('/')}/version.json"
            print(f"[Update Check] Sending requests to: {version_url}")
            r = requests.get(version_url, timeout=6)
            print(f"[Update Check] Server responded with status code: {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                srv_ver = str(data.get("version", CURRENT_VERSION)).strip()
                print(f"[Update Check] Server version: {srv_ver} | Local version: {CURRENT_VERSION}")
                is_newer = self._parse_version(srv_ver) > self._parse_version(CURRENT_VERSION)
                if is_newer:
                    raw_dl = data.get("download_url", "TokenPet.exe")
                    dl_url = raw_dl if raw_dl.startswith("http") else f"{update_url.rstrip('/')}/{raw_dl.lstrip('/')}"
                    msg = data.get("changelog", "有新版本更新可用！")
                    self.root.after(0, self._prompt_update, srv_ver, dl_url, msg)
                elif manual:
                    self.root.after(0, lambda: messagebox.showinfo("檢查更新", f"目前已是最新版本 (v{CURRENT_VERSION})！"))
            else:
                if manual:
                    self.root.after(0, lambda: messagebox.showerror("檢查更新", f"伺服器回應錯誤！狀態碼: {r.status_code}"))
        except Exception as e:
            import traceback
            traceback.print_exc()
            if manual:
                self.root.after(0, lambda: messagebox.showerror("檢查更新", f"連線更新伺服器失敗:\n{str(e)}"))

    def trigger_manual_update_check(self):
        """手動觸發更新檢查"""
        self.create_text_popup("🔍 檢查更新...", 170, 120, color=ACCENT_COLOR)
        threading.Thread(target=self.check_auto_update, kwargs={"manual": True}, daemon=True).start()

    def _parse_version(self, ver_str):
        """健壯解析版本號，自動濾除非數字字元 (例如 'v2.2.5' -> (2, 2, 5))"""
        try:
            import re
            if not ver_str:
                return (0, 0, 0)
            parts = re.findall(r'\d+', str(ver_str).strip())
            if parts:
                nums = [int(p) for p in parts[:3]]
                while len(nums) < 3:
                    nums.append(0)
                return tuple(nums)
            return (0, 0, 0)
        except Exception:
            return (0, 0, 0)

    def _prompt_update(self, new_ver, dl_url, changelog):
        """直接在背景自動下載更新並進行無縫替換"""
        self.create_text_popup(f"📥 發現 v{new_ver}，自動下載更新...", 170, 120, color=ACCENT_COLOR)
        threading.Thread(target=self._download_and_swap, args=(dl_url,), daemon=True).start()

    def _download_and_swap(self, dl_url):
        """下載新版本，並生成獨立升級批次腳本交棒替換，徹底 100% 根除 Windows 檔案鎖死與權限問題"""
        try:
            if not getattr(sys, 'frozen', False):
                self.root.after(0, lambda: messagebox.showinfo("更新資訊", "目前為開發原始碼模式，不支援自動替換更新。"))
                return

            current_exe = os.path.abspath(sys.executable)
            exe_dir = os.path.dirname(current_exe)
            
            temp_download_path = os.path.join(exe_dir, f"TokenPet_new_{int(time.time())}.tmp")
            self.create_text_popup("📥 正在下載更新檔案...", 170, 120, color=ACCENT_COLOR)
            
            is_dl_file_path = not (dl_url.lower().startswith("http://") or dl_url.lower().startswith("https://"))
            
            # 複製/下載檔案 (帶 3 次重試)
            download_success = False
            last_err = None
            for attempt in range(3):
                try:
                    if is_dl_file_path:
                        import shutil
                        if not os.path.exists(dl_url):
                            raise Exception(f"找不到伺服器更新檔案: {dl_url}")
                        shutil.copy2(dl_url, temp_download_path)
                    else:
                        r = requests.get(dl_url, stream=True, timeout=60)
                        if r.status_code == 200:
                            with open(temp_download_path, "wb") as f:
                                for chunk in r.iter_content(chunk_size=65536):
                                    if chunk: f.write(chunk)
                        else:
                            raise Exception(f"HTTP 下載錯誤: {r.status_code}")
                    download_success = True
                    break
                except Exception as e:
                    last_err = e
                    time.sleep(1.0)
                    
            if not download_success:
                raise Exception(f"下載失敗 (已重試 3 次): {last_err}")
                
            # 檔案完整性檢查 (> 5MB)
            if not os.path.exists(temp_download_path) or os.path.getsize(temp_download_path) < 5 * 1024 * 1024:
                size_kb = (os.path.getsize(temp_download_path) / 1024.0) if os.path.exists(temp_download_path) else 0.0
                if os.path.exists(temp_download_path):
                    try: os.remove(temp_download_path)
                    except: pass
                raise Exception(f"更新檔案不完整 ({size_kb:.1f} KB)，已終止以防損壞。")
                
            # 生成獨立升級腳本 update_patcher.bat
            # 該腳本在主進程退出後，等待 0.8 秒完全釋放檔案 Handle，然後無縫覆蓋並重啟新程式
            bat_path = os.path.join(exe_dir, f"update_patcher_{int(time.time())}.bat")
            backup_old_exe = os.path.join(exe_dir, f"TokenPet_backup.old")
            
            bat_content = f"""@echo off
chcp 65001 >nul
title TokenPet Auto Updater
echo [TokenPet] Waiting for main process to release file lock...
ping 127.0.0.1 -n 2 >nul

echo [TokenPet] Backing up and applying new version...
if exist "{backup_old_exe}" del /f /q "{backup_old_exe}" >nul 2>&1
move /y "{current_exe}" "{backup_old_exe}" >nul 2>&1
move /y "{temp_download_path}" "{current_exe}" >nul 2>&1

echo [TokenPet] Launching updated TokenPet...
start "" "{current_exe}"

echo [TokenPet] Cleaning up...
ping 127.0.0.1 -n 2 >nul
del /f /q "{backup_old_exe}" >nul 2>&1
(goto) 2>nul & del "%~f0"
"""
            with open(bat_path, "w", encoding="utf-8") as f:
                f.write(bat_content)
                
            self.create_text_popup("🚀 更新就緒，自動重啟...", 170, 120, color="#a6e3a1")
            time.sleep(0.5)
            
            # 啟動獨立升級腳本
            import subprocess
            subprocess.Popen([bat_path], shell=True, creationflags=subprocess.DETACHED_PROCESS)
            
            # 主程序退出，徹底釋放檔案鎖
            self.root.after(100, self.root.destroy)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.root.after(0, lambda: messagebox.showerror("更新錯誤", f"自動更新失敗:\n{str(e)}"))


# ──────────────────────────────────────────────────
# 投籃小遊戲籃框視窗 (Basketball Hoop Window)
# ──────────────────────────────────────────────────
class BasketballHoop(tk.Toplevel):
    def __init__(self, parent_monitor):
        super().__init__(parent_monitor.root)
        self.monitor = parent_monitor
        self.title("籃框")
        
        # 取得主視窗所在的螢幕，放置籃框在相對偏右上的位置
        m_info = parent_monitor.get_current_monitor_info()
        wx = parent_monitor.root.winfo_x()
        wy = parent_monitor.root.winfo_y()
        
        # 初始幾何設定 300x300，放在靠近桌寵右上方
        hx = max(m_info["mon_x"] + 50, min(m_info["mon_x"] + m_info["mon_w"] - 350, wx + 180))
        hy = max(m_info["mon_y"] + 50, min(m_info["mon_y"] + m_info["mon_h"] - 450, wy - 280))
        
        self.geometry(f"300x300+{int(hx)}+{int(hy)}")
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.config(bg="#111111")
        
        if IS_WINDOWS:
            self.attributes("-transparentcolor", "#111111")
            
        self.canvas = tk.Canvas(self, width=300, height=300, bg="#111111", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.score = 0
        self.net_offset_y = 0.0
        self.net_shake_timer = 0
        self.confetti = []
        
        # 拖曳籃框視窗
        self.canvas.bind("<Button-1>", self._on_drag_start)
        self.canvas.bind("<B1-Motion>", self._on_drag_motion)
        
        self.draw_hoop()
        self.animate()

    def _on_drag_start(self, event):
        # 關閉按鈕點擊判定 (✕ 座標在 260, 35 附近)
        if math.hypot(event.x - 260, event.y - 35) < 15:
            self.close_game()
            return
        self._start_x_root = event.x_root
        self._start_y_root = event.y_root
        self._start_win_x = self.winfo_x()
        self._start_win_y = self.winfo_y()

    def _on_drag_motion(self, event):
        # 如果是關閉按鈕點擊，不進行拖曳
        if math.hypot(event.x - 260, event.y - 35) < 15:
            return
        dx = event.x_root - self._start_x_root
        dy = event.y_root - self._start_y_root
        x = self._start_win_x + dx
        y = self._start_win_y + dy
        self.geometry(f"+{int(x)}+{int(y)}")

    def draw_hoop(self):
        self.canvas.delete("hoop")
        
        # 霓虹籃板 (Vertical Neon Backboard on the Right)
        # x1 = 220, y1 = 40, x2 = 235, y2 = 180
        self.canvas.create_rectangle(220, 40, 235, 180, outline="#89b4fa", width=4, fill="#181825", tags="hoop")
        # 籃圈固定鐵片 (Connects rim to backboard)
        self.canvas.create_line(200, 130, 220, 130, fill="#f38ba8", width=4, tags="hoop")
        
        # 電子計分板 (Scoreboard)
        create_outlined_text(self.canvas, 130, 35, text=f"SCORE: {self.score}", fill="#a6e3a1", font=("Consolas", 18, "bold"), outline="#11111b", width=2.0, tags=("hoop", "score"))
        
        # 籃網震動物理 (Hangs down from rim x=[80, 200] at y=130 to bottom x=[110, 170] at y=195)
        oy = self.net_offset_y
        net_color = "#cdd6f4"
        # 左側網邊
        self.canvas.create_line(80, 130, 110 + oy*0.4, 195 + oy, fill=net_color, width=2.5, tags="hoop")
        # 右側網邊
        self.canvas.create_line(200, 130, 170 - oy*0.4, 195 + oy, fill=net_color, width=2.5, tags="hoop")
        # 中間網線
        self.canvas.create_line(110, 130, 125 + oy*0.2, 195 + oy, fill=net_color, width=2, tags="hoop")
        self.canvas.create_line(140, 130, 140, 195 + oy, fill=net_color, width=2, tags="hoop")
        self.canvas.create_line(170, 130, 155 - oy*0.2, 195 + oy, fill=net_color, width=2, tags="hoop")
        
        # 網孔交叉線
        self.canvas.create_line(90, 150 + oy*0.3, 190, 150 + oy*0.3, fill=net_color, width=1.5, tags="hoop")
        self.canvas.create_line(100, 170 + oy*0.6, 180, 170 + oy*0.6, fill=net_color, width=1.5, tags="hoop")
        
        # 橘紅色框 (Rim - Ellipse showing 3D perspective)
        # x1 = 80, y1 = 120, x2 = 200, y2 = 140
        self.canvas.create_oval(80, 120, 200, 140, outline="#f38ba8", width=5, fill="", tags="hoop")
        
        # 右上角關閉按鈕 ✕
        self.canvas.create_text(260, 35, text="✕", fill="#f38ba8", font=("Arial", 12, "bold"), tags=("hoop", "close"))

    def trigger_goal(self):
        """觸發進球：增加分數，啟動網子擺動，並噴射七彩碎紙"""
        self.score += 1
        self.net_shake_timer = 30
        self.spawn_confetti()
        self.draw_hoop()
        
    def spawn_confetti(self):
        colors = ["#ff5555", "#ffaa00", "#ffdd00", "#a6e3a1", "#89b4fa", "#f5c2e7"]
        for _ in range(30):
            cx = random.randint(100, 180)
            cy = 150
            cid = self.canvas.create_oval(cx-3, cy-3, cx+3, cy+3, fill=random.choice(colors), outline="", tags="confetti")
            self.confetti.append({
                "id": cid,
                "x": cx,
                "y": cy,
                "vx": random.uniform(-4.0, 4.0),
                "vy": random.uniform(-8.0, -3.0),
                "life": random.randint(35, 55)
            })

    def animate(self):
        if not self.winfo_exists():
            return
            
        # 1. 更新籃網晃動
        if self.net_shake_timer > 0:
            self.net_shake_timer -= 1
            self.net_offset_y = 18.0 * (self.net_shake_timer / 30.0) * math.sin(self.net_shake_timer * 0.8)
            self.draw_hoop()
        elif self.net_offset_y != 0:
            self.net_offset_y = 0.0
            self.draw_hoop()
            
        # 2. 更新慶祝彩紙粒子
        active_c = []
        for c in self.confetti:
            c["vy"] += 0.25  # 重力
            c["x"] += c["vx"]
            c["y"] += c["vy"]
            c["life"] -= 1
            self.canvas.coords(c["id"], c["x"]-3, c["y"]-3, c["x"]+3, c["y"]+3)
            
            if c["life"] > 0 and c["y"] < 300:
                active_c.append(c)
            else:
                self.canvas.delete(c["id"])
        self.confetti = active_c
        
        self.after(16, self.animate)

    def close_game(self):
        self.monitor.basketball_hoop = None
        self.destroy()


# ──────────────────────────────────────────────────
# 接水果小遊戲視窗 (Fruit Catcher Game Window)
# ──────────────────────────────────────────────────
class FruitCatcherWindow(tk.Toplevel):
    def __init__(self, parent_monitor):
        super().__init__(parent_monitor.root)
        self.monitor = parent_monitor
        self.title("🍎 地瓜球接水果")
        self.width, self.height = 360, 420
        
        m_info = parent_monitor.get_current_monitor_info()
        wx = (m_info["mon_w"] - self.width) // 2 + m_info["mon_x"]
        wy = (m_info["mon_h"] - self.height) // 2 + m_info["mon_y"] - 50
        self.geometry(f"{self.width}x{self.height}+{int(wx)}+{int(wy)}")
        
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.config(bg="#111111")
        if IS_WINDOWS:
            self.attributes("-transparentcolor", "#111111")
            
        self.canvas = tk.Canvas(self, width=self.width, height=self.height, bg="#111111", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.score = 0
        self.time_left = 30
        self.game_over = False
        self.catcher_x = 180
        self.fruits = []
        self.particles = []
        self.is_stunned = 0
        
        self.canvas.bind("<Motion>", self._on_mouse_move)
        self.canvas.bind("<Button-1>", self._on_click)
        
        self._spawn_timer = 0
        self.draw_frame()
        self.game_loop()
        self.timer_countdown()

    def _on_mouse_move(self, event):
        if not self.game_over and self.is_stunned <= 0:
            self.catcher_x = max(35, min(self.width - 35, event.x))

    def _on_click(self, event):
        if math.hypot(event.x - 330, event.y - 25) < 16:
            self.close_game()

    def timer_countdown(self):
        if self.game_over or not self.winfo_exists():
            return
        if self.time_left > 0:
            self.time_left -= 1
            self.after(1000, self.timer_countdown)
        else:
            self.game_over = True
            self.finish_game()

    def finish_game(self):
        coins_won = max(5, self.score // 4)
        xp_won = max(10, self.score * 2)
        self.monitor.pet_data["coins"] = self.monitor.pet_data.get("coins", 0) + coins_won
        self.monitor.gain_pet_xp(xp_won)
        self.monitor.save_pet_savegame()
        self.monitor.create_text_popup(f"🎉 結算！+{coins_won} 🪙 +{xp_won} XP", 170, 100, color="#a6e3a1")

    def spawn_fruit(self):
        r = random.random()
        if r < 0.45:
            f_type = "apple"
            icon = "🍎"
            val = 10
            vy = random.uniform(3.0, 4.5)
        elif r < 0.75:
            f_type = "strawberry"
            icon = "🍓"
            val = 20
            vy = random.uniform(3.5, 5.2)
        elif r < 0.90:
            f_type = "star"
            icon = "⭐"
            val = 50
            vy = random.uniform(4.5, 6.5)
        else:
            f_type = "bomb"
            icon = "💣"
            val = -30
            vy = random.uniform(3.5, 5.0)
            
        fx = random.randint(35, self.width - 35)
        self.fruits.append({
            "x": fx, "y": 50, "vy": vy,
            "type": f_type, "val": val, "icon": icon
        })

    def draw_frame(self):
        self.canvas.delete("all")
        
        # 1. 遊戲視窗背板
        self.canvas.create_polygon(
            15, 10, self.width - 15, 10, self.width - 5, 25, self.width - 5, self.height - 15,
            self.width - 15, self.height - 5, 15, self.height - 5, 5, self.height - 15, 5, 25,
            fill="#181825", outline="#45475a", width=2.0, smooth=True
        )
        
        # 2. 頂部資訊欄
        create_outlined_text(self.canvas, 80, 30, text=f"🍎 分數: {self.score}", fill="#fab387", font=("Consolas", 14, "bold"), outline="#11111b", width=1.5)
        create_outlined_text(self.canvas, 200, 30, text=f"⏱️ 倒數: {self.time_left}s", fill="#89b4fa" if self.time_left > 5 else "#f38ba8", font=("Consolas", 14, "bold"), outline="#11111b", width=1.5)
        
        # 右上角關閉按鈕 ✕
        self.canvas.create_oval(318, 14, 342, 38, fill="#313244", outline="#f38ba8", width=1.5)
        self.canvas.create_text(330, 26, text="✕", fill="#f38ba8", font=("Arial", 11, "bold"))
        
        # 接物基準水平底線
        self.canvas.create_line(15, 370, self.width - 15, 370, fill="#313244", width=2.0)
        
        # 3. 繪製掉落中的水果
        for f in self.fruits:
            self.canvas.create_text(f["x"], f["y"], text=f["icon"], font=("微軟正黑體", 16))
            
        # 4. 繪製底部接物地瓜球與小竹籃
        cx = self.catcher_x
        cy = 350
        
        if self.is_stunned > 0:
            self.canvas.create_oval(cx - 24, cy - 20, cx + 24, cy + 16, fill="#cdd6f4", outline="#3c2203", width=2.0)
            self.canvas.create_text(cx - 8, cy - 5, text="✖", fill="#11111b", font=("Arial", 9, "bold"))
            self.canvas.create_text(cx + 8, cy - 5, text="✖", fill="#11111b", font=("Arial", 9, "bold"))
            self.canvas.create_text(cx, cy + 5, text="﹏", fill="#11111b", font=("Arial", 10))
            self.canvas.create_text(cx, cy - 28, text="💫", font=("微軟正黑體", 12))
        else:
            self.canvas.create_oval(cx - 24, cy - 20, cx + 24, cy + 16, fill="#f9e2af", outline="#3c2203", width=2.0)
            self.canvas.create_oval(cx - 18, cy - 2, cx - 10, cy + 4, fill="#f38ba8", outline="")
            self.canvas.create_oval(cx + 10, cy - 2, cx + 18, cy + 4, fill="#f38ba8", outline="")
            self.canvas.create_arc(cx - 14, cy - 10, cx - 4, cy, start=0, extent=180, style=tk.ARC, width=2.0, outline="#3c2203")
            self.canvas.create_arc(cx + 4, cy - 10, cx + 14, cy, start=0, extent=180, style=tk.ARC, width=2.0, outline="#3c2203")
            self.canvas.create_oval(cx - 4, cy + 2, cx + 4, cy + 8, fill="#ff5555", outline="#3c2203", width=1.0)
            self.canvas.create_arc(cx - 28, cy - 16, cx + 28, cy + 14, start=180, extent=180, fill="#fab387", outline="#3c2203", width=1.8)
            
        # 5. 繪製拾取粒子特效
        for p in self.particles:
            self.canvas.create_oval(p["x"] - p["r"], p["y"] - p["r"], p["x"] + p["r"], p["y"] + p["r"], fill=p["col"], outline="")
            
        # 6. 遊戲結束畫面
        if self.game_over:
            self.canvas.create_rectangle(30, 120, self.width - 30, 290, fill="#11111b", outline="#fab387", width=2.5)
            create_outlined_text(self.canvas, self.width // 2, 160, text="🎉 遊戲結束！", fill="#f9e2af", font=("微軟正黑體", 16, "bold"), outline="#11111b", width=1.5)
            create_outlined_text(self.canvas, self.width // 2, 200, text=f"最終得分: {self.score}", fill="#a6e3a1", font=("Consolas", 18, "bold"), outline="#11111b", width=1.5)
            coins_won = max(5, self.score // 4)
            create_outlined_text(self.canvas, self.width // 2, 245, text=f"獲得獎勵: +{coins_won} 🪙", fill="#f9e2af", font=("微軟正黑體", 13, "bold"), outline="#11111b", width=1.2)

    def game_loop(self):
        if not self.winfo_exists():
            return
            
        if not self.game_over:
            if self.is_stunned > 0:
                self.is_stunned -= 1
                
            self._spawn_timer += 1
            if self._spawn_timer >= 24:
                self._spawn_timer = 0
                self.spawn_fruit()
                
            active_f = []
            for f in self.fruits:
                f["y"] += f["vy"]
                
                if 335 <= f["y"] <= 365 and abs(f["x"] - self.catcher_x) < 32 and self.is_stunned <= 0:
                    self.score = max(0, self.score + f["val"])
                    if f["type"] == "bomb":
                        self.is_stunned = 35
                        self.spawn_burst(f["x"], f["y"], ["#11111b", "#ff5555"])
                    else:
                        cols = ["#ff5555", "#a6e3a1"] if f["type"] == "apple" else ["#f38ba8", "#ffffff"] if f["type"] == "strawberry" else ["#f9e2af", "#ffffff"]
                        self.spawn_burst(f["x"], f["y"], cols)
                elif f["y"] < 390:
                    active_f.append(f)
            self.fruits = active_f
            
        active_p = []
        for p in self.particles:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["vy"] += 0.2
            p["life"] -= 1
            if p["life"] > 0:
                active_p.append(p)
        self.particles = active_p
        
        self.draw_frame()
        self.after(16, self.game_loop)

    def spawn_burst(self, x, y, cols):
        for _ in range(12):
            self.particles.append({
                "x": x, "y": y,
                "vx": random.uniform(-3.5, 3.5),
                "vy": random.uniform(-5.0, -1.0),
                "r": random.uniform(2.0, 4.0),
                "col": random.choice(cols),
                "life": random.randint(15, 30)
            })

    def close_game(self):
        self.monitor.fruit_catcher_game = None
        self.destroy()


# ──────────────────────────────────────────────────
# 幸運拉霸機小遊戲視窗 (Slot Machine Window)
# ──────────────────────────────────────────────────
class SlotMachineWindow(tk.Toplevel):
    def __init__(self, parent_monitor):
        super().__init__(parent_monitor.root)
        self.monitor = parent_monitor
        self.title("🎰 幸運地瓜拉霸機")
        self.width, self.height = 320, 360
        
        m_info = parent_monitor.get_current_monitor_info()
        wx = (m_info["mon_w"] - self.width) // 2 + m_info["mon_x"]
        wy = (m_info["mon_h"] - self.height) // 2 + m_info["mon_y"] - 40
        self.geometry(f"{self.width}x{self.height}+{int(wx)}+{int(wy)}")
        
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.config(bg="#111111")
        if IS_WINDOWS:
            self.attributes("-transparentcolor", "#111111")
            
        self.canvas = tk.Canvas(self, width=self.width, height=self.height, bg="#111111", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.symbols = ["🍠", "🌸", "💎", "7️⃣", "🪙", "⭐"]
        self.reels = ["🍠", "🍠", "🍠"]
        self.is_spinning = False
        self.lever_offset = 0.0
        self.spin_timer = 0
        self.status_msg = "點擊 SPIN 試試手氣！"
        
        self.canvas.bind("<Button-1>", self._on_click)
        self.draw_machine()

    def _on_click(self, event):
        if math.hypot(event.x - 290, event.y - 25) < 16:
            self.close_game()
            return
            
        if 90 <= event.x <= 230 and 275 <= event.y <= 325 and not self.is_spinning:
            self.start_spin()
        elif 260 <= event.x <= 295 and 90 <= event.y <= 190 and not self.is_spinning:
            self.start_spin()

    def start_spin(self):
        cur_coins = self.monitor.pet_data.get("coins", 0)
        if cur_coins < 10:
            self.status_msg = "地瓜幣不足 10 🪙！"
            self.draw_machine()
            return
            
        self.monitor.pet_data["coins"] -= 10
        self.monitor.save_pet_savegame()
        self.is_spinning = True
        self.status_msg = "高速旋轉中... 祝好運！"
        self.spin_timer = 0
        self.lever_offset = 18.0
        self._spin_step()

    def _spin_step(self):
        if not self.winfo_exists():
            return
            
        self.spin_timer += 1
        
        if self.lever_offset > 0:
            self.lever_offset = max(0.0, self.lever_offset - 2.0)
            
        if self.spin_timer < 25:
            self.reels[0] = random.choice(self.symbols)
        if self.spin_timer < 40:
            self.reels[1] = random.choice(self.symbols)
        if self.spin_timer < 55:
            self.reels[2] = random.choice(self.symbols)
            self.draw_machine()
            self.after(35, self._spin_step)
        else:
            self.is_spinning = False
            self.check_win()
            self.draw_machine()

    def check_win(self):
        r1, r2, r3 = self.reels
        if r1 == r2 == r3:
            if r1 == "7️⃣":
                reward = 500
                self.status_msg = "🔥 JACKPOT 超級大獎！+500 🪙 🔥"
            elif r1 == "💎":
                reward = 250
                self.status_msg = "💎 鑽石特獎！+250 🪙 💎"
            elif r1 == "🍠":
                reward = 150
                self.status_msg = "🍠 地瓜之王大獎！+150 🪙 🍠"
                self.monitor.pet_data["satiety"] = 100.0
            else:
                reward = 80
                self.status_msg = f"🎉 三連大獎！+{reward} 🪙 🎉"
            self.monitor.gain_pet_xp(reward)
        elif r1 == r2 or r2 == r3 or r1 == r3:
            reward = 20
            self.status_msg = "✨ 雙喜臨門！+20 🪙 ✨"
        else:
            reward = 2
            self.status_msg = "下次一定中！安慰獎 +2 🪙"
            
        self.monitor.pet_data["coins"] = self.monitor.pet_data.get("coins", 0) + reward
        self.monitor.save_pet_savegame()
        self.monitor.create_text_popup(f"🎰 {self.status_msg}", 170, 100, color="#f9e2af")

    def draw_machine(self):
        self.canvas.delete("all")
        
        # 1. 復古街機拉霸機外殼
        self.canvas.create_polygon(
            20, 10, 260, 10, 270, 25, 270, self.height - 15,
            260, self.height - 5, 20, self.height - 5, 10, self.height - 15, 10, 25,
            fill="#313244", outline="#fab387", width=2.5, smooth=True
        )
        
        # 頂部招牌
        self.canvas.create_rectangle(30, 20, 250, 60, fill="#181825", outline="#f9e2af", width=2.0)
        create_outlined_text(self.canvas, 140, 40, text="🎰 LUCKY SLOTS 🎰", fill="#f9e2af", font=("微軟正黑體", 12, "bold"), outline="#11111b", width=1.5)
        
        # 右上角關閉按鈕 ✕
        self.canvas.create_oval(278, 14, 302, 38, fill="#1e1e2e", outline="#f38ba8", width=1.5)
        self.canvas.create_text(290, 26, text="✕", fill="#f38ba8", font=("Arial", 11, "bold"))
        
        # 2. 三個滾輪窗口
        for i, sym in enumerate(self.reels):
            rx1 = 38 + i * 72
            rx2 = rx1 + 64
            self.canvas.create_rectangle(rx1, 75, rx2, 175, fill="#11111b", outline="#fab387", width=2.0)
            self.canvas.create_line(rx1, 125, rx2, 125, fill="#313244", width=1.0)
            self.canvas.create_text(rx1 + 32, 125, text=sym, font=("微軟正黑體", 26))
            
        # 3. 拉霸桿
        loy = self.lever_offset
        self.canvas.create_line(270, 130, 285, 110 + loy, fill="#cdd6f4", width=4.0)
        self.canvas.create_oval(280, 100 + loy, 296, 116 + loy, fill="#ff5555", outline="#3c2203", width=2.0)
        
        # 4. 狀態提示與持有金幣
        cur_coins = self.monitor.pet_data.get("coins", 0)
        create_outlined_text(self.canvas, 140, 205, text=self.status_msg, fill="#a6e3a1", font=("微軟正黑體", 10, "bold"), outline="#11111b", width=1.0)
        create_outlined_text(self.canvas, 140, 235, text=f"💰 錢包: {cur_coins} 🪙 (每次 10 🪙)", fill="#f9e2af", font=("Consolas", 11, "bold"), outline="#11111b", width=1.0)
        
        # 5. SPIN 按鈕
        btn_col = "#585b70" if self.is_spinning else "#f38ba8"
        self.canvas.create_polygon(
            95, 275, 185, 275, 195, 285, 195, 315,
            185, 325, 95, 325, 85, 315, 85, 285,
            fill=btn_col, outline="#3c2203", width=2.0, smooth=True
        )
        self.canvas.create_text(140, 300, text="SPIN 🎰", fill="#11111b", font=("Arial", 14, "bold"))

    def close_game(self):
        self.monitor.slot_machine_game = None
        self.destroy()





class TokenPetActionMenu(tk.Toplevel):
    """Warm, compact replacement for the native Windows menu in Unity mode."""

    BG = "#fff4d2"
    HEADER_BG = "#f6b942"
    TEXT = "#4f2a14"
    HOVER = "#ffdc83"
    BORDER = "#7b431e"

    def __init__(self, monitor, title, entries, x, y):
        previous = getattr(monitor, "_unity_action_menu", None)
        if previous is not None:
            try:
                previous.destroy()
            except Exception:
                pass

        super().__init__(monitor.root)
        self.monitor = monitor
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=self.BORDER)

        columns = 2 if len(entries) > 5 else 1
        rows = max(1, math.ceil(len(entries) / columns))
        width = 264 if columns == 2 else 236
        header_height = 34
        row_height = 27
        height = header_height + rows * row_height + 8

        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        left = max(8, min(int(x), screen_width - width - 8))
        top = max(8, min(int(y), screen_height - height - 48))
        self.geometry(f"{width}x{height}+{left}+{top}")

        shell = tk.Frame(
            self,
            bg=self.BG,
            highlightbackground=self.BORDER,
            highlightthickness=2,
            bd=0,
        )
        shell.pack(fill=tk.BOTH, expand=True)
        header = tk.Label(
            shell,
            text=title,
            bg=self.HEADER_BG,
            fg=self.TEXT,
            anchor="w",
            padx=11,
            font=("Microsoft JhengHei UI", 9, "bold"),
        )
        header.pack(fill=tk.X, padx=2, pady=(2, 3), ipady=5)

        grid = tk.Frame(shell, bg=self.BG)
        grid.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))
        for column in range(columns):
            grid.grid_columnconfigure(column, weight=1, uniform="menu tokens")

        for index, (label, command) in enumerate(entries):
            row = index % rows
            column = index // rows
            is_exit = "退出寵物" in label
            button_bg = "#ffe1d5" if is_exit else self.BG
            button_fg = "#a33a2b" if is_exit else self.TEXT
            button_hover = "#ffc9b8" if is_exit else self.HOVER
            button = tk.Label(
                grid,
                text=label,
                bg=button_bg,
                fg=button_fg,
                anchor="w",
                padx=7,
                cursor="hand2",
                font=("Microsoft JhengHei UI", 8, "bold" if is_exit else "normal"),
            )
            button.grid(
                row=row,
                column=column,
                sticky="nsew",
                padx=2,
                pady=1,
                ipady=4,
            )
            button.bind(
                "<Enter>",
                lambda _event, widget=button, color=button_hover: widget.configure(bg=color),
            )
            button.bind(
                "<Leave>",
                lambda _event, widget=button, color=button_bg: widget.configure(bg=color),
            )
            button.bind(
                "<ButtonRelease-1>",
                lambda _event, callback=command: self._invoke(callback),
            )

        self.bind("<Escape>", lambda _event: self.destroy())
        self.bind("<ButtonPress-3>", lambda _event: self.destroy())
        self.bind("<FocusOut>", self._on_focus_out)
        self._outside_binding = self.bind_class(
            "all", "<ButtonPress-1>", self._dismiss_if_outside, add="+"
        )
        self._global_left_was_down = self._is_global_left_button_down()
        self.after(20, self._take_focus)
        self.after(25, self._poll_global_dismiss)

    def _take_focus(self):
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _invoke(self, callback):
        self.destroy()
        self.monitor.root.after(0, callback)

    def _dismiss_if_outside(self, event):
        try:
            inside = (
                self.winfo_rootx() <= event.x_root < self.winfo_rootx() + self.winfo_width()
                and self.winfo_rooty() <= event.y_root < self.winfo_rooty() + self.winfo_height()
            )
            if not inside:
                self.destroy()
        except Exception:
            pass

    def _on_focus_out(self, _event):
        self.after(10, self._close_if_focus_left)

    def _close_if_focus_left(self):
        try:
            focused = self.focus_get()
            if focused is None or focused.winfo_toplevel() != self:
                self.destroy()
        except Exception:
            self.destroy()

    @staticmethod
    def _is_global_left_button_down():
        if not IS_WINDOWS:
            return False
        try:
            return bool(ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000)
        except Exception:
            return False

    def _poll_global_dismiss(self):
        """Close like a native popup even when the click targets another process."""
        try:
            if not self.winfo_exists():
                return
            is_down = self._is_global_left_button_down()
            if is_down and not self._global_left_was_down:
                pointer_x, pointer_y = self.winfo_pointerxy()
                inside = (
                    self.winfo_rootx() <= pointer_x < self.winfo_rootx() + self.winfo_width()
                    and self.winfo_rooty() <= pointer_y < self.winfo_rooty() + self.winfo_height()
                )
                if not inside:
                    self.destroy()
                    return
            self._global_left_was_down = is_down
            self.after(25, self._poll_global_dismiss)
        except Exception:
            pass

    def destroy(self):
        binding = getattr(self, "_outside_binding", None)
        if binding:
            try:
                self.unbind_class("all", "<ButtonPress-1>", binding)
            except Exception:
                pass
            self._outside_binding = None
        try:
            super().destroy()
        except Exception:
            pass


class HudWindow(tk.Toplevel):
    """專門用於貼地顯示等級徽章、漸層經驗條、飽食度與地瓜幣的懸浮膠囊風 HUD 看板視窗"""
    def __init__(self, monitor):
        super().__init__(monitor.root)
        self.monitor = monitor
        self.width, self.height = 340, 45
        
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg="#181825")
        if IS_WINDOWS:
            self.attributes("-transparentcolor", "#181825")
            
        # 初始預設坐標移至螢幕外，徹底杜絕 Windows (0,0) 預設正方形閃爍
        self.geometry(f"{self.width}x{self.height}+-2000+-2000")
        
        self.canvas = tk.Canvas(self, bg="#181825", highlightthickness=0, width=self.width, height=self.height)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
    def draw_hud(self, coins, level, xp, satiety, price_str, pet_state):
        self.canvas.delete("all")
        
        # 追逐滑鼠、回到原位、睡覺或空中特技彈跳飛行時不畫 HUD 看板，保持畫面清爽乾淨且絕不遮擋
        if pet_state in ("chase_mouse", "return_home", "sleep", "sleep_futon", "fall", "backflip", "balloon"):
            return
            
        # 繪製基準 Y 座標 (在 45 像素高的視窗中設為 18)
        hud_y = 18
        
        # (0) 繪製懸浮膠囊風外框 (雙層：深色落影 + 極致深色圓角膠囊背板 + 質感茶金邊框)
        # 底部微落影
        self.canvas.create_polygon(
            22, hud_y - 12 + 2, 318, hud_y - 12 + 2, 330, hud_y + 6 + 2, 318, hud_y + 24 + 2,
            22, hud_y + 24 + 2, 10, hud_y + 6 + 2,
            fill="#11111b", outline="", smooth=True
        )
        # 膠囊主體
        self.canvas.create_polygon(
            22, hud_y - 12, 318, hud_y - 12, 330, hud_y + 6, 318, hud_y + 24,
            22, hud_y + 24, 10, hud_y + 6,
            fill="#181825", outline="#3c2203", width=2.0, smooth=True
        )

        # (1) 精緻等級徽章 (Level Badge)
        # 徽章小底卡
        self.canvas.create_rectangle(20, hud_y - 9, 62, hud_y + 5, fill="#313244", outline="#45475a", width=1.0)
        level_str = f"Lv.{level}"
        create_outlined_text(self.canvas, 41, hud_y - 2, text=level_str, fill="#f9e2af", font=("微軟正黑體", 8, "bold"), outline="#11111b", width=1.0)
        
        # 經驗值外框與漸層條 (XP Bar: 紫羅蘭色)
        xp_bar_x1, xp_bar_y1 = 68, hud_y - 7
        xp_bar_x2, xp_bar_y2 = 152, hud_y + 3
        xp_threshold = PET_XP_THRESHOLD + (level - 1) * 50.0
        xp_ratio = max(0.0, min(1.0, xp / xp_threshold))
        xp_fill_width = (xp_bar_x2 - xp_bar_x1) * xp_ratio
        
        # 畫經驗條背景
        self.canvas.create_rectangle(xp_bar_x1, xp_bar_y1, xp_bar_x2, xp_bar_y2, fill="#11111b", outline="#313244", width=1.5)
        # 畫經驗條填充 (高質感雙色)
        if xp_fill_width > 0:
            fill_x2 = xp_bar_x1 + xp_fill_width
            self.canvas.create_rectangle(xp_bar_x1 + 1, xp_bar_y1 + 1, fill_x2 - 1, xp_bar_y2 - 1, fill="#cba6f7", outline="")
            # 頂部亮白高光細線
            self.canvas.create_line(xp_bar_x1 + 1, xp_bar_y1 + 2, fill_x2 - 1, xp_bar_y1 + 2, fill="#f5c2e7", width=1.0)

        # (2) 飽食度條 (Satiety Bar: 蜜桃粉/清新草綠)
        create_outlined_text(self.canvas, 172, hud_y - 2, text="🍴", fill="#a6e3a1", font=("微軟正黑體", 9), outline="#11111b", width=1.0)
        
        sat_bar_x1, sat_bar_y1 = 188, hud_y - 7
        sat_bar_x2, sat_bar_y2 = 272, hud_y + 3
        sat_ratio = max(0.0, min(1.0, satiety / 100.0))
        sat_fill_width = (sat_bar_x2 - sat_bar_x1) * sat_ratio
        
        sat_color = "#f38ba8" if satiety <= 20.0 else "#a6e3a1"
        sat_hl = "#ffb7c5" if satiety <= 20.0 else "#c9f5c4"
        
        # 畫飽食度條背景
        self.canvas.create_rectangle(sat_bar_x1, sat_bar_y1, sat_bar_x2, sat_bar_y2, fill="#11111b", outline="#313244", width=1.5)
        # 畫飽食度條填充
        if sat_fill_width > 0:
            fill_sat_x2 = sat_bar_x1 + sat_fill_width
            self.canvas.create_rectangle(sat_bar_x1 + 1, sat_bar_y1 + 1, fill_sat_x2 - 1, sat_bar_y2 - 1, fill=sat_color, outline="")
            self.canvas.create_line(sat_bar_x1 + 1, sat_bar_y1 + 2, fill_sat_x2 - 1, sat_bar_y1 + 2, fill=sat_hl, width=1.0)

        # (3) 底部貨幣與費用文字 (高對比度排版)
        info_str = f"🪙 {coins:,}  •  {price_str}"
        create_outlined_text(self.canvas, 170, hud_y + 14, text=info_str, fill="#f9e2af", font=("微軟正黑體", 8, "bold"), outline="#11111b", width=1.0)


class ShadowWindow(tk.Toplevel):
    """專門用於貼地顯示、帶有雙層羽化物理高度淡出縮放與不遮擋點擊效果的獨立影子視窗"""
    def __init__(self, monitor):
        super().__init__(monitor.root)
        self.monitor = monitor
        self.width, self.height = 160, 30
        
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg="#181825")
        if IS_WINDOWS:
            self.attributes("-transparentcolor", "#181825")
            
        # 初始預設坐標移至螢幕外，徹底杜絕 Windows (0,0) 預設正方形閃爍
        self.geometry(f"{self.width}x{self.height}+-2000+-2000")
        
        self.canvas = tk.Canvas(self, bg="#181825", highlightthickness=0, width=self.width, height=self.height)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.update_shadow(1.0)
        
    def update_shadow(self, scale_factor):
        self.canvas.delete("all")
        if scale_factor <= 0.05:
            return
            
        cx = self.width / 2
        cy = self.height / 2
        
        # 1. 外層柔和淡陰影 (羽化效果)
        w_out = 46 * scale_factor
        h_out = 4.5 * scale_factor
        self.canvas.create_oval(cx - w_out, cy - h_out, cx + w_out, cy + h_out, fill="#1c1d2b", outline="")
        
        # 2. 內層濃密核心陰影
        w_in = 28 * scale_factor
        h_in = 2.4 * scale_factor
        self.canvas.create_oval(cx - w_in, cy - h_in, cx + w_in, cy + h_in, fill="#11111b", outline="")


class MemoWindow(tk.Toplevel):
    """獨立的日系和紙質感 2.5D 便利貼視窗 (支援自由拖曳縮放 Resizable)"""
    def __init__(self, monitor, memo_id, x, y, text="", w=180, h=160):
        super().__init__(monitor.root)
        self.monitor = monitor
        self.memo_id = memo_id
        self.width = max(140, min(800, int(w)))
        self.height = max(120, min(800, int(h)))
        
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg="#181825") # 透明底色
        if IS_WINDOWS:
            self.attributes("-transparentcolor", "#181825")
            
        self.canvas = tk.Canvas(self, bg="#181825", highlightthickness=0, width=self.width, height=self.height)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # 拖曳與縮放變數
        self._start_x = None
        self._start_y = None
        self._resize_start_x = None
        self._resize_start_y = None
        self._resize_orig_w = None
        self._resize_orig_h = None
        
        # 內嵌編輯文字框 (溫潤和紙底色)
        self.text_widget = tk.Text(
            self.canvas,
            bg="#fdf6e2",
            fg="#3c2203",
            font=("微軟正黑體", 9, "bold"),
            bd=0,
            highlightthickness=0,
            wrap=tk.WORD,
            undo=True
        )
        self.text_widget.insert("1.0", text)
        self.text_window_id = self.canvas.create_window(
            self.width / 2, self.height / 2 + 6,
            window=self.text_widget,
            width=self.width - 32,
            height=self.height - 58
        )
        
        # 渲染便利貼紙張、膠帶、關閉按鈕與縮放把手
        self.draw_memo()
        
        # 綁定自動儲存
        self.text_widget.bind("<KeyRelease>", self.on_text_change)
        
        # 解決 Windows 下 Tkinter 對數字鍵盤 NumPad 的相容性 Bug (防範小數點變 Delete 或方向鍵)
        kp_bindings = {
            "<KP_0>": "0",
            "<KP_1>": "1",
            "<KP_2>": "2",
            "<KP_3>": "3",
            "<KP_4>": "4",
            "<KP_5>": "5",
            "<KP_6>": "6",
            "<KP_7>": "7",
            "<KP_8>": "8",
            "<KP_9>": "9",
            "<KP_Decimal>": ".",
            "<KP_Separator>": "."
        }
        for pattern, char in kp_bindings.items():
            self.text_widget.bind(pattern, lambda e, c=char: self._handle_kp_input(e, c))
        
        # 定位視窗
        self.geometry(f"{self.width}x{self.height}+{int(x)}+{int(y)}")
        
        # 綁定拖曳與縮放事件
        self.canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        self.canvas.bind("<B1-Motion>", self.on_canvas_motion)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        
    def draw_memo(self):
        for item in self.canvas.find_withtag("memo_bg"):
            self.canvas.delete(item)
            
        w, h = self.width, self.height
        
        # 1. 繪製雙層柔和落影 (深色半透明)
        self.canvas.create_rectangle(16, 16, w - 6, h - 4, fill="#11111b", outline="", tags="memo_bg")
        self.canvas.create_rectangle(13, 13, w - 9, h - 7, fill="#181825", outline="", tags="memo_bg")
        
        # 2. 繪製和紙暖米黃紙張主體 (帶有精細邊框)
        self.canvas.create_rectangle(10, 10, w - 10, h - 10, fill="#fdf6e2", outline="#3c2203", width=2.0, tags="memo_bg")
        # 紙張底部淡淡的捲邊陰影線
        self.canvas.create_line(12, h - 12, w - 12, h - 12, fill="#eee0b8", width=1.5, tags="memo_bg")
        
        # 3. 頂部撕裂和紙膠帶裝飾 (置中斜斜貼著的鋸齒膠帶)
        tape_cx = w / 2
        self.canvas.create_polygon(
            tape_cx - 26, 3, tape_cx + 26, 7, tape_cx + 23, 19, tape_cx - 29, 15,
            fill="#d4a373", outline="#3c2203", width=1.5, tags="memo_bg"
        )
        self.canvas.create_line(tape_cx - 24, 9, tape_cx + 21, 13, fill="#faedcd", width=1.5, tags="memo_bg")
        
        # 4. 右上角關閉按鈕 ✕ (精美朱紅色小圓扣)
        close_x = w - 23
        self.canvas.create_oval(close_x - 9, 13, close_x + 9, 31, fill="#f38ba8", outline="#3c2203", width=1.5, tags=("memo_bg", "close_btn"))
        self.canvas.create_text(close_x, 22, text="✕", fill="#11111b", font=("Arial", 8, "bold"), tags=("memo_bg", "close_btn"))
        self.canvas.tag_bind("close_btn", "<ButtonRelease-1>", self.on_close_click)
        
        # 5. 右下角縮放手把 (Resize Grip - 3 條精美和風斜線)
        gx, gy = w - 14, h - 14
        self.canvas.create_line(gx - 4, gy, gx, gy - 4, fill="#b08968", width=1.5, tags=("memo_bg", "resize_grip"))
        self.canvas.create_line(gx - 8, gy, gx, gy - 8, fill="#b08968", width=1.5, tags=("memo_bg", "resize_grip"))
        self.canvas.create_line(gx - 12, gy, gx, gy - 12, fill="#b08968", width=1.5, tags=("memo_bg", "resize_grip"))
        self.canvas.create_rectangle(gx - 14, gy - 14, gx + 2, gy + 2, fill="", outline="", tags=("memo_bg", "resize_grip"))
        
        # 將文字框提升至背景層之上
        self.canvas.tag_raise(self.text_window_id)
        
    def on_canvas_press(self, event):
        w, h = self.width, self.height
        # 檢測是否點擊在右下角縮放區 (22x22)
        if event.x >= w - 24 and event.y >= h - 24:
            self._resize_start_x = event.x_root
            self._resize_start_y = event.y_root
            self._resize_orig_w = self.width
            self._resize_orig_h = self.height
            self._start_x = None
            self._start_y = None
        elif event.y < 35 or event.x < 12 or event.x > w - 12:
            self._start_x = event.x_root - self.winfo_x()
            self._start_y = event.y_root - self.winfo_y()
            self._resize_start_x = None
        else:
            self._start_x = None
            self._start_y = None
            self._resize_start_x = None
            
    def on_canvas_motion(self, event):
        if getattr(self, "_resize_start_x", None) is not None:
            # 處理即時縮放
            dx = event.x_root - self._resize_start_x
            dy = event.y_root - self._resize_start_y
            new_w = max(140, min(800, self._resize_orig_w + dx))
            new_h = max(120, min(800, self._resize_orig_h + dy))
            
            if new_w != self.width or new_h != self.height:
                self.width = new_w
                self.height = new_h
                self.geometry(f"{new_w}x{new_h}+{self.winfo_x()}+{self.winfo_y()}")
                self.canvas.config(width=new_w, height=new_h)
                self.canvas.coords(self.text_window_id, new_w / 2, new_h / 2 + 6)
                self.canvas.itemconfigure(self.text_window_id, width=new_w - 32, height=new_h - 58)
                self.draw_memo()
        elif getattr(self, "_start_x", None) is not None:
            # 處理拖曳
            new_x = event.x_root - self._start_x
            new_y = event.y_root - self._start_y
            self.geometry(f"+{int(new_x)}+{int(new_y)}")
            
            for m in self.monitor.pet_data.get("memos", []):
                if m["id"] == self.memo_id:
                    m["x"] = new_x
                    m["y"] = new_y
                    break
                    
    def on_canvas_release(self, event):
        if getattr(self, "_resize_start_x", None) is not None or getattr(self, "_start_x", None) is not None:
            self._resize_start_x = None
            self._start_x = None
            # 儲存便利貼尺寸與坐標
            for m in self.monitor.pet_data.get("memos", []):
                if m["id"] == self.memo_id:
                    m["w"] = self.width
                    m["h"] = self.height
                    m["x"] = self.winfo_x()
                    m["y"] = self.winfo_y()
                    break
            self.monitor.save_pet_savegame()
            
    def on_text_change(self, event=None):
        text_content = self.text_widget.get("1.0", tk.END).strip()
        for m in self.monitor.pet_data.get("memos", []):
            if m["id"] == self.memo_id:
                m["text"] = text_content
                break
        self.monitor.save_pet_savegame()
        
    def on_close_click(self, event):
        self.monitor.trigger_eat_memo(self.memo_id)

    def _handle_kp_input(self, event, char):
        self.text_widget.insert(tk.INSERT, char)
        self.on_text_change()
        return "break"


class UnityFurnitureProxy:
    """Tk-compatible position model for furniture rendered by Unity.

    Existing game physics intentionally talks to the same winfo-style surface,
    which lets the Unity migration preserve every old interaction without
    duplicating the behaviour engine or deleting the Tk fallback.
    """

    SIZES = {
        "futon": (180, 100),
        "laptop": (180, 115),
        "night_lamp": (120, 110),
        "succulent_pot": (110, 100),
        "lazy_sofa": (160, 100),
        "pixel_tv": (140, 110),
        "kotatsu": (170, 100),
        "trampoline": (140, 60),
    }

    def __init__(self, monitor, item_id):
        self.monitor = monitor
        self.item_id = item_id
        self.width, self.height = self.SIZES.get(item_id, (140, 80))
        screen_w = monitor.root.winfo_screenwidth()
        screen_h = monitor.root.winfo_screenheight()
        default_x = (screen_w - self.width) // 2 + (
            150 if item_id == "laptop" else -150
        )
        default_y = screen_h - self.height - 120
        saved = monitor.pet_data.get("furniture_positions", {}).get(item_id, {})
        self.x = int(saved.get("x", default_x))
        self.y = int(saved.get("y", default_y))
        if self.x < -50 or self.x > screen_w - 50:
            self.x = default_x
        if self.y < -50 or self.y > screen_h - 50:
            self.y = default_y
        self._exists = True

    def winfo_x(self):
        return self.x

    def winfo_y(self):
        return self.y

    def winfo_width(self):
        return self.width

    def winfo_height(self):
        return self.height

    def winfo_exists(self):
        return self._exists

    def set_position(self, x, y):
        self.x = int(x)
        self.y = int(y)

    def geometry(self, value):
        match = re.search(r"\+(-?\d+)\+(-?\d+)$", str(value))
        if match:
            self.set_position(match.group(1), match.group(2))

    def attributes(self, *_args, **_kwargs):
        return None

    def lift(self):
        return None

    def destroy(self):
        self._exists = False

    def trigger_bounce(self):
        bridge = getattr(self.monitor, "unity_renderer", None)
        if bridge is not None:
            bridge.trigger_furniture(self.item_id, "bounce")


class FurnitureWindow(tk.Toplevel):
    def __init__(self, monitor, item_id):
        super().__init__(monitor.root)
        self.monitor = monitor
        self.item_id = item_id
        
        # 凹陷回彈物理參數 (專用於蹦蹦床的擠壓動畫)
        self.depress_val = 0.0
        self.depress_speed = 0.0
        self.shockwave_r = 0.0
        self._bounce_job = None
        
        if item_id == "futon":
            self.width, self.height = 180, 100
        elif item_id == "laptop":
            self.width, self.height = 180, 115
        elif item_id == "night_lamp":
            self.width, self.height = 120, 110
        elif item_id == "succulent_pot":
            self.width, self.height = 110, 100
        elif item_id == "lazy_sofa":
            self.width, self.height = 160, 100
        elif item_id == "pixel_tv":
            self.width, self.height = 140, 110
        elif item_id == "kotatsu":
            self.width, self.height = 170, 100
        else: # trampoline
            self.width, self.height = 140, 60
            
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg="#111111")
        if IS_WINDOWS:
            self.attributes("-transparentcolor", "#111111")
            
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        default_x = (screen_w - self.width) // 2 + (150 if item_id == "laptop" else -150)
        default_y = screen_h - self.height - 120
        
        # 優先讀取保存的家具位置
        saved_pos = self.monitor.pet_data.get("furniture_positions", {}).get(item_id, {})
        start_x = saved_pos.get("x", default_x)
        start_y = saved_pos.get("y", default_y)
        
        # 邊界防護
        if start_x < -50 or start_x > screen_w - 50: start_x = default_x
        if start_y < -50 or start_y > screen_h - 50: start_y = default_y
        
        self.geometry(f"{self.width}x{self.height}+{int(start_x)}+{int(start_y)}")
        
        self.canvas = tk.Canvas(self, bg="#111111", highlightthickness=0, width=self.width, height=self.height)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.draw_furniture()
        
        self.canvas.bind("<Button-1>", self.on_drag_start)
        self.canvas.bind("<B1-Motion>", self.on_drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self.on_drag_end)
        self.canvas.bind("<Button-3>", self.show_context_menu)
        
    def trigger_bounce(self):
        """地瓜球踩上彈簧床時，觸發凹陷回彈動畫與霓虹環形波紋"""
        if self.item_id == "trampoline":
            self.depress_speed += 4.5  # 累加向下衝擊速度
            self.shockwave_r = 5.0
            if self._bounce_job is None:
                self.animate_bounce()
            
    def animate_bounce(self):
        """彈力物理回彈震盪模擬 (防重入單一計時器)"""
        if not self.winfo_exists():
            self._bounce_job = None
            return
            
        k = 0.22   # 彈力彈簧常數
        c = 0.16   # 阻尼係數 (防止無限震盪)
        accel = -k * self.depress_val - c * self.depress_speed
        self.depress_speed += accel
        self.depress_val += self.depress_speed
        
        if getattr(self, "shockwave_r", 0.0) > 0.0:
            self.shockwave_r += 3.5
            if self.shockwave_r > 48.0:
                self.shockwave_r = 0.0
                
        self.draw_furniture()
        
        # 當震動幅度仍大於微小門檻時，持續更新
        if abs(self.depress_val) > 0.05 or abs(self.depress_speed) > 0.05 or getattr(self, "shockwave_r", 0.0) > 0.0:
            self._bounce_job = self.after(16, self.animate_bounce)
        else:
            self.depress_val = 0.0
            self.depress_speed = 0.0
            self.shockwave_r = 0.0
            self._bounce_job = None
            self.draw_furniture()
        
    def draw_furniture(self):
        self.canvas.delete("all")
        if self.item_id == "futon":
            # 1. 榻榻米蓆木邊底座 (立體厚度與和風細紋)
            self.canvas.create_rectangle(15, 35, 165, 88, fill="#ecd3da", outline="#313244", width=2)
            # 榻榻米蓆面 (草編米黃)
            self.canvas.create_rectangle(20, 40, 160, 83, fill="#f2cdcd", outline="#45475a", width=1)
            # 蓆面橫向草紋細線
            for y_line in range(45, 80, 7):
                self.canvas.create_line(22, y_line, 158, y_line, fill="#e8b4b8", width=1.0)
            
            # 2. 柔軟蓬鬆凹陷枕頭 (白色、圓潤高光、微陰影)
            self.canvas.create_rectangle(25, 45, 55, 78, fill="#ffffff", outline="#313244", width=2)
            self.canvas.create_line(40, 48, 40, 75, fill="#b4befe", width=1.5) # 枕頭中央下陷摺痕
            # 枕頭柔光
            self.canvas.create_line(27, 47, 53, 47, fill="#ffffff", width=1.5)
            
            # 3. 厚棉被外蓋 (莫蘭迪藍綠色，帶有可愛反摺被頭)
            self.canvas.create_rectangle(65, 25, 168, 92, fill="#89b4fa", outline="#313244", width=2)
            # 反摺被頭
            self.canvas.create_rectangle(60, 25, 75, 92, fill="#f5e0dc", outline="#313244", width=1.5)
            # 棉被刺繡星點裝飾
            for x in range(90, 150, 18):
                self.canvas.create_line(x, 40, x + 8, 48, fill="#cdd6f4", width=2)
                self.canvas.create_line(x, 70, x + 8, 62, fill="#cdd6f4", width=2)
                self.canvas.create_oval(x + 3, 54, x + 5, 56, fill="#f9e2af", outline="")
                
        elif self.item_id == "laptop":
            # 💻 2.5D 3/4 等角透視精緻筆電：右側立體螢幕面向左側地瓜球 + 左下方斜向鍵盤底座 + RGB 背光 + 代碼滾動
            # 1. 溫暖黑胡桃木辦公桌板 (底座平台)
            self.canvas.create_rectangle(10, 84, 170, 96, fill="#252535", outline="#11111b", width=1.5)
            self.canvas.create_line(12, 85, 168, 85, fill="#45475a", width=1.0) # 桌板邊緣高光
            # 桌腳 (金屬細柱)
            self.canvas.create_line(24, 96, 24, 110, fill="#1e1e2e", width=3)
            self.canvas.create_line(156, 96, 156, 110, fill="#1e1e2e", width=3)
            
            # 2. 右側立體展開上螢幕 (面向左前方地瓜球與使用者，3/4 透視)
            # 螢幕金屬外殼背框
            self.canvas.create_polygon(
                95, 14, 158, 22, 152, 74, 88, 66,
                fill="#313244", outline="#181825", width=2.0
            )
            # 頂部視訊鏡頭與綠色指示燈
            self.canvas.create_oval(124, 17, 128, 21, fill="#11111b", outline="")
            self.canvas.create_oval(132, 18, 134, 20, fill="#a6e3a1", outline="")
            
            # 發光螢幕面板 (深邃夜幕藍)
            self.canvas.create_polygon(
                100, 20, 152, 27, 147, 69, 94, 62,
                fill="#181825", outline="#11111b", width=1.0
            )
            
            # 螢幕上的彩色程式碼行 (透視斜線)
            self.canvas.create_line(104, 28, 136, 32, fill="#a6e3a1", width=1.5) # const dev = true;
            self.canvas.create_line(104, 36, 146, 42, fill="#f38ba8", width=1.5) # function code() {
            self.canvas.create_line(108, 44, 140, 48, fill="#f9e2af", width=1.5) #   earn_token();
            self.canvas.create_line(108, 52, 132, 55, fill="#89b4fa", width=1.5) #   level_up();
            self.canvas.create_line(104, 60, 114, 61, fill="#cba6f7", width=1.5) # }
            
            # 閃爍的綠色打字游標
            if int(time.time() * 3) % 2 == 0:
                self.canvas.create_line(116, 59, 116, 64, fill="#a6e3a1", width=1.8)
                
            # 螢幕右下角微光小地瓜 Logo 水印
            self.canvas.create_oval(136, 60, 142, 65, fill="#f9e2af", outline="")
            
            # 3. 左下方 2.5D 3/4 等角斜向鍵盤底座
            # 機身金屬斜面底座
            self.canvas.create_polygon(
                88, 66, 152, 74, 122, 92, 48, 82,
                fill="#45475a", outline="#181825", width=2.0
            )
            # 鍵盤凹槽面板
            self.canvas.create_polygon(
                84, 69, 142, 77, 116, 88, 58, 80,
                fill="#1e1e2e", outline="#313244", width=1.0
            )
            
            # 鍵帽矩陣透視橫線與 RGB 呼吸背光
            t_col = time_ms() / 500.0
            rgb_cols = ["#a6e3a1", "#89b4fa", "#f5c2e7", "#f9e2af", "#cba6f7"]
            c1 = rgb_cols[int(t_col) % len(rgb_cols)]
            c2 = rgb_cols[(int(t_col) + 1) % len(rgb_cols)]
            
            self.canvas.create_line(80, 72, 136, 79, fill=c1, width=1.2) # 上排鍵盤發光條
            self.canvas.create_line(70, 77, 126, 84, fill=c2, width=1.2) # 下排鍵盤發光條
            
            # 鍵帽垂直透視小分割線
            for kx in range(68, 130, 12):
                self.canvas.create_line(kx, 71, kx - 4, 84, fill="#313244", width=1.0)
                
            # 底部觸控板 (Trackpad)
            self.canvas.create_polygon(
                74, 82, 94, 85, 88, 90, 68, 87,
                fill="#313244", outline="#181825", width=1.0
            )
            
        elif self.item_id == "trampoline":
            # 1. 繪製金屬支撐架 (八字撐腳與防滑橡膠頭)
            # 左腳
            self.canvas.create_line(25, 25, 12, 53, fill="#585b70", width=4)
            self.canvas.create_oval(8, 51, 16, 55, fill="#11111b", outline="")
            # 右腳
            self.canvas.create_line(115, 25, 128, 53, fill="#585b70", width=4)
            self.canvas.create_oval(124, 51, 132, 55, fill="#11111b", outline="")
            # 中間加固腳
            self.canvas.create_line(70, 26, 70, 52, fill="#45475a", width=3.5)
            self.canvas.create_oval(66, 50, 74, 54, fill="#11111b", outline="")
            
            # 2. 繪製四周鋼拉彈簧 (一圈 16 根拉力線)
            dep = getattr(self, "depress_val", 0.0)
            for i in range(16):
                angle = i * (2 * math.pi / 16)
                cos_a = math.cos(angle)
                sin_a = math.sin(angle)
                
                # 外環框邊緣
                ex = 70 + 55 * cos_a
                ey = 25 + 11 * sin_a
                
                # 內側網布邊緣 (隨 depress_val 動態向下拉伸)
                ix = 70 + 42 * cos_a
                iy = 25 + dep + 8 * sin_a
                
                self.canvas.create_line(ex, ey, ix, iy, fill="#9399b2", width=1.5)
                
            # 3. 繪製中間黑色跳躍彈性布面
            self.canvas.create_oval(70 - 42, 25 + dep - 8, 70 + 42, 25 + dep + 8, fill="#1e1e2e", outline="#313244", width=1.5)
            
            # 4. 繪製金屬框邊緣的安全防護橘色軟墊
            self.canvas.create_oval(15, 14, 125, 36, outline="#fab387", width=3)
            
            # 5. 彈跳時向外擴散的霓虹環形波紋 (Shockwave Ripple)
            sw_r = getattr(self, "shockwave_r", 0.0)
            if sw_r > 0.0:
                self.canvas.create_oval(70 - sw_r, 25 - sw_r * 0.25, 70 + sw_r, 25 + sw_r * 0.25,
                                        outline="#f9e2af", width=1.5)

        elif self.item_id == "night_lamp":
            # 🏮 蘑菇小夜燈 (暖黃柔光 + 蘑菇傘蓋 + 溫馨呼吸光暈)
            t_glow = time_ms() / 600.0
            glow_r = 4.0 * math.sin(t_glow)
            # 1. 外層溫暖呼吸光暈
            self.canvas.create_oval(15 - glow_r, 10 - glow_r, 105 + glow_r, 95 + glow_r, fill="", outline="#f9e2af", width=1.5)
            self.canvas.create_oval(25, 20, 95, 85, fill="", outline="#ffe875", width=2.0)
            # 2. 原木底座
            self.canvas.create_oval(35, 82, 85, 98, fill="#5a3d28", outline="#3c2203", width=2.0)
            self.canvas.create_oval(40, 84, 80, 94, fill="#8c6239", outline="")
            # 3. 彎曲金屬燈桿
            self.canvas.create_line(60, 85, 60, 48, fill="#45475a", width=3.5)
            # 4. 發光蘑菇傘蓋 (可愛粉紅紅傘 + 白斑點)
            self.canvas.create_polygon(30, 52, 90, 52, 60, 22, fill="#f38ba8", outline="#3c2203", width=2.0)
            # 白斑點
            self.canvas.create_oval(42, 38, 48, 44, fill="#ffffff", outline="")
            self.canvas.create_oval(72, 38, 78, 44, fill="#ffffff", outline="")
            self.canvas.create_oval(57, 27, 63, 33, fill="#ffffff", outline="")
            # 5. 蘑菇底下的暖黃發光小燈珠
            self.canvas.create_oval(52, 48, 68, 62, fill="#fffca8", outline="#3c2203", width=1.5)
            self.canvas.create_oval(56, 52, 64, 58, fill="#ffffff", outline="")
            
        elif self.item_id == "succulent_pot":
            # 🪴 療癒多肉小盆栽 (圓潤多肉厚葉片 + 白瓷盆 + 泥土 + 粉紅小花)
            # 1. 白瓷花盆
            self.canvas.create_polygon(32, 54, 78, 54, 70, 88, 40, 88, fill="#fdf6e2", outline="#3c2203", width=2.0)
            # 花盆邊緣藍色小裝飾線
            self.canvas.create_line(34, 60, 76, 60, fill="#89b4fa", width=1.5)
            # 2. 盆口深色泥土
            self.canvas.create_oval(32, 48, 78, 58, fill="#453225", outline="#3c2203", width=1.5)
            # 3. 多肉肥厚葉片 (層疊水滴厚葉)
            self.canvas.create_oval(25, 38, 45, 52, fill="#a6e3a1", outline="#3c2203", width=1.2)
            self.canvas.create_oval(65, 38, 85, 52, fill="#a6e3a1", outline="#3c2203", width=1.2)
            self.canvas.create_oval(34, 28, 52, 46, fill="#94e2d5", outline="#3c2203", width=1.2)
            self.canvas.create_oval(58, 28, 76, 46, fill="#94e2d5", outline="#3c2203", width=1.2)
            self.canvas.create_oval(46, 20, 64, 40, fill="#f5c2e7", outline="#3c2203", width=1.2)
            # 頂部綻放的小粉花
            self.canvas.create_oval(51, 16, 59, 24, fill="#f38ba8", outline="")
            self.canvas.create_oval(53, 18, 57, 22, fill="#ffe875", outline="")
            
        elif self.item_id == "lazy_sofa":
            # 🪑 柔軟懶人豆袋沙發 (蓬鬆大底座 + 兩側扶手 + 櫻花花瓣印花)
            # 1. 蓬鬆大底座
            self.canvas.create_oval(12, 28, 148, 90, fill="#f2cdcd", outline="#3c2203", width=2.0)
            # 2. 凹陷坐墊與靠背
            self.canvas.create_oval(32, 14, 128, 62, fill="#f5e0dc", outline="#3c2203", width=2.0)
            self.canvas.create_oval(35, 42, 125, 76, fill="#eba0ac", outline="", width=0)
            # 3. 兩側蓬鬆扶手枕
            self.canvas.create_oval(14, 38, 42, 72, fill="#f2cdcd", outline="#3c2203", width=1.5)
            self.canvas.create_oval(118, 38, 146, 72, fill="#f2cdcd", outline="#3c2203", width=1.5)
            # 4. 櫻花和風波點印花
            for px_c, py_c in [(48, 38), (80, 28), (112, 38), (60, 65), (100, 65)]:
                self.canvas.create_oval(px_c - 2, py_c - 2, px_c + 2, py_c + 2, fill="#f38ba8", outline="")
                
        elif self.item_id == "pixel_tv":
            # 📺 復古像素小電視 (復古映像管電視 + 4 大動態頻道)
            # 1. 木質外框
            self.canvas.create_rectangle(12, 22, 128, 98, fill="#8c6239", outline="#3c2203", width=2.0)
            self.canvas.create_line(14, 24, 126, 24, fill="#b7824f", width=1.0) # 頂部木紋高光
            # 2. 頂部 V 型金屬天線
            self.canvas.create_line(70, 22, 45, 6, fill="#cdd6f4", width=2.0)
            self.canvas.create_line(70, 22, 95, 6, fill="#cdd6f4", width=2.0)
            self.canvas.create_oval(41, 2, 49, 10, fill="#ff5555", outline="")
            self.canvas.create_oval(91, 2, 99, 10, fill="#ff5555", outline="")
            # 3. 映像管螢幕
            self.canvas.create_rectangle(22, 32, 98, 88, fill="#11111b", outline="#313244", width=1.5)
            
            # 4 大動態切換頻道 (每 4 秒輪播一個頻道)
            ch = int(time.time() / 4.0) % 4
            if ch == 0:
                # 頻道 1: 吃豆人小遊戲 👾
                self.canvas.create_text(60, 60, text="👾  •  •  🍠", font=("微軟正黑體", 10), fill="#fab387")
            elif ch == 1:
                # 頻道 2: 天氣預報 ☀️
                self.canvas.create_text(60, 52, text="☀️ 晴朗 26°C", font=("微軟正黑體", 9, "bold"), fill="#f9e2af")
                self.canvas.create_line(30, 68, 90, 68, fill="#89b4fa", width=1.0)
            elif ch == 2:
                # 頻道 3: 地瓜大冒險 💖
                self.canvas.create_oval(52, 48, 68, 64, fill="#a6e3a1", outline="")
                self.canvas.create_text(60, 56, text="💖", font=("微軟正黑體", 11))
            else:
                # 頻道 4: 彩色電視檢驗圖 📺
                cols = ["#ff5555", "#fab387", "#f9e2af", "#a6e3a1", "#89b4fa", "#cba6f7"]
                for ci, c in enumerate(cols):
                    self.canvas.create_rectangle(24 + ci * 12, 34, 36 + ci * 12, 86, fill=c, outline="")
                    
            # 4. 右側旋鈕與喇叭柵格
            self.canvas.create_oval(106, 38, 118, 50, fill="#313244", outline="#11111b", width=1.0)
            self.canvas.create_oval(106, 54, 118, 66, fill="#313244", outline="#11111b", width=1.0)
            self.canvas.create_line(104, 76, 120, 76, fill="#313244", width=1.5)
            self.canvas.create_line(104, 82, 120, 82, fill="#313244", width=1.5)
            
        elif self.item_id == "kotatsu":
            # 🍵 日式暖桌被爐 (木質底座 + 橘紅格紋暖被 + 原木桌板 + 熱茶小橘子 🍊)
            # 1. 木質底座
            self.canvas.create_rectangle(10, 80, 160, 92, fill="#585b70", outline="#313244", width=1.5)
            # 2. 鋪張開的暖被 (莫蘭迪橘紅格紋)
            self.canvas.create_polygon(16, 80, 38, 38, 132, 38, 154, 80, fill="#fab387", outline="#3c2203", width=2.0)
            self.canvas.create_line(48, 40, 32, 80, fill="#e78284", width=1.5)
            self.canvas.create_line(85, 40, 85, 80, fill="#e78284", width=1.5)
            self.canvas.create_line(122, 40, 138, 80, fill="#e78284", width=1.5)
            # 3. 暖被上的原木桌板
            self.canvas.create_rectangle(32, 28, 138, 38, fill="#5a3d28", outline="#3c2203", width=2.0)
            self.canvas.create_line(34, 30, 136, 30, fill="#8c6239", width=1.0)
            # 4. 桌上裝有蜜柑的木盤 🍊 與熱茶杯 🍵
            self.canvas.create_oval(60, 20, 74, 30, fill="#fe640b", outline="#3c2203", width=1.2)
            self.canvas.create_oval(65, 18, 69, 22, fill="#a6e3a1", outline="")
            # 熱茶杯
            self.canvas.create_rectangle(96, 20, 108, 30, fill="#fdf6e2", outline="#3c2203", width=1.2)
            self.canvas.create_oval(96, 18, 108, 22, fill="#a6e3a1", outline="")
            # 5. 裊裊熱呼呼蒸氣
            t_steam = time_ms() / 200.0
            sy1 = 4.0 * math.sin(t_steam)
            sy2 = 4.0 * math.cos(t_steam)
            self.canvas.create_line(100, 16, 98 + sy1 * 0.4, 8, fill="#ffffff", width=1.5, smooth=True)
            self.canvas.create_line(104, 16, 106 + sy2 * 0.4, 6, fill="#ffffff", width=1.5, smooth=True)
            
    def on_drag_start(self, event):
        self._start_x_root = event.x_root
        self._start_y_root = event.y_root
        self._start_win_x = self.winfo_x()
        self._start_win_y = self.winfo_y()
        self.lift()
        
    def on_drag_motion(self, event):
        dx = event.x_root - self._start_x_root
        dy = event.y_root - self._start_y_root
        new_x = self._start_win_x + dx
        new_y = self._start_win_y + dy
        self.geometry(f"+{int(new_x)}+{int(new_y)}")

    def on_drag_end(self, event):
        """拖曳放開時記錄坐標存檔"""
        try:
            positions = self.monitor.pet_data.setdefault("furniture_positions", {})
            positions[self.item_id] = {
                "x": self.winfo_x(),
                "y": self.winfo_y()
            }
            self.monitor.save_pet_savegame()
        except Exception:
            pass
        
    def show_context_menu(self, event):
        menu = tk.Menu(self, tearoff=0, bg="#1e1e2e", fg="#cdd6f4", activebackground="#f5c2e7", activeforeground="#11111b")
        menu.add_command(label="✕ 回收此家具 (Despawn)", command=self.despawn_self)
        menu.tk_popup(event.x_root, event.y_root)
        
    def despawn_self(self):
        self.monitor.despawn_furniture(self.item_id)


# ──────────────────────────────────────────────────
# 程式入口點
# ──────────────────────────────────────────────────
def _start_app():
    import sys
    
    # 單實例檢查 (防止多個相同目錄的實例同時執行導致存檔與熱更新互鎖)
    if not check_single_instance():
        # The normal integrated launcher uses pythonw. A modal here can become
        # invisible and leave a duplicate background process behind, so a
        # second integrated launch simply exits while the existing pet stays.
        if "--standalone" in sys.argv and "--unity-poc" in sys.argv:
            return
        try:
            temp_r = tk.Tk()
            temp_r.withdraw()
            messagebox.showinfo("地瓜球桌寵", "地瓜球已經在桌面上陪伴您囉！\n（若未看見請檢查工作列或按快捷鍵喚醒）")
            temp_r.destroy()
        except Exception:
            pass
        return

    if "--standalone" in sys.argv:
        main_root = tk.Tk()
        try: main_root.withdraw()
        except: pass
        EmojinokoMonitor(main_root, token="", phison_token="", name="主人", email="", password="")
        main_root.mainloop()
        return

    root = tk.Tk()

    def on_login_success(token, phison_token, name, email, password):
        try: root.destroy()
        except: pass
        main_root = tk.Tk()
        try: main_root.withdraw()
        except: pass
        # 啟動地瓜球桌寵
        EmojinokoMonitor(main_root, token, phison_token, name, email, password)
        main_root.mainloop()

    # 複用 LoginWindow，使用者帳密完全無縫對接！
    LoginWindow(root, on_login_success)
    root.mainloop()


if __name__ == "__main__":
    _install_runtime_log()
    _start_app()
