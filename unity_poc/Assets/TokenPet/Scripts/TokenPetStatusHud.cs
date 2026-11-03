using System.Globalization;
using UnityEngine;

namespace TokenPet
{
    /// <summary>A compact monthly USD cost label; Python owns the usage data.</summary>
    public sealed class TokenPetStatusHud : MonoBehaviour
    {
        private static readonly Color32 Outline = new(79, 42, 20, 255);
        private static readonly Color32 Cream = new(255, 244, 210, 255);
        private double costUsd;
        private string usageStatus = "loading";
        private bool isVisible = true;
        private GUIStyle titleLabel;
        private GUIStyle amountLabel;
        private Font uiFont;
        private Texture2D outlineTexture;
        private Texture2D creamTexture;
        private TokenPetWindowsOverlay overlay;

        public bool IsVisible => isVisible;

        public void Initialize(TokenPetWindowsOverlay windowsOverlay)
        {
            overlay = windowsOverlay;
        }

        public void SetUsage(double nextCostUsd, string nextUsageStatus)
        {
            costUsd = double.IsNaN(nextCostUsd) || double.IsInfinity(nextCostUsd)
                ? 0d : System.Math.Max(0d, nextCostUsd);
            usageStatus = nextUsageStatus ?? "loading";
        }

        public void SetVisible(bool visible)
        {
            isVisible = visible;
        }

        private void Awake()
        {
            outlineTexture = MakeTexture(Outline);
            creamTexture = MakeTexture(Cream);
        }

        private void OnGUI()
        {
            if (!isVisible)
                return;
            EnsureStyles();

            const float layoutWidth = 252f;
            const float layoutHeight = 36f;
            float scale = Mathf.Min(Mathf.Clamp(Screen.dpi / 96f, 1f, 2f),
                Mathf.Min((Screen.width - 8f) / layoutWidth, (Screen.height - 8f) / layoutHeight));
            float cardWidth = layoutWidth * scale;
            float cardHeight = layoutHeight * scale;
            float cardX = Mathf.Round((Screen.width - cardWidth) * 0.5f);
            float cardY = Screen.height - cardHeight - 2f;
            if (overlay != null && overlay.IsDesktopStage)
            {
                cardX = overlay.PetPosition.x - overlay.StageOrigin.x + 170f - cardWidth * 0.5f;
                cardY = overlay.PetPosition.y - overlay.StageOrigin.y + 266f;
                if (cardY + cardHeight > Screen.height - 4f)
                    cardY = overlay.PetPosition.y - overlay.StageOrigin.y + 120f - cardHeight - 8f;
            }
            cardX = Mathf.Clamp(cardX, 2f, Mathf.Max(2f, Screen.width - cardWidth - 2f));
            cardY = Mathf.Clamp(cardY, 2f, Mathf.Max(2f, Screen.height - cardHeight - 2f));

            Matrix4x4 previousMatrix = GUI.matrix;
            GUI.matrix = Matrix4x4.TRS(new Vector3(cardX, cardY, 0f), Quaternion.identity,
                new Vector3(scale, scale, 1f));
            try
            {
                GUI.DrawTexture(new Rect(0f, 0f, layoutWidth, layoutHeight), outlineTexture);
                GUI.DrawTexture(new Rect(1f, 1f, layoutWidth - 2f, layoutHeight - 2f), creamTexture);
                DrawFittedLabel(new Rect(12f, 7f, 70f, 22f), "本月費用", titleLabel, 12);
                string amount = usageStatus == "offline" ? "離線模式" :
                    usageStatus == "loading" ? "讀取中…" :
                    usageStatus == "error" ? "同步失敗" :
                    $"${costUsd.ToString("N2", CultureInfo.InvariantCulture)} USD";
                DrawFittedLabel(new Rect(90f, 5f, 150f, 26f), amount, amountLabel, 12);
            }
            finally
            {
                GUI.matrix = previousMatrix;
            }
        }

        private static void DrawFittedLabel(Rect rect, string text, GUIStyle style, int minimumFontSize)
        {
            int originalFontSize = style.fontSize;
            GUIContent content = new(text);
            while (style.fontSize > minimumFontSize)
            {
                Vector2 size = style.CalcSize(content);
                if (size.x <= rect.width && size.y <= rect.height)
                    break;
                style.fontSize--;
            }
            GUI.Label(rect, content, style);
            style.fontSize = originalFontSize;
        }

        private void EnsureStyles()
        {
            if (titleLabel != null)
                return;
            uiFont = Font.CreateDynamicFontFromOSFont(
                new[] { "Microsoft JhengHei UI", "Microsoft JhengHei", "Segoe UI" }, 18);
            titleLabel = new GUIStyle(GUI.skin.label)
            {
                alignment = TextAnchor.MiddleLeft,
                fontSize = 13,
                clipping = TextClipping.Clip,
                wordWrap = false,
                font = uiFont,
                padding = new RectOffset(0, 0, 0, 0),
                normal = { textColor = Outline }
            };
            amountLabel = new GUIStyle(titleLabel) { fontSize = 18, fontStyle = FontStyle.Bold };
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
            if (uiFont != null) Destroy(uiFont);
            if (outlineTexture != null) Destroy(outlineTexture);
            if (creamTexture != null) Destroy(creamTexture);
        }
    }
}
