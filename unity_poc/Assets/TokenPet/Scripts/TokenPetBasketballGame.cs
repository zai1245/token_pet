using UnityEngine;

namespace TokenPet
{
    /// <summary>
    /// Unity-stage version of the legacy desktop basketball hoop. Python keeps
    /// the pet physics and scoring authority; this component owns the visible,
    /// draggable hoop so it cannot disappear behind the full-desktop player.
    /// </summary>
    public sealed class TokenPetBasketballGame : MonoBehaviour
    {
        private static readonly Color32 Board = new(24, 24, 37, 255);
        private static readonly Color32 Blue = new(137, 180, 250, 255);
        private static readonly Color32 Pink = new(243, 139, 168, 255);
        private static readonly Color32 Net = new(205, 214, 244, 255);
        private static readonly Color32 Green = new(166, 227, 161, 255);

        private TokenPetIpcClient ipc;
        private TokenPetWindowsOverlay overlay;
        private Texture2D boardTexture;
        private Texture2D blueTexture;
        private Texture2D pinkTexture;
        private Texture2D netTexture;
        private GUIStyle scoreStyle;
        private GUIStyle closeStyle;
        private bool visible;
        private bool dragging;
        private Vector2Int dragOffset;
        private Vector2Int desktopPosition;
        private int score;
        private float netKick;

        public bool IsVisible => visible;

        public void Initialize(TokenPetIpcClient client, TokenPetWindowsOverlay windowsOverlay)
        {
            ipc = client;
            overlay = windowsOverlay;
        }

        public void Show(int x, int y)
        {
            desktopPosition = ClampPosition(new Vector2Int(x, y));
            score = 0;
            netKick = 0f;
            visible = true;
        }

        public void Hide()
        {
            visible = false;
            dragging = false;
        }

        public void TriggerGoal()
        {
            if (!visible)
                return;
            score++;
            netKick = 18f;
        }

        public bool HitTestDesktop(Vector2Int cursor)
        {
            if (!visible)
                return false;
            return dragging || IsCloseButton(cursor) || IsDragHandle(cursor);
        }

        private void Awake()
        {
            boardTexture = MakeTexture(Board);
            blueTexture = MakeTexture(Blue);
            pinkTexture = MakeTexture(Pink);
            netTexture = MakeTexture(Net);
        }

        private void Update()
        {
            if (!visible || overlay == null || !overlay.IsDesktopStage)
                return;

            if (netKick > 0.05f)
                netKick = Mathf.Lerp(netKick, 0f, Time.unscaledDeltaTime * 8f);
            else
                netKick = 0f;
        }

        public bool HandlePointer()
        {
            if (!visible || overlay == null || !overlay.IsDesktopStage)
                return false;

            Vector2Int cursor = overlay.GetCursorPosition();
            if (Input.GetMouseButtonDown(0))
            {
                if (IsCloseButton(cursor))
                {
                    Hide();
                    ipc?.Send(new RendererEvent { event_name = "basketball_closed" });
                    return true;
                }
                if (IsDragHandle(cursor))
                {
                    dragging = true;
                    dragOffset = cursor - desktopPosition;
                    return true;
                }
            }

            if (dragging && Input.GetMouseButton(0))
                desktopPosition = ClampPosition(cursor - dragOffset);

            if (dragging && Input.GetMouseButtonUp(0))
            {
                dragging = false;
                ipc?.Send(new RendererEvent
                {
                    event_name = "basketball_moved",
                    x = desktopPosition.x,
                    y = desktopPosition.y
                });
                return true;
            }
            if (dragging)
                return true;
            if (Input.GetMouseButtonDown(1) && HitTestDesktop(cursor))
                return true;
            return false;
        }

        private bool IsCloseButton(Vector2Int cursor)
        {
            return new RectInt(
                desktopPosition.x + 242,
                desktopPosition.y + 14,
                38,
                38).Contains(cursor);
        }

        private bool IsDragHandle(Vector2Int cursor)
        {
            // Every visible part of the hoop is a drag handle. Keep these as
            // separate silhouettes instead of one 300x300 rectangle so the
            // transparent area stays click-through and never steals a pet throw.
            RectInt scoreBoard = new(
                desktopPosition.x + 42,
                desktopPosition.y + 12,
                198,
                58);
            RectInt backboardAndPost = new(
                desktopPosition.x + 192,
                desktopPosition.y + 34,
                49,
                152);
            RectInt rimAndNet = new(
                desktopPosition.x + 70,
                desktopPosition.y + 112,
                139,
                94);
            return scoreBoard.Contains(cursor) ||
                   backboardAndPost.Contains(cursor) ||
                   rimAndNet.Contains(cursor);
        }

        private void OnGUI()
        {
            if (!visible || overlay == null)
                return;
            EnsureStyles();
            float x = desktopPosition.x - overlay.StageOrigin.x;
            float y = desktopPosition.y - overlay.StageOrigin.y;
            float kick = netKick;

            DrawRect(new Rect(x + 220f, y + 40f, 15f, 140f), boardTexture);
            DrawOutline(new Rect(x + 218f, y + 38f, 19f, 144f), blueTexture, 3f);
            DrawRect(new Rect(x + 198f, y + 127f, 24f, 5f), pinkTexture);
            DrawRect(new Rect(x + 80f, y + 123f, 120f, 6f), pinkTexture);
            DrawRect(new Rect(x + 80f, y + 136f, 120f, 4f), pinkTexture);

            DrawLine(new Vector2(x + 82f, y + 139f), new Vector2(x + 110f + kick * 0.35f, y + 195f + kick), netTexture, 2f);
            DrawLine(new Vector2(x + 200f, y + 139f), new Vector2(x + 170f - kick * 0.35f, y + 195f + kick), netTexture, 2f);
            DrawLine(new Vector2(x + 110f, y + 139f), new Vector2(x + 125f + kick * 0.2f, y + 195f + kick), netTexture, 2f);
            DrawLine(new Vector2(x + 140f, y + 139f), new Vector2(x + 140f, y + 195f + kick), netTexture, 2f);
            DrawLine(new Vector2(x + 170f, y + 139f), new Vector2(x + 155f - kick * 0.2f, y + 195f + kick), netTexture, 2f);
            DrawLine(new Vector2(x + 94f, y + 154f + kick * 0.3f), new Vector2(x + 188f, y + 154f + kick * 0.3f), netTexture, 1.5f);
            DrawLine(new Vector2(x + 104f, y + 174f + kick * 0.65f), new Vector2(x + 178f, y + 174f + kick * 0.65f), netTexture, 1.5f);

            GUI.Label(new Rect(x + 54f, y + 16f, 175f, 34f), $"SCORE: {score}", scoreStyle);
            GUI.Label(new Rect(x + 246f, y + 18f, 30f, 30f), "×", closeStyle);
        }

        private Vector2Int ClampPosition(Vector2Int position)
        {
            if (overlay == null)
                return position;
            RectInt work = overlay.GetPetWorkArea();
            int maxX = Mathf.Max(work.x + 8, work.xMax - 308);
            int maxY = Mathf.Max(work.y + 8, work.yMax - 308);
            return new Vector2Int(
                Mathf.Clamp(position.x, work.x + 8, maxX),
                Mathf.Clamp(position.y, work.y + 8, maxY));
        }

        private void EnsureStyles()
        {
            if (scoreStyle != null)
                return;
            scoreStyle = new GUIStyle(GUI.skin.label)
            {
                fontSize = 18,
                fontStyle = FontStyle.Bold,
                alignment = TextAnchor.MiddleCenter,
                clipping = TextClipping.Clip,
                normal = { textColor = Green }
            };
            closeStyle = new GUIStyle(GUI.skin.label)
            {
                fontSize = 22,
                fontStyle = FontStyle.Bold,
                alignment = TextAnchor.MiddleCenter,
                normal = { textColor = Pink }
            };
        }

        private static void DrawOutline(Rect rect, Texture2D texture, float thickness)
        {
            GUI.DrawTexture(new Rect(rect.x, rect.y, rect.width, thickness), texture);
            GUI.DrawTexture(new Rect(rect.x, rect.yMax - thickness, rect.width, thickness), texture);
            GUI.DrawTexture(new Rect(rect.x, rect.y, thickness, rect.height), texture);
            GUI.DrawTexture(new Rect(rect.xMax - thickness, rect.y, thickness, rect.height), texture);
        }

        private static void DrawRect(Rect rect, Texture2D texture)
        {
            GUI.DrawTexture(rect, texture);
        }

        private static void DrawLine(Vector2 start, Vector2 end, Texture2D texture, float width)
        {
            Matrix4x4 original = GUI.matrix;
            Vector2 delta = end - start;
            float angle = Mathf.Atan2(delta.y, delta.x) * Mathf.Rad2Deg;
            GUIUtility.RotateAroundPivot(angle, start);
            GUI.DrawTexture(new Rect(start.x, start.y - width * 0.5f, delta.magnitude, width), texture);
            GUI.matrix = original;
        }

        private static Texture2D MakeTexture(Color32 color)
        {
            Texture2D texture = new(1, 1, TextureFormat.RGBA32, false)
            {
                filterMode = FilterMode.Point,
                wrapMode = TextureWrapMode.Clamp,
                hideFlags = HideFlags.HideAndDontSave
            };
            texture.SetPixel(0, 0, color);
            texture.Apply(false, true);
            return texture;
        }

        private void OnDestroy()
        {
            if (boardTexture != null) Destroy(boardTexture);
            if (blueTexture != null) Destroy(blueTexture);
            if (pinkTexture != null) Destroy(pinkTexture);
            if (netTexture != null) Destroy(netTexture);
        }
    }
}
