import copy
import os
from pathlib import Path
import sys
import time
import tkinter as tk
import unittest
from unittest import mock

import emojinoko_monitor as app
import usage_widget as usage
from emojinoko_game import AIChatConfigWindow, ShopWindow
from usage_widget import ManagedToplevel


@unittest.skipUnless(os.name == "nt", "Windows desktop integration")
class UiLifecycleTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(str(error))
        self.root.withdraw()
        self.errors = []
        self.root.report_callback_exception = lambda *error: self.errors.append(error)
        self.addCleanup(self.close_root)

    def close_root(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_closing_an_animated_window_cancels_its_owned_callbacks(self):
        window = ManagedToplevel(self.root)
        callback = mock.Mock()
        token = window.after(1000, callback)
        window.destroy()
        self.assertNotIn(token, self.root.tk.splitlist(self.root.tk.call("after", "info")))
        self.assertIsNone(window.after(0, callback))
        callback.assert_not_called()

    def test_statistics_empty_month_charts_and_independent_hotkey(self):
        with mock.patch.object(usage, "load_config", return_value={"hotkey": {"vk": 118}}), \
                mock.patch.object(usage, "save_config"), \
                mock.patch.object(usage, "HotkeyManager"), \
                mock.patch.object(usage.UsageWidget, "_start_auto_refresh"):
            widget = usage.UsageWidget(self.root, "test", "test", "test", "test", "test")
            self.assertEqual(119, widget.hotkey_config["vk"])
            widget._show_pie.set(True)
            widget._update_ui([], {})
            self.root.update()
            self.assertIn("已更新", widget.status_label.cget("text"))
            widget._update_ui(usage.normalize_usage_data([
                {"model": "test", "price": "1.5", "prompt_tokens": "123", "api": "yes"}
            ]), {})
            widget._toggle_settings()
            widget._toggle_settings()
            widget._toggle_minimize()
            widget._toggle_minimize()
            self.root.update()
            self.root.destroy()
        self.assertEqual([], self.errors)

    def exercise_application(self, unity):
        config = {
            "last_github_update_check": time.time(),
            "pet_game": {"coins": 100000, "level": 1, "xp": 0, "satiety": 100,
                         "ai_config": {"auto_chatter": False, "api_key": ""}},
        }
        args = ["TokenPet", "--standalone"] + (["--unity-poc"] if unity else [])
        with mock.patch.object(sys, "argv", args), \
                mock.patch.dict(os.environ, TOKENPET_DEVELOPER_MODE="0", TOKENPET_AI_API_KEY=""), \
                mock.patch.object(app, "load_config", side_effect=lambda: copy.deepcopy(config)), \
                mock.patch.object(app, "save_config", return_value=True), \
                mock.patch.object(app, "HotkeyManager"), \
                mock.patch.object(app.EmojinokoMonitor, "_cleanup_old_versions_async"), \
                mock.patch.object(app.EmojinokoMonitor, "_start_game_loops"):
            pet = app.EmojinokoMonitor(self.root, "", "", "test", "", "")
            if unity:
                deadline = time.monotonic() + 15
                while not pet._unity_renderer_active and time.monotonic() < deadline:
                    self.root.update()
                    time.sleep(0.05)
                self.assertTrue(pet._unity_renderer_active)
            self.root.withdraw()
            shop = ShopWindow(None, pet, build_ui=False)
            for item in shop.items:
                shop._on_item_action(item)
                if item.get("type") == "furniture":
                    pet.spawn_furniture(item["id"])
                    self.root.update_idletasks()
                    pet.despawn_furniture(item["id"])
            pet.pet.state = "idle"
            pet.spawn_memo("smoke-memo", 400, 300, "  text\n\n", 260, 220)
            memo = pet.spawned_memo_wins["smoke-memo"]
            memo.text_widget.insert("end-1c", "pasted")
            self.root.update()
            self.assertEqual("  text\n\npasted", pet.pet_data["memos"][0]["text"])
            pet.play_rps()
            self.root.update_idletasks()
            pet.handle_rps_choice("rock")
            pet._cleanup_rps()
            pet.open_ai_chat()
            settings = AIChatConfigWindow(pet.ai_chat_win.win, pet)
            settings.win.destroy()
            pet.open_hotkey_settings()
            fruit = app.FruitCatcherWindow(pet)
            fruit.finish_game()
            fruit.close_game()
            slot = app.SlotMachineWindow(pet)
            slot.start_spin()
            slot.reels = ["🍠"] * 3
            slot.check_win()
            slot.close_game()
            pet.toggle_basketball_game()
            if pet.basketball_hoop is not None:
                pet.basketball_hoop.trigger_goal()
                pet.basketball_hoop.close_game()
            pet.pet.state = "idle"
            pet.tick_physics()
            self.root.update()
            if unity:
                pet._sync_unity_renderer(force=True)
                self.assertTrue(pet.unity_renderer.connected)
            self.root.destroy()
        self.assertEqual([], self.errors)

    def test_canvas_feature_windows_purchases_and_shutdown(self):
        self.exercise_application(unity=False)

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "unity_poc/Build/TokenPetUnity.exe").is_file(),
                         "Unity runtime not installed")
    def test_unity_integrated_feature_windows_purchases_and_shutdown(self):
        self.exercise_application(unity=True)


if __name__ == "__main__":
    unittest.main()
