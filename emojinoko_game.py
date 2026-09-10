import tkinter as tk
import math
import os
import random
import time

def interpolate_color(color_start, color_end, factor):
    """在兩個十六進位顏色之間進行線性插值，模擬漸層"""
    factor = max(0.0, min(1.0, factor))
    r1, g1, b1 = int(color_start[1:3], 16), int(color_start[3:5], 16), int(color_start[5:7], 16)
    r2, g2, b2 = int(color_end[1:3], 16), int(color_end[3:5], 16), int(color_end[5:7], 16)
    
    r = int(r1 + (r2 - r1) * factor)
    g = int(g1 + (g2 - g1) * factor)
    b = int(b1 + (b2 - b1) * factor)
    return f"#{r:02x}{g:02x}{b:02x}"

def create_outlined_text(canvas, x, y, text, fill, font, outline="#11111b", width=1.5, tags="character"):
    """在 Canvas 上繪製帶有深色背景描邊/外陰影的高對比度文字 (確保在白底與黑底均極度清晰)"""
    shadow_ids = []
    offsets = [(-width, -width), (-width, width), (width, -width), (width, width),
               (-width, 0), (width, 0), (0, -width), (0, width)]
    for dx, dy in offsets:
        sid = canvas.create_text(x + dx, y + dy, text=text, fill=outline, font=font, tags=tags)
        shadow_ids.append(sid)
    main_id = canvas.create_text(x, y, text=text, fill=fill, font=font, tags=tags)
    shadow_ids.append(main_id)
    return shadow_ids

# ===================== 經濟與數值平衡參數設定區 =====================
# 這些參數是全局常數，未來如果覺得遊戲節奏不對，可以直接在此處微調數值。
PET_BASE_EARNING = 1.0       # 基礎產量：每分鐘在「上班狀態」下被動產生的地瓜幣 (🪙)
PET_XP_THRESHOLD = 100.0     # 升級難度：基礎升級門檻 (XP)
PET_LEVEL_MULTIPLIER = 0.1   # 等級加成：每升一級，被動產幣效率增加 10% (即 1 + (Level-1)*0.1)
PET_SATIETY_DECAY = 1.0      # 飢餓速度：每 8 分鐘扣除的飽食度百分比 (%)
PET_SATIETY_THRESHOLD = 20.0 # 飢餓臨界點：飽食度低於此百分比時，產幣效率減半且寵物進入躺平睡覺狀態

# 真實 Token 轉換比例 (用於對接 Token Monitor 數據)
TOKEN_TO_XP_RATIO = 0.01     # 經驗轉換率：1 個 Prompt Token 轉換為 0.01 XP (原 0.15)
TOKEN_TO_SATIETY = 0.20      # 飽食恢復率：1 個 Prompt Token 恢復 0.2% 飽食度
TOKEN_TO_COIN = 0.05         # 產幣收益：1 個 Completion Token 轉換為 0.05 顆地瓜幣 (原 1.0)
# =================================================================


# ──────────────────────────────────────────────────
# 寵物抽象基底類別 (BasePet)
# ──────────────────────────────────────────────────
class BasePet:
    """
    這是一個通用的寵物抽象類別。
    主視窗 emojinoko_monitor.py 只會調用此類別定義的標準介面。
    未來若要換成別的寵物（例如貓咪或史萊姆），只需寫一個類別繼承 BasePet 並實作對應的方法即可，不需修改主程式。
    """
    def __init__(self, canvas, center_x, center_y):
        self.canvas = canvas
        self.cx = center_x
        self.cy = center_y
        self.state = "idle"  # 狀態機: "idle"(呼吸/發呆), "walk"(散步), "roll"(翻滾), "sleep"(躺平), "eat"(吃東西)

    def update_physics(self):
        """每幀更新物理與運動數值（如速度、比例、滾動角度）"""
        pass

    def draw(self, name="", price_str="", coins=0, level=1, xp=0.0, satiety=100.0):
        """在畫布上渲染寵物以及看板資訊與 HUD"""
        pass

    def handle_event(self, event_type, *args):
        """處理外部事件 (例如受擊 'poke', 餵食 'feed', 睡覺 'sleep')"""
        pass

    def restore_eye(self):
        """恢復正常眼睛與表情狀態"""
        pass


# ──────────────────────────────────────────────────
# 經典地瓜球桌寵實作 (EmojinokoPet)
# ──────────────────────────────────────────────────
class EmojinokoPet(BasePet):
    def __init__(self, canvas, center_x, center_y):
        super().__init__(canvas, center_x, center_y)
        
        # 物理震盪變數 (用於果凍般的彈性拉伸/壓扁效果)
        self.scale_x = 1.0
        self.scale_y = 1.0
        self.vel_scale_x = 0.0
        self.vel_scale_y = 0.0
        self.k = 0.13          # 彈簧彈力係數 (越小越軟)
        self.damping = 0.85    # 阻尼係數 (控制回彈次數，接近1會一直彈，接近0立刻停)

        # 散步 (Walk) 狀態變數
        self.walk_dir = 1      # 行走方向：1 表示向右，-1 表示向左
        self.walk_speed = 0.4  # 行走速度
        self.walk_target_x = center_x
        
        # 翻滾 (Roll) 狀態變數
        self.roll_angle = 0.0  # 當前旋轉弧度 (弧度制)
        self.roll_speed = 0.0  # 旋轉角速度
        
        # 眼睛與嘴巴表情控制
        self.eye_state = "normal"    # "normal"(小圓點), "happy"(彎彎眼^^), "blink"(眨眼線條)
        self.mouth_state = "normal"  # "normal"(w貓咪嘴), "open"(O型嘴)
        self.look_offset_x = 0.0     # 眼珠注視偏移 (用於追蹤掉落的 Token)
        self.look_offset_y = 0.0
        
        # 舉牌看板狀態
        self.show_board = False      # 是否正在舉看板 (雙擊地瓜球切換)
        
        # 基準地瓜球尺寸
        self.r = 52

        # 粒子系統與文字特效緩存
        self.particles = []          # 儲存掉落 Token 的粒子陣列
        self.text_popups = []        # 儲存上升 XP 文字的陣列

        # 隨機日常動作與 Coffee Buff 變數
        self.doze_timer = 0
        self.bubble_timer = 0
        self.bubble_scale = 0.0
        self.stretch_timer = 0
        self.coffee_timer = 0.0
        self.coffee_sparks = []
        self.is_overtime = False
        self.drink_timer = 0
        self.equipped_accessory = None
        self.fever_timer = 0
        self.wave_timer = 0
        self.custom_board_text = None
        self.candy_timer = 0
        self.ramen_timer = 0
        self.bubble_tea_timer = 0
        self.spicy_timer = 0
        self.backflip_timer = 0
        self.balloon_timer = 0
        self.ice_timer = 0
        self.singing_timer = 0
        self.rabbit_pop_timer = 0
        self.eat_type = ""
        self.matcha_timer = 0

    def rotate_point(self, dx, dy, angle):
        """
        二維旋轉矩陣運算 (2D Rotation Matrix)
        將相對於地瓜球中心 (cx, cy) 的偏移坐標 (dx, dy) 旋轉 angle 弧度。
        數學公式:
        x' = x * cos(θ) - y * sin(θ)
        y' = x * sin(θ) + y * cos(θ)
        這能讓地瓜球在翻滾時，眼睛、眉毛、嘴巴和四肢都完美跟著身體旋轉，呈現高品質的動畫！
        """
        cos_val = math.cos(angle)
        sin_val = math.sin(angle)
        rx = dx * cos_val - dy * sin_val
        ry = dx * sin_val + dy * cos_val
        return rx, ry

    def handle_event(self, event_type, *args):
        """事件接收器"""
        if event_type == "poke":
            # 被戳時觸發擠壓物理，並隨機給予翻滾的旋轉角速度
            self.vel_scale_x = 0.35
            self.vel_scale_y = -0.35
            self.state = "roll"
            self.roll_speed = random.choice([-0.25, -0.15, 0.15, 0.25])
            self.eye_state = "dizzy"
            self.mouth_state = "open"
        elif event_type == "feed":
            # 餵食時嘴巴張開、眼睛變開心，身體產生輕微下沉回彈
            self.mouth_state = "open"
            self.eye_state = "happy"
            self.vel_scale_y = -0.18
            self.vel_scale_x = 0.12

    def restore_eye(self):
        """餵食結束後恢復正常表情與眼睛"""
        if self.eye_state == "happy":
            self.eye_state = "normal"
        if self.mouth_state == "open" and self.state != "roll":
            self.mouth_state = "normal"

    def update_physics(self):
        """每幀物理計算 (約 60 FPS 執行)"""
        # 1. 彈簧阻尼簡諧運動系統 (對縮放比例進行回歸彈性計算)
        # 加速度 = -k * 偏移位移
        acc_x = -self.k * (self.scale_x - 1.0)
        self.vel_scale_x = (self.vel_scale_x + acc_x) * self.damping
        self.scale_x += self.vel_scale_x

        acc_y = -self.k * (self.scale_y - 1.0)
        self.vel_scale_y = (self.vel_scale_y + acc_y) * self.damping
        self.scale_y += self.vel_scale_y

        # Coffee Buff 效果計時與粒子生成
        if self.coffee_timer > 0:
            self.coffee_timer -= 0.016
            w = self.r * self.scale_x
            h = self.r * self.scale_y
            if random.random() < 0.25:
                self.coffee_sparks.append({
                    "dx": random.uniform(-w * 0.8, w * 0.8),
                    "dy": random.uniform(-h * 0.8, h * 0.8),
                    "vy": random.uniform(-1.2, -0.4),
                    "life": random.randint(25, 45),
                    "color": random.choice(["#f9e2af", "#fab387", "#fca826"])
                })
        
        # 更新咖啡粒子物理
        active_sparks = []
        for s in self.coffee_sparks:
            s["dy"] += s["vy"]
            s["life"] -= 1
            if s["life"] > 0:
                active_sparks.append(s)
        self.coffee_sparks = active_sparks
        
        # 更新揮手計時器
        if getattr(self, "wave_timer", 0) > 0:
            self.wave_timer -= 1

        # 活力糖果 Buff 計時與粒子特效
        if getattr(self, "candy_timer", 0) > 0:
            self.candy_timer -= 1
            if random.random() < 0.20:
                color = random.choice(["#f5c2e7", "#94e2d5", "#f9e2af"])
                angle = random.uniform(0, 2 * math.pi)
                dist = random.uniform(self.r * 0.4, self.r * 1.1)
                self.coffee_sparks.append({
                    "dx": dist * math.cos(angle),
                    "dy": dist * math.sin(angle),
                    "vy": random.uniform(-1.2, -0.4),
                    "color": color,
                    "life": random.randint(15, 30)
                })

        if getattr(self, "matcha_timer", 0) > 0:
            self.matcha_timer -= 1
            if random.random() < 0.10:
                self.coffee_sparks.append({
                    "dx": random.uniform(-self.r * 0.8, self.r * 0.8),
                    "dy": random.uniform(-self.r * 0.7, self.r * 0.5),
                    "vy": random.uniform(-1.2, -0.5),
                    "color": random.choice(["#a6e3a1", "#94e2d5", "#f9e2af"]),
                    "life": random.randint(18, 34)
                })

        # 珍珠奶茶 Buff 計時與青色泡泡粒子特效
        if getattr(self, "bubble_tea_timer", 0) > 0:
            self.bubble_tea_timer -= 1
            if random.random() < 0.15:
                color = random.choice(["#89b4fa", "#a6e3a1", "#ffffff"])
                angle = random.uniform(0, 2 * math.pi)
                dist = random.uniform(self.r * 0.3, self.r * 1.0)
                self.coffee_sparks.append({
                    "dx": dist * math.cos(angle),
                    "dy": dist * math.sin(angle),
                    "vy": random.uniform(-1.6, -0.6),
                    "color": color,
                    "life": random.randint(20, 40)
                })

        # ☄️ 夏亞面罩 (Char's Mask) 赤色彗星專屬光芒與尾跡粒子
        if getattr(self, "equipped_accessory", None) == "char_mask" and random.random() < 0.22:
            color = random.choice(["#f38ba8", "#eba0ac", "#fab387", "#f9e2af", "#ff5555"])
            angle = random.uniform(0, 2 * math.pi)
            dist = random.uniform(self.r * 0.3, self.r * 1.05)
            self.coffee_sparks.append({
                "dx": dist * math.cos(angle),
                "dy": dist * math.sin(angle),
                "vy": random.uniform(-2.0, -0.6),
                "color": color,
                "life": random.randint(15, 30)
            })

        # 超辣拉麵 Buff 計時與火焰粒子與氣泡特效
        if getattr(self, "spicy_timer", 0) > 0:
            self.spicy_timer -= 1
            if random.random() < 0.25:
                color = random.choice(["#ff5555", "#ffaa00", "#ffdd00"])
                angle = random.uniform(0, 2 * math.pi)
                dist = random.uniform(self.r * 0.3, self.r * 1.1)
                self.coffee_sparks.append({
                    "dx": dist * math.cos(angle),
                    "dy": dist * math.sin(angle),
                    "vy": random.uniform(-2.2, -0.8),
                    "color": color,
                    "life": random.randint(10, 25)
                })
            
            if self.spicy_timer % 20 == 0:
                monitor = getattr(self, "monitor", None)
                if monitor:
                    txt = random.choice(["🔥", "HOT!", "好辣!!", "🔥"])
                    monitor.create_text_popup(txt, 190 + random.randint(-15, 15), 180 + random.randint(-10, 10), color="#f38ba8")
                    
            if self.spicy_timer <= 0:
                self.eye_state = "normal"
                self.mouth_state = "normal"
                
        # 冰棒冰凍 Buff 計時與雪花飄散效果
        if getattr(self, "ice_timer", 0) > 0:
            self.ice_timer -= 1
            if random.random() < 0.15:
                angle = random.uniform(0, 2 * math.pi)
                dist = random.uniform(self.r * 0.4, self.r * 1.1)
                self.coffee_sparks.append({
                    "dx": dist * math.cos(angle),
                    "dy": dist * math.sin(angle),
                    "vy": random.uniform(0.6, 1.3),
                    "color": "#ffffff",
                    "life": random.randint(20, 45)
                })
            if random.random() < 0.008 and self.state not in ("sleep", "sleep_futon", "eat", "drink", "balloon"):
                self.state = "idle"
                monitor = getattr(self, "monitor", None)
                if monitor:
                    monitor.create_text_popup("❄ 凍僵了... ❄", 170, 140, color="#89b4fa")

        # 紳士帽小兔子蹦出計時
        self.rabbit_pop_timer = (getattr(self, "rabbit_pop_timer", 0) + 1) % 180

        # 氣球狀態計時與飄動傾斜
        if self.state == "balloon":
            if getattr(self, "balloon_timer", 0) > 0:
                self.balloon_timer -= 1
                self.roll_angle = 0.08 * math.sin(time_ms() / 400.0)
                self.eye_state = "happy"
                self.mouth_state = "open"
                if self.balloon_timer <= 0:
                    self.state = "fall"
                    self.roll_angle = 0.0
                    self.eye_state = "normal"
                    self.mouth_state = "normal"
                    monitor = getattr(self, "monitor", None)
                    if monitor:
                        monitor.create_text_popup("氣球飛走了～", 170, 140, color="#ff5555")

        # 吃拉麵/披薩/冰棒狀態定時處理
        if self.state == "eat":
            if getattr(self, "ramen_timer", 0) > 0:
                self.ramen_timer -= 1
                if self.ramen_timer % 15 == 0:
                    self.vel_scale_y = -0.15
                    self.vel_scale_x = 0.1
                    monitor = getattr(self, "monitor", None)
                    if monitor:
                        eat_t = getattr(self, "eat_type", "")
                        if eat_t == "pizza":
                            monitor.create_text_popup("*嚼嚼*", 205, 185, color="#f9e2af")
                        elif eat_t == "popsicle":
                            monitor.create_text_popup("*舔舔*", 205, 185, color="#89b4fa")
                        else:
                            monitor.create_text_popup("*吸溜吸溜*", 205, 185, color="#fab387")
                if self.ramen_timer <= 0:
                    if getattr(self, "eat_type", "") == "popsicle":
                        self.ice_timer = 600  # 10s Ice Buff
                    
                    if getattr(self, "spicy_timer", 0) > 0:
                        self.state = "walk"
                        self.eye_state = "blink"
                        self.mouth_state = "open"
                    else:
                        self.state = "idle"
                        self.eye_state = "normal"
                        self.mouth_state = "normal"
                        
        # 喝飲料狀態定時處理
        if self.state == "drink":
            self.drink_timer -= 1
            if self.drink_timer % 10 == 0:
                self.vel_scale_y = -0.15
                self.vel_scale_x = 0.1
            if self.drink_timer <= 0:
                self.state = "idle"
                self.coffee_timer = 180.0  # 啟動 3 分鐘 Coffee Buff
                self.eye_state = "normal"
                self.mouth_state = "normal"

        # 2. 狀態機行為邏輯
        if getattr(self, "fever_timer", 0) > 0:
            self.fever_timer -= 1
            # 摸摸 Fever 歡樂起舞動態：左右晃動平移、果凍彈性縮放、微幅傾斜
            self.cx += 2.5 * math.sin(time.time() * 20.0)
            self.scale_y = 1.0 + 0.12 * abs(math.sin(time.time() * 15.0))
            self.scale_x = 1.0 - 0.08 * abs(math.sin(time.time() * 15.0))
            self.roll_angle = 0.10 * math.sin(time.time() * 12.0)
            self.eye_state = "happy"
            self.mouth_state = "open"
            
            # 邊界碰撞限制
            margin = self.r + 10
            if self.cx < margin: self.cx = margin
            elif self.cx > 340 - margin: self.cx = 340 - margin
            
            if self.fever_timer == 0:
                self.roll_angle = 0.0
                self.eye_state = "normal"
                self.mouth_state = "normal"
                
        elif self.state == "roll":
            # 翻滾狀態：角速度衰減，角色沿角速度旋轉，並左右移動碰撞反彈
            self.roll_angle += self.roll_speed
            self.roll_speed *= 0.98  # 角速度阻尼摩擦力
            self.cx += self.roll_speed * 40  # 旋轉帶動水平位移
            
            # 畫布邊界碰撞偵測 (邊界寬度為 340 像素)
            margin = self.r + 5
            if self.cx < margin:
                self.cx = margin
                self.roll_speed = -self.roll_speed * 0.8  # 反彈並損失 20% 動能
            elif self.cx > 340 - margin:
                self.cx = 340 - margin
                self.roll_speed = -self.roll_speed * 0.8
                
            # 當旋轉速度極低時，停下並回到正常狀態
            if abs(self.roll_speed) < 0.01:
                self.state = "idle"
                self.roll_angle = 0.0
                self.eye_state = "normal"
                self.mouth_state = "normal"
                
        elif self.state == "backflip":
            self.roll_angle += (2 * math.pi) / 40.0
            if getattr(self, "backflip_timer", 0) > 0:
                self.backflip_timer -= 1
                if self.backflip_timer <= 0:
                    self.state = "fall"
                    self.eye_state = "normal"
                    self.mouth_state = "normal"
                    
        elif self.state in ("walk", "chase_mouse"):
            # 散步 / 追滑鼠狀態：水平移動
            speed_mult = 1.6 if self.state == "chase_mouse" else 1.0
            if self.coffee_timer > 0:
                speed_mult *= 1.5
            if getattr(self, "candy_timer", 0) > 0:
                speed_mult *= 1.3
            if getattr(self, "spicy_timer", 0) > 0:
                speed_mult *= 2.2
            if getattr(self, "ice_timer", 0) > 0:
                speed_mult *= 0.5
            curr_speed = self.walk_speed * speed_mult
            self.cx += self.walk_dir * curr_speed
            margin = self.r + 10
            # 撞牆回頭
            if self.cx < margin:
                self.cx = margin
                self.walk_dir = 1
            elif self.cx > 340 - margin:
                self.cx = 340 - margin
                self.walk_dir = -1
                
            # 隨機轉為發呆狀態
            if getattr(self, "spicy_timer", 0) > 0:
                self.state = "walk"  # 強制持續跑步
            elif self.state == "chase_mouse":
                pass  # 由 monitor 控制退出
            elif random.random() < 0.005:
                self.state = "idle"
                
        elif self.state == "idle":
            # 發呆狀態：原地不動
            # 只有當沒有執行隨機日常動作時，才判定轉換狀態
            if self.doze_timer == 0 and self.bubble_timer == 0 and self.stretch_timer == 0 and getattr(self, "wave_timer", 0) == 0 and getattr(self, "singing_timer", 0) == 0 and getattr(self, "read_timer", 0) == 0:
                # 隨機轉為專注閱讀便利貼 (發呆且身邊有便利貼時)
                monitor = getattr(self, "monitor", None)
                if monitor and getattr(monitor, "spawned_memo_wins", {}):
                    pet_cx = monitor.root.winfo_x() + 170
                    pet_cy = monitor.root.winfo_y() + 205
                    near_memo = None
                    near_dir = 1
                    for memo_id, m_win in monitor.spawned_memo_wins.items():
                        try:
                            mx = m_win.winfo_x()
                            my = m_win.winfo_y()
                            dx = (mx + 90) - pet_cx
                            dy = (my + 80) - pet_cy
                            if 50 <= abs(dx) <= 150 and abs(dy) < 80:
                                near_memo = memo_id
                                near_dir = 1 if dx > 0 else -1
                                break
                        except Exception:
                            pass
                    if near_memo and random.random() < 0.05: # 5% 的發呆機會去讀書
                        self.state = "memo_read"
                        self.read_timer = random.randint(100, 180)
                        self.walk_dir = near_dir
                        self.eye_state = "normal"
                        self.mouth_state = "normal"
                        
                        bubble_text = random.choice(["閱讀中... 📖", "了解！💡", "主人加油 📝", "我有在看喔 👀", "原來如此 🤔"])
                        monitor.create_text_popup(bubble_text, 170, 100, color="#fef5d1")
                        return

                # 隨機轉為散步狀態
                if random.random() < 0.008:
                    self.state = "walk"
                    self.walk_dir = random.choice([1, -1])
                # 隨機轉為背向發呆狀態 (背向扭扭/擺尾)
                elif random.random() < 0.006:
                    self.state = "turn_to_back"
                    self.turn_timer = 15
                # 隨機打招呼揮手
                elif random.random() < 0.015:
                    self.wave_timer = 60
                # 隨機唱歌跳舞
                elif random.random() < 0.012:
                    self.singing_timer = 180
                    self.eye_state = "happy"
                    self.mouth_state = "open"
                # 隨機打瞌睡 (加班疲倦時間機率提高)
                elif random.random() < (0.0045 if self.is_overtime else 0.0015):
                    self.doze_timer = 180
                    self.eye_state = "blink"
                # 隨機吹氣泡
                elif random.random() < 0.002:
                    self.bubble_timer = 120
                    self.bubble_scale = 0.0
                    self.mouth_state = "open"
                # 隨機伸懶腰
                elif random.random() < 0.001:
                    self.stretch_timer = 90

            # 執行打瞌睡物理與表情
            if self.doze_timer > 0:
                self.doze_timer -= 1
                # 緩慢閉眼點頭下沉
                self.scale_y = 1.0 - 0.08 * math.sin(math.pi * (180 - self.doze_timer) / 180.0)
                self.scale_x = 1.0 + 0.05 * math.sin(math.pi * (180 - self.doze_timer) / 180.0)
                self.eye_state = "blink"
                if self.doze_timer == 20: # 驚醒彈跳
                    self.vel_scale_y = -0.25
                    self.vel_scale_x = 0.18
                    self.eye_state = "happy"
                if self.doze_timer == 0:
                    self.eye_state = "normal"

            # 執行吹泡泡
            elif self.bubble_timer > 0:
                self.bubble_timer -= 1
                if self.bubble_timer > 40:
                    self.bubble_scale = (120 - self.bubble_timer) * 0.16
                    self.mouth_state = "open"
                elif self.bubble_timer == 40:
                    # 泡泡破裂！
                    self.bubble_scale = -1.0
                    self.vel_scale_y = -0.26
                    self.vel_scale_x = 0.18
                    self.eye_state = "dizzy"
                    self.mouth_state = "open"
                else:
                    self.mouth_state = "open"
                if self.bubble_timer == 0:
                    self.eye_state = "normal"
                    self.mouth_state = "normal"
                    self.bubble_scale = 0.0

            # 執行伸懶腰
            elif self.stretch_timer > 0:
                self.stretch_timer -= 1
                if self.stretch_timer > 45:
                    self.scale_y = 1.0 + 0.22 * math.sin(math.pi * (90 - self.stretch_timer) / 90.0)
                    self.scale_x = 1.0 - 0.15 * math.sin(math.pi * (90 - self.stretch_timer) / 90.0)
                else:
                    self.scale_y = 1.0 + 0.22 * math.sin(math.pi * self.stretch_timer / 90.0)
                    self.scale_x = 1.0 - 0.15 * math.sin(math.pi * self.stretch_timer / 90.0)
            
            # 執行唱歌跳舞
            elif getattr(self, "singing_timer", 0) > 0:
                self.singing_timer -= 1
                self.roll_angle = 0.15 * math.sin(time_ms() / 100.0)
                self.eye_state = "happy"
                self.mouth_state = "open"
                if random.random() < 0.15:
                    monitor = getattr(self, "monitor", None)
                    if monitor:
                        note = random.choice(["🎵", "🎶", "♩", "♬"])
                        monitor.create_text_popup(note, self.cx + random.randint(-15, 15), 170 + random.randint(-10, 10),
                                                   color=random.choice(["#f5c2e7", "#a6e3a1", "#89b4fa", "#f9e2af"]))
                if self.singing_timer <= 0:
                    self.roll_angle = 0.0
                    self.eye_state = "normal"
                    self.mouth_state = "normal"
                    
        elif self.state == "back_idle":
            # 背向發呆狀態：原地不動，身體會扭扭 wiggle
            if getattr(self, "back_idle_timer", 0) > 0:
                self.back_idle_timer -= 1
                # 左右小角度擺動
                self.roll_angle = 0.045 * math.sin(time_ms() / 120.0)
            else:
                self.state = "turn_to_front"
                self.turn_timer = 15
                self.roll_angle = 0.0
                
        elif self.state == "turn_to_back":
            if getattr(self, "turn_timer", 0) > 0:
                self.turn_timer -= 1
                if self.turn_timer <= 0:
                    self.state = "back_idle"
                    self.back_idle_timer = random.randint(120, 240)
            self.roll_angle = 0.02 * math.sin(time_ms() / 120.0)
            
        elif self.state == "turn_to_front":
            if getattr(self, "turn_timer", 0) > 0:
                self.turn_timer -= 1
                if self.turn_timer <= 0:
                    self.state = "idle"
            self.roll_angle = 0.02 * math.sin(time_ms() / 120.0)

        elif self.state == "memo_perch":
            # 站在便利貼上唱歌律動：果凍呼吸起伏、擺動身體、開心張嘴
            self.roll_angle = 0.05 * math.sin(time_ms() / 150.0)
            self.scale_y = 1.0 + 0.05 * math.sin(time_ms() / 150.0)
            self.scale_x = 1.0 - 0.03 * math.sin(time_ms() / 150.0)
            self.eye_state = "happy"
            self.mouth_state = "open"

        elif self.state == "memo_read":
            # 專注閱讀便利貼：讀書時身體微微前傾扭動、眼神偏向便利貼方向
            if getattr(self, "read_timer", 0) > 0:
                self.read_timer -= 1
                self.roll_angle = self.walk_dir * 0.03 * math.sin(time_ms() / 100.0)
                self.look_offset_x = self.walk_dir * 12.0
            else:
                self.state = "idle"
                self.look_offset_x = 0.0

    def draw(self, name="", price_str="", coins=0, level=1, xp=0.0, satiety=100.0):
        """Canvas 繪製地瓜球與看板及底部狀態欄 HUD"""
        self.canvas.delete("character")
        
        # 取得當前縮放後的寬高 (用於果凍動態)
        if getattr(self, "state", "idle") == "relax_sofa":
            w = self.r * self.scale_x * 1.15
            h = self.r * self.scale_y * 0.88
        else:
            w = self.r * self.scale_x
            h = self.r * self.scale_y
        
        # 計算背面/側身旋轉比例 (0.0 = 完全正面, 0.42 = 側身面向右側, 1.0 = 完全背面)
        rotation_fraction = 0.0
        state = getattr(self, "state", "idle")
        if state == "back_idle":
            rotation_fraction = 1.0
        elif state == "turn_to_back":
            turn_timer = getattr(self, "turn_timer", 15)
            rotation_fraction = 1.0 - (turn_timer / 15.0)
        elif state == "turn_to_front":
            turn_timer = getattr(self, "turn_timer", 15)
            rotation_fraction = turn_timer / 15.0
        elif state == "work_laptop":
            rotation_fraction = 0.42  # 3D 側身面向右側電腦寫代碼
        elif state in ("watch_tv", "water_plant"):
            rotation_fraction = 0.35  # 3D 側身面向右側電視/盆栽
        else:
            rotation_fraction = 0.0
        
        # 1. 影子繪製已完全移交至獨立的 ShadowWindow (貼地物理與高度漸層淡出視窗)
        pass

        # 繪製咖啡 Buff 金色火花粒子
        for s in self.coffee_sparks:
            rx_sp, ry_sp = self.rotate_point(s["dx"], s["dy"], self.roll_angle)
            sp_r = 2.0 if s["life"] < 15 else 3.5
            self.canvas.create_oval(self.cx + rx_sp - sp_r, self.cy + ry_sp - sp_r,
                                    self.cx + rx_sp + sp_r, self.cy + ry_sp + sp_r,
                                    fill=s["color"], outline="", tags="character")
        
        # 2. 計算旋轉後的手腳坐標 (如果是睡眠/躺平狀態則收起手腳)
        if self.state in ("sleep", "sleep_futon"):
            # 躺平狀態：眼睛閉上，身體扁平
            w_sleep = self.r * 1.15
            h_sleep = self.r * 0.75
            
            # 身體：扁圓形
            self.draw_gradient_body(self.cx, self.cy + 10, w_sleep, h_sleep)
            
            # 閉眼 (︶ ︶)
            eye_y = self.cy + 5
            self.draw_rotated_arc_eye(self.cx - 16, eye_y, 12, 0.0, flip=True)
            self.draw_rotated_arc_eye(self.cx + 16, eye_y, 12, 0.0, flip=True)
            
            # 貓咪嘴
            self.draw_rotated_cat_mouth(self.cx, self.cy + 16, 0.0)
            return

        # ── 正常有手腳的狀態 ──
        # 3. 繪製身體 (球體立體漸層)
        self.draw_gradient_body(self.cx, self.cy, w, h)

        # 繪製加班頭帶
        if self.is_overtime:
            # 頭帶端點
            rx_hbl, ry_hbl = self.rotate_point(-w * 0.68, -h * 0.48, self.roll_angle)
            rx_hbr, ry_hbr = self.rotate_point(w * 0.68, -h * 0.48, self.roll_angle)
            # 畫紅色頭帶粗線
            self.canvas.create_line(self.cx + rx_hbl, self.cy + ry_hbl,
                                    self.cx + rx_hbr, self.cy + ry_hbr,
                                    fill="#f38ba8", width=7.0, capstyle=tk.ROUND, tags="character")
            # 畫頭帶打結部分 (右側兩個小紅飄帶)
            rx_k1, ry_k1 = self.rotate_point(w * 0.65, -h * 0.45, self.roll_angle)
            rx_k1_end, ry_k1_end = self.rotate_point(w * 0.85, -h * 0.30, self.roll_angle)
            self.canvas.create_line(self.cx + rx_k1, self.cy + ry_k1,
                                    self.cx + rx_k1_end, self.cy + ry_k1_end,
                                    fill="#f38ba8", width=3.5, capstyle=tk.ROUND, tags="character")
            rx_k2, ry_k2 = self.rotate_point(w * 0.65, -h * 0.45, self.roll_angle)
            rx_k2_end, ry_k2_end = self.rotate_point(w * 0.78, -h * 0.22, self.roll_angle)
            self.canvas.create_line(self.cx + rx_k2, self.cy + ry_k2,
                                    self.cx + rx_k2_end, self.cy + ry_k2_end,
                                    fill="#f38ba8", width=3.5, capstyle=tk.ROUND, tags="character")
            
            # 寫上 "奮鬥" 二字 (白色小字，與頭帶一同旋轉)
            rx_hbt, ry_hbt = self.rotate_point(0, -h * 0.50, self.roll_angle)
            self.canvas.create_text(self.cx + rx_hbt, self.cy + ry_hbt, text="奮鬥",
                                    fill="#ffffff", font=("微軟正黑體", 6, "bold"), tags="character")

        # 走路時雙腳交叉擺動的偏移量
        walk_offset = 0
        if self.state in ("walk", "chase_mouse", "return_home"):
            if getattr(self, "spicy_timer", 0) > 0:
                walk_offset = 8 * math.sin(time_ms() / 45.0)  # 超辣慌張快速擺腿
            else:
                walk_offset = 6 * math.sin(time_ms() / 120.0)
        elif self.state == "fall":
            walk_offset = 8 * math.sin(time_ms() / 40.0)  # 慌張踢腳

        # 4. 繪製雙腳 (茶色粗線，從身體邊緣向外延伸，在身體之上渲染)
        # 計算 3D 旋轉下的手腳偏移
        rotation_fraction = 0.0
        state = getattr(self, "state", "idle")
        if state == "back_idle":
            rotation_fraction = 1.0
        elif state == "turn_to_back":
            turn_timer = getattr(self, "turn_timer", 15)
            rotation_fraction = 1.0 - (turn_timer / 15.0)
        elif state == "turn_to_front":
            turn_timer = getattr(self, "turn_timer", 15)
            rotation_fraction = turn_timer / 15.0
        elif state == "work_laptop":
            rotation_fraction = 0.42
        elif state in ("watch_tv", "water_plant"):
            rotation_fraction = 0.35
        else:
            rotation_fraction = 0.0

        if rotation_fraction > 0.0 and state not in ("back_idle", "turn_to_back", "turn_to_front"):
            angle_rad = rotation_fraction * (math.pi / 2.0)
            limb_rot_scale = math.cos(angle_rad)
            limb_slide_x = math.sin(angle_rad) * w * 0.65
        else:
            limb_rot_scale = math.cos(rotation_fraction * math.pi)
            limb_slide_x = 0.0

        # 左腳起點與終點 (加入旋轉與 3D 透視)
        lf_x = -16 * limb_rot_scale + limb_slide_x
        rx_lf_start, ry_lf_start = self.rotate_point(lf_x, h - 5, self.roll_angle)
        rx_lf_end, ry_lf_end = self.rotate_point(lf_x, h + 10 + walk_offset, self.roll_angle)
        self.canvas.create_line(self.cx + rx_lf_start, self.cy + ry_lf_start,
                                self.cx + rx_lf_end, self.cy + ry_lf_end,
                                width=4.5, fill="#3c2203", capstyle=tk.ROUND, tags="character")

        # 右腳起點與終點 (加入旋轉與 3D 透視)
        rf_x = 16 * limb_rot_scale + limb_slide_x
        rx_rf_start, ry_rf_start = self.rotate_point(rf_x, h - 5, self.roll_angle)
        rx_rf_end, ry_rf_end = self.rotate_point(rf_x, h + 10 - walk_offset, self.roll_angle)
        self.canvas.create_line(self.cx + rx_rf_start, self.cy + ry_rf_start,
                                self.cx + rx_rf_end, self.cy + ry_rf_end,
                                width=4.5, fill="#3c2203", capstyle=tk.ROUND, tags="character")

        # 5. 繪製手部 (茶色粗線，在身體之上渲染)
        hand_swing = 0
        if self.state == "idle":
            hand_swing = 2.0 * math.sin(time_ms() / 200.0)
        elif self.state == "fall":
            hand_swing = 12.0 * math.sin(time_ms() / 50.0)

        lh_start_x = (-w + 8) * limb_rot_scale + limb_slide_x
        rh_start_x = (w - 8) * limb_rot_scale + limb_slide_x

        # 左手繪製
        if self.show_board:
            # 舉牌時左手往上抬抓著看板邊緣
            rx_lh_start, ry_lh_start = self.rotate_point((-w + 10) * limb_rot_scale + limb_slide_x, -h * 0.3, self.roll_angle)
            rx_lh_end, ry_lh_end = self.rotate_point((-w - 2) * limb_rot_scale + limb_slide_x, -h * 0.75, self.roll_angle)
            self.canvas.create_line(self.cx + rx_lh_start, self.cy + ry_lh_start,
                                    self.cx + rx_lh_end, self.cy + ry_lh_end,
                                    width=4.5, fill="#3c2203", capstyle=tk.ROUND, tags="character")
        elif self.state == "fall":
            # 慌張掉落時左手向上揮舞
            rx_lh_start, ry_lh_start = self.rotate_point(lh_start_x, 0, self.roll_angle)
            rx_lh_end, ry_lh_end = self.rotate_point((-w - 12) * limb_rot_scale + limb_slide_x, -12 + hand_swing, self.roll_angle)
            self.canvas.create_line(self.cx + rx_lh_start, self.cy + ry_lh_start,
                                    self.cx + rx_lh_end, self.cy + ry_lh_end,
                                    width=4.5, fill="#3c2203", capstyle=tk.ROUND, tags="character")
        elif getattr(self, "is_reaching", False):
            # 向滑鼠親近伸手
            rx_lh_start, ry_lh_start = self.rotate_point(lh_start_x, 4, self.roll_angle)
            rx_lh_end, ry_lh_end = self.rotate_point((-w - 10) * limb_rot_scale + limb_slide_x, -4, self.roll_angle)
            self.canvas.create_line(self.cx + rx_lh_start, self.cy + ry_lh_start,
                                    self.cx + rx_lh_end, self.cy + ry_lh_end,
                                    width=4.5, fill="#3c2203", capstyle=tk.ROUND, tags="character")
        elif self.state == "balloon":
            # 抓氣球線 (左手斜向上伸展)
            rx_lh_start, ry_lh_start = self.rotate_point(lh_start_x, 8, self.roll_angle)
            rx_lh_end, ry_lh_end = self.rotate_point((-w - 10) * limb_rot_scale + limb_slide_x, -14, self.roll_angle)
            self.canvas.create_line(self.cx + rx_lh_start, self.cy + ry_lh_start,
                                    self.cx + rx_lh_end, self.cy + ry_lh_end,
                                    width=4.5, fill="#3c2203", capstyle=tk.ROUND, tags="character")
        elif self.state == "eat":
            # 吃拉麵端碗 (左手端碗)
            rx_lh_start, ry_lh_start = self.rotate_point(lh_start_x, 8, self.roll_angle)
            bowl_bounce = 3.0 * abs(math.sin(time_ms() / 120.0))
            rx_lh_end, ry_lh_end = self.rotate_point(self.look_offset_x - 12, h * 0.22 + bowl_bounce, self.roll_angle)
            self.canvas.create_line(self.cx + rx_lh_start, self.cy + ry_lh_start,
                                    self.cx + rx_lh_end, self.cy + ry_lh_end,
                                    width=4.5, fill="#3c2203", capstyle=tk.ROUND, tags="character")
        elif self.state == "work_laptop":
            # 寫扣加班打鍵盤 (3D 側身朝向右側鍵盤敲擊)
            rx_lh_start, ry_lh_start = self.rotate_point(lh_start_x, 8, self.roll_angle)
            type_swing_l = 6.0 * math.sin(time_ms() / 35.0)
            rx_lh_end, ry_lh_end = self.rotate_point((w * 0.15) * limb_rot_scale + limb_slide_x, 15 + type_swing_l, self.roll_angle)
            self.canvas.create_line(self.cx + rx_lh_start, self.cy + ry_lh_start,
                                    self.cx + rx_lh_end, self.cy + ry_lh_end,
                                    width=4.5, fill="#3c2203", capstyle=tk.ROUND, tags="character")
        elif self.state == "relax_sofa":
            # 躺沙發看漫畫 (左手扶書)
            rx_lh_start, ry_lh_start = self.rotate_point(lh_start_x, 6, self.roll_angle)
            rx_lh_end, ry_lh_end = self.rotate_point(-14, h * 0.3, self.roll_angle)
            self.canvas.create_line(self.cx + rx_lh_start, self.cy + ry_lh_start,
                                    self.cx + rx_lh_end, self.cy + ry_lh_end,
                                    width=4.5, fill="#3c2203", capstyle=tk.ROUND, tags="character")
        elif self.state == "water_plant":
            # 澆水手持噴水壺 (雙手捧水壺)
            rx_lh_start, ry_lh_start = self.rotate_point(lh_start_x, 8, self.roll_angle)
            rx_lh_end, ry_lh_end = self.rotate_point(-10, h * 0.35, self.roll_angle)
            self.canvas.create_line(self.cx + rx_lh_start, self.cy + ry_lh_start,
                                    self.cx + rx_lh_end, self.cy + ry_lh_end,
                                    width=4.5, fill="#3c2203", capstyle=tk.ROUND, tags="character")
        elif self.state in ("warm_kotatsu", "meditate_lamp"):
            # 鑽暖桌或小夜燈打坐 (雙手乖乖放在身前)
            rx_lh_start, ry_lh_start = self.rotate_point(lh_start_x, 8, self.roll_angle)
            rx_lh_end, ry_lh_end = self.rotate_point(-12, h * 0.4, self.roll_angle)
            self.canvas.create_line(self.cx + rx_lh_start, self.cy + ry_lh_start,
                                    self.cx + rx_lh_end, self.cy + ry_lh_end,
                                    width=4.5, fill="#3c2203", capstyle=tk.ROUND, tags="character")
        else:
            # 正常狀態下左手向下放
            rx_lh_start, ry_lh_start = self.rotate_point(lh_start_x, 8, self.roll_angle)
            curr_y = 12 + walk_offset if self.state in ("walk", "chase_mouse", "return_home", "approach_furniture") else 12
            rx_lh_end, ry_lh_end = self.rotate_point((-w - 6) * limb_rot_scale + limb_slide_x, curr_y, self.roll_angle)
            self.canvas.create_line(self.cx + rx_lh_start, self.cy + ry_lh_start,
                                    self.cx + rx_lh_end, self.cy + ry_lh_end,
                                    width=4.5, fill="#3c2203", capstyle=tk.ROUND, tags="character")

        # 右手繪製
        if self.show_board:
            # 舉牌時右手往上抬抓著看板邊緣
            rx_rh_start, ry_rh_start = self.rotate_point((w - 10) * limb_rot_scale + limb_slide_x, -h * 0.3, self.roll_angle)
            rx_rh_end, ry_rh_end = self.rotate_point((w + 2) * limb_rot_scale + limb_slide_x, -h * 0.75, self.roll_angle)
            self.canvas.create_line(self.cx + rx_rh_start, self.cy + ry_rh_start,
                                    self.cx + rx_rh_end, self.cy + ry_rh_end,
                                    width=4.5, fill="#3c2203", capstyle=tk.ROUND, tags="character")
        elif self.state == "drink":
            # 喝水/咖啡時，右手拿著杯子放到嘴邊
            rx_rh_start, ry_rh_start = self.rotate_point(rh_start_x, 8, self.roll_angle)
            rx_rh_end, ry_rh_end = self.rotate_point(w * 0.38, h * 0.1, self.roll_angle)
            self.canvas.create_line(self.cx + rx_rh_start, self.cy + ry_rh_start,
                                    self.cx + rx_rh_end, self.cy + ry_rh_end,
                                    width=4.5, fill="#3c2203", capstyle=tk.ROUND, tags="character")
        elif self.state == "fall":
            # 慌張掉落時右手向上揮舞
            rx_rh_start, ry_rh_start = self.rotate_point(rh_start_x, 0, self.roll_angle)
            rx_rh_end, ry_rh_end = self.rotate_point((w + 12) * limb_rot_scale + limb_slide_x, -12 - hand_swing, self.roll_angle)
            self.canvas.create_line(self.cx + rx_rh_start, self.cy + ry_rh_start,
                                    self.cx + rx_rh_end, self.cy + ry_rh_end,
                                    width=4.5, fill="#3c2203", capstyle=tk.ROUND, tags="character")
        elif getattr(self, "is_reaching", False):
            # 向滑鼠親近伸手
            rx_rh_start, ry_rh_start = self.rotate_point(rh_start_x, 4, self.roll_angle)
            rx_rh_end, ry_rh_end = self.rotate_point((w + 10) * limb_rot_scale + limb_slide_x, -4, self.roll_angle)
            self.canvas.create_line(self.cx + rx_rh_start, self.cy + ry_rh_start,
                                    self.cx + rx_rh_end, self.cy + ry_rh_end,
                                    width=4.5, fill="#3c2203", capstyle=tk.ROUND, tags="character")
        elif getattr(self, "wave_timer", 0) > 0:
            # 隨機打招呼揮手
            rx_rh_start, ry_rh_start = self.rotate_point(rh_start_x, 8, self.roll_angle)
            wave_y = -6 + 4 * math.sin(time_ms() / 80.0)
            wave_x = w + 4 + 6 * math.sin(time_ms() / 80.0)
            rx_rh_end, ry_rh_end = self.rotate_point(wave_x * limb_rot_scale + limb_slide_x, wave_y, self.roll_angle)
            self.canvas.create_line(self.cx + rx_rh_start, self.cy + ry_rh_start,
                                    self.cx + rx_rh_end, self.cy + ry_rh_end,
                                    width=4.5, fill="#3c2203", capstyle=tk.ROUND, tags="character")
        elif self.state == "work_laptop":
            # 寫扣加班打鍵盤 (3D 側身朝向右側鍵盤交替敲擊)
            rx_rh_start, ry_rh_start = self.rotate_point(rh_start_x, 8, self.roll_angle)
            type_swing_r = 6.0 * math.cos(time_ms() / 35.0)
            rx_rh_end, ry_rh_end = self.rotate_point((w * 0.45) * limb_rot_scale + limb_slide_x, 12 + type_swing_r, self.roll_angle)
            self.canvas.create_line(self.cx + rx_rh_start, self.cy + ry_rh_start,
                                    self.cx + rx_rh_end, self.cy + ry_rh_end,
                                    width=4.5, fill="#3c2203", capstyle=tk.ROUND, tags="character")
        elif self.state == "relax_sofa":
            # 躺沙發看漫畫 (右手捧書與漫畫書本體)
            rx_rh_start, ry_rh_start = self.rotate_point(rh_start_x, 6, self.roll_angle)
            rx_rh_end, ry_rh_end = self.rotate_point(14, h * 0.3, self.roll_angle)
            self.canvas.create_line(self.cx + rx_rh_start, self.cy + ry_rh_start,
                                    self.cx + rx_rh_end, self.cy + ry_rh_end,
                                    width=4.5, fill="#3c2203", capstyle=tk.ROUND, tags="character")
            # 繪製可愛漫畫書本 (雙頁展開)
            rx_bk1, ry_bk1 = self.rotate_point(-16, h * 0.18, self.roll_angle)
            rx_bk2, ry_bk2 = self.rotate_point(16, h * 0.42, self.roll_angle)
            self.canvas.create_rectangle(self.cx + rx_bk1, self.cy + ry_bk1, self.cx + rx_bk2, self.cy + ry_bk2,
                                         fill="#89b4fa", outline="#3c2203", width=1.5, tags="character")
            # 書頁白紙與線條
            self.canvas.create_rectangle(self.cx + rx_bk1 + 2, self.cy + ry_bk1 + 2, self.cx + rx_bk2 - 2, self.cy + ry_bk2 - 2,
                                         fill="#ffffff", outline="", tags="character")
            self.canvas.create_text(self.cx, self.cy + (ry_bk1 + ry_bk2) * 0.5, text="📖", font=("微軟正黑體", 9), tags="character")
        elif self.state == "watch_tv":
            # 看電視手拿遙控器
            rx_rh_start, ry_rh_start = self.rotate_point(rh_start_x, 8, self.roll_angle)
            rx_rh_end, ry_rh_end = self.rotate_point(w * 0.45, -2, self.roll_angle)
            self.canvas.create_line(self.cx + rx_rh_start, self.cy + ry_rh_start,
                                    self.cx + rx_rh_end, self.cy + ry_rh_end,
                                    width=4.5, fill="#3c2203", capstyle=tk.ROUND, tags="character")
            # 黑色小遙控器
            rx_rc1, ry_rc1 = self.rotate_point(w * 0.42, -10, self.roll_angle)
            rx_rc2, ry_rc2 = self.rotate_point(w * 0.58, 4, self.roll_angle)
            self.canvas.create_rectangle(self.cx + rx_rc1, self.cy + ry_rc1, self.cx + rx_rc2, self.cy + ry_rc2,
                                         fill="#11111b", outline="#fab387", width=1.0, tags="character")
            self.canvas.create_oval(self.cx + rx_rc1 + 2, self.cy + ry_rc1 - 2, self.cx + rx_rc1 + 5, self.cy + ry_rc1 + 1, fill="#ff5555", outline="", tags="character")
        elif self.state == "water_plant":
            # 澆水手持噴水壺
            rx_rh_start, ry_rh_start = self.rotate_point(rh_start_x, 8, self.roll_angle)
            rx_rh_end, ry_rh_end = self.rotate_point(18, h * 0.25, self.roll_angle)
            self.canvas.create_line(self.cx + rx_rh_start, self.cy + ry_rh_start,
                                    self.cx + rx_rh_end, self.cy + ry_rh_end,
                                    width=4.5, fill="#3c2203", capstyle=tk.ROUND, tags="character")
            # 綠色迷你小噴水壺
            rx_can1, ry_can1 = self.rotate_point(8, h * 0.15, self.roll_angle)
            rx_can2, ry_can2 = self.rotate_point(26, h * 0.38, self.roll_angle)
            self.canvas.create_rectangle(self.cx + rx_can1, self.cy + ry_can1, self.cx + rx_can2, self.cy + ry_can2,
                                         fill="#a6e3a1", outline="#3c2203", width=1.5, tags="character")
            # 水壺長嘴與水滴
            self.canvas.create_line(self.cx + rx_can2, self.cy + ry_can1 + 2, self.cx + rx_can2 + 8, self.cy + ry_can1 - 4,
                                    fill="#a6e3a1", width=2.5, tags="character")
            if int(time.time() * 4) % 2 == 0:
                self.canvas.create_oval(self.cx + rx_can2 + 9, self.cy + ry_can1 - 2, self.cx + rx_can2 + 12, self.cy + ry_can1 + 1,
                                        fill="#89b4fa", outline="", tags="character")
        elif self.state in ("warm_kotatsu", "meditate_lamp"):
            # 暖桌或打坐右手在身前
            rx_rh_start, ry_rh_start = self.rotate_point(rh_start_x, 8, self.roll_angle)
            rx_rh_end, ry_rh_end = self.rotate_point(12, h * 0.4, self.roll_angle)
            self.canvas.create_line(self.cx + rx_rh_start, self.cy + ry_rh_start,
                                    self.cx + rx_rh_end, self.cy + ry_rh_end,
                                    width=4.5, fill="#3c2203", capstyle=tk.ROUND, tags="character")
            if self.state == "warm_kotatsu":
                # 頭頂小橘子 🍊
                rx_org, ry_org = self.rotate_point(0, -h * 0.95, self.roll_angle)
                self.canvas.create_oval(self.cx + rx_org - 8, self.cy + ry_org - 7, self.cx + rx_org + 8, self.cy + ry_org + 7,
                                        fill="#fe640b", outline="#3c2203", width=1.2, tags="character")
                self.canvas.create_oval(self.cx + rx_org - 2, self.cy + ry_org - 9, self.cx + rx_org + 4, self.cy + ry_org - 5,
                                        fill="#a6e3a1", outline="", tags="character")
        elif self.state in ("walk", "chase_mouse", "return_home", "approach_furniture"):
            # 走路時手前後擺動
            rx_rh_start, ry_rh_start = self.rotate_point(rh_start_x, 8, self.roll_angle)
            rx_rh_end, ry_rh_end = self.rotate_point((w + 6) * limb_rot_scale + limb_slide_x, 12 - walk_offset, self.roll_angle)
            self.canvas.create_line(self.cx + rx_rh_start, self.cy + ry_rh_start,
                                    self.cx + rx_rh_end, self.cy + ry_rh_end,
                                    width=4.5, fill="#3c2203", capstyle=tk.ROUND, tags="character")
        elif self.state == "eat":
            # 吃拉麵端碗 (右手端碗)
            rx_rh_start, ry_rh_start = self.rotate_point(rh_start_x, 8, self.roll_angle)
            bowl_bounce = 3.0 * abs(math.sin(time_ms() / 120.0))
            rx_rh_end, ry_rh_end = self.rotate_point(self.look_offset_x + 12, h * 0.22 + bowl_bounce, self.roll_angle)
            self.canvas.create_line(self.cx + rx_rh_start, self.cy + ry_rh_start,
                                    self.cx + rx_rh_end, self.cy + ry_rh_end,
                                    width=4.5, fill="#3c2203", capstyle=tk.ROUND, tags="character")
        else:
            # 正常狀態下右手向下放 (對稱)
            rx_rh_start, ry_rh_start = self.rotate_point(rh_start_x, 8, self.roll_angle)
            rx_rh_end, ry_rh_end = self.rotate_point((w + 6) * limb_rot_scale + limb_slide_x, 12, self.roll_angle)
            self.canvas.create_line(self.cx + rx_rh_start, self.cy + ry_rh_start,
                                    self.cx + rx_rh_end, self.cy + ry_rh_end,
                                    width=4.5, fill="#3c2203", capstyle=tk.ROUND, tags="character")

        # 4. 繪製五官與尾巴 (支援轉向背面的過渡動畫)
        # 3D 旋轉透視投影公式 (球面旋轉投影)
        # Face rotation angle: 0 (front) to pi/2 (side/back)
        angle_rad = rotation_fraction * (math.pi / 2.0)
        face_rot_scale = math.cos(angle_rad)
        slide_x = math.sin(angle_rad) * w * 0.65
        
        # 繪製小尾巴 (只要 rotation_fraction > 0 即可繪製，大小比例隨之漸變)
        if rotation_fraction > 0.0:
            tail_wiggle = 0.0
            if state == "back_idle":
                tail_wiggle = 5.0 * math.sin(time_ms() / 120.0)
            
            tail_alpha = (1.0 - rotation_fraction) * (math.pi / 2.0)
            tail_rot_scale = math.cos(tail_alpha)
            tail_slide_x = -math.sin(tail_alpha) * w * 0.45
            
            wgl = tail_wiggle * tail_rot_scale
            rx_t1, ry_t1 = self.rotate_point(tail_slide_x + wgl, h * 0.35, self.roll_angle)
            rx_t2, ry_t2 = self.rotate_point(tail_slide_x + (5.0 * self.scale_x + wgl) * tail_rot_scale, h * 0.58, self.roll_angle)
            rx_t3, ry_t3 = self.rotate_point(tail_slide_x + 2.0 * self.scale_x * tail_rot_scale, h * 0.68, self.roll_angle)
            self.canvas.create_line(self.cx + rx_t1, self.cy + ry_t1,
                                    self.cx + rx_t2, self.cy + ry_t2,
                                    self.cx + rx_t3, self.cy + ry_t3,
                                    width=3.5 * tail_rot_scale, fill="#5c3a21", capstyle=tk.ROUND, tags="character")

        # 眼睛與眉毛基準座標 (僅在 rotation_fraction < 0.8 時繪製五官)
        eye_y_offset = -h * 0.08 + self.look_offset_y
        left_eye_dx = (-w * 0.28 + self.look_offset_x) * face_rot_scale + slide_x
        right_eye_dx = (w * 0.28 + self.look_offset_x) * face_rot_scale + slide_x
        
        if rotation_fraction < 0.8:
            rx_le, ry_le = self.rotate_point(left_eye_dx, eye_y_offset, self.roll_angle)
            rx_re, ry_re = self.rotate_point(right_eye_dx, eye_y_offset, self.roll_angle)
            
            # 眉毛基準坐標
            eb_y_offset = -h * 0.28 + self.look_offset_y
            left_eb_dx = (-w * 0.32 + self.look_offset_x) * face_rot_scale + slide_x
            right_eb_dx = (w * 0.32 + self.look_offset_x) * face_rot_scale + slide_x
            
            rx_leb, ry_leb = self.rotate_point(left_eb_dx, eb_y_offset, self.roll_angle)
            rx_reb, ry_reb = self.rotate_point(right_eb_dx, eb_y_offset, self.roll_angle)

            eb_w = 13.0 * self.scale_x

            # 根據 3D 球體表面投影公式 (X/R) 計算眼睛與眉毛的水平透視縮放，越接近邊緣收縮越明顯 (最小保留 65% 寬度，最為萌萌可愛)
            left_eye_scale_x = math.sqrt(max(0.4225, 1.0 - (left_eye_dx / w)**2)) * face_rot_scale
            right_eye_scale_x = math.sqrt(max(0.4225, 1.0 - (right_eye_dx / w)**2)) * face_rot_scale
            
            eb_scale_l = math.sqrt(max(0.4225, 1.0 - (left_eb_dx / w)**2)) * face_rot_scale
            eb_scale_r = math.sqrt(max(0.4225, 1.0 - (right_eb_dx / w)**2)) * face_rot_scale

            # 優先繪製星星眼 (★ ★)
            if self.coffee_timer > 0 or self.eye_state == "star":
                star_r = 7.5 * self.scale_x
                self.draw_rotated_star_eye(self.cx + rx_le, self.cy + ry_le, star_r, self.roll_angle, scale_x=left_eye_scale_x)
                self.draw_rotated_star_eye(self.cx + rx_re, self.cy + ry_re, star_r, self.roll_angle, scale_x=right_eye_scale_x)
            elif self.state == "fall":
                # 慌張掉落眼 (圓框白底黑眼珠，極度慌張)
                eye_r = 7.5 * self.scale_x
                self.canvas.create_oval(self.cx + rx_le - eye_r * left_eye_scale_x, self.cy + ry_le - eye_r,
                                        self.cx + rx_le + eye_r * left_eye_scale_x, self.cy + ry_le + eye_r,
                                        fill="#ffffff", outline="#3c2203", width=2.5, tags="character")
                self.canvas.create_oval(self.cx + rx_le - 2.5 * face_rot_scale, self.cy + ry_le - 2.5,
                                        self.cx + rx_le + 2.5 * face_rot_scale, self.cy + ry_le + 2.5,
                                        fill="#3c2203", outline="", tags="character")
                self.canvas.create_oval(self.cx + rx_re - eye_r * right_eye_scale_x, self.cy + ry_re - eye_r,
                                        self.cx + rx_re + eye_r * right_eye_scale_x, self.cy + ry_re + eye_r,
                                        fill="#ffffff", outline="#3c2203", width=2.5, tags="character")
                self.canvas.create_oval(self.cx + rx_re - 2.5 * face_rot_scale, self.cy + ry_re - 2.5,
                                        self.cx + rx_re + 2.5 * face_rot_scale, self.cy + ry_re + 2.5,
                                        fill="#3c2203", outline="", tags="character")
            elif self.eye_state == "normal":
                # 經典呆萌眼：小圓點 + 倒彎粗眉
                # 眉毛 (⌒)
                self.draw_rotated_arc_eyebrow(self.cx + rx_leb, self.cy + ry_leb, eb_w * eb_scale_l, self.roll_angle)
                self.draw_rotated_arc_eyebrow(self.cx + rx_reb, self.cy + ry_reb, eb_w * eb_scale_r, self.roll_angle)
                
                # 眼珠 (清澈自然日系萌瞳：黑瞳 + 左上小巧微高光點，不刺眼)
                eye_r = 4.6 * self.scale_x
                # 左眼
                self.canvas.create_oval(self.cx + rx_le - eye_r * left_eye_scale_x, self.cy + ry_le - eye_r,
                                        self.cx + rx_le + eye_r * left_eye_scale_x, self.cy + ry_le + eye_r,
                                        fill="#3c2203", outline="", tags="character")
                # 左眼小巧高光點
                hl_r1 = 1.2 * self.scale_x
                rx_hl1, ry_hl1 = self.rotate_point(-1.2 * left_eye_scale_x, -1.2, self.roll_angle)
                self.canvas.create_oval(self.cx + rx_le + rx_hl1 - hl_r1 * left_eye_scale_x, self.cy + ry_le + ry_hl1 - hl_r1,
                                        self.cx + rx_le + rx_hl1 + hl_r1 * left_eye_scale_x, self.cy + ry_le + ry_hl1 + hl_r1,
                                        fill="#ffffff", outline="", tags="character")

                # 右眼
                self.canvas.create_oval(self.cx + rx_re - eye_r * right_eye_scale_x, self.cy + ry_re - eye_r,
                                        self.cx + rx_re + eye_r * right_eye_scale_x, self.cy + ry_re + eye_r,
                                        fill="#3c2203", outline="", tags="character")
                # 右眼小巧高光點
                rx_rhl1, ry_rhl1 = self.rotate_point(-1.2 * right_eye_scale_x, -1.2, self.roll_angle)
                self.canvas.create_oval(self.cx + rx_re + rx_rhl1 - hl_r1 * right_eye_scale_x, self.cy + ry_re + ry_rhl1 - hl_r1,
                                        self.cx + rx_re + rx_rhl1 + hl_r1 * right_eye_scale_x, self.cy + ry_re + ry_rhl1 + hl_r1,
                                        fill="#ffffff", outline="", tags="character")
                
            elif self.eye_state == "happy":
                # 吃到東西瞇眼笑 (^^) - 不需要眉毛，眼睛直接變彎弧
                self.draw_rotated_arc_eye(self.cx + rx_le, self.cy + ry_le, eye_r_size=8.5 * left_eye_scale_x, angle=self.roll_angle, flip=True)
                self.draw_rotated_arc_eye(self.cx + rx_re, self.cy + ry_re, eye_r_size=8.5 * right_eye_scale_x, angle=self.roll_angle, flip=True)
                
            elif self.eye_state == "dizzy":
                # 翻滾時的暈眩眼 (x x) - 不需要眉毛
                left_x = self.cx + rx_le
                right_x = self.cx + rx_re
                # 左眼 x
                self.canvas.create_line(left_x - 5 * left_eye_scale_x, self.cy + ry_le - 5, left_x + 5 * left_eye_scale_x, self.cy + ry_le + 5, width=3.5, fill="#3c2203", capstyle=tk.ROUND, tags="character")
                self.canvas.create_line(left_x - 5 * left_eye_scale_x, self.cy + ry_le + 5, left_x + 5 * left_eye_scale_x, self.cy + ry_le - 5, width=3.5, fill="#3c2203", capstyle=tk.ROUND, tags="character")
                # 右眼 x
                self.canvas.create_line(right_x - 5 * right_eye_scale_x, self.cy + ry_re - 5, right_x + 5 * right_eye_scale_x, self.cy + ry_re + 5, width=3.5, fill="#3c2203", capstyle=tk.ROUND, tags="character")
                self.canvas.create_line(right_x - 5 * right_eye_scale_x, self.cy + ry_re + 5, right_x + 5 * right_eye_scale_x, self.cy + ry_re - 5, width=3.5, fill="#3c2203", capstyle=tk.ROUND, tags="character")
                
            elif self.eye_state == "blink":
                # 眨眼：眉毛在，眼睛縮成橫線
                self.draw_rotated_arc_eyebrow(self.cx + rx_leb, self.cy + ry_leb, eb_w * eb_scale_l, self.roll_angle)
                self.draw_rotated_arc_eyebrow(self.cx + rx_reb, self.cy + ry_reb, eb_w * eb_scale_r, self.roll_angle)
                
                # 用旋轉後的線段表示閉眼
                blink_dx1, blink_dy1 = left_eye_dx - 5 * left_eye_scale_x, eye_y_offset
                blink_dx2, blink_dy2 = left_eye_dx + 5 * left_eye_scale_x, eye_y_offset
                rx_b1_l, ry_b1_l = self.rotate_point(blink_dx1, blink_dy1, self.roll_angle)
                rx_b1_r, ry_b1_r = self.rotate_point(blink_dx2, blink_dy2, self.roll_angle)
                self.canvas.create_line(self.cx + rx_b1_l, self.cy + ry_b1_l, self.cx + rx_b1_r, self.cy + ry_b1_r,
                                        width=4.0, fill="#3c2203", capstyle=tk.ROUND, tags="character")
                
                blink_dx3, blink_dy3 = right_eye_dx - 5 * right_eye_scale_x, eye_y_offset
                blink_dx4, blink_dy4 = right_eye_dx + 5 * right_eye_scale_x, eye_y_offset
                rx_b2_l, ry_b2_l = self.rotate_point(blink_dx3, blink_dy3, self.roll_angle)
                rx_b2_r, ry_b2_r = self.rotate_point(blink_dx4, blink_dy4, self.roll_angle)
                self.canvas.create_line(self.cx + rx_b2_l, self.cy + ry_b2_l, self.cx + rx_b2_r, self.cy + ry_b2_r,
                                        width=4.0, fill="#3c2203", capstyle=tk.ROUND, tags="character")

            # 畫眉毛 (非 happy, dizzy, sleep, 且沒有咖啡星星眼時)
            if self.eye_state not in ("happy", "dizzy") and self.state not in ("sleep", "sleep_futon") and self.coffee_timer <= 0:
                if self.state == "fall":
                    # 慌張八字眉 (\ /)
                    rx_leb_s, ry_leb_s = self.rotate_point(left_eb_dx - 6 * eb_scale_l, eb_y_offset + 3, self.roll_angle)
                    rx_leb_e, ry_leb_e = self.rotate_point(left_eb_dx + 6 * eb_scale_l, eb_y_offset - 3, self.roll_angle)
                    self.canvas.create_line(self.cx + rx_leb_s, self.cy + ry_leb_s,
                                            self.cx + rx_leb_e, self.cy + ry_leb_e,
                                            width=3.5, fill="#3c2203", capstyle=tk.ROUND, tags="character")
                    rx_reb_s, ry_reb_s = self.rotate_point(right_eb_dx - 6 * eb_scale_r, eb_y_offset - 3, self.roll_angle)
                    rx_reb_e, ry_reb_e = self.rotate_point(right_eb_dx + 6 * eb_scale_r, eb_y_offset + 3, self.roll_angle)
                    self.canvas.create_line(self.cx + rx_reb_s, self.cy + ry_reb_s,
                                            self.cx + rx_reb_e, self.cy + ry_reb_e,
                                            width=3.5, fill="#3c2203", capstyle=tk.ROUND, tags="character")
                else:
                    self.draw_rotated_arc_eyebrow(self.cx + rx_leb, self.cy + ry_leb, eb_w * eb_scale_l, self.roll_angle)
                    self.draw_rotated_arc_eyebrow(self.cx + rx_reb, self.cy + ry_reb, eb_w * eb_scale_r, self.roll_angle)

            # 4.5 繪製粉嫩萌系腮紅 (Cheeks Blush)
            self.draw_blush(w, h, face_rot_scale, slide_x)

            # 5. 繪製人中與貓咪嘴 (加算旋轉，且嘴巴亦加入水平透視收縮)
            mouth_y_offset = h * 0.16 + self.look_offset_y
            nose_y_offset = eye_y_offset + 2
            
            mouth_dx = self.look_offset_x * face_rot_scale + slide_x
            nose_dx = self.look_offset_x * face_rot_scale + slide_x
            
            rx_n, ry_n = self.rotate_point(nose_dx, nose_y_offset, self.roll_angle)
            rx_m, ry_m = self.rotate_point(mouth_dx, mouth_y_offset, self.roll_angle)
            
            mouth_scale_x = max(0.40, 1.0 - (abs(mouth_dx) / w) * 0.40) * face_rot_scale
            
            if self.state == "fall":
                # 掉落時慌張張大的大口
                rx_m_c, ry_m_c = self.rotate_point(mouth_dx, mouth_y_offset + 3, self.roll_angle)
                self.canvas.create_oval(self.cx + rx_m_c - 10.0 * mouth_scale_x, self.cy + ry_m_c - 6.0,
                                        self.cx + rx_m_c + 10.0 * mouth_scale_x, self.cy + ry_m_c + 14.0,
                                        fill="#b83526", outline="#3c2203", width=3.5, tags="character")
            elif self.mouth_state == "normal":
                # 畫人中豎線
                self.canvas.create_line(self.cx + rx_n, self.cy + ry_n, self.cx + rx_m, self.cy + ry_m,
                                        width=4.0, fill="#3c2203", capstyle=tk.ROUND, tags="character")
                # 畫雙弧線貓咪嘴 (w)
                self.draw_rotated_cat_mouth(self.cx + rx_m, self.cy + ry_m, self.roll_angle, scale_x=mouth_scale_x)
                
            elif self.mouth_state == "open":
                # 吃 Token 或吹泡泡時的圓嘴巴
                rx_n_short, ry_n_short = self.rotate_point(mouth_dx, mouth_y_offset - 2, self.roll_angle)
                # 畫短人中
                self.canvas.create_line(self.cx + rx_n, self.cy + ry_n, self.cx + rx_n_short, self.cy + ry_n_short,
                                        width=4.0, fill="#3c2203", capstyle=tk.ROUND, tags="character")
                
                # 張大的實心圓嘴巴 (吃東西)
                mouth_r = 7.5
                rx_m_c, ry_m_c = self.rotate_point(mouth_dx, mouth_y_offset + 3, self.roll_angle)
                self.canvas.create_oval(self.cx + rx_m_c - mouth_r * mouth_scale_x, self.cy + ry_m_c - mouth_r * 0.8,
                                        self.cx + rx_m_c + mouth_r * mouth_scale_x, self.cy + ry_m_c + mouth_r * 1.2,
                                        fill="#b83526", outline="#3c2203", width=3.5, tags="character")

        # 5.5 繪製裝備中的配件
        self.draw_accessories(w, h, left_eye_dx, right_eye_dx, eye_y_offset)

        # 6. 繪製舉起的看板 (如果 show_board 為 True，且非翻滾狀態)
        if self.show_board and self.state != "roll":
            self.draw_sign_board(name, price_str, coins)

        # 繪製咖啡杯
        if self.state == "drink":
            rx_cup_c, ry_cup_c = self.rotate_point(w * 0.45, h * 0.1, self.roll_angle)
            cup_x = self.cx + rx_cup_c
            cup_y = self.cy + ry_cup_c
            # 畫白色咖啡杯身 (小矩形)
            self.canvas.create_rectangle(cup_x - 6, cup_y - 8, cup_x + 6, cup_y + 8,
                                         fill="#ffffff", outline="#3c2203", width=2.0, tags="character")
            # 畫杯耳 (小弧/線)
            self.canvas.create_arc(cup_x + 3, cup_y - 4, cup_x + 10, cup_y + 4,
                                   start=-90, extent=180, style=tk.ARC, outline="#3c2203", width=2.0, tags="character")
            # 畫一條深褐色的咖啡液體在頂部
            self.canvas.create_line(cup_x - 5, cup_y - 6, cup_x + 5, cup_y - 6, fill="#5a3d28", width=2.0, tags="character")

        # 繪製拉麵碗與麵條、披薩、冰棒、氣球
        if self.state == "eat":
            eat_t = getattr(self, "eat_type", "")
            if eat_t in ("ramen", "spicy_ramen", ""):
                # 碗垂直居中放在嘴部正下方，加入抖動
                bowl_bounce = 3.0 * abs(math.sin(time_ms() / 120.0))
                rx_bowl_c, ry_bowl_c = self.rotate_point(self.look_offset_x, h * 0.22 + bowl_bounce, self.roll_angle)
                bowl_x = self.cx + rx_bowl_c
                bowl_y = self.cy + ry_bowl_c
                # 畫個紅色的碗 (半圓形弧線，開口朝上)
                self.canvas.create_arc(bowl_x - 14, bowl_y - 14, bowl_x + 14, bowl_y + 14,
                                       start=180, extent=180, fill="#f38ba8", outline="#3c2203", width=2.5, tags="character")
                # 畫幾條黃色麵條 (連到嘴巴位置)
                rx_mouth, ry_mouth = self.rotate_point(self.look_offset_x, mouth_y_offset + 3, self.roll_angle)
                mouth_x = self.cx + rx_mouth
                mouth_y = self.cy + ry_mouth
                self.canvas.create_line(bowl_x, bowl_y - 2, mouth_x, mouth_y, fill="#f9e2af", width=2.5, tags="character")
                self.canvas.create_line(bowl_x - 4, bowl_y - 2, mouth_x - 2, mouth_y, fill="#f9e2af", width=1.5, tags="character")
                self.canvas.create_line(bowl_x + 4, bowl_y - 2, mouth_x + 2, mouth_y, fill="#f9e2af", width=1.5, tags="character")
            elif eat_t == "pizza":
                # 披薩與拉絲起司
                bounce = 2.0 * abs(math.sin(time_ms() / 100.0))
                rx_pz, ry_pz = self.rotate_point(self.look_offset_x, h * 0.24 + bounce, self.roll_angle)
                pz_x = self.cx + rx_pz
                pz_y = self.cy + ry_pz
                # 畫三角形披薩片
                pts_pizza = [pz_x - 12, pz_y + 10, pz_x + 12, pz_y + 10, pz_x, pz_y - 8]
                self.canvas.create_polygon(pts_pizza, fill="#f9e2af", outline="#3c2203", width=2.0, tags="character")
                pts_sauce = [pz_x - 8, pz_y + 7, pz_x + 8, pz_y + 7, pz_x, pz_y - 4]
                self.canvas.create_polygon(pts_sauce, fill="#ff5555", tags="character")
                self.canvas.create_line(pz_x - 12, pz_y + 10, pz_x + 12, pz_y + 10, fill="#fca826", width=4.0, capstyle=tk.ROUND, tags="character")
                
                # 起司拉絲線到嘴巴
                rx_mouth, ry_mouth = self.rotate_point(self.look_offset_x, mouth_y_offset + 3, self.roll_angle)
                mouth_x = self.cx + rx_mouth
                mouth_y = self.cy + ry_mouth
                self.canvas.create_line(pz_x - 3, pz_y + 2, mouth_x, mouth_y, fill="#ffe875", width=2.0, tags="character")
                self.canvas.create_line(pz_x + 3, pz_y + 2, mouth_x, mouth_y, fill="#ffe875", width=2.0, tags="character")
            elif eat_t == "popsicle":
                # 冰棒
                bounce = 2.0 * abs(math.sin(time_ms() / 120.0))
                rx_pop, ry_pop = self.rotate_point(self.look_offset_x, h * 0.22 + bounce, self.roll_angle)
                pop_x = self.cx + rx_pop
                pop_y = self.cy + ry_pop
                # 木棒
                self.canvas.create_line(pop_x, pop_y + 5, pop_x, pop_y + 18, fill="#fca826", width=3.0, capstyle=tk.ROUND, tags="character")
                # 冰棒本體
                self.canvas.create_rectangle(pop_x - 6, pop_y - 12, pop_x + 6, pop_y + 6,
                                             fill="#89b4fa", outline="#3c2203", width=2.0, tags="character")
                # 冰棒白光高光線
                self.canvas.create_line(pop_x - 3, pop_y - 9, pop_x - 3, pop_y + 3, fill="#ffffff", width=1.5, tags="character")
            elif eat_t == "salmon_sushi":
                # 🍣 炙燒鮭魚握壽司
                bounce = 2.0 * abs(math.sin(time_ms() / 110.0))
                rx_s, ry_s = self.rotate_point(self.look_offset_x, h * 0.22 + bounce, self.roll_angle)
                sx, sy = self.cx + rx_s, self.cy + ry_s
                # 白醋飯
                self.canvas.create_oval(sx - 12, sy - 2, sx + 12, sy + 8, fill="#ffffff", outline="#3c2203", width=1.5, tags="character")
                # 鮭魚生魚片 (橙紅 + 白條紋)
                self.canvas.create_oval(sx - 14, sy - 7, sx + 14, sy + 3, fill="#ff7043", outline="#3c2203", width=1.5, tags="character")
                self.canvas.create_line(sx - 8, sy - 5, sx - 2, sy + 1, fill="#ffffff", width=1.2, tags="character")
                self.canvas.create_line(sx + 2, sy - 5, sx + 8, sy + 1, fill="#ffffff", width=1.2, tags="character")
                # 海苔束帶
                self.canvas.create_rectangle(sx - 3, sy - 7, sx + 3, sy + 8, fill="#1e1e2e", outline="", tags="character")
            elif eat_t == "cheeseburger":
                # 🍔 豪華起司雙層漢堡
                bounce = 2.5 * abs(math.sin(time_ms() / 90.0))
                rx_b, ry_b = self.rotate_point(self.look_offset_x, h * 0.23 + bounce, self.roll_angle)
                bx, by = self.cx + rx_b, self.cy + ry_b
                # 底層麵包
                self.canvas.create_rectangle(bx - 12, by + 4, bx + 12, by + 9, fill="#fab387", outline="#3c2203", width=1.5, tags="character")
                # 肉餅
                self.canvas.create_rectangle(bx - 13, by + 1, bx + 13, by + 4, fill="#5a3d28", outline="#3c2203", width=1.2, tags="character")
                # 起司熔岩
                self.canvas.create_polygon(bx - 13, by + 1, bx + 13, by + 1, bx + 11, by + 5, bx - 11, by + 5, fill="#f9e2af", tags="character")
                # 生菜
                self.canvas.create_line(bx - 14, by, bx + 14, by, fill="#a6e3a1", width=2.5, capstyle=tk.ROUND, tags="character")
                # 頂層圓麵包
                self.canvas.create_arc(bx - 13, by - 12, bx + 13, by + 2, start=0, extent=180, fill="#fab387", outline="#3c2203", width=1.5, tags="character")
                # 芝麻粒
                self.canvas.create_oval(bx - 4, by - 6, bx - 2, by - 4, fill="#ffffff", outline="", tags="character")
                self.canvas.create_oval(bx + 3, by - 7, bx + 5, by - 5, fill="#ffffff", outline="", tags="character")
            elif eat_t == "matcha_boba":
                # 🧋 抹茶黑糖波霸鮮奶
                bounce = 1.5 * abs(math.sin(time_ms() / 130.0))
                rx_m, ry_m = self.rotate_point(self.look_offset_x, h * 0.20 + bounce, self.roll_angle)
                mx, my = self.cx + rx_m, self.cy + ry_m
                # 透明手搖杯
                self.canvas.create_polygon(mx - 7, my - 12, mx + 7, my - 12, mx + 5, my + 10, mx - 5, my + 10, fill="#a6e3a1", outline="#3c2203", width=1.5, tags="character")
                # 鮮奶漸層頂部
                self.canvas.create_rectangle(mx - 7, my - 12, mx + 7, my - 5, fill="#ffffff", outline="", tags="character")
                # 底部黑糖波霸小圓珍珠
                for px_c, py_c in [(mx - 2, my + 6), (mx + 2, my + 7), (mx, my + 3)]:
                    self.canvas.create_oval(px_c - 1.5, py_c - 1.5, px_c + 1.5, py_c + 1.5, fill="#1e1e2e", outline="", tags="character")
                # 吸管
                self.canvas.create_line(mx, my - 16, mx + 4, my - 4, fill="#f38ba8", width=2.0, tags="character")
            elif eat_t == "dango":
                # 🍡 和風三色糰子
                bounce = 2.0 * abs(math.sin(time_ms() / 110.0))
                rx_d, ry_d = self.rotate_point(self.look_offset_x, h * 0.22 + bounce, self.roll_angle)
                dx, dy = self.cx + rx_d, self.cy + ry_d
                # 竹籤
                self.canvas.create_line(dx - 10, dy + 10, dx + 12, dy - 12, fill="#fca826", width=2.0, tags="character")
                # 綠糰子
                self.canvas.create_oval(dx - 8, dy + 2, dx - 2, dy + 8, fill="#a6e3a1", outline="#3c2203", width=1.2, tags="character")
                # 白糰子
                self.canvas.create_oval(dx - 3, dy - 3, dx + 3, dy + 3, fill="#ffffff", outline="#3c2203", width=1.2, tags="character")
                # 粉糰子
                self.canvas.create_oval(dx + 2, dy - 8, dx + 8, dy - 2, fill="#f5c2e7", outline="#3c2203", width=1.2, tags="character")
                
        # 繪製氣球
        if self.state == "balloon":
            rx_lh_end, ry_lh_end = self.rotate_point(-w - 10, -14, self.roll_angle)
            hand_x = self.cx + rx_lh_end
            hand_y = self.cy + ry_lh_end
            
            # 氣球飄浮微動
            drift_x = 8.0 * math.sin(time_ms() / 250.0)
            balloon_x = hand_x + drift_x - 10.0
            balloon_y = hand_y - 80.0
            
            # 畫氣球拉線
            self.canvas.create_line(hand_x, hand_y, balloon_x, balloon_y + 9, fill="#cdd6f4", width=1.5, tags="character")
            # 畫氣球本體 (紅色)
            self.canvas.create_oval(balloon_x - 15, balloon_y - 20, balloon_x + 15, balloon_y + 8,
                                    fill="#ff5555", outline="#3c2203", width=2.0, tags="character")
            # 畫氣球打結三角形
            self.canvas.create_polygon(balloon_x - 3, balloon_y + 8, balloon_x + 3, balloon_y + 8, balloon_x, balloon_y + 11,
                                       fill="#ff5555", outline="#3c2203", tags="character")

        # 繪製吹出的泡泡
        if self.bubble_scale > 0.0:
            rx_bb, ry_bb = self.rotate_point(self.look_offset_x - 12 - self.bubble_scale * 0.3,
                                             mouth_y_offset + 3 + self.bubble_scale * 0.2, self.roll_angle)
            bx_c = self.cx + rx_bb
            by_c = self.cy + ry_bb
            self.canvas.create_oval(bx_c - self.bubble_scale, by_c - self.bubble_scale,
                                    bx_c + self.bubble_scale, by_c + self.bubble_scale,
                                    fill="", outline="#f5c2e7", width=2.0, tags="character")
            if self.bubble_scale > 4:
                ref_r = max(1.0, self.bubble_scale * 0.15)
                self.canvas.create_oval(bx_c - self.bubble_scale*0.4 - ref_r, by_c - self.bubble_scale*0.4 - ref_r,
                                        bx_c - self.bubble_scale*0.4 + ref_r, by_c - self.bubble_scale*0.4 + ref_r,
                                        fill="#ffffff", outline="", tags="character")
        elif self.bubble_scale == -1.0:
            rx_bb, ry_bb = self.rotate_point(self.look_offset_x - 18, mouth_y_offset + 8, self.roll_angle)
            bx_c = self.cx + rx_bb
            by_c = self.cy + ry_bb
            for angle_pop in [0, 60, 120, 180, 240, 300]:
                rad = math.radians(angle_pop)
                x1_pop = bx_c + 3 * math.cos(rad)
                y1_pop = by_c + 3 * math.sin(rad)
                x2_pop = bx_c + 9 * math.cos(rad)
                y2_pop = by_c + 9 * math.sin(rad)
                self.canvas.create_line(x1_pop, y1_pop, x2_pop, y2_pop, fill="#f5c2e7", width=1.5, tags="character")
            create_outlined_text(self.canvas, bx_c, by_c - 12, text="*POP*", fill="#f5c2e7", font=("Consolas", 8, "bold"), outline="#11111b", width=1.0, tags="character")

    def draw_blush(self, w, h, face_rot_scale, slide_x):
        """繪製粉嫩萌系腮紅 (支援 3D 水平透視收縮與多種情緒狀態)"""
        blush_y_offset = h * 0.04 + self.look_offset_y
        left_b_dx = (-w * 0.44 + self.look_offset_x) * face_rot_scale + slide_x
        right_b_dx = (w * 0.44 + self.look_offset_x) * face_rot_scale + slide_x
        
        # 3D 球體表面水平透視縮放 (邊緣壓縮)
        b_scale_l = math.sqrt(max(0.35, 1.0 - (left_b_dx / w)**2)) * face_rot_scale
        b_scale_r = math.sqrt(max(0.35, 1.0 - (right_b_dx / w)**2)) * face_rot_scale
        
        rx_lb, ry_lb = self.rotate_point(left_b_dx, blush_y_offset, self.roll_angle)
        rx_rb, ry_rb = self.rotate_point(right_b_dx, blush_y_offset, self.roll_angle)
        
        bw = 8.5 * self.scale_x
        bh = 4.2 * self.scale_y
        
        # 情緒色調調整
        blush_color = "#f4a8b8"  # 甜美粉紅
        if self.eye_state in ("happy", "star") or getattr(self, "fever_timer", 0) > 0 or getattr(self, "candy_timer", 0) > 0:
            blush_color = "#f38ba8"  # 興奮深粉紅
            bw *= 1.15
            bh *= 1.15
        elif getattr(self, "spicy_timer", 0) > 0:
            blush_color = "#ff6666"  # 辣紅
        elif getattr(self, "ice_timer", 0) > 0:
            blush_color = "#b4befe"  # 凍紫
            
        # 左腮紅 (外層柔粉 + 內側萌萌小斜線)
        self.canvas.create_oval(self.cx + rx_lb - bw * b_scale_l, self.cy + ry_lb - bh,
                                self.cx + rx_lb + bw * b_scale_l, self.cy + ry_lb + bh,
                                fill=blush_color, outline="", tags="character")
        # 腮紅斜線 1 & 2
        rx_s1_s, ry_s1_s = self.rotate_point(left_b_dx - 2.5 * b_scale_l, blush_y_offset - 2.5, self.roll_angle)
        rx_s1_e, ry_s1_e = self.rotate_point(left_b_dx - 0.5 * b_scale_l, blush_y_offset + 2.5, self.roll_angle)
        self.canvas.create_line(self.cx + rx_s1_s, self.cy + ry_s1_s, self.cx + rx_s1_e, self.cy + ry_s1_e,
                                fill="#ffffff", width=1.2, tags="character")
                                
        # 右腮紅
        self.canvas.create_oval(self.cx + rx_rb - bw * b_scale_r, self.cy + ry_rb - bh,
                                self.cx + rx_rb + bw * b_scale_r, self.cy + ry_rb + bh,
                                fill=blush_color, outline="", tags="character")
        # 腮紅斜線
        rx_s2_s, ry_s2_s = self.rotate_point(right_b_dx + 0.5 * b_scale_r, blush_y_offset - 2.5, self.roll_angle)
        rx_s2_e, ry_s2_e = self.rotate_point(right_b_dx + 2.5 * b_scale_r, blush_y_offset + 2.5, self.roll_angle)
        self.canvas.create_line(self.cx + rx_s2_s, self.cy + ry_s2_s, self.cx + rx_s2_e, self.cy + ry_s2_e,
                                fill="#ffffff", width=1.2, tags="character")

    def draw_gradient_body(self, cx, cy, w, h):
        """繪製帶有 3D 左上角光源高光效果、果凍高光點與邊緣環境反光弧的立體球體"""
        steps = 10
        color_shadow = "#fca826"     # 右下角深陰影黃
        color_highlight = "#ffe875"  # 左上角高光淡黃
        
        equipped = getattr(self, "equipped_accessory", None)
        
        if getattr(self, "spicy_timer", 0) > 0:
            color_shadow = "#b31e1e"
            color_highlight = "#ff7777"
        elif getattr(self, "ice_timer", 0) > 0:
            color_shadow = "#589dbd"     # 冰藍陰影
            color_highlight = "#b4f4f4"  # 冰綠藍高光
        elif equipped == "crown":
            color_shadow = "#f59e0b"     # 溫暖明亮金
            color_highlight = "#fffbeb"  # 璀璨香檳亮金高光
        elif equipped == "rainbow":
            import colorsys
            t = time_ms() / 1500.0
            r, g, b = colorsys.hsv_to_rgb(t % 1.0, 0.55, 0.95)
            color_highlight = f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
            r_s, g_s, b_s = colorsys.hsv_to_rgb(t % 1.0, 0.75, 0.75)
            color_shadow = f"#{int(r_s*255):02x}{int(g_s*255):02x}{int(b_s*255):02x}"
            
        # 最底層外圍黑線輪廓圓
        self.canvas.create_oval(cx - w, cy - h, cx + w, cy + h,
                                fill=color_shadow, outline="#3c2203", width=5.0, tags="character")
        
        # 同心圓疊加層，偏向左上方 (細膩 10 steps 漸層)
        for i in range(1, steps):
            factor = i / steps
            curr_w = w * (1.0 - factor * 0.95)
            curr_h = h * (1.0 - factor * 0.95)
            
            # 中心偏向左上 (光源位置偏移)
            offset_x = - (w - curr_w) * 0.17
            offset_y = - (h - curr_h) * 0.17
            
            curr_color = interpolate_color(color_shadow, color_highlight, factor)
            self.canvas.create_oval(cx + offset_x - curr_w, cy + offset_y - curr_h,
                                    cx + offset_x + curr_w, cy + offset_y + curr_h,
                                    fill=curr_color, outline="", tags="character")

        # 🌟 額外 1：左上方水滴狀果凍高光 (Glossy Specular Highlight)
        hl_spot_x = cx - w * 0.38
        hl_spot_y = cy - h * 0.38
        hl_w = w * 0.22
        hl_h = h * 0.14
        # 主高光橢圓
        self.canvas.create_oval(hl_spot_x - hl_w, hl_spot_y - hl_h,
                                hl_spot_x + hl_w, hl_spot_y + hl_h,
                                fill="#ffffff", outline="", tags="character")
        # 次高光微小光點
        sub_hl_x = cx - w * 0.20
        sub_hl_y = cy - h * 0.52
        sub_hl_r = min(w, h) * 0.055
        self.canvas.create_oval(sub_hl_x - sub_hl_r, sub_hl_y - sub_hl_r,
                                sub_hl_x + sub_hl_r, sub_hl_y + sub_hl_r,
                                fill="#ffffff", outline="", tags="character")

        # 🌟 額外 2：右下方環境反光弧 (Rim Bounce Light)
        rim_color = "#fbe7aa" if equipped != "ice_timer" else "#cceeff"
        self.canvas.create_arc(cx - w * 0.88, cy - h * 0.88, cx + w * 0.88, cy + h * 0.88,
                               start=-60, extent=45, style=tk.ARC,
                               outline=rim_color, width=2.0, tags="character")

    def draw_sign_board(self, name, price_str, coins):
        """繪製地瓜球頭頂上舉著的高質感日系黑板木框看板"""
        # 看板坐標位置 (在地瓜球上方)
        bx = self.cx
        by = self.cy - (self.r * self.scale_y) - 48
        
        bw = 88   # 看板半寬
        bh = 34   # 看板半高
        
        # 1. 繪製看板背後落影
        self.canvas.create_rectangle(bx - bw + 3, by - bh + 3, bx + bw + 3, by + bh + 3,
                                     fill="#11111b", outline="", tags="character")
        
        # 2. 繪製外層木紋邊框 (溫暖濃茶色)
        self.canvas.create_rectangle(bx - bw, by - bh, bx + bw, by + bh,
                                     fill="#3c2203", outline="#251605", width=2.0, tags="character")
        # 內層深黑板底
        self.canvas.create_rectangle(bx - bw + 3, by - bh + 3, bx + bw - 3, by + bh - 3,
                                     fill="#181825", outline="#45475a", width=1.0, tags="character")
        
        # 3. 繪製精緻連接支架與頂部固定小銅扣
        self.canvas.create_line(self.cx - self.r * 0.5, self.cy - self.r * 0.7, bx - bw * 0.7, by + bh,
                                width=2.5, fill="#3c2203", tags="character")
        self.canvas.create_line(self.cx + self.r * 0.5, self.cy - self.r * 0.7, bx + bw * 0.7, by + bh,
                                width=2.5, fill="#3c2203", tags="character")
        # 頂部四角小銅扣
        for cx_k, cy_k in [(bx - bw + 6, by - bh + 6), (bx + bw - 6, by - bh + 6)]:
            self.canvas.create_oval(cx_k - 2, cy_k - 2, cx_k + 2, cy_k + 2, fill="#fab387", outline="", tags="character")

        if getattr(self, "custom_board_text", None):
            lines = self.custom_board_text
            if len(lines) >= 1:
                create_outlined_text(self.canvas, bx, by - 15, text=lines[0], fill="#f5c2e7",
                                     font=("微軟正黑體", 9, "bold"), outline="#11111b", width=1.0, tags="character")
            if len(lines) >= 2:
                create_outlined_text(self.canvas, bx, by + 1, text=lines[1], fill="#cdd6f4",
                                     font=("微軟正黑體", 9, "bold"), outline="#11111b", width=1.0, tags="character")
            if len(lines) >= 3:
                create_outlined_text(self.canvas, bx, by + 16, text=lines[2], fill="#fab387",
                                     font=("微軟正黑體", 8, "bold"), outline="#11111b", width=1.0, tags="character")
        else:
            display_name = name[:10] + "..." if len(name) > 10 else name
            create_outlined_text(self.canvas, bx, by - 15, text=f"👤 {display_name}", fill="#89dceb",
                                     font=("微軟正黑體", 9, "bold"), outline="#11111b", width=1.0, tags="character")
            create_outlined_text(self.canvas, bx, by + 1, text=f"💰 {price_str}", fill="#a6e3a1",
                                 font=("微軟正黑體", 9, "bold"), outline="#11111b", width=1.0, tags="character")
            create_outlined_text(self.canvas, bx, by + 16, text=f"🪙 地瓜幣: {coins:,}", fill="#f9e2af",
                                 font=("微軟正黑體", 8, "bold"), outline="#11111b", width=1.0, tags="character")

    def draw_rotated_arc_eyebrow(self, x, y, r, angle):
        """繪製跟著身體旋轉的向下彎眉毛"""
        pts = []
        steps = 8
        for i in range(steps + 1):
            # 弧線在本地坐標的偏移
            dx = -r * 0.5 + r * (i / steps)
            dy = - (r * 0.28) * math.sin(math.pi * (i / steps))
            # 旋轉偏移
            rx, ry = self.rotate_point(dx, dy, angle)
            pts.append(x + rx)
            pts.append(y + ry)
        self.canvas.create_line(*pts, smooth=True, width=4.0, fill="#3c2203", capstyle=tk.ROUND, tags="character")

    def draw_rotated_arc_eye(self, x, y, eye_r_size, angle, flip=False):
        """繪製旋轉後的笑笑彎眼 (^^)"""
        pts = []
        steps = 8
        for i in range(steps + 1):
            dx = -eye_r_size * 0.5 + eye_r_size * (i / steps)
            factor = -0.9 if flip else 0.9
            dy = factor * (eye_r_size * 0.3) * math.sin(math.pi * (i / steps))
            rx, ry = self.rotate_point(dx, dy, angle)
            pts.append(x + rx)
            pts.append(y + ry)
        self.canvas.create_line(*pts, smooth=True, width=4.0, fill="#3c2203", capstyle=tk.ROUND, tags="character")

    def draw_rotated_cat_mouth(self, x, y, angle, scale_x=1.0):
        """繪製旋轉後的貓咪 w 嘴 (支援水平透視縮放)"""
        # 左半弧本地點
        left_pts = [(-7 * scale_x, 1), (-4.5 * scale_x, 4.5), (0, 0)]
        rotated_l = []
        for dx, dy in left_pts:
            rx, ry = self.rotate_point(dx, dy, angle)
            rotated_l.append(x + rx)
            rotated_l.append(y + ry)
        self.canvas.create_line(*rotated_l, smooth=True, width=4.0, fill="#3c2203", capstyle=tk.ROUND, tags="character")
        
        # 右半弧本地點
        right_pts = [(0, 0), (4.5 * scale_x, 4.5), (7 * scale_x, 1)]
        rotated_r = []
        for dx, dy in right_pts:
            rx, ry = self.rotate_point(dx, dy, angle)
            rotated_r.append(x + rx)
            rotated_r.append(y + ry)
        self.canvas.create_line(*rotated_r, smooth=True, width=4.0, fill="#3c2203", capstyle=tk.ROUND, tags="character")

    def draw_rotated_star_eye(self, x, y, r, angle, scale_x=1.0):
        """在 (x, y) 位置繪製一個旋轉了 angle 角度的五角星眼 (★) (支援水平透視縮放)"""
        pts = []
        for i in range(10):
            r_curr = r if i % 2 == 0 else r * 0.4
            angle_star = -math.pi/2 + i * (2 * math.pi / 10)
            dx = r_curr * math.cos(angle_star) * scale_x
            dy = r_curr * math.sin(angle_star)
            # 旋轉偏移
            rx, ry = self.rotate_point(dx, dy, angle)
            pts.append(x + rx)
            pts.append(y + ry)
        self.canvas.create_polygon(pts, fill="#fca826", outline="#3c2203", width=2.0, tags="character")

    def draw_accessories(self, w, h, left_eye_dx, right_eye_dx, eye_y_offset):
        """依當前裝備的配件進行動態旋轉與縮放繪製"""
        equipped = getattr(self, "equipped_accessory", None)
        
        # 計算背面旋轉比例 (0.0 = 完全正面, 1.0 = 完全背面)
        rotation_fraction = 0.0
        state = getattr(self, "state", "idle")
        if state == "back_idle":
            rotation_fraction = 1.0
        elif state == "turn_to_back":
            turn_timer = getattr(self, "turn_timer", 15)
            rotation_fraction = 1.0 - (turn_timer / 15.0)
        elif state == "turn_to_front":
            turn_timer = getattr(self, "turn_timer", 15)
            rotation_fraction = turn_timer / 15.0

        if not equipped or self.state in ("sleep", "sleep_futon"):
            return
            
        if rotation_fraction >= 0.8 and equipped != "char_mask":
            return
            
        acc_rot_scale = 1.0 - rotation_fraction
        slide_x = rotation_fraction * w * 0.55
            
        if equipped == "crown":
            # 👑 皇家皇冠
            crown_w = 12.0 * self.scale_x
            crown_h = 14.0 * self.scale_y
            pts = []
            for dx_p, dy_p in [(-crown_w, 0), (-crown_w - 2, -crown_h), (-crown_w * 0.4, -crown_h * 0.4), 
                               (0, -crown_h * 1.2), (crown_w * 0.4, -crown_h * 0.4), (crown_w + 2, -crown_h), (crown_w, 0)]:
                rx_p, ry_p = self.rotate_point(dx_p * acc_rot_scale + slide_x, -h * 0.85 + dy_p, self.roll_angle)
                pts.append(self.cx + rx_p)
                pts.append(self.cy + ry_p)
            self.canvas.create_polygon(pts, fill="#f9e2af", outline="#3c2203", width=2.0, tags="character")
            
            # 寶石裝飾
            for dx_t, dy_t, col in [(-crown_w - 2, -crown_h, "#f38ba8"), (0, -crown_h * 1.2, "#a6e3a1"), (crown_w + 2, -crown_h, "#89b4fa")]:
                rx_t, ry_t = self.rotate_point(dx_t * acc_rot_scale + slide_x, -h * 0.85 + dy_t, self.roll_angle)
                self.canvas.create_oval(self.cx + rx_t - 2.5 * acc_rot_scale, self.cy + ry_t - 2.5, self.cx + rx_t + 2.5 * acc_rot_scale, self.cy + ry_t + 2.5,
                                        fill=col, outline="#3c2203", width=1.0, tags="character")
                                        
        elif equipped == "scholar_cap":
            # 🎓 博士帽 (精緻 3D 透視平頂方帽 + 圓柱帽箍 + 垂墜流蘇，全比例防穿模)
            cap_w = 20.0 * self.scale_x
            cap_h = 6.5 * self.scale_y
            cap_base_w = 11.0 * self.scale_x
            cap_y = -h * 0.90
            
            # 1. 圓柱帽箍 (梯形底座，先畫在底層)
            pts_base = []
            for dx_p, dy_p in [(-cap_base_w * 0.9, 0), (cap_base_w * 0.9, 0), (cap_base_w, 7.5 * self.scale_y), (-cap_base_w, 7.5 * self.scale_y)]:
                rx_p, ry_p = self.rotate_point(dx_p * acc_rot_scale + slide_x, cap_y + dy_p, self.roll_angle)
                pts_base.append(self.cx + rx_p)
                pts_base.append(self.cy + ry_p)
            self.canvas.create_polygon(pts_base, fill="#181825", outline="#3c2203", width=1.8, tags="character")

            # 2. 頂部菱形平頂方板 (Mortarboard)
            pts_diamond = []
            for dx_p, dy_p in [(-cap_w, 0), (0, -cap_h), (cap_w, 0), (0, cap_h)]:
                rx_p, ry_p = self.rotate_point(dx_p * acc_rot_scale + slide_x, cap_y + dy_p, self.roll_angle)
                pts_diamond.append(self.cx + rx_p)
                pts_diamond.append(self.cy + ry_p)
            self.canvas.create_polygon(pts_diamond, fill="#313244", outline="#3c2203", width=2.0, tags="character")
            
            # 3. 頂部中心小鈕扣
            rx_btn, ry_btn = self.rotate_point(slide_x, cap_y, self.roll_angle)
            self.canvas.create_oval(self.cx + rx_btn - 2.5 * acc_rot_scale, self.cy + ry_btn - 2.0,
                                    self.cx + rx_btn + 2.5 * acc_rot_scale, self.cy + ry_btn + 2.0,
                                    fill="#f9e2af", outline="#3c2203", width=1.0, tags="character")
            
            # 4. 垂墜金色流蘇穗 (帶有自然微擺動)
            tassel_swing = 1.5 * math.sin(time_ms() / 200.0)
            rx_t1, ry_t1 = self.rotate_point((cap_w * 0.65) * acc_rot_scale + slide_x, cap_y + 3, self.roll_angle)
            rx_t2, ry_t2 = self.rotate_point((cap_w * 0.75) * acc_rot_scale + slide_x + tassel_swing, cap_y + 13, self.roll_angle)
            self.canvas.create_line(self.cx + rx_btn, self.cy + ry_btn, self.cx + rx_t1, self.cy + ry_t1, fill="#f9e2af", width=1.5, tags="character")
            self.canvas.create_line(self.cx + rx_t1, self.cy + ry_t1, self.cx + rx_t2, self.cy + ry_t2, fill="#fab387", width=2.2, tags="character")
            self.canvas.create_oval(self.cx + rx_t2 - 2, self.cy + ry_t2 - 2, self.cx + rx_t2 + 2, self.cy + ry_t2 + 2,
                                    fill="#f9e2af", outline="#3c2203", width=1.0, tags="character")
            
        elif equipped == "sunglasses":
            # 🕶️ 酷炫墨鏡
            lens_w = 11.0 * self.scale_x
            lens_h = 7.0 * self.scale_y
            
            # 左鏡片
            pts_l = []
            for dx_p, dy_p in [(-lens_w * acc_rot_scale, -lens_h), (lens_w * acc_rot_scale, -lens_h), (lens_w * acc_rot_scale, lens_h), (-lens_w * acc_rot_scale, lens_h)]:
                rx_p, ry_p = self.rotate_point(left_eye_dx + dx_p, eye_y_offset + dy_p, self.roll_angle)
                pts_l.append(self.cx + rx_p)
                pts_l.append(self.cy + ry_p)
            
            # 右鏡片
            pts_r = []
            for dx_p, dy_p in [(-lens_w * acc_rot_scale, -lens_h), (lens_w * acc_rot_scale, -lens_h), (lens_w * acc_rot_scale, lens_h), (-lens_w * acc_rot_scale, lens_h)]:
                rx_p, ry_p = self.rotate_point(right_eye_dx + dx_p, eye_y_offset + dy_p, self.roll_angle)
                pts_r.append(self.cx + rx_p)
                pts_r.append(self.cy + ry_p)
                
            self.canvas.create_polygon(pts_l, fill="#11111b", outline="#3c2203", width=2.0, tags="character")
            self.canvas.create_polygon(pts_r, fill="#11111b", outline="#3c2203", width=2.0, tags="character")
            
            # 鏡架鼻樑
            rx_b1, ry_b1 = self.rotate_point(left_eye_dx + 3 * acc_rot_scale, eye_y_offset - 2, self.roll_angle)
            rx_b2, ry_b2 = self.rotate_point(right_eye_dx - 3 * acc_rot_scale, eye_y_offset - 2, self.roll_angle)
            self.canvas.create_line(self.cx + rx_b1, self.cy + ry_b1, self.cx + rx_b2, self.cy + ry_b2, fill="#11111b", width=3.0, tags="character")
            
        elif equipped == "bandage":
            # 🩹 OK繃
            band_dx = w * 0.42 * acc_rot_scale + slide_x
            band_dy = h * 0.22
            band_w = 9.0 * self.scale_x * acc_rot_scale
            band_h = 5.0 * self.scale_y
            
            pts_band = []
            local_angle = -math.pi / 6
            for dx_p, dy_p in [(-band_w, -band_h), (band_w, -band_h), (band_w, band_h), (-band_w, band_h)]:
                ldx = dx_p * math.cos(local_angle) - dy_p * math.sin(local_angle)
                ldy = dx_p * math.sin(local_angle) + dy_p * math.cos(local_angle)
                rx_p, ry_p = self.rotate_point(band_dx + ldx, band_dy + ldy, self.roll_angle)
                pts_band.append(self.cx + rx_p)
                pts_band.append(self.cy + ry_p)
            self.canvas.create_polygon(pts_band, fill="#f2cdcd", outline="#3c2203", width=1.5, tags="character")
            
            # OK繃中心紅十字
            rx_c, ry_c = self.rotate_point(band_dx, band_dy, self.roll_angle)
            self.canvas.create_line(self.cx + rx_c - 2 * acc_rot_scale, self.cy + ry_c, self.cx + rx_c + 2 * acc_rot_scale, self.cy + ry_c, fill="#f38ba8", width=1.5, tags="character")
            self.canvas.create_line(self.cx + rx_c, self.cy + ry_c - 2, self.cx + rx_c, self.cy + ry_c + 2, fill="#f38ba8", width=1.5, tags="character")
            
        elif equipped == "cat_ears":
            # 🐱 貓咪耳朵 (在頭頂兩側繪製旋轉三角形耳朵)
            # 左耳
            le_pts = [
                self.rotate_point(-w * 0.6 * acc_rot_scale + slide_x, -h * 0.4, self.roll_angle),
                self.rotate_point(-w * 0.2 * acc_rot_scale + slide_x, -h * 0.55, self.roll_angle),
                self.rotate_point(-w * 0.45 * acc_rot_scale + slide_x, -h * 0.88, self.roll_angle)
            ]
            le_abs = []
            for dx, dy in le_pts:
                le_abs.extend([self.cx + dx, self.cy + dy])
            self.canvas.create_polygon(le_abs, fill="#3c2203", outline="#3c2203", width=2.0, tags="character")
            
            le_inner = [
                self.rotate_point(-w * 0.52 * acc_rot_scale + slide_x, -h * 0.45, self.roll_angle),
                self.rotate_point(-w * 0.25 * acc_rot_scale + slide_x, -h * 0.53, self.roll_angle),
                self.rotate_point(-w * 0.42 * acc_rot_scale + slide_x, -h * 0.78, self.roll_angle)
            ]
            le_inner_abs = []
            for dx, dy in le_inner:
                le_inner_abs.extend([self.cx + dx, self.cy + dy])
            self.canvas.create_polygon(le_inner_abs, fill="#ffb7c5", tags="character")
            
            # 右耳
            re_pts = [
                self.rotate_point(w * 0.2 * acc_rot_scale + slide_x, -h * 0.55, self.roll_angle),
                self.rotate_point(w * 0.6 * acc_rot_scale + slide_x, -h * 0.4, self.roll_angle),
                self.rotate_point(w * 0.45 * acc_rot_scale + slide_x, -h * 0.88, self.roll_angle)
            ]
            re_abs = []
            for dx, dy in re_pts:
                re_abs.extend([self.cx + dx, self.cy + dy])
            self.canvas.create_polygon(re_abs, fill="#3c2203", outline="#3c2203", width=2.0, tags="character")
            
            re_inner = [
                self.rotate_point(w * 0.25 * acc_rot_scale + slide_x, -h * 0.53, self.roll_angle),
                self.rotate_point(w * 0.52 * acc_rot_scale + slide_x, -h * 0.45, self.roll_angle),
                self.rotate_point(w * 0.42 * acc_rot_scale + slide_x, -h * 0.78, self.roll_angle)
            ]
            re_inner_abs = []
            for dx, dy in re_inner:
                re_inner_abs.extend([self.cx + dx, self.cy + dy])
            self.canvas.create_polygon(re_inner_abs, fill="#ffb7c5", tags="character")
            
        elif equipped == "halo":
            # 😇 天使光環 (浮動發光黃金環)
            hover = 4.0 * math.sin(time_ms() / 150.0)
            halo_y_local = -h * 0.90 + hover
            pts_halo = []
            steps_halo = 12
            for i in range(steps_halo):
                angle_h = i * (2 * math.pi / steps_halo)
                dx_h = (15 * self.scale_x * acc_rot_scale) * math.cos(angle_h) + slide_x
                dy_h = (4 * self.scale_y) * math.sin(angle_h)
                rx_h, ry_h = self.rotate_point(dx_h, halo_y_local + dy_h, self.roll_angle)
                pts_halo.append(self.cx + rx_h)
                pts_halo.append(self.cy + ry_h)
            self.canvas.create_polygon(pts_halo, fill="", outline="#ffe875", width=3.5, tags="character")
            
        elif equipped == "gentleman_hat":
            # 🎩 紳士魔術帽 (包含小兔子蹦跳動畫)
            pop_y = 0.0
            pop_timer = getattr(self, "rabbit_pop_timer", 0)
            if pop_timer > 140:
                t_p = (pop_timer - 140) / 40.0
                pop_y = 14.0 * math.sin(t_p * math.pi)
            
            if pop_y > 0.1:
                # 畫兔子頭與耳朵 (先畫以利被帽身遮擋)
                rx_r, ry_r = self.rotate_point(slide_x, -h * 0.90 - pop_y, self.roll_angle)
                self.canvas.create_oval(self.cx + rx_r - 6 * acc_rot_scale, self.cy + ry_r - 6,
                                        self.cx + rx_r + 6 * acc_rot_scale, self.cy + ry_r + 6,
                                        fill="#ffffff", outline="#3c2203", width=1.5, tags="character")
                rx_le_s, ry_le_s = self.rotate_point(-3 * acc_rot_scale + slide_x, -h * 0.90 - pop_y - 4, self.roll_angle)
                rx_le_e, ry_le_e = self.rotate_point(-4 * acc_rot_scale + slide_x, -h * 0.90 - pop_y - 12, self.roll_angle)
                self.canvas.create_line(self.cx + rx_le_s, self.cy + ry_le_s,
                                        self.cx + rx_le_e, self.cy + ry_le_e,
                                        width=2.5, fill="#ffffff", tags="character")
                rx_re_s, ry_re_s = self.rotate_point(3 * acc_rot_scale + slide_x, -h * 0.90 - pop_y - 4, self.roll_angle)
                rx_re_e, ry_re_e = self.rotate_point(4 * acc_rot_scale + slide_x, -h * 0.90 - pop_y - 12, self.roll_angle)
                self.canvas.create_line(self.cx + rx_re_s, self.cy + ry_re_s,
                                        self.cx + rx_re_e, self.cy + ry_re_e,
                                        width=2.5, fill="#ffffff", tags="character")
            
            # 畫帽沿
            brim_w = 22.0 * self.scale_x
            pts_brim = []
            for dx_p, dy_p in [(-brim_w, 0), (brim_w, 0), (brim_w, 3.0 * self.scale_y), (-brim_w, 3.0 * self.scale_y)]:
                rx_p, ry_p = self.rotate_point(dx_p * acc_rot_scale + slide_x, -h * 0.82 + dy_p, self.roll_angle)
                pts_brim.append(self.cx + rx_p)
                pts_brim.append(self.cy + ry_p)
            self.canvas.create_polygon(pts_brim, fill="#11111b", outline="#3c2203", width=2.0, tags="character")
            
            # 畫帽身
            hat_w = 14.0 * self.scale_x
            hat_h = 16.0 * self.scale_y
            pts_hat = []
            for dx_p, dy_p in [(-hat_w, 0), (hat_w, 0), (hat_w, -hat_h), (-hat_w, -hat_h)]:
                rx_p, ry_p = self.rotate_point(dx_p * acc_rot_scale + slide_x, -h * 0.82 + dy_p, self.roll_angle)
                pts_hat.append(self.cx + rx_p)
                pts_hat.append(self.cy + ry_p)
            self.canvas.create_polygon(pts_hat, fill="#11111b", outline="#3c2203", width=2.0, tags="character")
            
            # 畫紅緞帶
            pts_ribbon = []
            for dx_p, dy_p in [(-hat_w, 0), (hat_w, 0), (hat_w, -3.0 * self.scale_y), (-hat_w, -3.0 * self.scale_y)]:
                rx_p, ry_p = self.rotate_point(dx_p * acc_rot_scale + slide_x, -h * 0.82 + dy_p, self.roll_angle)
                pts_ribbon.append(self.cx + rx_p)
                pts_ribbon.append(self.cy + ry_p)
            self.canvas.create_polygon(pts_ribbon, fill="#ff5555", outline="#3c2203", width=1.0, tags="character")
            
        elif equipped == "demon_horns":
            # 😈 惡魔雙角 (小紅角)
            # 左角
            pts_lh = []
            for dx_p, dy_p in [(-w*0.35, -h*0.55), (-w*0.52, -h*0.85), (-w*0.22, -h*0.65)]:
                rx_p, ry_p = self.rotate_point(dx_p * acc_rot_scale + slide_x, dy_p, self.roll_angle)
                pts_lh.append(self.cx + rx_p)
                pts_lh.append(self.cy + ry_p)
            self.canvas.create_polygon(pts_lh, fill="#ff5555", outline="#3c2203", width=2.0, tags="character")
            # 右角
            pts_rh = []
            for dx_p, dy_p in [(w*0.35, -h*0.55), (w*0.52, -h*0.85), (w*0.22, -h*0.65)]:
                rx_p, ry_p = self.rotate_point(dx_p * acc_rot_scale + slide_x, dy_p, self.roll_angle)
                pts_rh.append(self.cx + rx_p)
                pts_rh.append(self.cy + ry_p)
            self.canvas.create_polygon(pts_rh, fill="#ff5555", outline="#3c2203", width=2.0, tags="character")
            
        elif equipped == "star_sunglasses":
            # 🌟 星星墨鏡 (黃色亮星)
            # 左星星鏡片
            pts_l = []
            for i in range(10):
                r_curr = 9.5 if i % 2 == 0 else 3.8
                angle_star = -math.pi/2 + i * (2 * math.pi / 10) + self.roll_angle
                rx, ry = self.rotate_point(r_curr * math.cos(angle_star) * acc_rot_scale, r_curr * math.sin(angle_star), 0)
                pts_l.append(self.cx + left_eye_dx + rx)
                pts_l.append(self.cy + eye_y_offset + ry)
            self.canvas.create_polygon(pts_l, fill="#ffe875", outline="#3c2203", width=2.0, tags="character")
            
            # 右星星鏡片
            pts_r = []
            for i in range(10):
                r_curr = 9.5 if i % 2 == 0 else 3.8
                angle_star = -math.pi/2 + i * (2 * math.pi / 10) + self.roll_angle
                rx, ry = self.rotate_point(r_curr * math.cos(angle_star) * acc_rot_scale, r_curr * math.sin(angle_star), 0)
                pts_r.append(self.cx + right_eye_dx + rx)
                pts_r.append(self.cy + eye_y_offset + ry)
            self.canvas.create_polygon(pts_r, fill="#ffe875", outline="#3c2203", width=2.0, tags="character")
            
            # 鏡架鼻樑
            rx_b1, ry_b1 = self.rotate_point(left_eye_dx + 3 * acc_rot_scale, eye_y_offset - 2, self.roll_angle)
            rx_b2, ry_b2 = self.rotate_point(right_eye_dx - 3 * acc_rot_scale, eye_y_offset - 2, self.roll_angle)
            self.canvas.create_line(self.cx + rx_b1, self.cy + ry_b1, self.cx + rx_b2, self.cy + ry_b2, fill="#11111b", width=3.0, tags="character")

        elif equipped == "bowtie":
            # 🎀 優雅蝴蝶結 (移至胸前正中，增加精緻雙層立體感與下垂緞帶)
            bt_y = h * 0.52
            bw = 10.0 * self.scale_x
            bh = 6.0 * self.scale_y
            
            # 左下垂緞帶
            pts_ribbon_l = [
                self.rotate_point(-2 * acc_rot_scale + slide_x, bt_y + 1, self.roll_angle),
                self.rotate_point(-6 * acc_rot_scale + slide_x, bt_y + 9, self.roll_angle),
                self.rotate_point(-3 * acc_rot_scale + slide_x, bt_y + 8, self.roll_angle),
                self.rotate_point(slide_x, bt_y + 2, self.roll_angle)
            ]
            abs_rib_l = []
            for dx, dy in pts_ribbon_l: abs_rib_l.extend([self.cx + dx, self.cy + dy])
            self.canvas.create_polygon(abs_rib_l, fill="#f38ba8", outline="#3c2203", width=1.2, tags="character")

            # 右下垂緞帶
            pts_ribbon_r = [
                self.rotate_point(2 * acc_rot_scale + slide_x, bt_y + 1, self.roll_angle),
                self.rotate_point(6 * acc_rot_scale + slide_x, bt_y + 9, self.roll_angle),
                self.rotate_point(3 * acc_rot_scale + slide_x, bt_y + 8, self.roll_angle),
                self.rotate_point(slide_x, bt_y + 2, self.roll_angle)
            ]
            abs_rib_r = []
            for dx, dy in pts_ribbon_r: abs_rib_r.extend([self.cx + dx, self.cy + dy])
            self.canvas.create_polygon(abs_rib_r, fill="#f38ba8", outline="#3c2203", width=1.2, tags="character")

            # 左翼 (帶微摺角)
            pts_l = [
                self.rotate_point(-bw * acc_rot_scale + slide_x, bt_y - bh, self.roll_angle),
                self.rotate_point(slide_x, bt_y - 1, self.roll_angle),
                self.rotate_point(slide_x, bt_y + 1, self.roll_angle),
                self.rotate_point(-bw * acc_rot_scale + slide_x, bt_y + bh, self.roll_angle),
                self.rotate_point(-bw * 0.8 * acc_rot_scale + slide_x, bt_y, self.roll_angle)
            ]
            abs_l = []
            for dx, dy in pts_l: abs_l.extend([self.cx + dx, self.cy + dy])
            self.canvas.create_polygon(abs_l, fill="#ffb7c5", outline="#3c2203", width=1.5, tags="character")
            
            # 右翼
            pts_r = [
                self.rotate_point(bw * acc_rot_scale + slide_x, bt_y - bh, self.roll_angle),
                self.rotate_point(slide_x, bt_y - 1, self.roll_angle),
                self.rotate_point(slide_x, bt_y + 1, self.roll_angle),
                self.rotate_point(bw * acc_rot_scale + slide_x, bt_y + bh, self.roll_angle),
                self.rotate_point(bw * 0.8 * acc_rot_scale + slide_x, bt_y, self.roll_angle)
            ]
            abs_r = []
            for dx, dy in pts_r: abs_r.extend([self.cx + dx, self.cy + dy])
            self.canvas.create_polygon(abs_r, fill="#ffb7c5", outline="#3c2203", width=1.5, tags="character")
            
            # 中間圓結
            rx_c, ry_c = self.rotate_point(slide_x, bt_y, self.roll_angle)
            self.canvas.create_oval(self.cx + rx_c - 3.5 * acc_rot_scale, self.cy + ry_c - 3.5,
                                    self.cx + rx_c + 3.5 * acc_rot_scale, self.cy + ry_c + 3.5,
                                    fill="#f38ba8", outline="#3c2203", width=1.5, tags="character")

        elif equipped == "sakura_hairpin":
            # 🌸 櫻花小髮夾 (頭側粉嫩五瓣櫻花 + 花蕊)
            fx = w * 0.45 * acc_rot_scale + slide_x
            fy = -h * 0.60
            for i in range(5):
                ang = i * (2 * math.pi / 5) - math.pi / 2
                p_dx = fx + math.cos(ang) * 5.5 * acc_rot_scale
                p_dy = fy + math.sin(ang) * 5.5
                rx_p, ry_p = self.rotate_point(p_dx, p_dy, self.roll_angle)
                self.canvas.create_oval(self.cx + rx_p - 3.5 * acc_rot_scale, self.cy + ry_p - 3.5,
                                        self.cx + rx_p + 3.5 * acc_rot_scale, self.cy + ry_p + 3.5,
                                        fill="#ffc0cb", outline="#3c2203", width=1.0, tags="character")
            # 花心金色花蕊
            rx_fc, ry_fc = self.rotate_point(fx, fy, self.roll_angle)
            self.canvas.create_oval(self.cx + rx_fc - 2.5 * acc_rot_scale, self.cy + ry_fc - 2.5,
                                    self.cx + rx_fc + 2.5 * acc_rot_scale, self.cy + ry_fc + 2.5,
                                    fill="#f9e2af", outline="#3c2203", width=1.0, tags="character")

        elif equipped == "fox_mask":
            # 🦊 和風狐狸面具 (斜戴在頭部右上方)
            mx = w * 0.45 * acc_rot_scale + slide_x
            my = -h * 0.65
            mw = 12.0 * self.scale_x * acc_rot_scale
            mh = 14.0 * self.scale_y
            # 面具主體 (白底狐面)
            pts_mask = [
                self.rotate_point(mx - mw, my - mh * 0.2, self.roll_angle),
                self.rotate_point(mx - mw * 0.7, my - mh, self.roll_angle), # 左耳尖
                self.rotate_point(mx, my - mh * 0.5, self.roll_angle),
                self.rotate_point(mx + mw * 0.7, my - mh, self.roll_angle), # 右耳尖
                self.rotate_point(mx + mw, my - mh * 0.2, self.roll_angle),
                self.rotate_point(mx, my + mh * 0.8, self.roll_angle) # 下巴
            ]
            abs_m = []
            for dx, dy in pts_mask: abs_m.extend([self.cx + dx, self.cy + dy])
            self.canvas.create_polygon(abs_m, fill="#ffffff", outline="#3c2203", width=1.5, tags="character")
            # 耳朵內側紅紋
            rx_el, ry_el = self.rotate_point(mx - mw * 0.5, my - mh * 0.7, self.roll_angle)
            self.canvas.create_oval(self.cx + rx_el - 2, self.cy + ry_el - 3, self.cx + rx_el + 2, self.cy + ry_el + 3, fill="#ff5555", outline="", tags="character")
            rx_er, ry_er = self.rotate_point(mx + mw * 0.5, my - mh * 0.7, self.roll_angle)
            self.canvas.create_oval(self.cx + rx_er - 2, self.cy + ry_er - 3, self.cx + rx_er + 2, self.cy + ry_er + 3, fill="#ff5555", outline="", tags="character")
            # 狐狸眼睛紅紋
            rx_eye1, ry_eye1 = self.rotate_point(mx - mw * 0.35, my, self.roll_angle)
            self.canvas.create_line(self.cx + rx_eye1 - 3, self.cy + ry_eye1, self.cx + rx_eye1 + 3, self.cy + ry_eye1 + 2, fill="#ff5555", width=2.0, tags="character")
            rx_eye2, ry_eye2 = self.rotate_point(mx + mw * 0.35, my, self.roll_angle)
            self.canvas.create_line(self.cx + rx_eye2 - 3, self.cy + ry_eye2 + 2, self.cx + rx_eye2 + 3, self.cy + ry_eye2, fill="#ff5555", width=2.0, tags="character")
            # 黑色小鼻尖
            rx_n, ry_n = self.rotate_point(mx, my + mh * 0.4, self.roll_angle)
            self.canvas.create_oval(self.cx + rx_n - 1.5, self.cy + ry_n - 1.5, self.cx + rx_n + 1.5, self.cy + ry_n + 1.5, fill="#11111b", outline="", tags="character")
            # 側面繫繩與紅流蘇
            rx_cord, ry_cord = self.rotate_point(mx - mw * 0.8, my + mh * 0.2, self.roll_angle)
            self.canvas.create_line(self.cx + rx_cord, self.cy + ry_cord, self.cx + rx_cord - 4, self.cy + ry_cord + 10, fill="#ff5555", width=1.5, tags="character")
            self.canvas.create_oval(self.cx + rx_cord - 6, self.cy + ry_cord + 9, self.cx + rx_cord - 2, self.cy + ry_cord + 13, fill="#fab387", outline="", tags="character")

        elif equipped == "frog_hat":
            # 🐸 呆萌青蛙小雨帽 (綠色圓頂漁夫帽 + 頂部兩顆大青蛙圓眼)
            hw = 20.0 * self.scale_x
            hy = -h * 0.82
            # 1. 漁夫帽沿
            pts_brim = []
            for dx_p, dy_p in [(-hw, 2), (hw, 2), (hw * 0.9, -3), (-hw * 0.9, -3)]:
                rx_p, ry_p = self.rotate_point(dx_p * acc_rot_scale + slide_x, hy + dy_p, self.roll_angle)
                pts_brim.append(self.cx + rx_p)
                pts_brim.append(self.cy + ry_p)
            self.canvas.create_polygon(pts_brim, fill="#a6e3a1", outline="#3c2203", width=2.0, tags="character")
            # 2. 帽冠
            pts_crown = [
                self.rotate_point(-hw * 0.75 * acc_rot_scale + slide_x, hy - 2, self.roll_angle),
                self.rotate_point(-hw * 0.60 * acc_rot_scale + slide_x, hy - 14, self.roll_angle),
                self.rotate_point(hw * 0.60 * acc_rot_scale + slide_x, hy - 14, self.roll_angle),
                self.rotate_point(hw * 0.75 * acc_rot_scale + slide_x, hy - 2, self.roll_angle)
            ]
            abs_cr = []
            for dx, dy in pts_crown: abs_cr.extend([self.cx + dx, self.cy + dy])
            self.canvas.create_polygon(abs_cr, fill="#a6e3a1", outline="#3c2203", width=2.0, tags="character")
            # 3. 青蛙左眼
            rx_fe1, ry_fe1 = self.rotate_point(-hw * 0.35 * acc_rot_scale + slide_x, hy - 14, self.roll_angle)
            self.canvas.create_oval(self.cx + rx_fe1 - 5 * acc_rot_scale, self.cy + ry_fe1 - 5,
                                    self.cx + rx_fe1 + 5 * acc_rot_scale, self.cy + ry_fe1 + 5,
                                    fill="#a6e3a1", outline="#3c2203", width=1.5, tags="character")
            self.canvas.create_oval(self.cx + rx_fe1 - 3 * acc_rot_scale, self.cy + ry_fe1 - 3,
                                    self.cx + rx_fe1 + 3 * acc_rot_scale, self.cy + ry_fe1 + 3,
                                    fill="#ffffff", outline="", tags="character")
            self.canvas.create_oval(self.cx + rx_fe1 - 1.5 * acc_rot_scale, self.cy + ry_fe1 - 1.5,
                                    self.cx + rx_fe1 + 1.5 * acc_rot_scale, self.cy + ry_fe1 + 1.5,
                                    fill="#11111b", outline="", tags="character")
            # 青蛙右眼
            rx_fe2, ry_fe2 = self.rotate_point(hw * 0.35 * acc_rot_scale + slide_x, hy - 14, self.roll_angle)
            self.canvas.create_oval(self.cx + rx_fe2 - 5 * acc_rot_scale, self.cy + ry_fe2 - 5,
                                    self.cx + rx_fe2 + 5 * acc_rot_scale, self.cy + ry_fe2 + 5,
                                    fill="#a6e3a1", outline="#3c2203", width=1.5, tags="character")
            self.canvas.create_oval(self.cx + rx_fe2 - 3 * acc_rot_scale, self.cy + ry_fe2 - 3,
                                    self.cx + rx_fe2 + 3 * acc_rot_scale, self.cy + ry_fe2 + 3,
                                    fill="#ffffff", outline="", tags="character")
            self.canvas.create_oval(self.cx + rx_fe2 - 1.5 * acc_rot_scale, self.cy + ry_fe2 - 1.5,
                                    self.cx + rx_fe2 + 1.5 * acc_rot_scale, self.cy + ry_fe2 + 1.5,
                                    fill="#11111b", outline="", tags="character")

        elif equipped == "angel_wings":
            # 🪽 璀璨天使羽翼 (背後左右羽翼，帶有拍動微幅動畫)
            flap = 3.5 * math.sin(time_ms() / 140.0)
            wing_w = 18.0 * self.scale_x
            wing_y = -h * 0.1
            pts_wl = [
                self.rotate_point(-w * 0.55 * acc_rot_scale + slide_x, wing_y, self.roll_angle),
                self.rotate_point((-w * 0.55 - wing_w) * acc_rot_scale + slide_x, wing_y - 14 + flap, self.roll_angle),
                self.rotate_point((-w * 0.55 - wing_w * 0.8) * acc_rot_scale + slide_x, wing_y + 2 + flap * 0.5, self.roll_angle),
                self.rotate_point((-w * 0.55 - wing_w * 0.4) * acc_rot_scale + slide_x, wing_y + 12, self.roll_angle),
                self.rotate_point(-w * 0.45 * acc_rot_scale + slide_x, wing_y + 6, self.roll_angle)
            ]
            abs_wl = []
            for dx, dy in pts_wl: abs_wl.extend([self.cx + dx, self.cy + dy])
            self.canvas.create_polygon(abs_wl, fill="#ffffff", outline="#3c2203", width=1.5, tags="character")
            # 右羽翼
            pts_wr = [
                self.rotate_point(w * 0.55 * acc_rot_scale + slide_x, wing_y, self.roll_angle),
                self.rotate_point((w * 0.55 + wing_w) * acc_rot_scale + slide_x, wing_y - 14 + flap, self.roll_angle),
                self.rotate_point((w * 0.55 + wing_w * 0.8) * acc_rot_scale + slide_x, wing_y + 2 + flap * 0.5, self.roll_angle),
                self.rotate_point((w * 0.55 + wing_w * 0.4) * acc_rot_scale + slide_x, wing_y + 12, self.roll_angle),
                self.rotate_point(w * 0.45 * acc_rot_scale + slide_x, wing_y + 6, self.roll_angle)
            ]
            abs_wr = []
            for dx, dy in pts_wr: abs_wr.extend([self.cx + dx, self.cy + dy])
            self.canvas.create_polygon(abs_wr, fill="#ffffff", outline="#3c2203", width=1.5, tags="character")

        elif equipped == "char_mask":
            # ☄️ 赤色彗星・夏亞白色軍官鋼盔與 3D 動態轉頭白面具 (Classic Perfect Char Mask & Seamless Turn)
            # 核心架構：
            # 1. 正面 (rotation_fraction = 0.0)：100% 呈現精緻立體六邊形全白面具、五官對齊純白冷光目鏡、霸氣衝天黃金大鷹角
            # 2. 背面 (rotation_fraction = 1.0)：100% 呈現垂直居中、完全左右對稱的全覆式鋼盔後腦穹頂、後頸金屬護甲板與中線脊線
            # 3. 轉身過渡 (0.0 < rot < 1.0)：透過 Cosine/Sine 權重平滑收放與側滑，側面過渡絲滑自然無任何割裂感！
            
            my = eye_y_offset - 2.0
            hw = w * 1.22 * self.scale_x
            mask_base_w = 32.0 * self.scale_x
            
            angle_rad = rotation_fraction * (math.pi / 2.0)
            front_weight = math.cos(angle_rad) # 1.0 (正面) -> 0.0 (正背面)
            back_weight = math.sin(angle_rad)  # 0.0 (正面) -> 1.0 (正背面)
            
            # 精準平移量控制：sin(rot * pi) 在 rot=0.0 (正面) 與 rot=1.0 (正背面) 精確歸零，絕不偏歪！
            turn_slide_x = math.sin(rotation_fraction * math.pi) * (w * 0.35)
            look_shift_x = self.look_offset_x * (1.0 - rotation_fraction)
            helm_shift_x = turn_slide_x + look_shift_x * 0.35
            center_x = turn_slide_x + look_shift_x
            turn_ratio = max(-0.85, min(0.85, center_x / max(1.0, w)))
            
            # 1. 巨大白色鋼盔外殼 (Giant White Helmet Shell - 完整全覆式包覆後腦勺，正背面完全居中)
            neck_rim_y = (my - 2.0) * front_weight + (my + 13.0) * back_weight
            neck_center_y = (my - 10.0) * front_weight + (my + 16.0) * back_weight
            pts_helmet = [
                self.rotate_point(-hw * 0.94 + helm_shift_x, my + 6.0, self.roll_angle),   # 左後護耳
                self.rotate_point(-hw * 0.90 + helm_shift_x, my - 20.0, self.roll_angle),  # 左側臉
                self.rotate_point(-hw * 0.68 + helm_shift_x, my - 48.0, self.roll_angle),  # 左上穹頂
                self.rotate_point(0.0 + helm_shift_x, my - 58.0, self.roll_angle),         # 天靈蓋頂點 (完美中軸)
                self.rotate_point(hw * 0.68 + helm_shift_x, my - 48.0, self.roll_angle),   # 右上穹頂
                self.rotate_point(hw * 0.90 + helm_shift_x, my - 20.0, self.roll_angle),  # 右側臉
                self.rotate_point(hw * 0.94 + helm_shift_x, my + 6.0, self.roll_angle),    # 右後護耳
                self.rotate_point(hw * 0.76 + helm_shift_x, neck_rim_y, self.roll_angle),  # 右下頸緣
                self.rotate_point(0.0 + helm_shift_x, neck_center_y, self.roll_angle),     # 中點下緣 (完美中軸)
                self.rotate_point(-hw * 0.76 + helm_shift_x, neck_rim_y, self.roll_angle), # 左下頸緣
            ]
            abs_helmet = []
            for dx, dy in pts_helmet: abs_helmet.extend([self.cx + dx, self.cy + dy])
            self.canvas.create_polygon(abs_helmet, fill="#fbf8f0", outline="#3c2203", width=3.0, tags="character")
            
            # 頭盔頂部大高光反射弧面 (完整全覆式穹頂高光)
            pts_hel_hi = [
                self.rotate_point(-hw * 0.62 + helm_shift_x, my - 45.0, self.roll_angle),
                self.rotate_point(0.0 + helm_shift_x, my - 54.0, self.roll_angle),
                self.rotate_point(hw * 0.62 + helm_shift_x, my - 45.0, self.roll_angle),
                self.rotate_point(hw * 0.48 + helm_shift_x, my - 30.0, self.roll_angle),
                self.rotate_point(0.0 + helm_shift_x, my - 34.0, self.roll_angle),
                self.rotate_point(-hw * 0.48 + helm_shift_x, my - 30.0, self.roll_angle),
            ]
            abs_hhi = []
            for dx, dy in pts_hel_hi: abs_hhi.extend([self.cx + dx, self.cy + dy])
            self.canvas.create_polygon(abs_hhi, fill="#ffffff", outline="", tags="character")

            # 兩側護耳裝甲刻線
            rx_el1, ry_el1 = self.rotate_point(-hw * 0.88 + helm_shift_x, my - 12.0, self.roll_angle)
            rx_el2, ry_el2 = self.rotate_point(-hw * 0.90 + helm_shift_x, my + 5.0, self.roll_angle)
            self.canvas.create_line(self.cx + rx_el1, self.cy + ry_el1, self.cx + rx_el2, self.cy + ry_el2,
                                    fill="#d5cfbe", width=2.0, tags="character")
            rx_er1, ry_er1 = self.rotate_point(hw * 0.88 + helm_shift_x, my - 12.0, self.roll_angle)
            rx_er2, ry_er2 = self.rotate_point(hw * 0.90 + helm_shift_x, my + 5.0, self.roll_angle)
            self.canvas.create_line(self.cx + rx_er1, self.cy + ry_er1, self.cx + rx_er2, self.cy + ry_er2,
                                    fill="#d5cfbe", width=2.0, tags="character")

            # ==========================================
            # 2. 背面特徵層 (Back Features: 後頸護板與後中線裝甲脊線，隨轉身平滑展開)
            # ==========================================
            if rotation_fraction >= 0.35:
                back_scale = max(0.0, min(1.0, (rotation_fraction - 0.35) / 0.65))
                
                # 後頸金屬裝甲護板凸緣 (Neck Guard Plate - 完美對稱)
                pts_neck = [
                    self.rotate_point(-hw * 0.85 * back_scale + helm_shift_x, my + 6.0, self.roll_angle),
                    self.rotate_point(0.0 + helm_shift_x, my + 8.0, self.roll_angle),
                    self.rotate_point(hw * 0.85 * back_scale + helm_shift_x, my + 6.0, self.roll_angle),
                    self.rotate_point(hw * 0.75 * back_scale + helm_shift_x, my + 13.0, self.roll_angle),
                    self.rotate_point(0.0 + helm_shift_x, my + 16.0, self.roll_angle),
                    self.rotate_point(-hw * 0.75 * back_scale + helm_shift_x, my + 13.0, self.roll_angle),
                ]
                abs_neck = []
                for dx, dy in pts_neck: abs_neck.extend([self.cx + dx, self.cy + dy])
                self.canvas.create_polygon(abs_neck, fill="#ede5d5", outline="#3c2203", width=2.0, tags="character")
                
                # 後腦勺中央垂直裝甲脊線 (完美中軸貫穿)
                rx_rsp1, ry_rsp1 = self.rotate_point(0.0 + helm_shift_x, my - 58.0, self.roll_angle)
                rx_rsp2, ry_rsp2 = self.rotate_point(0.0 + helm_shift_x, my + 16.0, self.roll_angle)
                self.canvas.create_line(self.cx + rx_rsp1, self.cy + ry_rsp1, self.cx + rx_rsp2, self.cy + ry_rsp2,
                                        fill="#d5cfbe", width=2.5, tags="character")

            # ==========================================
            # 3. 正面特徵層 (Front Features: 經典六邊形面具、純白目鏡、突出帽簷、黃金大鷹角)
            # ==========================================
            if rotation_fraction <= 0.65:
                front_scale = max(0.0, min(1.0, (0.65 - rotation_fraction) / 0.65))
                
                # 正頂脊線 (連接至帽簷)
                rx_cr1, ry_cr1 = self.rotate_point(0.0 * acc_rot_scale + helm_shift_x * 0.5, my - 58.0, self.roll_angle)
                rx_cr2, ry_cr2 = self.rotate_point(center_x * 0.70, my - 15.0, self.roll_angle)
                self.canvas.create_line(self.cx + rx_cr1, self.cy + ry_cr1, self.cx + rx_cr2, self.cy + ry_cr2,
                                        fill="#d5cfbe", width=2.5, tags="character")

                # 正面白色突出帽簷 (Visor Brim)
                pts_brim = [
                    self.rotate_point(-hw * 0.88 * front_scale + helm_shift_x, my - 3.0, self.roll_angle),
                    self.rotate_point(center_x * 0.75, my - 11.0, self.roll_angle),
                    self.rotate_point(hw * 0.88 * front_scale + helm_shift_x, my - 3.0, self.roll_angle),
                    self.rotate_point(hw * 0.82 * front_scale + helm_shift_x, my + 1.0, self.roll_angle),
                    self.rotate_point(center_x * 0.75, my - 6.0, self.roll_angle),
                    self.rotate_point(-hw * 0.82 * front_scale + helm_shift_x, my + 1.0, self.roll_angle),
                ]
                abs_brim = []
                for dx, dy in pts_brim: abs_brim.extend([self.cx + dx, self.cy + dy])
                self.canvas.create_polygon(abs_brim, fill="#ede5d5", outline="#3c2203", width=2.2, tags="character")

                # 3D 動態白色夏亞經典六邊形面具主體 (Classic Hexagonal Char Mask)
                mask_w = mask_base_w * front_scale
                mask_left_w = mask_w * (1.0 + turn_ratio * 0.40)
                mask_right_w = mask_w * (1.0 - turn_ratio * 0.40)
                
                pts_mask = [
                    self.rotate_point(center_x - mask_left_w * 0.88, my - 2.0, self.roll_angle),
                    self.rotate_point(center_x - mask_left_w * 0.65, my + 4.0, self.roll_angle),
                    self.rotate_point(center_x, my + 6.0, self.roll_angle), # 鼻尖上提露出嘴巴
                    self.rotate_point(center_x + mask_right_w * 0.65, my + 4.0, self.roll_angle),
                    self.rotate_point(center_x + mask_right_w * 0.88, my - 2.0, self.roll_angle),
                    self.rotate_point(center_x, my - 7.0, self.roll_angle),
                ]
                abs_mask = []
                for dx, dy in pts_mask: abs_mask.extend([self.cx + dx, self.cy + dy])
                self.canvas.create_polygon(abs_mask, fill="#fbf8f0", outline="#3c2203", width=2.2, tags="character")

                # 面具陰影面 (根據轉向動態決定)
                if turn_ratio >= 0.0:
                    pts_mask_shadow = [
                        self.rotate_point(center_x - mask_left_w * 0.88, my - 2.0, self.roll_angle),
                        self.rotate_point(center_x - mask_left_w * 0.65, my + 4.0, self.roll_angle),
                        self.rotate_point(center_x, my + 6.0, self.roll_angle),
                        self.rotate_point(center_x, my - 7.0, self.roll_angle),
                    ]
                else:
                    pts_mask_shadow = [
                        self.rotate_point(center_x, my - 7.0, self.roll_angle),
                        self.rotate_point(center_x, my + 6.0, self.roll_angle),
                        self.rotate_point(center_x + mask_right_w * 0.65, my + 4.0, self.roll_angle),
                        self.rotate_point(center_x + mask_right_w * 0.88, my - 2.0, self.roll_angle),
                    ]
                abs_ms = []
                for dx, dy in pts_mask_shadow: abs_ms.extend([self.cx + dx, self.cy + dy])
                self.canvas.create_polygon(abs_ms, fill="#ede5d5", outline="", tags="character")

                # 黑色狹長眼部觀測窗 + 【純白冷光鏡片】 (White Lens Visors - 精確跟隨地瓜球眼睛)
                slit_w_l = 8.5 * self.scale_x * (1.0 + turn_ratio * 0.35) * front_scale
                if slit_w_l > 1.0:
                    pts_slit_l = [
                        self.rotate_point(left_eye_dx - slit_w_l, my - 1.5, self.roll_angle),
                        self.rotate_point(left_eye_dx + slit_w_l * 0.7, my + 1.0, self.roll_angle),
                        self.rotate_point(left_eye_dx + slit_w_l * 0.7, my + 3.8, self.roll_angle),
                        self.rotate_point(left_eye_dx - slit_w_l, my + 1.2, self.roll_angle),
                    ]
                    abs_sl = []
                    for dx, dy in pts_slit_l: abs_sl.extend([self.cx + dx, self.cy + dy])
                    self.canvas.create_polygon(abs_sl, fill="#11111b", outline="#251605", width=1.2, tags="character")
                    
                    rx_egl1, ry_egl1 = self.rotate_point(left_eye_dx - slit_w_l * 0.8, my + 0.0, self.roll_angle)
                    rx_egl2, ry_egl2 = self.rotate_point(left_eye_dx + slit_w_l * 0.5, my + 2.4, self.roll_angle)
                    self.canvas.create_line(self.cx + rx_egl1, self.cy + ry_egl1, self.cx + rx_egl2, self.cy + ry_egl2,
                                            fill="#ffffff", width=2.0, capstyle=tk.ROUND, tags="character")
                    rx_hl_l, ry_hl_l = self.rotate_point(left_eye_dx - slit_w_l * 0.4, my + 0.2, self.roll_angle)
                    self.canvas.create_oval(self.cx + rx_hl_l - 1.5, self.cy + ry_hl_l - 1.0,
                                            self.cx + rx_hl_l + 1.5, self.cy + ry_hl_l + 1.0, fill="#ffffff", outline="", tags="character")

                slit_w_r = 8.5 * self.scale_x * (1.0 - turn_ratio * 0.35) * front_scale
                if slit_w_r > 1.0:
                    pts_slit_r = [
                        self.rotate_point(right_eye_dx - slit_w_r * 0.7, my + 1.0, self.roll_angle),
                        self.rotate_point(right_eye_dx + slit_w_r, my - 1.5, self.roll_angle),
                        self.rotate_point(right_eye_dx + slit_w_r, my + 1.2, self.roll_angle),
                        self.rotate_point(right_eye_dx - slit_w_r * 0.7, my + 3.8, self.roll_angle),
                    ]
                    abs_sr = []
                    for dx, dy in pts_slit_r: abs_sr.extend([self.cx + dx, self.cy + dy])
                    self.canvas.create_polygon(abs_sr, fill="#11111b", outline="#251605", width=1.2, tags="character")
                    
                    rx_egr1, ry_egr1 = self.rotate_point(right_eye_dx - slit_w_r * 0.5, my + 2.4, self.roll_angle)
                    rx_egr2, ry_egr2 = self.rotate_point(right_eye_dx + slit_w_r * 0.8, my + 0.0, self.roll_angle)
                    self.canvas.create_line(self.cx + rx_egr1, self.cy + ry_egr1, self.cx + rx_egr2, self.cy + ry_egr2,
                                            fill="#ffffff", width=2.0, capstyle=tk.ROUND, tags="character")
                    rx_hl_r, ry_hl_r = self.rotate_point(right_eye_dx + slit_w_r * 0.4, my + 0.2, self.roll_angle)
                    self.canvas.create_oval(self.cx + rx_hl_r - 1.5, self.cy + ry_hl_r - 1.0,
                                            self.cx + rx_hl_r + 1.5, self.cy + ry_hl_r + 1.0, fill="#ffffff", outline="", tags="character")

                # 面具中央白色立體鼻樑脊線 (跟隨 center_x)
                rx_nb1, ry_nb1 = self.rotate_point(center_x, my - 7.0, self.roll_angle)
                rx_nb2, ry_nb2 = self.rotate_point(center_x, my + 6.0, self.roll_angle)
                self.canvas.create_line(self.cx + rx_nb1, self.cy + ry_nb1, self.cx + rx_nb2, self.cy + ry_nb2,
                                        fill="#ffffff", width=2.2, tags="character")

                # 正額正中央【官方正統・夏亞純白三叉立體鋼角冠】 (Official Char Silver-White Trident Crest)
                crest_y = my - 8.0
                cx_c = center_x * 0.75
                crest_lw = (1.0 + turn_ratio * 0.35) * front_scale
                crest_rw = (1.0 - turn_ratio * 0.35) * front_scale
                
                # 1. 左右兩支高聳白色側角 (Side Crest Horns)
                # 左側高聳白角
                pts_lhorn = [
                    self.rotate_point(cx_c - 5.5 * self.scale_x * crest_lw, crest_y + 2.0, self.roll_angle),
                    self.rotate_point(cx_c - 13.5 * self.scale_x * crest_lw, crest_y - 28.0 * self.scale_y, self.roll_angle), # 左角尖端
                    self.rotate_point(cx_c - 9.0 * self.scale_x * crest_lw, crest_y - 28.0 * self.scale_y, self.roll_angle),  # 內緣
                    self.rotate_point(cx_c - 3.5 * self.scale_x * crest_lw, crest_y - 8.0, self.roll_angle),
                ]
                abs_lh = []
                for dx, dy in pts_lhorn: abs_lh.extend([self.cx + dx, self.cy + dy])
                self.canvas.create_polygon(abs_lh, fill="#e6ebf2", outline="#3c2203", width=1.8, tags="character")

                # 右側高聳白角
                pts_rhorn = [
                    self.rotate_point(cx_c + 3.5 * self.scale_x * crest_rw, crest_y - 8.0, self.roll_angle),
                    self.rotate_point(cx_c + 9.0 * self.scale_x * crest_rw, crest_y - 28.0 * self.scale_y, self.roll_angle),  # 內緣
                    self.rotate_point(cx_c + 13.5 * self.scale_x * crest_rw, crest_y - 28.0 * self.scale_y, self.roll_angle), # 右角尖端
                    self.rotate_point(cx_c + 5.5 * self.scale_x * crest_rw, crest_y + 2.0, self.roll_angle),
                ]
                abs_rh = []
                for dx, dy in pts_rhorn: abs_rh.extend([self.cx + dx, self.cy + dy])
                self.canvas.create_polygon(abs_rh, fill="#f5f7fa", outline="#3c2203", width=1.8, tags="character")

                # 2. 中央菱形/六邊形立體底座與中央立體尖脊 (Central Diamond Base & Center Fin)
                pts_cbase = [
                    self.rotate_point(cx_c, crest_y - 22.0 * self.scale_y, self.roll_angle),                    # 中角尖端
                    self.rotate_point(cx_c + 6.0 * self.scale_x * crest_rw, crest_y - 6.0, self.roll_angle),   # 右中側點
                    self.rotate_point(cx_c, crest_y + 5.0, self.roll_angle),                                    # 下方尖端
                    self.rotate_point(cx_c - 6.0 * self.scale_x * crest_lw, crest_y - 6.0, self.roll_angle),   # 左中側點
                ]
                abs_cb = []
                for dx, dy in pts_cbase: abs_cb.extend([self.cx + dx, self.cy + dy])
                self.canvas.create_polygon(abs_cb, fill="#fbf8f0", outline="#3c2203", width=2.0, tags="character")

                # 立體陰影面 (根據視角)
                if turn_ratio >= 0.0:
                    pts_base_shadow = [
                        self.rotate_point(cx_c, crest_y - 22.0 * self.scale_y, self.roll_angle),
                        self.rotate_point(cx_c, crest_y + 5.0, self.roll_angle),
                        self.rotate_point(cx_c - 6.0 * self.scale_x * crest_lw, crest_y - 6.0, self.roll_angle),
                    ]
                else:
                    pts_base_shadow = [
                        self.rotate_point(cx_c, crest_y - 22.0 * self.scale_y, self.roll_angle),
                        self.rotate_point(cx_c + 6.0 * self.scale_x * crest_rw, crest_y - 6.0, self.roll_angle),
                        self.rotate_point(cx_c, crest_y + 5.0, self.roll_angle),
                    ]
                abs_bs = []
                for dx, dy in pts_base_shadow: abs_bs.extend([self.cx + dx, self.cy + dy])
                self.canvas.create_polygon(abs_bs, fill="#dce3eb", outline="", tags="character")

                # 中央純白立體高光脊線
                rx_cg1, ry_cg1 = self.rotate_point(cx_c, crest_y - 22.0 * self.scale_y, self.roll_angle)
                rx_cg2, ry_cg2 = self.rotate_point(cx_c, crest_y + 5.0, self.roll_angle)
                self.canvas.create_line(self.cx + rx_cg1, self.cy + ry_cg1, self.cx + rx_cg2, self.cy + ry_cg2,
                                        fill="#ffffff", width=2.0, tags="character")

        elif equipped == "gamer_headset":
            # 🎧 霓虹電競耳機 (RGB 呼吸光圈 + 拱形頭梁 + 麥克風)
            import colorsys
            rgb_t = (time_ms() / 1200.0) % 1.0
            r_rgb, g_rgb, b_rgb = colorsys.hsv_to_rgb(rgb_t, 0.8, 1.0)
            neon_col = f"#{int(r_rgb*255):02x}{int(g_rgb*255):02x}{int(b_rgb*255):02x}"
            
            # 頭頂連接拱形梁
            pts_band = []
            for i in range(11):
                th = -math.pi * 0.85 + (i / 10.0) * math.pi * 0.70
                b_dx = (w * 0.82 * acc_rot_scale) * math.cos(th) + slide_x
                b_dy = (h * 0.90) * math.sin(th)
                rx_b, ry_b = self.rotate_point(b_dx, b_dy, self.roll_angle)
                pts_band.append(self.cx + rx_b)
                pts_band.append(self.cy + ry_b)
            self.canvas.create_line(*pts_band, smooth=True, width=4.5, fill="#1e1e2e", capstyle=tk.ROUND, tags="character")
            self.canvas.create_line(*pts_band, smooth=True, width=2.0, fill=neon_col, capstyle=tk.ROUND, tags="character")
            
            # 左耳罩
            lx_ec = -w * 0.78 * acc_rot_scale + slide_x
            ly_ec = -h * 0.05
            rx_lec, ry_lec = self.rotate_point(lx_ec, ly_ec, self.roll_angle)
            self.canvas.create_oval(self.cx + rx_lec - 6 * acc_rot_scale, self.cy + ry_lec - 10,
                                    self.cx + rx_lec + 6 * acc_rot_scale, self.cy + ry_lec + 10,
                                    fill="#1e1e2e", outline="#3c2203", width=2.0, tags="character")
            self.canvas.create_oval(self.cx + rx_lec - 3 * acc_rot_scale, self.cy + ry_lec - 6,
                                    self.cx + rx_lec + 3 * acc_rot_scale, self.cy + ry_lec + 6,
                                    fill=neon_col, outline="", tags="character")
            
            # 右耳罩
            rx_ec = w * 0.78 * acc_rot_scale + slide_x
            ry_ec = -h * 0.05
            rx_rec, ry_rec = self.rotate_point(rx_ec, ry_ec, self.roll_angle)
            self.canvas.create_oval(self.cx + rx_rec - 6 * acc_rot_scale, self.cy + ry_rec - 10,
                                    self.cx + rx_rec + 6 * acc_rot_scale, self.cy + ry_rec + 10,
                                    fill="#1e1e2e", outline="#3c2203", width=2.0, tags="character")
            self.canvas.create_oval(self.cx + rx_rec - 3 * acc_rot_scale, self.cy + ry_rec - 6,
                                    self.cx + rx_rec + 3 * acc_rot_scale, self.cy + ry_rec + 6,
                                    fill=neon_col, outline="", tags="character")
            
            # 麥克風伸出小桿
            rx_m_tip, ry_m_tip = self.rotate_point(lx_ec + 12 * acc_rot_scale, ly_ec + 12, self.roll_angle)
            self.canvas.create_line(self.cx + rx_lec, self.cy + ry_lec + 5, self.cx + rx_m_tip, self.cy + ry_m_tip,
                                    fill="#313244", width=2.0, tags="character")
            self.canvas.create_oval(self.cx + rx_m_tip - 2.5 * acc_rot_scale, self.cy + ry_m_tip - 2.5,
                                    self.cx + rx_m_tip + 2.5 * acc_rot_scale, self.cy + ry_m_tip + 2.5,
                                    fill=neon_col, outline="#11111b", width=1.0, tags="character")

        elif equipped == "wizard_hat":
            # 🧙 魔法師尖帽 (星空紫尖頂 + 金色星月 + 魔法微光)
            hat_w = 22.0 * self.scale_x
            hat_y = -h * 0.80
            # 帽沿
            pts_brim = []
            for dx_p, dy_p in [(-hat_w, 0), (hat_w, 0), (hat_w * 0.9, 3.5), (-hat_w * 0.9, 3.5)]:
                rx_p, ry_p = self.rotate_point(dx_p * acc_rot_scale + slide_x, hat_y + dy_p, self.roll_angle)
                pts_brim.append(self.cx + rx_p)
                pts_brim.append(self.cy + ry_p)
            self.canvas.create_polygon(pts_brim, fill="#1e1e2e", outline="#3c2203", width=2.0, tags="character")
            
            # 尖頂帽身
            pts_cone = [
                self.rotate_point(-hat_w * 0.65 * acc_rot_scale + slide_x, hat_y, self.roll_angle),
                self.rotate_point(hat_w * 0.65 * acc_rot_scale + slide_x, hat_y, self.roll_angle),
                self.rotate_point(hat_w * 0.2 * acc_rot_scale + slide_x, hat_y - 18, self.roll_angle),
                self.rotate_point(-hat_w * 0.15 * acc_rot_scale + slide_x, hat_y - 28, self.roll_angle),
                self.rotate_point(-hat_w * 0.4 * acc_rot_scale + slide_x, hat_y - 16, self.roll_angle)
            ]
            abs_cone = []
            for dx, dy in pts_cone: abs_cone.extend([self.cx + dx, self.cy + dy])
            self.canvas.create_polygon(abs_cone, fill="#313244", outline="#3c2203", width=2.0, tags="character")
            
            # 金黃月亮符文
            rx_moon, ry_moon = self.rotate_point(slide_x, hat_y - 12, self.roll_angle)
            self.canvas.create_oval(self.cx + rx_moon - 3 * acc_rot_scale, self.cy + ry_moon - 3,
                                    self.cx + rx_moon + 3 * acc_rot_scale, self.cy + ry_moon + 3,
                                    fill="#f9e2af", outline="", tags="character")

        elif equipped == "clover_sprout":
            # 🌱 幸運四葉草小豆苗 (頭頂搖曳嫩綠小苗)
            sway = 2.5 * math.sin(time_ms() / 180.0)
            stem_base_x = slide_x
            stem_base_y = -h * 0.88
            stem_top_x = slide_x + sway * acc_rot_scale
            stem_top_y = -h * 0.88 - 14
            
            rx_sb, ry_sb = self.rotate_point(stem_base_x, stem_base_y, self.roll_angle)
            rx_st, ry_st = self.rotate_point(stem_top_x, stem_top_y, self.roll_angle)
            self.canvas.create_line(self.cx + rx_sb, self.cy + ry_sb, self.cx + rx_st, self.cy + ry_st,
                                    fill="#a6e3a1", width=2.5, tags="character")
            # 左右兩片嫩綠小葉子
            rx_ll, ry_ll = self.rotate_point(stem_top_x - 5 * acc_rot_scale, stem_top_y - 2, self.roll_angle)
            self.canvas.create_oval(self.cx + rx_ll - 4 * acc_rot_scale, self.cy + ry_ll - 3,
                                    self.cx + rx_ll + 4 * acc_rot_scale, self.cy + ry_ll + 3,
                                    fill="#a6e3a1", outline="#3c2203", width=1.2, tags="character")
            rx_rl, ry_rl = self.rotate_point(stem_top_x + 5 * acc_rot_scale, stem_top_y - 2, self.roll_angle)
            self.canvas.create_oval(self.cx + rx_rl - 4 * acc_rot_scale, self.cy + ry_rl - 3,
                                    self.cx + rx_rl + 4 * acc_rot_scale, self.cy + ry_rl + 3,
                                    fill="#a6e3a1", outline="#3c2203", width=1.2, tags="character")

class _ShopNoopWidget:
    def config(self, **_kwargs):
        pass


class ShopWindow:
    def __init__(self, parent, monitor=None, build_ui=True):
        self.monitor = monitor
        self.build_ui = build_ui
        self.win = None
        if build_ui:
            self.win = tk.Toplevel(parent)
            self.win.title("地瓜球配件與道具商店")
            self.win.geometry("380x480")
            self.win.configure(bg="#1e1e2e")
            self.win.resizable(True, True)
            self.win.minsize(320, 300)
            self.win.attributes("-topmost", True)

            # A transient follows its owner into the withdrawn state. In Unity
            # renderer mode the legacy Canvas root is intentionally withdrawn,
            # so keep auxiliary tools as independent top-level windows there.
            try:
                if parent.state() != "withdrawn":
                    self.win.transient(parent)
            except Exception:
                pass
        
        self.items = [
            {
                "id": "char_mask",
                "name": "☄️ 赤色彗星・夏亞面罩",
                "price": 300,
                "desc": "初代灰藍機械面罩。可與夏亞頭盔分開裝備，移動速度提升 3 倍！",
                "slot": "face"
            },
            {
                "id": "char_helmet",
                "name": "🪖 赤色彗星・夏亞頭盔",
                "price": 260,
                "desc": "初代白色側翼軍盔與金色指揮官角；和面罩組合就是完整造型。",
                "slot": "head"
            },
            {
                "id": "sunglasses",
                "name": "🕶️ 酷炫墨鏡",
                "price": 100,
                "desc": "帥氣度爆表！產幣效率增加 10%"
            },
            {
                "id": "scholar_cap",
                "name": "🎓 學術博士帽",
                "price": 180,
                "desc": "博學多聞！對帳經驗獲得提升 20%"
            },
            {
                "id": "cat_ears",
                "name": "🐱 軟萌貓咪耳朵",
                "price": 120,
                "desc": "太萌了吧！地瓜幣產幣效率增加 15%"
            },
            {
                "id": "crown",
                "name": "👑 皇家黃金皇冠",
                "price": 300,
                "desc": "貴族氣息！雙重效率+15% & 全身散發溫潤金光"
            },
            {
                "id": "rainbow",
                "name": "🎨 炫彩身體彩繪",
                "price": 200,
                "desc": "動態彩虹漸變色！讓你成為桌面最炫的一顆球"
            },
            {
                "id": "halo",
                "name": "😇 天使發光光環",
                "price": 160,
                "desc": "神聖光環！頭頂飄浮金色發光環，且經驗加成 1.2x"
            },
            {
                "id": "gentleman_hat",
                "name": "🎩 紳士魔術禮帽",
                "price": 150,
                "desc": "魔術帽子！每隔幾秒會蹦出白色小白兔，且產幣效率+15%"
            },
            {
                "id": "demon_horns",
                "name": "😈 惡魔雙角",
                "price": 130,
                "desc": "調皮小惡魔！頭上長出紅色惡魔角，產幣效率+15%"
            },
            {
                "id": "star_sunglasses",
                "name": "🌟 炫彩星星墨鏡",
                "price": 140,
                "desc": "潮流必備！黃色大星星鏡片，雙向產幣效率均+10%"
            },
            {
                "id": "bowtie",
                "name": "🎀 優雅領結蝴蝶結",
                "price": 40,
                "desc": "可愛小粉結！胸前精緻領結裝飾，飽食度消化速度減緩 10%"
            },
            {
                "id": "sakura_hairpin",
                "name": "🌸 浪漫櫻花小髮夾",
                "price": 50,
                "desc": "粉嫩和風！頭側別上櫻花髮夾，心情愉悅產幣+10%"
            },
            {
                "id": "gamer_headset",
                "name": "🎧 霓虹電競發光耳機",
                "price": 160,
                "desc": "電競氛圍感！RGB呼吸流光耳罩與小麥克風，工作產幣+20%"
            },
            {
                "id": "wizard_hat",
                "name": "🧙 星空魔法師尖帽",
                "price": 180,
                "desc": "神秘魔法！星空紫尖帽與金色星月，對帳經驗加成+25%"
            },
            {
                "id": "clover_sprout",
                "name": "🌱 幸運四葉草豆苗",
                "price": 60,
                "desc": "超萌搖曳！頭頂長出綠色嫩芽，帶來好運與額外星星粒子"
            },
            {
                "id": "bandage",
                "name": "🩹 療癒OK繃",
                "price": 15,
                "desc": "迅速止痛！Token 飽食度回復增加 30%"
            },
            {
                "id": "matcha_parfait",
                "name": "🍵 宇治抹茶聖代",
                "price": 22,
                "desc": "清爽微苦甘甜！飽食度+35%，獲得抹茶清爽特效與經驗加成 1.3x",
                "type": "food",
                "restore": 35.0
            },
            {
                "id": "souffle_pancake",
                "name": "🥞 抖動舒芙蕾鬆餅",
                "price": 20,
                "desc": "入口即化！飽食度+40%，享受抖動ㄉㄨㄞ ㄉㄨㄞ吃食動畫",
                "type": "food",
                "restore": 40.0
            },
            {
                "id": "pizza",
                "name": "🍕 美味芝士披薩",
                "price": 12,
                "desc": "極品美味！飽食度+20%，享用芝士拉絲的嚼嚼吃食動畫",
                "type": "food",
                "restore": 20.0
            },
            {
                "id": "lollipop",
                "name": "🍭 彩虹大棒棒糖",
                "price": 25,
                "desc": "開心極了！飽食度+15%，進入 1.5s 舔糖果興奮動畫並增加 50 XP",
                "type": "food",
                "restore": 15.0
            },
            {
                "id": "balloon_toy",
                "name": "🎈 炫彩手拿氣球",
                "price": 30,
                "desc": "好玩！飽食度+10%，召喚氣球上升飄浮 20 秒",
                "type": "food",
                "restore": 10.0
            },
            {
                "id": "spicy_ramen",
                "name": "🌶️ 勁辣地瓜拉麵",
                "price": 35,
                "desc": "超辣！飽食度+40%，辣到全身發紅並超高速狂奔 15 秒",
                "type": "food",
                "restore": 40.0
            },
            {
                "id": "popsicle",
                "name": "🧊 冰凍蘇打冰棒",
                "price": 10,
                "desc": "好涼爽！飽食度+15%，進入 10s 冰凍慢速狀態並飄散雪花",
                "type": "food",
                "restore": 15.0
            },
            {
                "id": "candy",
                "name": "🍬 活力糖果",
                "price": 8,
                "desc": "甜甜的！飽食度+15%，且獲得 30s 活力移速與產幣加成",
                "type": "food",
                "restore": 15.0
            },
            {
                "id": "bubble_tea",
                "name": "🥤 經典珍珠奶茶",
                "price": 18,
                "desc": "吸一口！飽食度+30%，獲得 45s 青色珍珠泡泡與經驗加成 1.2x",
                "type": "food",
                "restore": 30.0
            },
            {
                "id": "ramen",
                "name": "🍜 美味拉麵",
                "price": 25,
                "desc": "真香！飽食度+50%，並享用端碗美味拉麵吃食動畫",
                "type": "food",
                "restore": 50.0
            },
            {
                "id": "balloon",
                "name": "🎈 飄浮紅色氣球",
                "price": 15,
                "desc": "抓緊囉！飽食度不變，地瓜球手握氣球線在空中悠閒飄浮 30 秒",
                "type": "food",
                "restore": 0.0
            },
            {
                "id": "futon",
                "desc": "讓地瓜球躺平補眠，睡醒會精神滿滿。",
                "name": "🛌 日式溫馨地舖",
                "price": 80,
                "desc": "召喚日式被鋪。拖地瓜球到被子內，它就會鑽進被窩熟睡，飽食度消耗減半、浮現Zzz！",
                "type": "furniture"
            },
            {
                "id": "laptop",
                "desc": "地瓜球會坐下打扣，螢幕與游標持續動起來。",
                "name": "💻 加班寫扣筆電",
                "price": 120,
                "desc": "召喚小筆電。拖地瓜球到鍵盤前，它會開啟認真寫扣加班動畫，且工作產幣效率額外+25%！",
                "type": "furniture"
            },
            {
                "id": "trampoline",
                "desc": "接住下落的地瓜球，觸發彈跳與擴散波紋。",
                "name": "🤸 霓虹彈簧蹦蹦床",
                "price": 90,
                "desc": "召喚彈簧床。當放開地瓜球、掉落其上時會將其高高彈飛，極具動感且重置完美落地判定！",
                "type": "furniture"
            },
            {
                "id": "night_lamp",
                "desc": "暖色呼吸光，地瓜球會在旁邊靜靜冥想。",
                "name": "🏮 療癒蘑菇小夜燈",
                "price": 100,
                "desc": "召喚溫馨小夜燈。在昏暗時散發暖黃微光，地瓜球靠近會靜心發呆放鬆！",
                "type": "furniture"
            },
            {
                "id": "succulent_pot",
                "desc": "陪地瓜球澆水照顧植物，偶爾獲得經驗值。",
                "name": "🪴 療癒多肉小盆栽",
                "price": 70,
                "desc": "召喚綠意多肉盆栽。地瓜球靠近時會開心地給小植物澆水，冒出愛心！",
                "type": "furniture"
            }
        ]
        
        # Ensure accessories and equipped_accessory exist in pet_data
        if monitor:
            if "accessories" not in monitor.pet_data:
                monitor.pet_data["accessories"] = []
            if "equipped_accessory" not in monitor.pet_data:
                monitor.pet_data["equipped_accessory"] = None
            if not isinstance(monitor.pet_data.get("equipped_accessories"), dict):
                monitor.pet_data["equipped_accessories"] = {}
                legacy_equipped = monitor.pet_data.get("equipped_accessory")
                if legacy_equipped:
                    monitor.pet_data["equipped_accessories"][
                        self._get_accessory_slot(legacy_equipped)
                    ] = legacy_equipped
            if "furniture" not in monitor.pet_data:
                monitor.pet_data["furniture"] = []
            if "spawned_furniture" not in monitor.pet_data:
                monitor.pet_data["spawned_furniture"] = []

            self.developer_mode = os.environ.get("TOKENPET_DEVELOPER_MODE") == "1"
            if self.developer_mode:
                accessory_ids = [
                    item["id"] for item in self.items
                    if item.get("type", "accessory") not in ("food", "furniture")
                ]
                furniture_ids = [
                    item["id"] for item in self.items
                    if item.get("type") == "furniture"
                ]
                monitor.pet_data["accessories"] = list(dict.fromkeys(
                    monitor.pet_data["accessories"] + accessory_ids
                ))
                monitor.pet_data["furniture"] = list(dict.fromkeys(
                    monitor.pet_data["furniture"] + furniture_ids
                ))
                monitor.pet_data["coins"] = max(
                    int(monitor.pet_data.get("coins", 0)), 999999
                )
                monitor.save_pet_savegame()
        else:
            self.developer_mode = False
                
        if build_ui:
            self._build_ui()
        else:
            self.coins_label = _ShopNoopWidget()
            self.buttons = {
                item["id"]: _ShopNoopWidget() for item in self.items
            }

    def _get_accessory_slot(self, item_id):
        for item in self.items:
            if item["id"] == item_id:
                if item.get("slot"):
                    return item["slot"]
                break
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

    def _sync_legacy_equipped_accessory(self, preferred=None):
        equipment = self.monitor.pet_data.setdefault("equipped_accessories", {})
        values = [item_id for item_id in equipment.values() if item_id]
        if "char_mask" in values:
            primary = "char_mask"
        elif preferred in values:
            primary = preferred
        else:
            primary = values[0] if values else None
        self.monitor.pet_data["equipped_accessory"] = primary
        self.monitor.pet.equipped_accessory = primary

    def _build_ui(self):
        # Title
        tk.Label(self.win, text="🛒 地瓜球配件與家具商店 🛍️", bg="#1e1e2e", fg="#fab387",
                 font=("微軟正黑體", 13, "bold")).pack(pady=10)
                 
        # Coins Balance
        self.coins_label = tk.Label(self.win, text=self._get_coins_text(), bg="#1e1e2e", fg="#f9e2af",
                                    font=("微軟正黑體", 11, "bold"))
        self.coins_label.pack(pady=2)
        
        # 建立 Tab 切換選單
        tab_frame = tk.Frame(self.win, bg="#1e1e2e")
        tab_frame.pack(pady=5, fill=tk.X)
        
        self.current_tab = "accessory"
        self.tab_buttons = {}
        
        tabs_config = [
            ("accessory", "🧢 裝飾配件"),
            ("food", "🍏 食物玩具"),
            ("furniture", "🛋️ 互動家具")
        ]
        
        for tab_id, tab_title in tabs_config:
            btn = tk.Button(tab_frame, text=tab_title, font=("微軟正黑體", 9, "bold"),
                            relief=tk.FLAT, bd=0, cursor="hand2")
            btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
            btn.config(command=lambda tid=tab_id: self.select_tab(tid))
            self.tab_buttons[tab_id] = btn
        
        # 1. 建立滾動容器 (Canvas + Scrollbar)
        container = tk.Frame(self.win, bg="#1e1e2e")
        container.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(container, bg="#1e1e2e", highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = tk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        # 2. 建立內層擺放商品的 Frame
        self.scrollable_frame = tk.Frame(self.canvas, bg="#1e1e2e")
        
        self.canvas_frame_id = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        
        def on_frame_configure(event):
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.scrollable_frame.bind("<Configure>", on_frame_configure)
        
        def on_canvas_configure(event):
            self.canvas.itemconfig(self.canvas_frame_id, width=event.width)
        self.canvas.bind("<Configure>", on_canvas_configure)
        
        # 3. 綁定滑鼠滾輪
        def on_mousewheel(event):
            if event.delta:
                self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            elif event.num == 4:
                self.canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                self.canvas.yview_scroll(1, "units")
                
        # 綁定事件到 Canvas 內
        self.canvas.bind_all("<MouseWheel>", on_mousewheel)
        self.canvas.bind_all("<Button-4>", on_mousewheel)
        self.canvas.bind_all("<Button-5>", on_mousewheel)
        
        # 關閉視窗時解除全域綁定
        def on_destroy(event):
            if event.widget == self.win:
                self.win.unbind_all("<MouseWheel>")
                self.win.unbind_all("<Button-4>")
                self.win.unbind_all("<Button-5>")
        self.win.bind("<Destroy>", on_destroy)
        
        # 4. 初始化商品行容器 dict
        self.item_rows = {}
        self.buttons = {}
        
        # 建立所有商品行，但不直接 pack 顯示
        for item in self.items:
            item_id = item["id"]
            row = tk.Frame(self.scrollable_frame, bg="#252535", bd=1, relief=tk.FLAT)
            self.item_rows[item_id] = row
            
            # Info subframe (Left)
            info_frame = tk.Frame(row, bg="#252535")
            info_frame.pack(side=tk.LEFT, padx=8, fill=tk.Y)
            
            lbl_name = tk.Label(info_frame, text=item["name"], bg="#252535", fg="#cdd6f4",
                                font=("微軟正黑體", 10, "bold"), anchor="w")
            lbl_name.pack(fill=tk.X, anchor="w")
            
            lbl_desc = tk.Label(info_frame, text=item.get("desc", ""), bg="#252535", fg="#a6adc8",
                                font=("微軟正黑體", 8), anchor="w", justify=tk.LEFT, wraplength=210)
            lbl_desc.pack(fill=tk.X, anchor="w")
            
            # Action button (Right)
            btn = tk.Button(row, text="", font=("微軟正黑體", 9, "bold"), relief=tk.FLAT, cursor="hand2")
            btn.pack(side=tk.RIGHT, padx=10, ipadx=6, ipady=2)
            self.buttons[item_id] = btn
            
            # Bind action
            btn.config(command=lambda i=item: self._on_item_action(i))
            
        self._update_button_states()
        self.select_tab("accessory")
        
        # Close button at bottom
        btn_close = tk.Button(self.win, text="關閉商店", bg="#313244", fg="#cdd6f4",
                              activebackground="#45475a", font=("微軟正黑體", 9, "bold"),
                              relief=tk.FLAT, cursor="hand2", command=self.win.destroy)
        btn_close.pack(pady=10, ipadx=15)

    def _get_coins_text(self):
        if self.monitor:
            coins = self.monitor.pet_data.get("coins", 0)
            return f"您的餘額: {coins} 🪙"
        return "您的餘額: 0 🪙"

    def select_tab(self, tab_id):
        self.current_tab = tab_id
        
        # 更新 Tab 按鈕樣式
        for tid, btn in self.tab_buttons.items():
            if tid == tab_id:
                btn.config(bg="#f5c2e7", fg="#11111b", activebackground="#f5c2e7")
            else:
                btn.config(bg="#313244", fg="#cdd6f4", activebackground="#45475a")
                
        # 顯示或隱藏對應分類的商品
        for item in self.items:
            item_id = item["id"]
            row = self.item_rows[item_id]
            
            # 判斷分類
            item_type = item.get("type", "accessory")
            if item_type == tab_id:
                row.pack(fill=tk.X, pady=4, ipady=4, expand=True)
            elif tab_id == "accessory" and item_type not in ("food", "furniture"):
                row.pack(fill=tk.X, pady=4, ipady=4, expand=True)
            else:
                row.pack_forget()
                
        self.canvas.yview_moveto(0.0)
        self._update_button_states()

    def _update_button_states(self):
        if not self.monitor:
            return
            
        owned = self.monitor.pet_data.get("accessories", [])
        equipped_slots = self.monitor.pet_data.get("equipped_accessories", {})
        
        owned_furniture = self.monitor.pet_data.get("furniture", [])
        spawned_furniture = self.monitor.pet_data.get("spawned_furniture", [])
        
        for item in self.items:
            item_id = item["id"]
            btn = self.buttons[item_id]
            item_type = item.get("type", "accessory")
            
            if item_type == "food":
                btn.config(text=f"購買 {item['price']} 🪙", bg="#fab387", fg="#1e1e2e", activebackground="#f9e2af")
            elif item_type == "furniture":
                if item_id in owned_furniture:
                    if item_id in spawned_furniture:
                        btn.config(text="收回(Despawn)", bg="#cba6f7", fg="#1e1e2e", activebackground="#f5e0dc")
                    else:
                        btn.config(text="召喚(Spawn)", bg="#89b4fa", fg="#1e1e2e", activebackground="#b4befe")
                else:
                    btn.config(text=f"購買 {item['price']} 🪙", bg="#a6e3a1", fg="#1e1e2e", activebackground="#a6e3a1")
            else:
                slot = self._get_accessory_slot(item_id)
                if equipped_slots.get(slot) == item_id:
                    btn.config(text="使用中(卸下)", bg="#f38ba8", fg="#1e1e2e", activebackground="#f5e0dc")
                elif item_id in owned:
                    btn.config(text="裝備", bg="#89b4fa", fg="#1e1e2e", activebackground="#b4befe")
                else:
                    btn.config(text=f"購買 {item['price']} 🪙", bg="#a6e3a1", fg="#1e1e2e", activebackground="#a6e3a1")

    def _on_item_action(self, item):
        if not self.monitor:
            return
            
        item_id = item["id"]
        price = item["price"]
        owned = self.monitor.pet_data.setdefault("accessories", [])
        equipped_slots = self.monitor.pet_data.setdefault("equipped_accessories", {})
        coins = self.monitor.pet_data.get("coins", 0)
        item_type = item.get("type", "accessory")
        
        if item_type == "food":
            # Consumable food item
            if coins < price:
                self._show_shop_error(
                    f"地瓜幣不足：需要 {price}，目前有 {coins} 🪙"
                )
                return
                
            self.monitor.pet_data["coins"] = coins - price
            satiety = self.monitor.pet_data.get("satiety", 100.0)
            restore_val = item["restore"]
            self.monitor.pet_data["satiety"] = min(100.0, satiety + restore_val)
            self.monitor.save_pet_savegame()
            
            self.monitor.create_text_popup(f"-{price} 🪙", 170, 120, color="#f38ba8")
            self.monitor.create_text_popup(f"食用 {item['name']} 😋", 170, 140, color="#fab387")

            # Unity uses this stable item id to select the matching prop.  The
            # legacy Canvas also benefits because every consumable now gets a
            # short, consistent eating reaction instead of silently applying
            # only the numeric effect.
            self.monitor.pet.eat_type = item_id
            
            # Apply food-specific effects
            if item_id == "candy":
                self.monitor.pet.candy_timer = 1800  # 30s
                self.monitor.pet.ramen_timer = 90
                self.monitor.pet.state = "eat"
                self.monitor.pet.eye_state = "happy"
                self.monitor.pet.mouth_state = "open"
            elif item_id == "bubble_tea":
                self.monitor.pet.bubble_tea_timer = 2700  # 45s
                self.monitor.pet.ramen_timer = 90
                self.monitor.pet.state = "eat"
                self.monitor.pet.eye_state = "happy"
                self.monitor.pet.mouth_state = "open"
            elif item_id == "ramen":
                self.monitor.pet.ramen_timer = 90  # 1.5s
                self.monitor.pet.eat_type = "ramen"
                self.monitor.pet.state = "eat"
                self.monitor.pet.eye_state = "happy"
                self.monitor.pet.mouth_state = "open"
            elif item_id == "spicy_ramen":
                self.monitor.pet.spicy_timer = 900  # 15s
                self.monitor.pet.ramen_timer = 90  # 1.5s
                self.monitor.pet.eat_type = "spicy_ramen"
                self.monitor.pet.state = "eat"
                self.monitor.pet.eye_state = "happy"
                self.monitor.pet.mouth_state = "open"
            elif item_id == "pizza":
                self.monitor.pet.ramen_timer = 90  # 1.5s
                self.monitor.pet.eat_type = "pizza"
                self.monitor.pet.state = "eat"
                self.monitor.pet.eye_state = "happy"
                self.monitor.pet.mouth_state = "open"
            elif item_id == "popsicle":
                self.monitor.pet.ramen_timer = 90  # 1.5s
                self.monitor.pet.eat_type = "popsicle"
                self.monitor.pet.state = "eat"
                self.monitor.pet.eye_state = "happy"
                self.monitor.pet.mouth_state = "open"
            elif item_id == "balloon":
                self.monitor.pet.balloon_timer = 1800  # 30s
                self.monitor.pet.state = "balloon"
                self.monitor.pet.eye_state = "happy"
                self.monitor.pet.mouth_state = "open"
            elif item_id == "lollipop":
                self.monitor.pet.ramen_timer = 90  # 1.5s
                self.monitor.pet.eat_type = "lollipop"
                self.monitor.pet.state = "eat"
                self.monitor.pet.eye_state = "happy"
                self.monitor.pet.mouth_state = "open"
                # Add 50 XP
                xp = self.monitor.pet_data.get("xp", 0.0)
                self.monitor.pet_data["xp"] = xp + 50.0
                self.monitor.check_level_up()
            elif item_id == "balloon_toy":
                self.monitor.pet.balloon_timer = 1200  # 20s
                self.monitor.pet.state = "balloon"
                self.monitor.pet.eye_state = "happy"
                self.monitor.pet.mouth_state = "open"
            elif item_id in ("bandage", "matcha_parfait", "souffle_pancake"):
                self.monitor.pet.ramen_timer = 90
                self.monitor.pet.state = "eat"
                self.monitor.pet.eye_state = "happy"
                self.monitor.pet.mouth_state = "open"
                if item_id == "matcha_parfait":
                    self.monitor.pet.matcha_timer = 1800
                
            self.coins_label.config(text=self._get_coins_text())
            return
            
        elif item_type == "furniture":
            owned_furniture = self.monitor.pet_data.setdefault("furniture", [])
            spawned_furniture = self.monitor.pet_data.setdefault("spawned_furniture", [])
            
            if item_id in owned_furniture:
                if item_id in spawned_furniture:
                    # Despawn
                    spawned_furniture.remove(item_id)
                    if hasattr(self.monitor, "despawn_furniture"):
                        self.monitor.despawn_furniture(item_id)
                    self.monitor.create_text_popup("已收回家具 🛌", 170, 120, color="#cba6f7")
                else:
                    # Spawn
                    spawned_furniture.append(item_id)
                    if hasattr(self.monitor, "spawn_furniture"):
                        self.monitor.spawn_furniture(item_id)
                    self.monitor.create_text_popup("召喚家具 🛋️", 170, 120, color="#a6e3a1")
                self.monitor.save_pet_savegame()
                self._update_button_states()
            else:
                if coins < price:
                    self._show_shop_error(
                        f"地瓜幣不足：需要 {price}，目前有 {coins} 🪙"
                    )
                    return
                self.monitor.pet_data["coins"] = coins - price
                owned_furniture.append(item_id)
                self.monitor.pet_data["furniture"] = owned_furniture
                self.monitor.save_pet_savegame()
                self.monitor.create_text_popup(f"-{price} 🪙", 170, 120, color="#f38ba8")
                self.monitor.create_text_popup("獲得家具！✨", 170, 140, color="#a6e3a1")
                self.coins_label.config(text=self._get_coins_text())
                self._update_button_states()
            return

        slot = self._get_accessory_slot(item_id)
        if equipped_slots.get(slot) == item_id:
            equipped_slots.pop(slot, None)
            self._sync_legacy_equipped_accessory()
            self.monitor.create_text_popup("已卸下裝飾", 170, 120, color="#cba6f7")
        elif item_id in owned:
            equipped_slots[slot] = item_id
            self._sync_legacy_equipped_accessory(item_id)
            self.monitor.create_text_popup(f"裝備 {item['name']}", 170, 120, color="#a6e3a1")
        else:
            if coins < price:
                self._show_shop_error(
                    f"地瓜幣不足：需要 {price}，目前有 {coins} 🪙"
                )
                return
                
            self.monitor.pet_data["coins"] = coins - price
            owned.append(item_id)
            self.monitor.pet_data["accessories"] = owned
            equipped_slots[slot] = item_id
            self._sync_legacy_equipped_accessory(item_id)
            
            self.monitor.create_text_popup(f"-{price} 🪙", 170, 120, color="#f38ba8")
            self.monitor.create_text_popup(f"獲得 {item['name']}！", 170, 140, color="#fab387")
            
        self.monitor.save_pet_savegame()
        self.coins_label.config(text=self._get_coins_text())

    def _show_shop_error(self, message):
        if self.build_ui:
            messagebox.showerror("地瓜幣不足", message)
        elif self.monitor:
            self.monitor.create_text_popup(message, 170, 120, color="#f38ba8")
def time_ms():
    return time.time() * 1000.0


class RPSWindow:
    def __init__(self, parent, monitor):
        self.win = tk.Toplevel(parent)
        self.win.title("猜拳對決！")
        self.win.geometry("260x100")
        self.win.configure(bg="#1e1e2e")
        self.win.resizable(False, False)
        self.win.attributes("-topmost", True)
        
        self.monitor = monitor
        
        # Make it modal/transient
        self.win.transient(parent)
        self.win.grab_set()
        
        tk.Label(
            self.win,
            text="請出拳！(每次 5 🪙)",
            bg="#1e1e2e", fg="#cdd6f4",
            font=("微軟正黑體", 10, "bold")
        ).pack(pady=8)
        
        btn_frame = tk.Frame(self.win, bg="#1e1e2e")
        btn_frame.pack(pady=2)
        
        choices = [
            ("✊ 石頭", "rock"),
            ("✌️ 剪刀", "scissors"),
            ("🖐️ 布", "paper")
        ]
        
        for name, choice_id in choices:
            btn = tk.Button(
                btn_frame, text=name,
                bg="#313244", fg="#f5c2e7",
                relief=tk.FLAT, cursor="hand2",
                command=lambda c=choice_id: self.make_choice(c),
                font=("微軟正黑體", 9, "bold")
            )
            btn.pack(side=tk.LEFT, padx=5, ipady=3)
            
    def make_choice(self, user_choice):
        self.win.destroy()
        if self.monitor:
            self.monitor.handle_rps_choice(user_choice)


# ──────────────────────────────────────────────────
# AI 尬聊設定視窗 (AIChatConfigWindow)
# ──────────────────────────────────────────────────
class AIChatConfigWindow:
    def __init__(self, parent, monitor):
        self.monitor = monitor
        self.win = tk.Toplevel(parent)
        self.win.title("⚙️ AI 尬聊設定")
        self.win.geometry("380x320")
        self.win.configure(bg="#181825")
        self.win.resizable(False, False)
        self.win.attributes("-topmost", True)
        self.win.transient(parent)
        self.win.grab_set()
        
        cfg = self.monitor.pet_data.setdefault("ai_config", {
            "ccr_url": "http://ainexus.phison.com:5155/api/external/v1/chat/completions",
            "api_key": "AINX-9BA1E6EC81F095A0F9CE8E16F543E557925591303398051A57F5176DB7289874",
            "model": "deepseek-ai/DeepSeek-V4-Flash-0731",
            "auto_chatter": True,
            "chatter_interval_min": 15
        })
        
        tk.Label(self.win, text="🤖 內網 AI Nexus (DeepSeek-V4) 設定", font=("微軟正黑體", 11, "bold"), bg="#181825", fg="#fab387").pack(pady=(12, 6))
        
        # AI Nexus Endpoint
        f1 = tk.Frame(self.win, bg="#181825")
        f1.pack(fill=tk.X, padx=20, pady=4)
        tk.Label(f1, text="伺服器端點 (URL):", font=("微軟正黑體", 9), bg="#181825", fg="#cdd6f4").pack(anchor="w")
        self.url_entry = tk.Entry(f1, font=("Consolas", 8), bg="#313244", fg="#cdd6f4", insertbackground="#cdd6f4")
        self.url_entry.insert(0, cfg.get("ccr_url", "http://ainexus.phison.com:5155/api/external/v1/chat/completions"))
        self.url_entry.pack(fill=tk.X, pady=2)
        
        # Model Name
        f2 = tk.Frame(self.win, bg="#181825")
        f2.pack(fill=tk.X, padx=20, pady=4)
        tk.Label(f2, text="指定模型名稱 (Model):", font=("微軟正黑體", 9), bg="#181825", fg="#cdd6f4").pack(anchor="w")
        self.model_entry = tk.Entry(f2, font=("Consolas", 8), bg="#313244", fg="#cdd6f4", insertbackground="#cdd6f4")
        self.model_entry.insert(0, cfg.get("model", "deepseek-ai/DeepSeek-V4-Flash-0731"))
        self.model_entry.pack(fill=tk.X, pady=2)
        
        # Auto chatter
        f3 = tk.Frame(self.win, bg="#181825")
        f3.pack(fill=tk.X, padx=20, pady=6)
        self.auto_var = tk.BooleanVar(value=cfg.get("auto_chatter", True))
        chk = tk.Checkbutton(f3, text="開啟桌面自發主動搭話 (每隔幾分鐘碎碎念)", variable=self.auto_var,
                             font=("微軟正黑體", 9), bg="#181825", fg="#cdd6f4", selectcolor="#313244", activebackground="#181825")
        chk.pack(anchor="w")
        
        # Interval
        f4 = tk.Frame(self.win, bg="#181825")
        f4.pack(fill=tk.X, padx=20, pady=2)
        tk.Label(f4, text="搭話間隔 (分鐘):", font=("微軟正黑體", 9), bg="#181825", fg="#cdd6f4").pack(side=tk.LEFT)
        self.interval_spin = tk.Spinbox(f4, from_=3, to=60, width=5, font=("Consolas", 9), bg="#313244", fg="#cdd6f4")
        self.interval_spin.delete(0, tk.END)
        self.interval_spin.insert(0, str(cfg.get("chatter_interval_min", 15)))
        self.interval_spin.pack(side=tk.LEFT, padx=6)
        
        # Buttons
        f_btn = tk.Frame(self.win, bg="#181825")
        f_btn.pack(fill=tk.X, padx=20, pady=(14, 10))
        tk.Button(f_btn, text="💾 儲存設定", font=("微軟正黑體", 9, "bold"), bg="#a6e3a1", fg="#11111b",
                  relief=tk.FLAT, cursor="hand2", command=self.save_config).pack(side=tk.RIGHT, padx=5, ipady=3, ipadx=8)
        tk.Button(f_btn, text="測試連線", font=("微軟正黑體", 9), bg="#45475a", fg="#cdd6f4",
                  relief=tk.FLAT, cursor="hand2", command=self.test_connection).pack(side=tk.RIGHT, padx=5, ipady=3)

    def test_connection(self):
        import threading
        from tkinter import messagebox
        url = self.url_entry.get().strip()
        model = self.model_entry.get().strip()
        def _run():
            ok, msg = self.monitor.test_ccr_connection(url, model)
            if ok:
                self.win.after(0, lambda: messagebox.showinfo("連線成功", "🎉 AI Nexus 連線測試成功！"))
            else:
                self.win.after(0, lambda: messagebox.showerror("連線失敗", f"無法連線到伺服器：\n{msg}"))
        threading.Thread(target=_run, daemon=True).start()

    def save_config(self):
        cfg = self.monitor.pet_data.setdefault("ai_config", {})
        cfg["ccr_url"] = self.url_entry.get().strip()
        cfg["model"] = self.model_entry.get().strip()
        cfg["auto_chatter"] = self.auto_var.get()
        try:
            cfg["chatter_interval_min"] = max(3, int(self.interval_spin.get()))
        except Exception:
            cfg["chatter_interval_min"] = 15
        self.monitor.save_pet_savegame()
        self.win.destroy()


# ──────────────────────────────────────────────────
# AI 尬聊主視窗 (AIChatWindow)
# ──────────────────────────────────────────────────
class AIChatWindow:
    def __init__(self, parent, monitor):
        self.monitor = monitor
        self.win = tk.Toplevel(parent)
        self.win.title("💬 找地瓜球尬聊")
        self.win.geometry("380x520")
        self.win.configure(bg="#181825")
        self.win.attributes("-topmost", True)
        
        # 居中在螢幕稍微偏右
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        self.win.geometry(f"380x520+{sw - 420}+{sh - 620}")
        
        self._build_ui()
        self._greet()

    def _build_ui(self):
        # 1. 頂部 Header
        header = tk.Frame(self.win, bg="#11111b", height=45)
        header.pack(fill=tk.X)
        
        tk.Label(header, text="🍠 地瓜球 AI 尬聊", font=("微軟正黑體", 11, "bold"), bg="#11111b", fg="#fab387").pack(side=tk.LEFT, padx=12, pady=8)
        
        # 連線狀態指示燈
        self.status_lbl = tk.Label(header, text="🟢 AI Nexus 在線", font=("微軟正黑體", 8), bg="#11111b", fg="#a6e3a1")
        self.status_lbl.pack(side=tk.LEFT, padx=4)
        
        # ⚙️ 設定按鈕
        tk.Button(
            header, text="⚙️", font=("Segoe UI Emoji", 10),
            bg="#11111b", fg="#cdd6f4", activebackground="#313244", activeforeground="#ffffff",
            relief=tk.FLAT, bd=0, cursor="hand2", command=self._open_config
        ).pack(side=tk.RIGHT, padx=10)

        # 2. 對話歷史區域
        msg_frame = tk.Frame(self.win, bg="#181825")
        msg_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)
        
        self.msg_text = tk.Text(
            msg_frame, bg="#1e1e2e", fg="#cdd6f4", font=("微軟正黑體", 9),
            wrap=tk.WORD, relief=tk.FLAT, padx=10, pady=8, state=tk.DISABLED
        )
        scrollbar = tk.Scrollbar(msg_frame, command=self.msg_text.yview, bg="#181825", relief=tk.FLAT)
        self.msg_text.config(yscrollcommand=scrollbar.set)
        
        self.msg_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Tag 配置
        self.msg_text.tag_config("pet_name", foreground="#fab387", font=("微軟正黑體", 9, "bold"))
        self.msg_text.tag_config("user_name", foreground="#89b4fa", font=("微軟正黑體", 9, "bold"))
        self.msg_text.tag_config("pet_msg", foreground="#f5c2e7")
        self.msg_text.tag_config("user_msg", foreground="#cdd6f4")
        self.msg_text.tag_config("sys_msg", foreground="#6c7086", font=("微軟正黑體", 8, "italic"))

        # 3. 快捷話題膠囊按鈕區
        capsule_frame = tk.Frame(self.win, bg="#181825")
        capsule_frame.pack(fill=tk.X, padx=10, pady=(0, 4))
        
        topics = [
            ("💖 打打氣", "主人工作好累喔，地瓜球給我打打氣！"),
            ("🍜 吃什麼", "地瓜球推薦我今天吃什麼好呢？"),
            ("💡 講笑話", "地瓜球講個冷笑話給我聽聽~"),
            ("🪙 錢包報告", "報告我現在有多少地瓜幣和經驗值！")
        ]
        for label, prompt in topics:
            btn = tk.Button(
                capsule_frame, text=label, font=("微軟正黑體", 8),
                bg="#313244", fg="#bac2de", activebackground="#45475a", activeforeground="#ffffff",
                relief=tk.FLAT, bd=0, cursor="hand2", command=lambda p=prompt: self._send_prompt(p)
            )
            btn.pack(side=tk.LEFT, padx=2)

        # 4. 底部輸入框與發送按鈕
        input_frame = tk.Frame(self.win, bg="#11111b", height=50)
        input_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        self.entry = tk.Entry(
            input_frame, bg="#313244", fg="#cdd6f4", font=("微軟正黑體", 10),
            insertbackground="#cdd6f4", relief=tk.FLAT
        )
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 4), pady=8, ipady=4)
        self.entry.bind("<Return>", lambda e: self._on_send())
        
        self.send_btn = tk.Button(
            input_frame, text="🚀 發送", font=("微軟正黑體", 9, "bold"),
            bg="#fab387", fg="#11111b", activebackground="#f9e2af",
            relief=tk.FLAT, bd=0, cursor="hand2", command=self._on_send
        )
        self.send_btn.pack(side=tk.RIGHT, padx=(0, 8), pady=8, ipady=2, ipadx=4)

    def _open_config(self):
        AIChatConfigWindow(self.win, self.monitor)

    def _append_message(self, role, text):
        self.msg_text.config(state=tk.NORMAL)
        if role == "pet":
            self.msg_text.insert(tk.END, "🍠 地瓜球: ", "pet_name")
            self.msg_text.insert(tk.END, f"{text}\n\n", "pet_msg")
        elif role == "user":
            self.msg_text.insert(tk.END, "👤 主人: ", "user_name")
            self.msg_text.insert(tk.END, f"{text}\n\n", "user_msg")
        else:
            self.msg_text.insert(tk.END, f"📢 {text}\n\n", "sys_msg")
        self.msg_text.config(state=tk.DISABLED)
        self.msg_text.see(tk.END)

    def _greet(self):
        name = self.monitor.user_name or "主人"
        self._append_message("pet", f"哈囉 {name}～！✨ 我是地瓜球！\n今天有什麼想跟我聊聊的嗎？(｡•ㅅ•｡)♡")

    def _send_prompt(self, text):
        self.entry.delete(0, tk.END)
        self.entry.insert(0, text)
        self._on_send()

    def _on_send(self):
        text = self.entry.get().strip()
        if not text:
            return
            
        self.entry.delete(0, tk.END)
        self._append_message("user", text)
        
        self.status_lbl.config(text="🟡 思考中...", fg="#f9e2af")
        self.send_btn.config(state=tk.DISABLED, bg="#585b70")
        
        # 觸發地瓜球在桌面上開心地說話
        self.monitor.pet.eye_state = "happy"
        self.monitor.pet.mouth_state = "open"
        
        def _on_reply(reply_text, error=None):
            def _ui():
                self.send_btn.config(state=tk.NORMAL, bg="#fab387")
                if error:
                    self.status_lbl.config(text="🔴 離線/錯誤", fg="#f38ba8")
                    self._append_message("sys", f"無法連接 CCR 伺服器：{error}")
                else:
                    self.status_lbl.config(text="🟢 CCR 在線", fg="#a6e3a1")
                    self._append_message("pet", reply_text)
                    # 同步在桌面彈出精簡短氣泡
                    short_bubble = reply_text.replace("\n", " ")
                    if len(short_bubble) > 28:
                        short_bubble = short_bubble[:26] + "..."
                    self.monitor.create_text_popup(short_bubble, 170, 100, color="#fab387")
                    self.monitor.pet.eye_state = "happy"
                    self.win.after(1000, self.monitor.pet.restore_eye)
            self.win.after(0, _ui)

        self.monitor.send_ai_chat_message(text, _on_reply)
