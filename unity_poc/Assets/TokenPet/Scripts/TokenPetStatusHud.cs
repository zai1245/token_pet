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

        private int level = 1;
        private float xp;
        private float xpMax = 100f;
        private float satiety = 100f;
        private int coins;
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
        private TokenPetWindowsOverlay overlay;

        public bool IsVisible => isVisible;

        public void Initialize(TokenPetWindowsOverlay windowsOverlay)
        {
            overlay = windowsOverlay;
        }

        public void SetStatus(int nextLevel, float nextXp, float nextXpMax,
            float nextSatiety, int nextCoins)
        {
            level = Mathf.Max(1, nextLevel);
            xp = Mathf.Max(0f, nextXp);
            xpMax = Mathf.Max(1f, nextXpMax);
            satiety = Mathf.Clamp(nextSatiety, 0f, 100f);
            coins = Mathf.Max(0, nextCoins);
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
        }

        private void OnGUI()
        {
            if (!isVisible)
                return;

            EnsureStyles();

            const float cardWidth = 252f;
            const float cardHeight = 38f;
            float cardX = Mathf.Round((Screen.width - cardWidth) * 0.5f);
            // Keep the centre/top of the transparent surface clear for the pet,
            // speech boards and future item reactions. This sits just below
            // the feet, in the space occupied by the legacy attached HUD.
            float cardY = Screen.height - cardHeight - 2f;
            if (overlay != null && overlay.IsDesktopStage)
            {
                cardX = overlay.PetPosition.x - overlay.StageOrigin.x + 44f;
                cardY = overlay.PetPosition.y - overlay.StageOrigin.y + 260f;
            }

            // A small warm tag instead of the old detached 340x45 dark window.
            GUI.DrawTexture(new Rect(cardX, cardY, cardWidth, cardHeight), outlineTexture);
            GUI.DrawTexture(new Rect(cardX + 2f, cardY + 2f, cardWidth - 4f, cardHeight - 4f), creamTexture);

            GUI.Label(new Rect(cardX + 12f, cardY + 4f, 44f, 18f), $"Lv.{level}", mainLabel);
            GUI.Label(new Rect(cardX + 12f, cardY + 21f, 24f, 12f), "XP", smallLabel);
            DrawBar(new Rect(cardX + 36f, cardY + 25f, 54f, 6f),
                Mathf.Clamp01(xp / xpMax), xpTexture);

            Texture2D currentFoodTexture = satiety <= 20f ? hungryTexture : foodTexture;
            GUI.DrawTexture(new Rect(cardX + 104f, cardY + 8f, 9f, 9f), currentFoodTexture);
            GUI.Label(new Rect(cardX + 117f, cardY + 3f, 48f, 18f), $"{satiety:0}%", mainLabel);
            GUI.Label(new Rect(cardX + 104f, cardY + 21f, 32f, 12f), "FULL", smallLabel);
            DrawBar(new Rect(cardX + 136f, cardY + 25f, 42f, 6f),
                satiety / 100f, currentFoodTexture);

            GUI.DrawTexture(new Rect(cardX + 192f, cardY + 10f, 10f, 10f), coinTexture);
            GUI.Label(new Rect(cardX + 207f, cardY + 5f, 38f, 18f), FormatCoins(coins), mainLabel);
            GUI.Label(new Rect(cardX + 192f, cardY + 22f, 48f, 11f), "COINS", smallLabel);
        }

        private void DrawBar(Rect rect, float ratio, Texture2D fill)
        {
            GUI.DrawTexture(rect, trackTexture);
            float innerWidth = Mathf.Max(0f, (rect.width - 2f) * Mathf.Clamp01(ratio));
            if (innerWidth > 0f)
                GUI.DrawTexture(new Rect(rect.x + 1f, rect.y + 1f, innerWidth, rect.height - 2f), fill);
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
                font = uiFont,
                normal = { textColor = Outline }
            };
            smallLabel = new GUIStyle(mainLabel)
            {
                fontSize = 7,
                fontStyle = FontStyle.Normal
            };
        }

        private static string FormatCoins(int value)
        {
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
        }
    }
}
