using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;

namespace TokenPet
{
    [Serializable]
    public sealed class TokenPetShopItem
    {
        public string id;
        public string name;
        public string description;
        public string category;
        public int price;
    }

    [Serializable]
    public sealed class TokenPetShopPayload
    {
        public int coins;
        public string equipped;
        public string[] equipped_items;
        public string[] owned;
        public string[] owned_furniture;
        public string[] spawned_furniture;
        public TokenPetShopItem[] items;
    }

    /// <summary>
    /// Compact data-driven shop drawn with IMGUI. This deliberately avoids a
    /// uGUI Canvas: Unity's stencil/UI material path is unreliable inside the
    /// chroma-key layered desktop window used by this PoC.
    /// </summary>
    public sealed class TokenPetShopPanel : MonoBehaviour
    {
        private static readonly Color Ink = new Color32(79, 42, 20, 255);
        private static readonly Color Cream = new Color32(255, 244, 210, 255);
        private static readonly Color Header = new Color32(246, 185, 66, 255);
        private static readonly Color Card = new Color32(255, 249, 231, 255);
        private static readonly Color CardAlt = new Color32(250, 235, 199, 255);
        private static readonly Color Accent = new Color32(242, 154, 62, 255);
        private static readonly Color Green = new Color32(130, 184, 102, 255);
        private static readonly Color Pink = new Color32(238, 139, 143, 255);

        private TokenPetIpcClient ipc;
        private GameObject petRoot;
        private TokenPetStatusHud statusHud;
        private TokenPetWindowsOverlay overlay;
        private Camera petCamera;
        private Vector3 compactCameraPosition;
        private Coroutine layoutRoutine;
        private TokenPetShopPayload payload;
        private Font font;
        private GUIStyle titleStyle;
        private GUIStyle coinsStyle;
        private GUIStyle tabStyle;
        private GUIStyle nameStyle;
        private GUIStyle descriptionStyle;
        private GUIStyle actionStyle;
        private GUIStyle pageStyle;
        private string category = "accessory";
        private int pageIndex;
        private bool isVisible;
        private bool previousStatusVisible = true;

        public bool IsVisible => isVisible;

        public bool HitTestDesktop(Vector2Int cursor)
        {
            if (!isVisible || overlay == null)
                return false;
            if (!overlay.IsDesktopStage)
                return true;
            Vector2 origin = DesktopGroupOrigin();
            Rect panel = new(
                overlay.StageOrigin.x + origin.x + 340f,
                overlay.StageOrigin.y + origin.y,
                380f, 300f);
            return panel.Contains(cursor);
        }

        public void Initialize(TokenPetIpcClient client, GameObject characterRoot,
            TokenPetStatusHud hud, TokenPetWindowsOverlay windowsOverlay, Camera camera)
        {
            ipc = client;
            petRoot = characterRoot;
            statusHud = hud;
            overlay = windowsOverlay;
            petCamera = camera;
            compactCameraPosition = camera != null ? camera.transform.position : Vector3.zero;
            font = Font.CreateDynamicFontFromOSFont(
                new[] { "Microsoft JhengHei UI", "Microsoft JhengHei", "Segoe UI", "Arial" },
                16);
        }

        public void Show(string json)
        {
            if (string.IsNullOrWhiteSpace(json))
                return;
            Debug.Log($"TokenPet shop command received ({json.Length} chars).");
            try
            {
                payload = JsonUtility.FromJson<TokenPetShopPayload>(json);
            }
            catch (Exception exception)
            {
                Debug.LogWarning($"Unable to parse shop payload: {exception.Message}");
                return;
            }
            if (payload == null)
                return;

            if (!isVisible)
            {
                previousStatusVisible = statusHud == null || statusHud.IsVisible;
                statusHud?.SetVisible(false);
                overlay?.SetShopExpanded(true);
                if (layoutRoutine != null)
                    StopCoroutine(layoutRoutine);
                layoutRoutine = StartCoroutine(ApplyExpandedCameraAfterResize());
            }
            isVisible = true;
            ClampPage();
            Debug.Log($"TokenPet IMGUI shop visible with {payload.items?.Length ?? 0} catalog items.");
        }

        public void Hide(bool notifyPython = true)
        {
            if (!isVisible)
                return;
            isVisible = false;
            if (layoutRoutine != null)
            {
                StopCoroutine(layoutRoutine);
                layoutRoutine = null;
            }
            if (petCamera != null && (overlay == null || !overlay.IsDesktopStage))
                petCamera.transform.position = compactCameraPosition;
            overlay?.SetShopExpanded(false);
            if (previousStatusVisible)
                statusHud?.SetVisible(true);
            if (notifyPython)
                ipc?.Send(new RendererEvent { event_name = "shop_closed" });
        }

        private IEnumerator ApplyExpandedCameraAfterResize()
        {
            yield return null;
            yield return null;
            if (overlay != null && overlay.IsDesktopStage)
            {
                layoutRoutine = null;
                yield break;
            }
            if (petCamera != null && petRoot != null && isVisible)
            {
                float worldWidth = petCamera.orthographicSize * 2f * petCamera.aspect;
                float desiredNormalizedX = 170f / Mathf.Max(1f, Screen.width);
                Vector3 position = compactCameraPosition;
                position.x = petRoot.transform.position.x -
                    (desiredNormalizedX - 0.5f) * worldWidth;
                petCamera.transform.position = position;
            }
            layoutRoutine = null;
        }

        private void OnGUI()
        {
            if (!isVisible || payload == null)
                return;
            // Wait until Win32 has applied the expanded surface. Drawing the
            // 720px drawer into the old 340px frame would briefly cover the pet.
            bool desktopStage = overlay != null && overlay.IsDesktopStage;
            if (!desktopStage && Screen.width < 600)
                return;
            EnsureStyles();

            Matrix4x4 previousMatrix = GUI.matrix;
            Color previousColor = GUI.color;
            Color previousBackground = GUI.backgroundColor;
            if (desktopStage)
            {
                Vector2 origin = DesktopGroupOrigin();
                GUI.BeginGroup(new Rect(origin.x, origin.y, 720f, 300f));
                GUI.matrix = Matrix4x4.identity;
            }
            else
            {
                GUI.matrix = Matrix4x4.Scale(new Vector3(
                    Screen.width / 720f,
                    Screen.height / 300f,
                    1f));
            }

            const float panelX = 340f;
            Fill(new Rect(panelX, 0f, 380f, 300f), new Color32(123, 67, 30, 255));
            Fill(new Rect(panelX + 3f, 3f, 374f, 294f), Cream);
            Fill(new Rect(panelX + 3f, 3f, 374f, 42f), Header);

            string title = category switch
            {
                "food" => "地瓜球食堂",
                "furniture" => "地瓜球家具屋",
                _ => "地瓜球配件舖"
            };
            GUI.Label(new Rect(353f, 8f, 184f, 27f), title, titleStyle);
            GUI.Label(new Rect(541f, 10f, 128f, 23f),
                $"{Mathf.Max(0, payload.coins)} COINS", coinsStyle);

            bool closeRequested = DrawButton(
                new Rect(680f, 7f, 30f, 28f), "×", Pink, actionStyle);

            Fill(new Rect(348f, 49f, 364f, 29f), CardAlt);
            if (DrawButton(new Rect(351f, 52f, 113f, 23f), "配件", Card, tabStyle))
                SelectCategory("accessory");
            if (DrawButton(new Rect(472f, 52f, 113f, 23f), "食物", Card, tabStyle))
                SelectCategory("food");
            if (DrawButton(new Rect(593f, 52f, 113f, 23f), "家具", Card, tabStyle))
                SelectCategory("furniture");

            List<TokenPetShopItem> visible = VisibleItems();
            const int pageSize = 3;
            const float rowHeight = 56f;
            int pageCount = Mathf.Max(1, Mathf.CeilToInt(visible.Count / (float)pageSize));
            pageIndex = Mathf.Clamp(pageIndex, 0, pageCount - 1);
            int first = pageIndex * pageSize;
            int last = Mathf.Min(visible.Count, first + pageSize);
            for (int itemIndex = first; itemIndex < last; itemIndex++)
            {
                int rowIndex = itemIndex - first;
                DrawRow(visible[itemIndex], rowIndex, 82f + rowIndex * rowHeight);
            }

            Fill(new Rect(348f, 258f, 364f, 29f), CardAlt);
            GUI.enabled = pageIndex > 0;
            if (DrawButton(new Rect(351f, 261f, 88f, 23f), "‹ 上頁", Card, tabStyle))
                pageIndex--;
            GUI.enabled = true;
            GUI.Label(new Rect(450f, 261f, 160f, 23f),
                $"{pageIndex + 1} / {pageCount}", pageStyle);
            GUI.enabled = pageIndex + 1 < pageCount;
            if (DrawButton(new Rect(621f, 261f, 88f, 23f), "下頁 ›", Card, tabStyle))
                pageIndex++;
            GUI.enabled = true;

            GUI.matrix = previousMatrix;
            GUI.color = previousColor;
            GUI.backgroundColor = previousBackground;
            if (desktopStage)
                GUI.EndGroup();
            if (closeRequested)
                Hide();
        }

        private Vector2 DesktopGroupOrigin()
        {
            float petLeft = overlay.PetPosition.x - overlay.StageOrigin.x;
            float petTop = overlay.PetPosition.y - overlay.StageOrigin.y;
            float panelLeft = petLeft + 340f;
            if (panelLeft + 380f > overlay.StageSize.x)
                panelLeft = petLeft - 380f;
            panelLeft = Mathf.Clamp(panelLeft, 0f, Mathf.Max(0f, overlay.StageSize.x - 380f));
            float panelTop = Mathf.Clamp(petTop, 0f,
                Mathf.Max(0f, overlay.StageSize.y - 300f));
            return new Vector2(panelLeft - 340f, panelTop);
        }

        private void DrawRow(TokenPetShopItem item, int rowIndex, float top)
        {
            Fill(new Rect(348f, top, 364f, 53f), rowIndex % 2 == 0 ? Card : CardAlt);
            GUI.Label(new Rect(356f, top + 2f, 246f, 22f),
                item.name ?? item.id, nameStyle);
            GUI.Label(new Rect(356f, top + 23f, 246f, 27f),
                item.description ?? "", descriptionStyle);
            if (DrawButton(new Rect(610f, top + 9f, 94f, 35f),
                    ActionLabel(item), ActionColor(item), actionStyle))
            {
                ipc?.Send(new RendererEvent
                {
                    event_name = "shop_action",
                    action = "activate",
                    item = item.id
                });
            }
        }

        private void SelectCategory(string next)
        {
            if (category == next)
                return;
            category = next;
            pageIndex = 0;
        }

        private List<TokenPetShopItem> VisibleItems()
        {
            List<TokenPetShopItem> result = new();
            foreach (TokenPetShopItem item in payload.items ?? Array.Empty<TokenPetShopItem>())
            {
                string itemCategory = string.IsNullOrEmpty(item.category)
                    ? "accessory" : item.category;
                if (itemCategory == category)
                    result.Add(item);
            }
            return result;
        }

        private void ClampPage()
        {
            int count = VisibleItems().Count;
            int pages = Mathf.Max(1, Mathf.CeilToInt(count / 3f));
            pageIndex = Mathf.Clamp(pageIndex, 0, pages - 1);
        }

        private string ActionLabel(TokenPetShopItem item)
        {
            if (item.category == "food")
                return $"買 {item.price}";
            if (item.category == "furniture")
            {
                if (Contains(payload.owned_furniture, item.id))
                    return Contains(payload.spawned_furniture, item.id) ? "收回" : "召喚";
                return $"買 {item.price}";
            }
            if (Contains(payload.equipped_items, item.id) || payload.equipped == item.id)
                return "卸下";
            return Contains(payload.owned, item.id) ? "裝備" : $"買 {item.price}";
        }

        private Color ActionColor(TokenPetShopItem item)
        {
            if (Contains(payload.equipped_items, item.id) || payload.equipped == item.id)
                return Pink;
            if (item.category == "furniture" && Contains(payload.owned_furniture, item.id))
                return new Color32(159, 181, 232, 255);
            return item.category == "food" ? Accent : Green;
        }

        private static bool Contains(string[] values, string expected)
        {
            if (values == null)
                return false;
            foreach (string value in values)
                if (string.Equals(value, expected, StringComparison.OrdinalIgnoreCase))
                    return true;
            return false;
        }

        private void EnsureStyles()
        {
            if (titleStyle != null)
                return;
            titleStyle = MakeStyle(17, FontStyle.Bold, TextAnchor.MiddleLeft, Ink);
            coinsStyle = MakeStyle(12, FontStyle.Bold, TextAnchor.MiddleRight, Ink);
            tabStyle = MakeStyle(12, FontStyle.Bold, TextAnchor.MiddleCenter, Ink);
            nameStyle = MakeStyle(12, FontStyle.Bold, TextAnchor.MiddleLeft, Ink);
            nameStyle.clipping = TextClipping.Clip;
            descriptionStyle = MakeStyle(10, FontStyle.Normal, TextAnchor.UpperLeft,
                new Color32(115, 79, 50, 255));
            descriptionStyle.wordWrap = true;
            descriptionStyle.clipping = TextClipping.Clip;
            actionStyle = MakeStyle(11, FontStyle.Bold, TextAnchor.MiddleCenter, Ink);
            pageStyle = MakeStyle(11, FontStyle.Bold, TextAnchor.MiddleCenter, Ink);
        }

        private GUIStyle MakeStyle(int size, FontStyle style, TextAnchor alignment, Color color)
        {
            GUIStyle result = new(GUI.skin.label)
            {
                font = font,
                fontSize = size,
                fontStyle = style,
                alignment = alignment
            };
            result.normal.textColor = color;
            return result;
        }

        private static bool DrawButton(Rect rect, string label, Color background, GUIStyle style)
        {
            Fill(rect, background);
            return GUI.Button(rect, label, style);
        }

        private static void Fill(Rect rect, Color color)
        {
            Color previous = GUI.color;
            GUI.color = color;
            GUI.DrawTexture(rect, Texture2D.whiteTexture);
            GUI.color = previous;
        }
    }
}
