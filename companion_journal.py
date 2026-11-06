"""Local companionship progress; rewards never depend on company API spending."""

from datetime import date, timedelta
from dataclasses import dataclass


GOALS = (
    dict(id="pet", title="摸摸小地瓜", detail="輕點地瓜球 3 次", target=3, coins=15, xp=5),
    dict(id="stretch", title="一起鬆一下", detail="一起伸個懶腰", target=1, coins=10, xp=5),
    dict(id="play", title="今天也要玩", detail="完成一局小遊戲，或投進一球", target=1, coins=20, xp=10),
)
BADGES = (
    dict(id="hello", title="初次見面", detail="向地瓜球打招呼", counter="greet", target=1),
    dict(id="gentle", title="摸摸專家", detail="累計摸摸 25 次", counter="pet", target=25),
    dict(id="playmate", title="最佳玩伴", detail="累計玩遊戲 5 次", counter="play", target=5),
    dict(id="relax", title="慢慢來就好", detail="累計一起伸懶腰 10 次", counter="stretch", target=10),
    dict(id="week", title="七日好友", detail="在 7 個不同日子留下互動", counter="days", target=7),
    dict(id="full_day", title="圓滿的一天", detail="領完一天的三份小獎勵", counter="complete_days", target=1),
)
MEMORIES = {
    "greet": "你來打了招呼，地瓜球開心地揮揮手。",
    "pet": "收到你的摸摸，今天又多了一點好心情。",
    "stretch": "一起伸了懶腰，肩膀也放鬆一點。",
    "play": "一起玩了遊戲，輸贏都是開心的回憶。",
    "complete": "三件小事都完成了，替今天蓋上一枚圓滿章。",
}


def _count(value):
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(0, min(value, 1_000_000_000))


def _day(value):
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError):
        return ""


@dataclass(frozen=True)
class Reward:
    coins: int = 0
    xp: int = 0
    bonus: bool = False


class CompanionJournal:
    """Mutate only pet_game.companionship, alongside the existing savegame."""

    def __init__(self, pet_data):
        raw = pet_data.get("companionship")
        raw = raw if isinstance(raw, dict) else {}
        days = {}
        history = raw.get("history") if isinstance(raw.get("history"), dict) else {}
        for key, value in history.items():
            if not _day(key) or not isinstance(value, dict):
                continue
            counts = value.get("counts") if isinstance(value.get("counts"), dict) else {}
            claimed = value.get("claimed") if isinstance(value.get("claimed"), list) else []
            days[key] = {
                "counts": {event: _count(counts.get(event)) for event in MEMORIES if event != "complete"},
                "claimed": [goal["id"] for goal in GOALS if goal["id"] in claimed],
                "complete": value.get("complete") is True,
            }
        totals = raw.get("totals") if isinstance(raw.get("totals"), dict) else {}
        badges = raw.get("badges") if isinstance(raw.get("badges"), dict) else {}
        self.data = {
            "history": dict(sorted(days.items())[-30:]),
            "latest_day": max([_day(raw.get("latest_day")), *days], default=""),
            "totals": {key: _count(totals.get(key)) for key in ("greet", "pet", "stretch", "play", "days", "complete_days")},
            "badges": {badge["id"]: _day(badges[badge["id"]]) for badge in BADGES
                       if _day(badges.get(badge["id"]))},
        }
        pet_data["companionship"] = self.data

    def _today(self, today=None):
        # A clock correction must not reopen an already claimed day.
        key = max((today or date.today()).isoformat(), self.data["latest_day"])
        self.data["latest_day"] = key
        history = self.data["history"]
        if key not in history:
            history[key] = {"counts": {event: 0 for event in ("greet", "pet", "stretch", "play")},
                            "claimed": [], "complete": False}
        cutoff = (date.fromisoformat(key) - timedelta(days=min(29, date.fromisoformat(key).toordinal() - 1))).isoformat()
        for old in list(history):
            if old < cutoff:
                del history[old]
        return key, history[key]

    def _unlock(self, key):
        unlocked = []
        for badge in BADGES:
            if (badge["id"] not in self.data["badges"] and
                    self.data["totals"][badge["counter"]] >= badge["target"]):
                self.data["badges"][badge["id"]] = key
                unlocked.append(badge["title"])
        return unlocked

    def record(self, event, today=None):
        if event not in ("greet", "pet", "stretch", "play"):
            return []
        key, entry = self._today(today)
        if not any(entry["counts"].values()):
            self.data["totals"]["days"] += 1
        entry["counts"][event] += 1
        self.data["totals"][event] += 1
        return self._unlock(key)

    def claim(self, goal_id, today=None):
        key, entry = self._today(today)
        goal = next((goal for goal in GOALS if goal["id"] == goal_id), None)
        if goal is None or goal_id in entry["claimed"] or entry["counts"][goal_id] < goal["target"]:
            return Reward()
        entry["claimed"].append(goal_id)
        bonus = len(entry["claimed"]) == len(GOALS) and not entry["complete"]
        if bonus:
            entry["complete"] = True
            self.data["totals"]["complete_days"] += 1
        self._unlock(key)
        return Reward(goal["coins"] + (30 if bonus else 0), goal["xp"] + (15 if bonus else 0), bonus)

    def snapshot(self, today=None):
        key, entry = self._today(today)
        return {
            "date": key,
            "goals": [dict(goal, progress=min(entry["counts"][goal["id"]], goal["target"]),
                           claimed=goal["id"] in entry["claimed"]) for goal in GOALS],
            "badges": [dict(badge, progress=min(self.data["totals"][badge["counter"]], badge["target"]),
                            unlocked=self.data["badges"].get(badge["id"])) for badge in BADGES],
            "days": self.data["totals"]["days"],
            "complete": entry["complete"],
            "memories": [dict(date=day, notes=[MEMORIES[event] for event, count in value["counts"].items() if count] +
                             ([MEMORIES["complete"]] if value["complete"] else []))
                         for day, value in sorted(self.data["history"].items(), reverse=True)
                         if any(value["counts"].values()) or value["complete"]],
        }
