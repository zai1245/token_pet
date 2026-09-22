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

    def test_head_accessories_have_artwork_aware_mount_pivots(self):
        catalog = json.loads((
            ROOT / "unity_poc" / "Assets" / "TokenPet" / "Resources" /
            "accessory_catalog.json"
        ).read_text(encoding="utf-8"))
        head_items = [item for item in catalog["items"] if item["slot"] == "head"]
        self.assertTrue(head_items)
        for item in head_items:
            with self.subTest(item=item["id"]):
                self.assertIn("pivot_x", item)
                self.assertIn("pivot_y", item)
                self.assertGreaterEqual(item["pivot_x"], 0.0)
                self.assertLessEqual(item["pivot_x"], 1.0)
                self.assertGreaterEqual(item["pivot_y"], 0.0)
                self.assertLessEqual(item["pivot_y"], 1.0)

        char_helmet = next(item for item in head_items if item["id"] == "char_helmet")
        char_mask = next(
            item for item in catalog["items"] if item["id"] == "char_mask"
        )
        self.assertEqual(
            "sprite:AccessoriesV2/char_helmet_back",
            char_helmet.get("back_resource"),
        )
        self.assertEqual("char_mask", char_helmet.get("paired_face_id"))
        self.assertEqual(
            "sprite:AccessoriesV2/char_helmet_with_mask",
            char_helmet.get("paired_resource"),
        )
        self.assertGreater(char_helmet["offset_y"], char_mask["offset_y"])
        self.assertGreater(char_helmet["sorting_order"], char_mask["sorting_order"])

        # Ordinary hats and ears must overlap the round head instead of using
        # the deliberately floating halo baseline. The helmet keeps its own
        # full-body wrap calibration.
        fitted_headwear = {
            "scholar_cap", "cat_ears", "crown", "gentleman_hat",
            "demon_horns", "sakura_hairpin", "wizard_hat", "clover_sprout",
        }
        for item in head_items:
            if item["id"] in fitted_headwear:
                with self.subTest(headwear=item["id"]):
                    self.assertLessEqual(item["offset_y"], 0.66)

        headset = next(item for item in catalog["items"] if item["id"] == "gamer_headset")
        self.assertLessEqual(headset["offset_y"], 0.0)
        equipment = (SCRIPTS / "TokenPetEquipmentController.cs").read_text(
            encoding="utf-8"
        )
        bootstrap = (SCRIPTS / "TokenPetPocBootstrap.cs").read_text(encoding="utf-8")
        self.assertIn("SetBackFacing", equipment)
        self.assertIn("PairedArtwork", equipment)
        self.assertIn("PairedUnderlayArtwork", equipment)
        self.assertIn("CreatePairedSideUnderlay", equipment)
        self.assertNotIn("PairedFrontSideArtwork", equipment)
        self.assertNotIn("CreatePairedFrontSideGuards", equipment)
        self.assertIn("renderer.sortingOrder = 9", equipment)
        self.assertIn("RefreshArtworkVariants", equipment)
        self.assertIn("bool showPaired = !backFacing && paired != null", equipment)
        self.assertNotIn(
            'equippedIds.TryGetValue("face", out string equippedFaceId)',
            equipment,
        )
        self.assertIn("equipment?.SetBackFacing(backFacing)", bootstrap)

        expression = (SCRIPTS / "TokenPetExpressionRig.cs").read_text(
            encoding="utf-8"
        )
        hungry_case = expression.split('case "hungry":', 1)[1].split("break;", 1)[0]
        self.assertIn("SetDorkyCatMouth", hungry_case)
        self.assertNotIn("SetWorryMouth", hungry_case)

    def test_unity_face_uses_the_canvas_emojinoko_proportions(self):
        expression = (SCRIPTS / "TokenPetExpressionRig.cs").read_text(
            encoding="utf-8"
        )
        self.assertIn("InitializeCanvasFaceSprites", expression)
        self.assertIn("ApplyCanvasSpriteExpression", expression)
        self.assertIn('Resources.Load<Texture2D>("FaceExpressions/" + name)', expression)
        self.assertIn("SpriteMeshType.FullRect", expression)
        for anchor in {
            "EyeCenterX = 0.308f",
            "EyeCenterY = 0.088f",
            "BrowCenterX = 0.352f",
            "BrowCenterY = 0.308f",
            "BlushCenterX = 0.484f",
            "BlushCenterY = -0.044f",
            "MouthCenterY = -0.176f",
        }:
            self.assertIn(anchor, expression)
        self.assertIn('CreateLine("Eye_Left_X_A", 0.074f', expression)
        self.assertIn("new Color32(60, 34, 3, 255)", expression)
        self.assertIn("new Color32(244, 168, 184, 220)", expression)
        self.assertIn("SetDorkyCatMouth(0.148f, 0.095f", expression)

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
        self.assertIn('event_name = "furniture_action"', stage)
        self.assertIn('event_name == "furniture_action"', monitor)
        self.assertIn("_request_furniture_interaction", monitor)
        self.assertIn("moveArmedId", stage)
        self.assertIn("ApplyPetState", stage)
        self.assertIn("FurnitureForState", stage)
        self.assertIn("ApplyFurnitureMotion", stage)
        self.assertIn("SetExternalFurnitureStage(true)", bootstrap)
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
        self.assertIn("Screen.SetResolution(StageSize.x, StageSize.y", overlay)
        self.assertIn("TokenPet desktop stage: render=", overlay)

    def test_unity_turning_and_furniture_poses_keep_canvas_character(self):
        bootstrap = (SCRIPTS / "TokenPetPocBootstrap.cs").read_text(encoding="utf-8")
        expression = (SCRIPTS / "TokenPetExpressionRig.cs").read_text(encoding="utf-8")
        limbs = (SCRIPTS / "TokenPetLimbRig.cs").read_text(encoding="utf-8")
        self.assertIn("FacingScaleForLegacyState", bootstrap)
        self.assertIn("ShouldUseBackArtwork", bootstrap)
        self.assertIn("Mathf.Cos(progress * Mathf.PI)", bootstrap)
        self.assertIn("faceVisible = progress < 0.5f", expression)
        self.assertIn("faceVisible = progress >= 0.5f", expression)
        self.assertIn('CreateLimb("Tail_Back"', limbs)
        self.assertIn("ApplyBackTail", limbs)
        for state in {"relax_sofa", "warm_kotatsu", "watch_tv", "meditate_lamp"}:
            self.assertIn(f'case "{state}"', limbs)

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
        self.assertIn("if not self._unity_requested:", source)
        self.assertIn('_fallback_to_legacy_renderer("start_failed"', source)

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

    def test_unity_chase_and_face_gaze_use_dpi_aware_desktop_coordinates(self):
        monitor = (ROOT / "emojinoko_monitor.py").read_text(encoding="utf-8")
        bootstrap = (SCRIPTS / "TokenPetPocBootstrap.cs").read_text(encoding="utf-8")
        ipc = (SCRIPTS / "TokenPetIpcClient.cs").read_text(encoding="utf-8")
        self.assertIn("def _get_pet_desktop_position", monitor)
        self.assertIn("def _get_pointer_desktop_position", monitor)
        self.assertIn('event_name == "cursor_position"', monitor)
        self.assertIn('event_name = "cursor_position"', bootstrap)
        self.assertIn("PublishCursorPosition();", bootstrap)
        self.assertIn("public int screen_width", ipc)
        self.assertIn("public float dpi", ipc)
        self.assertNotIn("random.random() < 0.00025", monitor)

    def test_status_hud_fits_text_inside_card_at_every_windows_scale(self):
        hud = (SCRIPTS / "TokenPetStatusHud.cs").read_text(encoding="utf-8")
        monitor = (ROOT / "emojinoko_monitor.py").read_text(encoding="utf-8")
        bridge = (ROOT / "unity_renderer_bridge.py").read_text(encoding="utf-8")
        ipc = (SCRIPTS / "TokenPetIpcClient.cs").read_text(encoding="utf-8")
        self.assertIn("DrawFittedLabel", hud)
        self.assertIn("style.CalcSize(content)", hud)
        self.assertIn("TextClipping.Clip", hud)
        self.assertIn("cardX = Mathf.Clamp", hud)
        self.assertIn("cardY = Mathf.Clamp", hud)
        self.assertIn("tokenTotal", hud)
        self.assertIn('"TOKENS"', hud)
        self.assertIn("prompt_tokens=self.monthly_prompt_tokens", monitor)
        self.assertIn('"prompt_tokens": max(0, int(prompt_tokens))', bridge)
        self.assertIn("public long prompt_tokens", ipc)

    def test_basketball_game_is_rendered_inside_unity_desktop_stage(self):
        monitor = (ROOT / "emojinoko_monitor.py").read_text(encoding="utf-8")
        bridge = (ROOT / "unity_renderer_bridge.py").read_text(encoding="utf-8")
        bootstrap = (SCRIPTS / "TokenPetPocBootstrap.cs").read_text(encoding="utf-8")
        basketball = (SCRIPTS / "TokenPetBasketballGame.cs").read_text(
            encoding="utf-8"
        )
        self.assertIn("class UnityBasketballHoop", monitor)
        self.assertIn("bridge.show_basketball", monitor)
        self.assertIn('"command": "show_basketball"', bridge)
        self.assertIn('case "show_basketball"', bootstrap)
        self.assertIn("basketballGame.HandlePointer()", bootstrap)
        self.assertIn("class TokenPetBasketballGame", basketball)
        self.assertIn('event_name = "basketball_moved"', basketball)
        self.assertIn('event_name = "basketball_closed"', basketball)
        self.assertIn("IsDragHandle", basketball)
        self.assertIn('self.pet_data["basketball_position"]', monitor)
        self.assertIn('monitor.pet_data.get("basketball_position", {})', monitor)
        self.assertIn("ComputeThrowVelocity", bootstrap)
        self.assertIn("throwSamplePositions", bootstrap)

    def test_unity_context_menu_keeps_the_complete_legacy_feature_set(self):
        monitor = (ROOT / "emojinoko_monitor.py").read_text(encoding="utf-8")
        start = monitor.index("    def _show_unity_action_menu")
        end = monitor.index("    def _show_deleted_memos_menu", start)
        menu = monitor[start:end]
        for callback in {
            "self.open_ai_chat",
            "self.simulate_usage",
            "self.show_current_cost",
            "self.open_detailed_stats",
            "self._toggle_unity_status_hud",
            "self.buy_coffee",
            "self.play_rps",
            "self.toggle_basketball_game",
            "self.toggle_fruit_catcher",
            "self.toggle_slot_machine",
            "self._open_unity_shop_from_menu",
            "self.add_new_memo",
            "self._show_deleted_memos_menu",
            "self.open_hotkey_settings",
            "self.trigger_manual_update_check",
            "self.manual_refresh",
            "self._logout",
            "self.root.destroy",
        }:
            with self.subTest(callback=callback):
                self.assertIn(callback, menu)

        # Cost and detailed statistics must remain visible in the local Unity
        # preview too; account-only refresh/logout stay mode-dependent.
        mode_gate = menu.index("if not self.STANDALONE:")
        self.assertLess(menu.index("self.show_current_cost"), mode_gate)
        self.assertLess(menu.index("self.open_detailed_stats"), mode_gate)
        self.assertLess(menu.index("self.trigger_manual_update_check"), menu.index("self.buy_coffee"))

    def test_face_textures_do_not_change_mip_level_across_windows_dpi(self):
        resources = ROOT / "unity_poc" / "Assets" / "TokenPet" / "Resources"
        metas = list((resources / "FaceExpressions").glob("*.png.meta"))
        metas.extend([
            resources / "tokenpet_body_round_clean_faceless.png.meta",
            resources / "tokenpet_body_round_faceless.png.meta",
        ])
        self.assertGreaterEqual(len(metas), 13)
        for meta in metas:
            with self.subTest(texture=meta.name):
                source = meta.read_text(encoding="utf-8")
                self.assertIn("enableMipMap: 0", source)
                self.assertNotIn("textureCompression: 1", source)

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
