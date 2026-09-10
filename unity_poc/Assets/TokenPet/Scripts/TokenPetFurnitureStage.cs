using System;
using System.Collections.Generic;
using UnityEngine;

namespace TokenPet
{
    [Serializable]
    public sealed class TokenPetFurnitureItem
    {
        public string id;
        public float x;
        public float y;
        public float width;
        public float height;
    }

    [Serializable]
    public sealed class TokenPetFurniturePayload
    {
        public TokenPetFurnitureItem[] items;
    }

    /// <summary>
    /// Unity-owned desktop furniture. Python retains save/economy/behaviour state,
    /// while this component owns visuals, hit testing and furniture dragging.
    /// </summary>
    public sealed class TokenPetFurnitureStage : MonoBehaviour
    {
        private sealed class FurnitureView
        {
            public TokenPetFurnitureItem data;
            public Transform root;
            public float bounce;
            public float bounceVelocity;
        }

        private const float WorldUnitsPerPixel = 2.20f / 104f;
        private static readonly Color Ink = new Color32(67, 39, 26, 255);
        private static readonly Color Cream = new Color32(255, 244, 210, 255);
        private static readonly Color Orange = new Color32(242, 154, 62, 255);
        private static readonly Color Pink = new Color32(238, 139, 143, 255);
        private static readonly Color Green = new Color32(130, 184, 102, 255);
        private static readonly Color Blue = new Color32(126, 181, 226, 255);
        private static readonly Color Wood = new Color32(140, 98, 57, 255);

        private readonly Dictionary<string, FurnitureView> views = new();
        private TokenPetIpcClient ipc;
        private TokenPetWindowsOverlay overlay;
        private Camera targetCamera;
        private string draggingId;
        private Vector2Int dragCursorStart;
        private Vector2 dragItemStart;
        private string contextId;
        private Vector2Int contextDesktop;
        private Font font;
        private GUIStyle contextStyle;
        private GUIStyle buttonStyle;

        public bool IsDragging => !string.IsNullOrEmpty(draggingId);

        public void Initialize(TokenPetIpcClient client, TokenPetWindowsOverlay windowsOverlay,
            Camera camera)
        {
            ipc = client;
            overlay = windowsOverlay;
            targetCamera = camera;
        }

        public void Sync(string json)
        {
            if (string.IsNullOrWhiteSpace(json))
                return;
            TokenPetFurniturePayload payload;
            try
            {
                payload = JsonUtility.FromJson<TokenPetFurniturePayload>(json);
            }
            catch (Exception exception)
            {
                Debug.LogWarning($"Unable to parse furniture payload: {exception.Message}");
                return;
            }

            HashSet<string> incoming = new(StringComparer.OrdinalIgnoreCase);
            foreach (TokenPetFurnitureItem item in payload?.items ?? Array.Empty<TokenPetFurnitureItem>())
            {
                if (string.IsNullOrWhiteSpace(item.id))
                    continue;
                incoming.Add(item.id);
                if (!views.TryGetValue(item.id, out FurnitureView view))
                {
                    view = CreateView(item);
                    views[item.id] = view;
                }
                view.data.x = item.x;
                view.data.y = item.y;
                view.data.width = Mathf.Max(40f, item.width);
                view.data.height = Mathf.Max(30f, item.height);
                PositionView(view);
            }

            List<string> removed = new();
            foreach (string id in views.Keys)
                if (!incoming.Contains(id))
                    removed.Add(id);
            foreach (string id in removed)
            {
                if (views.TryGetValue(id, out FurnitureView view) && view.root != null)
                    Destroy(view.root.gameObject);
                views.Remove(id);
                if (contextId == id)
                    contextId = null;
            }
        }

        public void Trigger(string id, string action)
        {
            if (string.Equals(action, "bounce", StringComparison.OrdinalIgnoreCase) &&
                views.TryGetValue(id ?? "", out FurnitureView view))
            {
                view.bounceVelocity += 4.5f;
            }
        }

        public void RefreshLayout()
        {
            foreach (FurnitureView view in views.Values)
                PositionView(view);
        }

        public bool HitTestDesktop(Vector2Int cursor)
        {
            if (!string.IsNullOrEmpty(contextId) && ContextRectDesktop().Contains(cursor))
                return true;
            return FindAt(cursor) != null;
        }

        public bool HandlePointer()
        {
            if (overlay == null || !overlay.IsDesktopStage)
                return false;

            Vector2Int cursor = overlay.GetCursorPosition();
            FurnitureView hovered = FindAt(cursor);

            if (Input.GetMouseButtonDown(1) && hovered != null)
            {
                contextId = hovered.data.id;
                contextDesktop = cursor;
                return true;
            }

            if (Input.GetMouseButtonDown(0))
            {
                if (!string.IsNullOrEmpty(contextId) && ContextRectDesktop().Contains(cursor))
                    return true;
                contextId = null;
                if (hovered != null)
                {
                    draggingId = hovered.data.id;
                    dragCursorStart = cursor;
                    dragItemStart = new Vector2(hovered.data.x, hovered.data.y);
                    return true;
                }
            }

            if (!string.IsNullOrEmpty(draggingId) && views.TryGetValue(draggingId, out FurnitureView drag))
            {
                Vector2Int delta = cursor - dragCursorStart;
                drag.data.x = Mathf.Clamp(dragItemStart.x + delta.x,
                    overlay.StageOrigin.x,
                    overlay.StageOrigin.x + overlay.StageSize.x - drag.data.width);
                drag.data.y = Mathf.Clamp(dragItemStart.y + delta.y,
                    overlay.StageOrigin.y,
                    overlay.StageOrigin.y + overlay.StageSize.y - drag.data.height);
                PositionView(drag);
                if (Input.GetMouseButtonUp(0))
                {
                    ipc?.Send(new RendererEvent
                    {
                        event_name = "furniture_moved",
                        item = drag.data.id,
                        x = Mathf.RoundToInt(drag.data.x),
                        y = Mathf.RoundToInt(drag.data.y)
                    });
                    draggingId = null;
                }
                return true;
            }

            return hovered != null ||
                (!string.IsNullOrEmpty(contextId) && ContextRectDesktop().Contains(cursor));
        }

        private void Update()
        {
            float delta = Time.unscaledDeltaTime;
            foreach (FurnitureView view in views.Values)
            {
                if (Mathf.Abs(view.bounce) < 0.001f && Mathf.Abs(view.bounceVelocity) < 0.001f)
                    continue;
                view.bounceVelocity += (-18f * view.bounce - 6f * view.bounceVelocity) * delta;
                view.bounce += view.bounceVelocity * delta;
                float compression = Mathf.Clamp(view.bounce * 0.035f, -0.18f, 0.24f);
                view.root.localScale = new Vector3(1f + compression * 0.35f, 1f - compression, 1f);
                if (Mathf.Abs(view.bounce) < 0.01f && Mathf.Abs(view.bounceVelocity) < 0.01f)
                {
                    view.bounce = 0f;
                    view.bounceVelocity = 0f;
                    view.root.localScale = Vector3.one;
                }
            }
        }

        private void OnGUI()
        {
            if (string.IsNullOrEmpty(contextId) || overlay == null || !overlay.IsDesktopStage)
                return;
            EnsureStyles();
            Rect desktop = ContextRectDesktop();
            Rect local = new(
                desktop.x - overlay.StageOrigin.x,
                desktop.y - overlay.StageOrigin.y,
                desktop.width, desktop.height);
            Color previous = GUI.color;
            GUI.color = Ink;
            GUI.DrawTexture(local, Texture2D.whiteTexture);
            GUI.color = Cream;
            GUI.DrawTexture(new Rect(local.x + 2f, local.y + 2f,
                local.width - 4f, local.height - 4f), Texture2D.whiteTexture);
            GUI.color = previous;
            GUI.Label(new Rect(local.x + 10f, local.y + 5f, 132f, 22f),
                "家具選項", contextStyle);
            if (GUI.Button(new Rect(local.x + 8f, local.y + 29f, 144f, 28f),
                "收回這件家具", buttonStyle))
            {
                ipc?.Send(new RendererEvent
                {
                    event_name = "furniture_despawn",
                    item = contextId,
                    action = "despawn"
                });
                contextId = null;
            }
        }

        private FurnitureView FindAt(Vector2Int cursor)
        {
            FurnitureView result = null;
            foreach (FurnitureView view in views.Values)
            {
                Rect rect = new(view.data.x, view.data.y, view.data.width, view.data.height);
                if (rect.Contains(cursor))
                    result = view;
            }
            return result;
        }

        private Rect ContextRectDesktop()
        {
            float x = Mathf.Clamp(contextDesktop.x,
                overlay.StageOrigin.x,
                overlay.StageOrigin.x + overlay.StageSize.x - 160f);
            float y = Mathf.Clamp(contextDesktop.y,
                overlay.StageOrigin.y,
                overlay.StageOrigin.y + overlay.StageSize.y - 64f);
            return new Rect(x, y, 160f, 64f);
        }

        private FurnitureView CreateView(TokenPetFurnitureItem item)
        {
            GameObject rootObject = new($"Furniture_{item.id}");
            FurnitureView view = new()
            {
                data = new TokenPetFurnitureItem
                {
                    id = item.id,
                    x = item.x,
                    y = item.y,
                    width = Mathf.Max(40f, item.width),
                    height = Mathf.Max(30f, item.height)
                },
                root = rootObject.transform
            };
            BuildArt(view.root, item.id, view.data.width, view.data.height);
            PositionView(view);
            return view;
        }

        private void PositionView(FurnitureView view)
        {
            if (targetCamera == null || overlay == null || view.root == null)
                return;
            Vector2 center = new(
                view.data.x + view.data.width * 0.5f,
                view.data.y + view.data.height * 0.5f);
            view.root.position = overlay.DesktopToWorld(center, targetCamera);
        }

        private static Vector2 Px(float x, float y) =>
            new(x * WorldUnitsPerPixel, y * WorldUnitsPerPixel);

        private static void BuildArt(Transform root, string id, float widthPixels, float heightPixels)
        {
            if (TryBuildPaintedArt(root, id, widthPixels, heightPixels))
                return;

            // Procedural furniture remains as an offline/missing-asset fallback.
            switch ((id ?? "").ToLowerInvariant())
            {
                case "futon":
                    TokenPetProceduralArt.Outlined(root, "Mat", TokenPetShape.Square,
                        Px(0, -10), Px(150, 45), new Color32(236, 211, 218, 255), Ink, 3, 0f, 1.05f);
                    TokenPetProceduralArt.Outlined(root, "Blanket", TokenPetShape.Square,
                        Px(18, 1), Px(82, 34), Pink, Ink, 5, -2f, 1.05f);
                    TokenPetProceduralArt.Outlined(root, "Pillow", TokenPetShape.Circle,
                        Px(-50, 5), Px(38, 24), Cream, Ink, 7, 0f, 1.08f);
                    break;
                case "laptop":
                    TokenPetProceduralArt.Outlined(root, "Screen", TokenPetShape.Square,
                        Px(0, 12), Px(92, 58), new Color32(60, 64, 82, 255), Ink, 4, 0f, 1.07f);
                    TokenPetProceduralArt.Shape(root, "Glow", TokenPetShape.Square,
                        Px(0, 12), Px(78, 44), Blue, 6);
                    TokenPetProceduralArt.Outlined(root, "Keyboard", TokenPetShape.Square,
                        Px(0, -27), Px(124, 22), new Color32(184, 188, 205, 255), Ink, 7, -4f, 1.06f);
                    break;
                case "trampoline":
                    TokenPetProceduralArt.Line(root, "LeftLeg", Px(-48, -6), Px(-58, -25),
                        Px(5, 0).x, Ink, 3);
                    TokenPetProceduralArt.Line(root, "RightLeg", Px(48, -6), Px(58, -25),
                        Px(5, 0).x, Ink, 3);
                    TokenPetProceduralArt.Outlined(root, "Bed", TokenPetShape.Circle,
                        Px(0, 6), Px(118, 25), Pink, Ink, 6, 0f, 1.10f);
                    TokenPetProceduralArt.Shape(root, "BedGlow", TokenPetShape.Circle,
                        Px(0, 8), Px(94, 11), Blue, 8);
                    break;
                case "night_lamp":
                    TokenPetProceduralArt.Shape(root, "Glow", TokenPetShape.Circle,
                        Px(0, 7), Px(82, 72), new Color32(255, 229, 128, 90), 2);
                    TokenPetProceduralArt.Outlined(root, "Stem", TokenPetShape.Square,
                        Px(0, -20), Px(15, 48), Wood, Ink, 5, 0f, 1.10f);
                    TokenPetProceduralArt.Outlined(root, "Shade", TokenPetShape.Circle,
                        Px(0, 17), Px(75, 45), Pink, Ink, 7, 0f, 1.08f);
                    TokenPetProceduralArt.Shape(root, "Bulb", TokenPetShape.Circle,
                        Px(0, 6), Px(18, 16), Cream, 9);
                    break;
                case "succulent_pot":
                    TokenPetProceduralArt.Outlined(root, "Pot", TokenPetShape.Square,
                        Px(0, -22), Px(48, 38), Cream, Ink, 5, 0f, 1.08f);
                    TokenPetProceduralArt.Outlined(root, "LeafL", TokenPetShape.Circle,
                        Px(-17, 9), Px(24, 40), Green, Ink, 6, -32f, 1.07f);
                    TokenPetProceduralArt.Outlined(root, "LeafR", TokenPetShape.Circle,
                        Px(17, 9), Px(24, 40), Green, Ink, 6, 32f, 1.07f);
                    TokenPetProceduralArt.Outlined(root, "LeafC", TokenPetShape.Circle,
                        Px(0, 15), Px(25, 47), new Color32(148, 226, 213, 255), Ink, 8, 0f, 1.07f);
                    TokenPetProceduralArt.Shape(root, "Flower", TokenPetShape.Star,
                        Px(0, 38), Px(18, 18), Pink, 10);
                    break;
                case "lazy_sofa":
                    TokenPetProceduralArt.Outlined(root, "Back", TokenPetShape.Circle,
                        Px(0, 10), Px(130, 67), new Color32(242, 205, 205, 255), Ink, 3, 0f, 1.06f);
                    TokenPetProceduralArt.Outlined(root, "Seat", TokenPetShape.Circle,
                        Px(0, -15), Px(105, 42), Pink, Ink, 6, 0f, 1.05f);
                    TokenPetProceduralArt.Shape(root, "Flower", TokenPetShape.Star,
                        Px(33, 9), Px(15, 15), Cream, 8);
                    break;
                case "pixel_tv":
                    TokenPetProceduralArt.Outlined(root, "Case", TokenPetShape.Square,
                        Px(0, -1), Px(116, 76), Wood, Ink, 3, 0f, 1.06f);
                    TokenPetProceduralArt.Outlined(root, "Screen", TokenPetShape.Square,
                        Px(-15, 2), Px(70, 50), new Color32(28, 32, 47, 255), Ink, 5, 0f, 1.05f);
                    TokenPetProceduralArt.Shape(root, "Pixel", TokenPetShape.Square,
                        Px(-15, 2), Px(24, 17), Green, 7);
                    TokenPetProceduralArt.Line(root, "AntennaL", Px(-5, 38), Px(-28, 56),
                        Px(3, 0).x, Ink, 7);
                    TokenPetProceduralArt.Line(root, "AntennaR", Px(5, 38), Px(28, 56),
                        Px(3, 0).x, Ink, 7);
                    break;
                case "kotatsu":
                    TokenPetProceduralArt.Outlined(root, "Quilt", TokenPetShape.Square,
                        Px(0, -8), Px(145, 58), new Color32(250, 179, 135, 255), Ink, 3, 0f, 1.05f);
                    TokenPetProceduralArt.Outlined(root, "Top", TokenPetShape.Square,
                        Px(0, 24), Px(112, 14), Wood, Ink, 6, 0f, 1.08f);
                    TokenPetProceduralArt.Shape(root, "Orange", TokenPetShape.Circle,
                        Px(-24, 37), Px(16, 14), Orange, 8);
                    TokenPetProceduralArt.Shape(root, "Tea", TokenPetShape.Square,
                        Px(24, 36), Px(14, 15), Cream, 8);
                    break;
                default:
                    TokenPetProceduralArt.Outlined(root, "Furniture", TokenPetShape.Square,
                        Vector2.zero, Px(90, 55), Orange, Ink, 3, 0f, 1.07f);
                    break;
            }
        }

        private static bool TryBuildPaintedArt(Transform root, string id,
            float widthPixels, float heightPixels)
        {
            string normalized = (id ?? "").Trim().ToLowerInvariant();
            if (string.IsNullOrEmpty(normalized))
                return false;

            Texture2D texture = Resources.Load<Texture2D>($"FurnitureV2/{normalized}");
            if (texture == null)
                return false;

            texture.filterMode = FilterMode.Bilinear;
            texture.wrapMode = TextureWrapMode.Clamp;
            Sprite sprite = Sprite.Create(texture,
                new Rect(0f, 0f, texture.width, texture.height),
                new Vector2(0.5f, 0.5f), 100f, 0u, SpriteMeshType.FullRect);
            sprite.name = $"{normalized}_painted";

            GameObject art = new($"{normalized}_PaintedArt");
            art.transform.SetParent(root, false);
            SpriteRenderer renderer = art.AddComponent<SpriteRenderer>();
            renderer.sprite = sprite;
            renderer.sortingOrder = 3;

            float targetWidth = Mathf.Max(40f, widthPixels) * WorldUnitsPerPixel;
            float targetHeight = Mathf.Max(30f, heightPixels) * WorldUnitsPerPixel;
            float scale = Mathf.Min(
                targetWidth / Mathf.Max(0.01f, sprite.bounds.size.x),
                targetHeight / Mathf.Max(0.01f, sprite.bounds.size.y));
            art.transform.localScale = Vector3.one * scale;
            return true;
        }

        private void EnsureStyles()
        {
            if (contextStyle != null)
                return;
            font = Font.CreateDynamicFontFromOSFont(
                new[] { "Microsoft JhengHei UI", "Microsoft JhengHei", "Segoe UI" }, 14);
            contextStyle = new GUIStyle(GUI.skin.label)
            {
                font = font,
                fontSize = 12,
                fontStyle = FontStyle.Bold,
                alignment = TextAnchor.MiddleLeft
            };
            contextStyle.normal.textColor = Ink;
            buttonStyle = new GUIStyle(GUI.skin.button)
            {
                font = font,
                fontSize = 12,
                fontStyle = FontStyle.Bold,
                alignment = TextAnchor.MiddleCenter
            };
            buttonStyle.normal.textColor = Ink;
            buttonStyle.hover.textColor = Ink;
            buttonStyle.active.textColor = Ink;
        }

        private void OnDestroy()
        {
            if (font != null)
                Destroy(font);
        }
    }
}
