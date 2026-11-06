"""A small opt-in paper journal shared by Canvas and Unity."""

import tkinter as tk

from usage_widget import ManagedToplevel


class CompanionWindow(ManagedToplevel):
    PAPER = "#fff9ed"
    INK = "#503625"
    MUTED = "#867057"
    GOLD = "#f3d38a"
    LINE = "#e5d6bf"
    FONT = "Microsoft JhengHei UI"

    def __init__(self, monitor):
        super().__init__(monitor.root)
        self.monitor = monitor
        self.tab = "today"
        self._last_view = None
        self.title("地瓜球的陪伴手帳")
        self.configure(bg=self.PAPER)
        self.resizable(False, False)
        self.attributes("-topmost", True)
        # Keep the whole window reachable even on a small display.
        width = min(440, self.winfo_screenwidth() - 40)
        height = min(570, self.winfo_screenheight() - 100)
        self.geometry(f"{width}x{height}+{max(0, (self.winfo_screenwidth()-width)//2)}+{max(0, (self.winfo_screenheight()-height)//2)}")

        header = tk.Frame(self, bg=self.PAPER)
        header.pack(fill="x", padx=20, pady=(16, 10))
        self._label(header, "地瓜球的陪伴手帳", 17, bold=True).pack(anchor="w")
        self.subtitle = self._label(header, "", 9, color=self.MUTED)
        self.subtitle.pack(anchor="w", pady=(5, 0))
        actions = tk.Frame(self, bg=self.PAPER)
        actions.pack(fill="x", padx=20, pady=(0, 12))
        self._button(actions, "打個招呼", monitor.greet_companion).pack(side="left", expand=True, fill="x", padx=(0, 6))
        self._button(actions, "一起伸懶腰", monitor.stretch_companion).pack(side="left", expand=True, fill="x")

        tabs = tk.Frame(self, bg=self.PAPER)
        tabs.pack(fill="x", padx=20)
        self.tabs = {}
        for key, title in (("today", "今日小事"), ("badges", "收藏徽章"), ("memories", "陪伴回憶")):
            button = self._button(tabs, title, lambda tab=key: self.select_tab(tab))
            button.pack(side="left", expand=True, fill="x", padx=2)
            self.tabs[key] = button

        area = tk.Frame(self, bg=self.PAPER)
        area.pack(fill="both", expand=True, padx=16, pady=12)
        self.canvas = tk.Canvas(area, bg=self.PAPER, highlightthickness=0)
        scrollbar = tk.Scrollbar(area, orient="vertical", command=self.canvas.yview)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.body = tk.Frame(self.canvas, bg=self.PAPER)
        self._body_id = self.canvas.create_window(0, 0, window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda event: self.canvas.itemconfigure(self._body_id, width=event.width))
        # Bind on this Toplevel, never bind_all: other app windows keep their wheel.
        self.bind("<MouseWheel>", lambda event: self.canvas.yview_scroll(-int(event.delta / 120), "units"))
        self.feedback = self._label(self, "想做再做，漏掉一天也沒關係。", 9, color=self.MUTED)
        self.feedback.pack(fill="x", padx=20, pady=(0, 12))
        self.bind("<Escape>", lambda _event: self.destroy())
        self.refresh()
        self._poll()

    def _label(self, parent, text, size=10, bold=False, color=None, **kwargs):
        return tk.Label(parent, text=text, bg=self.PAPER, fg=color or self.INK,
                        font=(self.FONT, size, "bold" if bold else "normal"), **kwargs)

    def _button(self, parent, text, command):
        return tk.Button(parent, text=text, command=command, bg=self.GOLD, fg=self.INK,
                         activebackground="#f9dfaa", activeforeground=self.INK,
                         relief="flat", bd=0, padx=8, pady=7, cursor="hand2", font=(self.FONT, 9))

    def select_tab(self, tab):
        self.tab = tab
        self._last_view = None
        self.refresh()
        self.canvas.yview_moveto(0)

    def _poll(self):
        self.refresh()
        self.after(1000, self._poll)

    def refresh(self):
        if not self.winfo_exists():
            return
        view = self.monitor.companion_snapshot()
        signature = (self.tab, view, self.monitor.pet_data.get("coins", 0))
        if signature == self._last_view:
            return
        self._last_view = signature
        self.subtitle.configure(text=f"已一起留下 {view['days']} 天回憶  ·  地瓜幣 {self.monitor.pet_data.get('coins', 0):,}")
        for key, button in self.tabs.items():
            button.configure(bg=self.GOLD if key == self.tab else "#eee5d6")
        for widget in self.body.winfo_children():
            widget.destroy()
        if self.tab == "today":
            self._today(view)
        elif self.tab == "badges":
            self._badges(view)
        else:
            self._memories(view)

    def _card(self, padding=10):
        frame = tk.Frame(self.body, bg=self.PAPER, highlightbackground=self.LINE, highlightthickness=1)
        frame.pack(fill="x", padx=4, pady=(0, 9))
        content = tk.Frame(frame, bg=self.PAPER)
        content.pack(fill="x", padx=12, pady=padding)
        return content

    def _today(self, view):
        self._label(self.body, view["date"] + "  ·  三件暖暖的小事", 10, bold=True).pack(anchor="w", padx=6, pady=(0, 10))
        for goal in view["goals"]:
            card = self._card(padding=6)
            top = tk.Frame(card, bg=self.PAPER)
            top.pack(fill="x")
            self._label(top, goal["title"], 11, bold=True).pack(side="left")
            if goal["id"] == "play":
                tk.Button(top, text="免費接水果 ›", command=self.monitor.toggle_fruit_catcher,
                          bg=self.PAPER, fg="#62825e", activebackground=self.PAPER,
                          relief="flat", bd=0, cursor="hand2", font=(self.FONT, 9)).pack(side="left", padx=6)
            self._label(top, f"{goal['progress']}/{goal['target']}", 10, color=self.MUTED).pack(side="right")
            bottom = tk.Frame(card, bg=self.PAPER)
            bottom.pack(fill="x", pady=(4, 0))
            self._label(bottom, f"{goal['detail']}\n+{goal['coins']} 地瓜幣  ·  +{goal['xp']} XP", 9,
                        color=self.MUTED, justify="left").pack(side="left")
            ready = goal["progress"] >= goal["target"]
            button = self._button(bottom, "已領取" if goal["claimed"] else ("領取" if ready else "進行中"),
                                  lambda goal_id=goal["id"]: self._claim(goal_id))
            button.configure(state="normal" if ready and not goal["claimed"] else "disabled")
            button.pack(side="right")
        self._label(self.body, "今日圓滿章已收藏！" if view["complete"] else "全部領取，再送 30 地瓜幣與 15 XP。",
                    9, color=self.MUTED, wraplength=330, justify="left").pack(anchor="w", padx=6, pady=2)

    def _claim(self, goal_id):
        message = self.monitor.claim_companion_goal(goal_id)
        self.feedback.configure(text=message)
        self.refresh()

    def _badges(self, view):
        count = sum(bool(badge["unlocked"]) for badge in view["badges"])
        self._label(self.body, f"小小收藏  {count}/{len(view['badges'])}", 10, bold=True).pack(anchor="w", padx=6, pady=(0, 10))
        for index, badge in enumerate(view["badges"], 1):
            card = self._card()
            stamp = tk.Canvas(card, width=42, height=42, bg=self.PAPER, highlightthickness=0)
            stamp.pack(side="left", padx=(0, 10))
            stamp.create_oval(3, 3, 39, 39, fill=self.GOLD if badge["unlocked"] else "#eee5d6", outline=self.LINE, width=2)
            stamp.create_text(21, 21, text=f"{index:02d}" if badge["unlocked"] else "?", fill=self.INK if badge["unlocked"] else self.MUTED,
                              font=(self.FONT, 11, "bold"))
            info = tk.Frame(card, bg=self.PAPER)
            info.pack(side="left", fill="x", expand=True)
            self._label(info, badge["title"], 11, bold=True).pack(anchor="w")
            self._label(info, badge["detail"], 9, color=self.MUTED).pack(anchor="w", pady=2)
            self._label(info, f"收藏於 {badge['unlocked']}" if badge["unlocked"] else f"{badge['progress']} / {badge['target']}",
                        8, color=self.MUTED).pack(anchor="w")

    def _memories(self, view):
        self._label(self.body, "最近 30 天的暖暖片段", 10, bold=True).pack(anchor="w", padx=6, pady=(0, 10))
        if not view["memories"]:
            self._label(self.body, "手帳還是空白的。\n打個招呼，留下第一段回憶吧。", 10, color=self.MUTED,
                        justify="left").pack(anchor="w", padx=8, pady=24)
        for memory in view["memories"]:
            card = self._card()
            self._label(card, memory["date"], 10, bold=True).pack(anchor="w", pady=(0, 4))
            for note in memory["notes"]:
                self._label(card, "・" + note, 9, color=self.MUTED, wraplength=310,
                            justify="left").pack(anchor="w", pady=3)
