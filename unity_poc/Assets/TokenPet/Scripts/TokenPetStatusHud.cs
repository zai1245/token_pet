using UnityEngine;

namespace TokenPet
{
    /// <summary>
    /// Compact status tag rendered in the same player surface as the pet.
    /// Python remains the source of truth; this component is presentation-only.
    /// Opaque warm colours are intentional because the Windows player uses a
    /// magenta colour key rather than per-pixel window alpha.
    /// </summary>
    public sealed class TokenPetStatusHud : MonoBehaviour
    {
        private static readonly Color32 Outline = new(79, 42, 20, 255);
        private static readonly Color32 Cream = new(255, 244, 210, 255);
        private static readonly Color32 Track = new(231, 210, 167, 255);
        private static readonly Color32 XpFill = new(245, 167, 55, 255);
        private static readonly Color32 FoodFill = new(115, 183, 91, 255);
        private static readonly Color32 HungryFill = new(240, 105, 91, 255);
        private static readonly Color32 CoinFill = new(255, 196, 54, 255);
        private static readonly Color32 TokenFill = new(88, 142, 214, 255);

        private int level = 1;
        private float xp;
        private float xpMax = 100f;
        private float satiety = 100f;
        private int coins;
        private long tokenTotal;
        private bool isVisible = true;
        private GUIStyle mainLabel;
        private GUIStyle smallLabel;
        private Font uiFont;
        private Texture2D outlineTexture;
        private Texture2D creamTexture;
        private Texture2D trackTexture;
        private Texture2D xpTexture;
        private Texture2D foodTexture;
        private Texture2D hungryTexture;
        private Texture2D coinTexture;
        private Texture2D tokenTexture;
        private TokenPetWindowsOverlay overlay;

        public bool IsVisible => isVisible;

        public void Initialize(TokenPetWindowsOverlay windowsOverlay)
        {
            overlay = windowsOverlay;
        }

        public void SetStatus(int nextLevel, float nextXp, float nextXpMax,
            float nextSatiety, int nextCoins, long promptTokens, long completeTokens)
        {
            level = Mathf.Max(1, nextLevel);
            xp = Mathf.Max(0f, nextXp);
            xpMax = Mathf.Max(1f, nextXpMax);
            satiety = Mathf.Clamp(nextSatiety, 0f, 100f);
            coins = Mathf.Max(0, nextCoins);
            tokenTotal = System.Math.Max(0L, promptTokens) + System.Math.Max(0L, completeTokens);
        }

        public void SetVisible(bool visible)
        {
            isVisible = visible;
        }

        private void Awake()
        {
            outlineTexture = MakeTexture(Outline);
            creamTexture = MakeTexture(Cream);
            trackTexture = MakeTexture(Track);
            xpTexture = MakeTexture(XpFill);
            foodTexture = MakeTexture(FoodFill);
            hungryTexture = MakeTexture(HungryFill);
            coinTexture = MakeTexture(CoinFill);
            tokenTexture = MakeTexture(TokenFill);
        }

        private void OnGUI()
        {
            if (!isVisible)
                return;

            EnsureStyles();

            const float cardWidth = 332f;
            const float cardHeight = 38f;
            float cardX = Mathf.Round((Screen.width - cardWidth) * 0.5f);
            // Keep the centre/top of the transparent surface clear for the pet,
            // speech boards and future item reactions. This sits just below
            // the feet, in the space occupied by the legacy attached HUD.
            float cardY = Screen.height - cardHeight - 2f;
            if (overlay != null && overlay.IsDesktopStage)
            {
                cardX = overlay.PetPosition.x - overlay.StageOrigin.x + 4f;
                cardY = overlay.PetPosition.y - overlay.StageOrigin.y + 260f;
            }
            cardX = Mathf.Clamp(cardX, 2f, Mathf.Max(2f, Screen.width - cardWidth - 2f));
            cardY = Mathf.Clamp(cardY, 2f, Mathf.Max(2f, Screen.height - cardHeight - 2f));

            // A small warm tag instead of the old detached 340x45 dark window.
            GUI.DrawTexture(new Rect(cardX, cardY, cardWidth, cardHeight), outlineTexture);
            GUI.DrawTexture(new Rect(cardX + 2f, cardY + 2f, cardWidth - 4f, cardHeight - 4f), creamTexture);

            DrawFittedLabel(new Rect(cardX + 10f, cardY + 4f, 72f, 18f), $"Lv.{level}", mainLabel, 7);
            DrawFittedLabel(new Rect(cardX + 10f, cardY + 21f, 20f, 12f), "XP", smallLabel, 5);
            DrawBar(new Rect(cardX + 30f, cardY + 25f, 52f, 6f),
                Mathf.Clamp01(xp / xpMax), xpTexture);

            Texture2D currentFoodTexture = satiety <= 20f ? hungryTexture : foodTexture;
            GUI.DrawTexture(new Rect(cardX + 91f, cardY + 8f, 9f, 9f), currentFoodTexture);
            DrawFittedLabel(new Rect(cardX + 104f, cardY + 3f, 48f, 18f), $"{satiety:0}%", mainLabel, 7);
            DrawFittedLabel(new Rect(cardX + 91f, cardY + 21f, 29f, 12f), "FULL", smallLabel, 5);
            DrawBar(new Rect(cardX + 120f, cardY + 25f, 37f, 6f),
                satiety / 100f, currentFoodTexture);

            // Token usage is the product's primary metric, so it receives the
            // widest field and is always visible alongside the pet stats.
            GUI.DrawTexture(new Rect(cardX + 166f, cardY + 9f, 10f, 10f), tokenTexture);
            DrawFittedLabel(new Rect(cardX + 181f, cardY + 4f, 68f, 18f), FormatMetric(tokenTotal), mainLabel, 6);
            DrawFittedLabel(new Rect(cardX + 166f, cardY + 22f, 75f, 11f), "TOKENS", smallLabel, 5);

            GUI.DrawTexture(new Rect(cardX + 260f, cardY + 9f, 10f, 10f), coinTexture);
            DrawFittedLabel(new Rect(cardX + 275f, cardY + 4f, 49f, 18f), FormatMetric(coins), mainLabel, 6);
            DrawFittedLabel(new Rect(cardX + 260f, cardY + 22f, 58f, 11f), "COINS", smallLabel, 5);
        }

        private void DrawBar(Rect rect, float ratio, Texture2D fill)
        {
            GUI.DrawTexture(rect, trackTexture);
            float innerWidth = Mathf.Max(0f, (rect.width - 2f) * Mathf.Clamp01(ratio));
            if (innerWidth > 0f)
                GUI.DrawTexture(new Rect(rect.x + 1f, rect.y + 1f, innerWidth, rect.height - 2f), fill);
        }

        private static void DrawFittedLabel(
            Rect rect, string text, GUIStyle style, int minimumFontSize)
        {
            int originalFontSize = style.fontSize;
            TextClipping originalClipping = style.clipping;
            style.clipping = TextClipping.Clip;
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
            style.clipping = originalClipping;
        }

        private void EnsureStyles()
        {
            if (mainLabel != null)
                return;

            uiFont = Font.CreateDynamicFontFromOSFont(
                new[] { "Microsoft JhengHei UI", "Microsoft JhengHei", "Segoe UI" },
                12);
            mainLabel = new GUIStyle(GUI.skin.label)
            {
                alignment = TextAnchor.MiddleLeft,
                fontSize = 11,
                fontStyle = FontStyle.Bold,
                clipping = TextClipping.Clip,
                wordWrap = false,
                font = uiFont,
                normal = { textColor = Outline }
            };
            smallLabel = new GUIStyle(mainLabel)
            {
                fontSize = 7,
                fontStyle = FontStyle.Normal
            };
        }

        private static string FormatMetric(long value)
        {
            if (value >= 1000000000)
                return $"{value / 1000000000f:0.#}b";
            if (value >= 1000000)
                return $"{value / 1000000f:0.#}m";
            if (value >= 1000)
                return $"{value / 1000f:0.#}k";
            return value.ToString();
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
            if (uiFont != null)
                Destroy(uiFont);
            if (outlineTexture != null)
                Destroy(outlineTexture);
            if (creamTexture != null)
                Destroy(creamTexture);
            if (trackTexture != null)
                Destroy(trackTexture);
            if (xpTexture != null)
                Destroy(xpTexture);
            if (foodTexture != null)
                Destroy(foodTexture);
            if (hungryTexture != null)
                Destroy(hungryTexture);
            if (coinTexture != null)
                Destroy(coinTexture);
            if (tokenTexture != null)
                Destroy(tokenTexture);
        }
    }
}
