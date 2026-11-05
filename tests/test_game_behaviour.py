import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

import emojinoko_monitor as app
from emojinoko_game import ShopWindow
from unity_renderer_bridge import UnityRendererBridge


def monitor():
    pet = app.EmojinokoMonitor.__new__(app.EmojinokoMonitor)
    pet.root = mock.Mock()
    pet.pet_data = {"coins": 10000, "xp": 0, "level": 1, "satiety": 50}
    pet.pet = SimpleNamespace(state="idle", eye_state="normal", mouth_state="normal")
    pet.save_pet_savegame = mock.Mock()
    pet.create_text_popup = mock.Mock()
    pet._spawn_token_particle = mock.Mock()
    pet.STANDALONE = False
    pet.is_manual_refresh = False
    return pet


class GameBehaviourTests(unittest.TestCase):
    def test_large_reward_crosses_multiple_levels(self):
        pet = monitor()
        pet.gain_pet_xp(500)
        self.assertEqual((4, 50), (pet.pet_data["level"], pet.pet_data["xp"]))
        pet.save_pet_savegame.assert_called()

    def test_every_food_purchase_applies_once_without_missing_callbacks(self):
        pet = monitor()
        shop = ShopWindow(None, pet, build_ui=False)
        for food in [item for item in shop.items if item.get("type") == "food"]:
            with self.subTest(food=food["id"]):
                before = pet.pet_data["coins"]
                shop._on_item_action(food)
                self.assertEqual(before - food["price"], pet.pet_data["coins"])
                self.assertLessEqual(pet.pet_data["satiety"], 100)

    def test_every_accessory_can_be_bought_equipped_and_removed(self):
        pet = monitor()
        shop = ShopWindow(None, pet, build_ui=False)
        for item in [i for i in shop.items if i.get("type", "accessory") == "accessory"]:
            with self.subTest(item=item["id"]):
                before = pet.pet_data["coins"]
                shop._on_item_action(item)
                slot = shop._get_accessory_slot(item["id"])
                self.assertEqual(item["id"], pet.pet_data["equipped_accessories"][slot])
                self.assertEqual(before - item["price"], pet.pet_data["coins"])
                shop._on_item_action(item)
                self.assertNotIn(slot, pet.pet_data["equipped_accessories"])
                self.assertEqual(before - item["price"], pet.pet_data["coins"])

    def test_all_python_slots_agree_with_the_unity_catalog(self):
        root = Path(__file__).resolve().parents[1]
        catalog = json.loads((root / "unity_poc/Assets/TokenPet/Resources/accessory_catalog.json").read_text())
        shop = ShopWindow(None, None, build_ui=False)
        for item in catalog["items"]:
            with self.subTest(item=item["id"]):
                self.assertEqual(item["slot"], app._accessory_slot(item["id"]))
                self.assertEqual(item["slot"], shop._get_accessory_slot(item["id"]))

    def test_fruit_game_settles_rewards_only_once(self):
        pet = monitor()
        game = app.FruitCatcherWindow.__new__(app.FruitCatcherWindow)
        game.monitor, game.score, game._settled = pet, 100, False
        game.finish_game()
        first = dict(pet.pet_data)
        game.finish_game()
        self.assertEqual(first, pet.pet_data)
        self.assertEqual(10025, pet.pet_data["coins"])
        self.assertEqual(2, pet.pet_data["level"])

    def test_slot_jackpot_settles_once_and_awards_experience(self):
        pet = monitor()
        game = app.SlotMachineWindow.__new__(app.SlotMachineWindow)
        game.monitor, game.reels, game._result_pending = pet, ["7️⃣"] * 3, True
        game.check_win()
        first = dict(pet.pet_data)
        game.check_win()
        self.assertEqual(first, pet.pet_data)
        self.assertEqual(10500, pet.pet_data["coins"])
        self.assertEqual((4, 50), (pet.pet_data["level"], pet.pet_data["xp"]))

    def test_rps_cannot_open_duplicate_rounds_or_repeat_payouts(self):
        pet = monitor()
        with mock.patch.object(app, "RPSWindow") as window, mock.patch.object(app.random, "choice", return_value="scissors"):
            pet.play_rps()
            pet.play_rps()
            window.assert_called_once()
            pet.handle_rps_choice("rock")
            pet.handle_rps_choice("rock")
        self.assertEqual(10010, pet.pet_data["coins"])

    def test_cancelling_unplayed_rps_refunds_the_entry_fee_once(self):
        pet = monitor()
        with mock.patch.object(app, "RPSWindow"):
            pet.play_rps()
        pet.cancel_rps()
        pet.cancel_rps()
        self.assertEqual(10000, pet.pet_data["coins"])

    def test_rps_multiline_board_is_a_string_on_the_unity_wire(self):
        bridge = UnityRendererBridge("unused.exe")
        bridge._connection = mock.Mock()
        bridge.send_snapshot(state="idle", emotion="normal", accessory=None, look_x=0, look_y=0,
                             board_text=["猜拳中", "請出拳", ""], show_board=True)
        wire = json.loads(bridge._connection.sendall.call_args.args[0])
        self.assertEqual("猜拳中\n請出拳\n", wire["board_text"])

    def test_zero_baseline_still_awards_first_usage_after_initial_sync(self):
        pet = monitor()
        pet._process_usage_delta([])
        pet._process_usage_delta([{"prompt_tokens": 1000, "complete_tokens": 1000}])
        self.assertGreater(pet.pet_data["coins"], 10000)
        pet._spawn_token_particle.assert_called()

    def test_temporary_counter_drop_does_not_duplicate_rewards(self):
        pet = monitor()
        pet._process_usage_delta([{"prompt_tokens": 1000, "complete_tokens": 1000}])
        pet._process_usage_delta([{"prompt_tokens": 2000, "complete_tokens": 2000}])
        first = pet.pet_data["coins"]
        pet._process_usage_delta([{"prompt_tokens": 500, "complete_tokens": 500}])
        pet._process_usage_delta([{"prompt_tokens": 2000, "complete_tokens": 2000}])
        self.assertEqual(first, pet.pet_data["coins"])

    def test_calendar_month_change_resets_baseline_even_if_new_total_is_larger(self):
        pet = monitor()
        pet.pet_data.update(usage_month="2000-01", usage_baseline_initialized=True,
                            last_prompt_baseline=1, last_complete_baseline=1)
        pet._process_usage_delta([{"prompt_tokens": 10000, "complete_tokens": 10000}])
        self.assertEqual(10000, pet.pet_data["coins"])
        pet._spawn_token_particle.assert_not_called()

    def test_offline_feeding_cannot_change_company_baselines(self):
        pet = monitor()
        pet.STANDALONE = True
        pet.pet_data.update(last_prompt_baseline=17, last_complete_baseline=23)
        pet.simulate_usage()
        self.assertEqual(17, pet.pet_data["last_prompt_baseline"])
        self.assertEqual(23, pet.pet_data["last_complete_baseline"])

    def test_each_equipment_slot_contributes_its_completion_bonus(self):
        pet = monitor()
        pet.pet_data["equipped_accessories"] = {"head": "crown", "face": "star_sunglasses"}
        pet._process_usage_delta([{"complete_tokens": 1}])
        pet._process_usage_delta([{"complete_tokens": 10001}])
        expected = int(10000 * app.TOKEN_TO_COIN * 1.15 * 1.10)
        self.assertEqual(10000 + expected, pet.pet_data["coins"])

    def test_small_completion_deltas_accumulate_fractional_coin_rewards(self):
        pet = monitor()
        pet._process_usage_delta([])
        for total in range(1, 21):
            pet._process_usage_delta([{"complete_tokens": total}])
        self.assertEqual(10001, pet.pet_data["coins"])
        self.assertEqual(0, pet.pet_data["usage_coin_remainder"])

    def test_restoring_a_memo_preserves_size_and_whitespace(self):
        pet = monitor()
        pet.pet_data["deleted_memos"] = [{"id": "memo", "x": 12, "y": 23, "w": 350, "h": 260,
                                           "text": "  indented\n\n", "deleted_at": 1}]
        pet.spawn_memo = mock.Mock()
        pet.restore_memo("memo")
        pet.spawn_memo.assert_called_once_with("memo", 12, 23, "  indented\n\n", 350, 260)

    def test_memo_edit_keeps_indentation_and_trailing_newlines(self):
        pet = monitor()
        pet.pet_data["memos"] = [{"id": "memo", "text": "old"}]
        memo = app.MemoWindow.__new__(app.MemoWindow)
        memo.monitor, memo.memo_id, memo.text_widget = pet, "memo", mock.Mock()
        memo.text_widget.get.return_value = "  indented\n\n"
        memo.on_text_change()
        self.assertEqual("  indented\n\n", pet.pet_data["memos"][0]["text"])


if __name__ == "__main__":
    unittest.main()
