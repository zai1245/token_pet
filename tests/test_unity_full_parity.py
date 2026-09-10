import json
import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "unity_poc" / "Assets" / "TokenPet" / "Scripts"


class UnityFullParityTests(unittest.TestCase):
    def test_shop_catalog_can_render_every_item_in_unity_mode(self):
        source = (ROOT / "emojinoko_game.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        catalog = None
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            if any(
                isinstance(target, ast.Attribute) and target.attr == "items"
                for target in node.targets
            ):
                catalog = ast.literal_eval(node.value)
                break
        self.assertIsNotNone(catalog)
        self.assertTrue(catalog)
        self.assertTrue(all("desc" in item for item in catalog))
        self.assertIn('item.get("desc", "")', source)

    def test_every_legacy_accessory_has_a_unity_catalog_entry(self):
        expected = {
            "char_mask", "char_helmet", "sunglasses", "scholar_cap", "cat_ears", "crown",
            "rainbow", "halo", "gentleman_hat", "demon_horns",
            "star_sunglasses", "bowtie", "sakura_hairpin",
            "gamer_headset", "wizard_hat", "clover_sprout", "bandage",
        }
        catalog = json.loads((
            ROOT / "unity_poc" / "Assets" / "TokenPet" / "Resources" /
            "accessory_catalog.json"
        ).read_text(encoding="utf-8"))
        self.assertEqual({item["id"] for item in catalog["items"]}, expected)

    def test_every_consumable_visual_is_implemented(self):
        source = (SCRIPTS / "TokenPetLegacyVisuals.cs").read_text(encoding="utf-8")
        for item_id in {
            "matcha_parfait", "souffle_pancake", "pizza", "lollipop",
            "spicy_ramen", "popsicle", "candy", "bubble_tea", "ramen",
            "balloon", "balloon_toy",
        }:
            self.assertIn(f'"{item_id}"', source)

    def test_every_furniture_reaction_is_implemented(self):
        source = (SCRIPTS / "TokenPetLegacyVisuals.cs").read_text(encoding="utf-8")
        for item_id in {
            "futon", "laptop", "trampoline", "night_lamp",
            "succulent_pot", "lazy_sofa", "pixel_tv", "kotatsu", "memo",
        }:
            self.assertIn(f'"{item_id}"', source)

    def test_furniture_entities_are_rendered_and_dragged_by_unity(self):
        monitor = (ROOT / "emojinoko_monitor.py").read_text(encoding="utf-8")
        bootstrap = (SCRIPTS / "TokenPetPocBootstrap.cs").read_text(encoding="utf-8")
        stage = (SCRIPTS / "TokenPetFurnitureStage.cs").read_text(encoding="utf-8")
        self.assertIn("class UnityFurnitureProxy", monitor)
        self.assertIn("def _sync_unity_furniture", monitor)
        self.assertIn('event_name == "furniture_moved"', monitor)
        self.assertIn('case "sync_furniture"', bootstrap)
        self.assertIn("class TokenPetFurnitureStage", stage)
        self.assertIn('event_name = "furniture_moved"', stage)
        self.assertIn('event_name = "furniture_despawn"', stage)
        for item_id in {
            "futon", "laptop", "trampoline", "night_lamp",
            "succulent_pot", "lazy_sofa", "pixel_tv", "kotatsu",
        }:
            self.assertIn(f'case "{item_id}"', stage)

    def test_desktop_stage_removes_the_compact_window_clip_boundary(self):
        overlay = (SCRIPTS / "TokenPetWindowsOverlay.cs").read_text(encoding="utf-8")
        bootstrap = (SCRIPTS / "TokenPetPocBootstrap.cs").read_text(encoding="utf-8")
        self.assertIn("SmXVirtualScreen", overlay)
        self.assertIn("WsExTransparent", overlay)
        self.assertIn("InteractiveHitTest", overlay)
        self.assertIn("GetPetWorkArea", overlay)
        self.assertIn('event_name = "desktop_metrics"', bootstrap)
        self.assertIn("floor_y", bootstrap)
        self.assertIn("if (overlay != null && overlay.IsDesktopStage)", bootstrap)

    def test_full_visual_snapshot_contract_exists_on_both_sides(self):
        python_source = (ROOT / "unity_renderer_bridge.py").read_text(encoding="utf-8")
        unity_source = (SCRIPTS / "TokenPetIpcClient.cs").read_text(encoding="utf-8")
        for field in {
            "eat_type", "furniture", "effects", "show_board", "board_text", "overtime"
        }:
            self.assertIn(field, python_source)
            self.assertIn(field, unity_source)

    def test_legacy_fallback_is_still_present(self):
        source = (ROOT / "emojinoko_monitor.py").read_text(encoding="utf-8")
        self.assertIn("_fallback_to_legacy_renderer", source)
        self.assertIn("legacy pet hidden and standing by as fallback", source)

    def test_hidden_canvas_feedback_is_rendered_by_unity(self):
        monitor = (ROOT / "emojinoko_monitor.py").read_text(encoding="utf-8")
        bridge = (ROOT / "unity_renderer_bridge.py").read_text(encoding="utf-8")
        ipc = (SCRIPTS / "TokenPetIpcClient.cs").read_text(encoding="utf-8")
        floating = (SCRIPTS / "TokenPetFloatingText.cs").read_text(encoding="utf-8")
        self.assertIn("bridge.show_popup", monitor)
        self.assertIn('"command": "popup"', bridge)
        self.assertIn("public string text", ipc)
        self.assertIn("class TokenPetFloatingText", floating)

    def test_unity_window_uses_original_python_desktop_physics(self):
        monitor = (ROOT / "emojinoko_monitor.py").read_text(encoding="utf-8")
        bootstrap = (SCRIPTS / "TokenPetPocBootstrap.cs").read_text(encoding="utf-8")
        self.assertIn("def _begin_unity_release_fall", monitor)
        self.assertIn("bridge.move_window", monitor)
        self.assertIn('case "move_window"', bootstrap)
        self.assertIn("overlay.MoveTo", bootstrap)
        self.assertIn("current_x = float(self._physics_win_x)", monitor)
        self.assertIn("current_y = float(self._physics_win_y)", monitor)

    def test_shop_is_integrated_into_the_unity_surface(self):
        monitor = (ROOT / "emojinoko_monitor.py").read_text(encoding="utf-8")
        bridge = (ROOT / "unity_renderer_bridge.py").read_text(encoding="utf-8")
        ipc = (SCRIPTS / "TokenPetIpcClient.cs").read_text(encoding="utf-8")
        bootstrap = (SCRIPTS / "TokenPetPocBootstrap.cs").read_text(encoding="utf-8")
        panel = (SCRIPTS / "TokenPetShopPanel.cs").read_text(encoding="utf-8")
        self.assertIn("bridge.show_shop", monitor)
        self.assertIn("self.root.after(120, self.open_shop)", monitor)
        self.assertIn('"command": "show_shop"', bridge)
        self.assertIn("public string payload", ipc)
        self.assertIn('case "show_shop"', bootstrap)
        self.assertIn("class TokenPetShopPanel", panel)
        self.assertIn('event_name = "shop_action"', panel)
        self.assertIn("private void OnGUI()", panel)
        self.assertIn("GUI.DrawTexture", panel)
        self.assertIn("overlay?.SetShopExpanded(true)", panel)
        self.assertIn("170f / Mathf.Max(1f, Screen.width)", panel)
        self.assertNotIn("UnityEngine.UI", panel)
        self.assertNotIn("AddComponent<Mask>", panel)
        self.assertIn("pageIndex--", panel)
        self.assertIn("pageIndex++", panel)


if __name__ == "__main__":
    unittest.main()
