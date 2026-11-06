import copy
from datetime import date, timedelta
import json
from types import SimpleNamespace
import unittest
from unittest import mock

import emojinoko_monitor as app
from companion_journal import CompanionJournal, GOALS
from test_game_behaviour import monitor


TODAY = date(2026, 11, 6)


class CompanionJournalTests(unittest.TestCase):
    def setUp(self):
        self.save = {"coins": 40, "last_prompt_baseline": 123, "usage_month": "2026-11"}
        self.journal = CompanionJournal(self.save)

    def complete_day(self, day=TODAY):
        for _ in range(3):
            self.journal.record("pet", day)
        self.journal.record("stretch", day)
        self.journal.record("play", day)

    def test_fresh_install_preserves_wallet_and_company_baselines(self):
        view = self.journal.snapshot(TODAY)
        self.assertEqual([0, 0, 0], [goal["progress"] for goal in view["goals"]])
        self.assertEqual((40, 123, "2026-11"), (self.save["coins"], self.save["last_prompt_baseline"], self.save["usage_month"]))
        self.assertEqual(0, view["days"])

    def test_pending_and_unknown_goals_never_pay(self):
        self.assertEqual(0, self.journal.claim("pet", TODAY).coins)
        self.assertEqual(0, self.journal.claim("unknown", TODAY).coins)
        self.assertEqual([], self.journal.record("api_spending", TODAY))

    def test_all_goals_and_completion_bonus_pay_once_across_reload(self):
        self.complete_day()
        rewards = [self.journal.claim(goal["id"], TODAY) for goal in GOALS]
        self.assertEqual((75, 35), (sum(r.coins for r in rewards), sum(r.xp for r in rewards)))
        self.assertEqual([False, False, True], [r.bonus for r in rewards])
        reopened = CompanionJournal(json.loads(json.dumps(self.save)))
        for goal in GOALS:
            self.assertEqual(0, reopened.claim(goal["id"], TODAY).coins)
        self.assertEqual(1, reopened.data["totals"]["complete_days"])
        self.assertTrue(reopened.snapshot(TODAY)["complete"])

    def test_new_day_resets_goals_and_keeps_totals_and_badges(self):
        self.journal.record("greet", TODAY)
        self.complete_day()
        self.journal.claim("pet", TODAY)
        tomorrow = self.journal.snapshot(TODAY + timedelta(days=1))
        self.assertEqual([0, 0, 0], [goal["progress"] for goal in tomorrow["goals"]])
        self.assertFalse(any(goal["claimed"] for goal in tomorrow["goals"]))
        self.assertTrue(tomorrow["badges"][0]["unlocked"])
        self.assertEqual(1, tomorrow["days"])
        self.journal.record("greet", TODAY + timedelta(days=1))
        self.assertEqual(2, self.journal.snapshot(TODAY + timedelta(days=1))["days"])

    def test_clock_rewind_cannot_reopen_a_paid_day(self):
        self.complete_day()
        self.journal.claim("pet", TODAY)
        self.journal.snapshot(TODAY + timedelta(days=1))
        self.assertEqual(0, self.journal.claim("pet", TODAY).coins)
        self.assertEqual("2026-11-07", self.journal.snapshot(TODAY)["date"])

    def test_memory_retention_is_thirty_calendar_days_and_totals_survive(self):
        for offset in range(40):
            self.journal.record("greet", TODAY + timedelta(days=offset))
        view = self.journal.snapshot(TODAY + timedelta(days=39))
        self.assertEqual(30, len(view["memories"]))
        self.assertEqual(40, view["days"])
        self.assertTrue(next(b for b in view["badges"] if b["id"] == "week")["unlocked"])
        # A long absence must not retain stale memories as if they were recent.
        self.assertEqual([], self.journal.snapshot(TODAY + timedelta(days=90))["memories"])

    def test_badge_unlocked_once_and_memories_group_repeated_events(self):
        self.assertEqual(["初次見面"], self.journal.record("greet", TODAY))
        self.assertEqual([], self.journal.record("greet", TODAY))
        self.assertEqual(1, len(self.journal.snapshot(TODAY)["memories"][0]["notes"]))
        unlocked = []
        for _ in range(26):
            unlocked += self.journal.record("pet", TODAY)
        self.assertEqual(["摸摸專家"], unlocked)

    def test_malformed_optional_journal_cannot_break_existing_savegame(self):
        for broken in ([], "bad", {"history": []}, {"history": {"bad-date": {}, "2026-11-06": []}},
                       {"totals": {"pet": float("nan")}, "badges": ["hello"]},
                       {"history": {"2026-11-06": {"counts": {"pet": -100}, "claimed": "pet"}}}):
            with self.subTest(broken=broken):
                saved = dict(coins=5, companionship=broken)
                view = CompanionJournal(saved).snapshot(TODAY)
                self.assertEqual(5, saved["coins"])
                self.assertEqual(0, view["goals"][0]["progress"])


class CompanionIntegrationTests(unittest.TestCase):
    def test_claim_updates_wallet_xp_and_flags_in_one_save_and_blocks_double_click(self):
        pet = monitor()
        pet.pet_data.update(coins=10, xp=98)
        for _ in range(3):
            pet._record_companion_event("pet")
        pet.save_pet_savegame.reset_mock()
        self.assertIn("+15", pet.claim_companion_goal("pet"))
        self.assertEqual((25, 2, 3), (pet.pet_data["coins"], pet.pet_data["level"], pet.pet_data["xp"]))
        pet.save_pet_savegame.assert_called_once()
        pet.claim_companion_goal("pet")
        self.assertEqual(25, pet.pet_data["coins"])

    def test_failed_save_rolls_back_claim_wallet_and_level_then_allows_retry(self):
        pet = monitor()
        for _ in range(3):
            pet._record_companion_event("pet")
        before = copy.deepcopy(pet.pet_data)
        pet.save_pet_savegame.return_value = False
        self.assertIn("無法儲存", pet.claim_companion_goal("pet"))
        self.assertEqual(before, pet.pet_data)
        pet.save_pet_savegame.return_value = True
        pet.claim_companion_goal("pet")
        self.assertEqual(before["coins"] + 15, pet.pet_data["coins"])

    def test_unity_and_canvas_pokes_advance_the_same_goal(self):
        pet = monitor()
        pet.pet.r = 52
        pet.pet.restore_eye = mock.Mock()
        pet.root.winfo_y.return_value = 500
        pet.root.winfo_x.return_value = 500
        pet._furniture_cooldown = 1
        pet._handle_unity_poke()
        with mock.patch.object(app, "save_config"):
            pet._on_drag_end(SimpleNamespace(x=170, y=205))
        self.assertEqual(2, pet.companion_snapshot()["goals"][0]["progress"])
        pet._has_dragged = True
        pet._drag_history = []
        with mock.patch.object(app, "save_config"), mock.patch.object(pet, "_release_desktop_drag"):
            pet._on_drag_end(SimpleNamespace(x=170, y=205))
        self.assertEqual(2, pet.companion_snapshot()["goals"][0]["progress"])

    def test_free_reactions_have_cooldown_and_do_not_interrupt_flight_or_furniture(self):
        pet = monitor()
        pet.pet.restore_eye = mock.Mock()
        pet.greet_companion()
        pet.greet_companion()
        self.assertEqual(1, pet._companion_progress().data["totals"]["greet"])
        pet.stretch_companion()
        pet.stretch_companion()
        self.assertEqual(1, pet._companion_progress().data["totals"]["stretch"])
        coins = pet.pet_data["coins"]
        for state in ("sleep_futon", "eat", "roll", "work_laptop"):
            pet.pet.state = state
            pet.pet.wave_timer = 0
            pet.pet.stretch_timer = 0
            pet.greet_companion()
            pet.stretch_companion()
            self.assertEqual(state, pet.pet.state)
        pet.pet.state = "idle"
        pet._fall_vy = 10
        pet.stretch_companion()
        self.assertEqual(0, pet.pet.stretch_timer)
        self.assertEqual(coins, pet.pet_data["coins"])

    def test_all_four_games_record_completion_and_settlements_remain_idempotent(self):
        pet = monitor()
        pet._record_companion_event = mock.Mock()
        with mock.patch.object(app, "RPSWindow"):
            pet.play_rps()
        pet.handle_rps_choice("rock")
        pet.handle_rps_choice("rock")
        fruit = app.FruitCatcherWindow.__new__(app.FruitCatcherWindow)
        fruit.monitor, fruit.score, fruit._settled = pet, 10, False
        fruit.finish_game()
        fruit.finish_game()
        slots = app.SlotMachineWindow.__new__(app.SlotMachineWindow)
        slots.monitor, slots.reels, slots._result_pending = pet, ["7", "a", "b"], True
        slots.check_win()
        slots.check_win()
        for kind in (app.UnityBasketballHoop, app.BasketballHoop):
            hoop = kind.__new__(kind)
            hoop.monitor, hoop.score = pet, 0
            if kind is app.BasketballHoop:
                hoop.spawn_confetti = mock.Mock()
                hoop.draw_hoop = mock.Mock()
            hoop.trigger_goal()
        self.assertEqual(5, pet._record_companion_event.call_count)
        self.assertEqual([mock.call("play")] * 5, pet._record_companion_event.call_args_list)

    def test_packaging_includes_companionship_modules(self):
        from tools.package_integrated import SOURCE_FILES
        self.assertTrue({"companion_journal.py", "companion_window.py"}.issubset(SOURCE_FILES))


if __name__ == "__main__":
    unittest.main()
