using System;
using System.Collections.Generic;
using UnityEngine;

namespace TokenPet
{
    internal enum TokenPetShape
    {
        Square,
        Circle,
        Triangle,
        Diamond,
        Star
    }

    /// <summary>Small reusable vector-like sprite factory used by equipment and reactions.</summary>
    internal static class TokenPetProceduralArt
    {
        private static readonly Dictionary<TokenPetShape, Sprite> Sprites = new();
        private static Sprite contactShadow;
        private static readonly Dictionary<Texture2D, RectInt> opaqueBounds = new();

        public static Bounds VisibleBounds(SpriteRenderer renderer, Transform reference)
        {
            Sprite sprite = renderer.sprite;
            Texture2D texture = sprite.texture;
            if (!opaqueBounds.TryGetValue(texture, out RectInt pixels))
            {
                Color32[] data = ReadPixels(texture);
                int left = texture.width, right = -1, bottom = texture.height, top = -1;
                for (int y = 0; y < texture.height; y++)
                for (int x = 0; x < texture.width; x++)
                {
                    if (data[y * texture.width + x].a < 64) continue;
                    left = Math.Min(left, x); right = Math.Max(right, x);
                    bottom = Math.Min(bottom, y); top = Math.Max(top, y);
                }
                pixels = right >= left ? new RectInt(left, bottom, right - left + 1, top - bottom + 1) :
                    new RectInt(0, 0, texture.width, texture.height);
                opaqueBounds[texture] = pixels;
            }
            Vector3 minimum = reference.InverseTransformPoint(renderer.transform.TransformPoint(
                new Vector3(pixels.xMin - sprite.pivot.x, pixels.yMin - sprite.pivot.y, 0f) / sprite.pixelsPerUnit));
            Vector3 maximum = reference.InverseTransformPoint(renderer.transform.TransformPoint(
                new Vector3(pixels.xMax - sprite.pivot.x, pixels.yMax - sprite.pivot.y, 0f) / sprite.pixelsPerUnit));
            Bounds bounds = new(); bounds.SetMinMax(minimum, maximum);
            return bounds;
        }

        public static Color32[] ReadPixels(Texture2D source)
        {
            if (source.isReadable) return source.GetPixels32();
            RenderTexture previous = RenderTexture.active;
            RenderTexture copy = RenderTexture.GetTemporary(source.width, source.height, 0,
                RenderTextureFormat.ARGB32, RenderTextureReadWrite.Linear);
            Texture2D readable = null;
            try
            {
                Graphics.Blit(source, copy); RenderTexture.active = copy;
                readable = new Texture2D(source.width, source.height, TextureFormat.RGBA32, false, true);
                readable.ReadPixels(new Rect(0, 0, source.width, source.height), 0, 0, false);
                readable.Apply(false, false);
                return readable.GetPixels32();
            }
            finally
            {
                RenderTexture.active = previous; RenderTexture.ReleaseTemporary(copy);
                if (readable != null) UnityEngine.Object.Destroy(readable);
            }
        }

        public static GameObject ContactShadow(Transform parent, Vector2 position, Vector2 size)
        {
            if (contactShadow == null)
            {
                const int resolution = 64;
                Texture2D texture = new(resolution, resolution, TextureFormat.RGBA32, false)
                {
                    filterMode = FilterMode.Bilinear, wrapMode = TextureWrapMode.Clamp,
                    name = "Soft warm contact shadow"
                };
                Color[] pixels = new Color[resolution * resolution];
                for (int y = 0; y < resolution; y++)
                for (int x = 0; x < resolution; x++)
                {
                    float nx = (x + 0.5f) / resolution * 2f - 1f;
                    float ny = (y + 0.5f) / resolution * 2f - 1f;
                    float radius = nx * nx + ny * ny;
                    float alpha = Mathf.Exp(-radius * 5f) *
                        (1f - Mathf.SmoothStep(0.5f, 1f, radius)) * 0.18f;
                    pixels[y * resolution + x] = new Color(0.22f, 0.13f, 0.08f, alpha);
                }
                texture.SetPixels(pixels); texture.Apply(false, true);
                contactShadow = Sprite.Create(texture, new Rect(0, 0, resolution, resolution),
                    new Vector2(0.5f, 0.5f), resolution);
            }
            GameObject item = new("Contact shadow");
            item.transform.SetParent(parent, false);
            item.transform.localPosition = position;
            item.transform.localScale = new Vector3(size.x, size.y, 1f);
            SpriteRenderer renderer = item.AddComponent<SpriteRenderer>();
            renderer.sprite = contactShadow;
            renderer.sortingOrder = 0;
            return item;
        }

        public static GameObject Shape(
            Transform parent, string name, TokenPetShape shape, Vector2 position,
            Vector2 size, Color color, int order, float rotation = 0f)
        {
            GameObject item = new(name);
            item.transform.SetParent(parent, false);
            item.transform.localPosition = new Vector3(position.x, position.y, 0f);
            item.transform.localScale = new Vector3(size.x, size.y, 1f);
            item.transform.localRotation = Quaternion.Euler(0f, 0f, rotation);
            SpriteRenderer renderer = item.AddComponent<SpriteRenderer>();
            renderer.sprite = GetSprite(shape);
            renderer.color = color;
            renderer.sortingOrder = order;
            return item;
        }

        public static GameObject Outlined(
            Transform parent, string name, TokenPetShape shape, Vector2 position,
            Vector2 size, Color fill, Color outline, int order, float rotation = 0f,
            float outlineScale = 1.12f)
        {
            GameObject root = new(name);
            root.transform.SetParent(parent, false);
            root.transform.localPosition = new Vector3(position.x, position.y, 0f);
            root.transform.localRotation = Quaternion.Euler(0f, 0f, rotation);
            Shape(root.transform, "Outline", shape, Vector2.zero, size * outlineScale, outline, order);
            Shape(root.transform, "Fill", shape, Vector2.zero, size, fill, order + 1);
            return root;
        }

        public static GameObject Line(
            Transform parent, string name, Vector2 from, Vector2 to,
            float width, Color color, int order)
        {
            Vector2 delta = to - from;
            return Shape(parent, name, TokenPetShape.Square, (from + to) * 0.5f,
                new Vector2(delta.magnitude, width), color, order,
                Mathf.Atan2(delta.y, delta.x) * Mathf.Rad2Deg);
        }

        private static Sprite GetSprite(TokenPetShape shape)
        {
            if (Sprites.TryGetValue(shape, out Sprite cached))
                return cached;

            const int size = 64;
            Texture2D texture = new(size, size, TextureFormat.RGBA32, false)
            {
                filterMode = FilterMode.Bilinear,
                wrapMode = TextureWrapMode.Clamp,
                name = $"TokenPet {shape}"
            };
            Color[] pixels = new Color[size * size];
            for (int y = 0; y < size; y++)
            {
                for (int x = 0; x < size; x++)
                {
                    float px = (x + 0.5f) / size * 2f - 1f;
                    float py = (y + 0.5f) / size * 2f - 1f;
                    bool inside = shape switch
                    {
                        TokenPetShape.Circle => px * px + py * py <= 0.94f,
                        TokenPetShape.Triangle => py >= -0.92f && py <= 0.92f &&
                            Mathf.Abs(px) <= (0.94f - py) * 0.58f,
                        TokenPetShape.Diamond => Mathf.Abs(px) + Mathf.Abs(py) <= 0.94f,
                        TokenPetShape.Star => InsideStar(px, py),
                        _ => Mathf.Abs(px) <= 0.94f && Mathf.Abs(py) <= 0.94f,
                    };
                    pixels[y * size + x] = inside ? Color.white : Color.clear;
                }
            }
            texture.SetPixels(pixels);
            texture.Apply();
            cached = Sprite.Create(texture, new Rect(0, 0, size, size),
                new Vector2(0.5f, 0.5f), size);
            cached.name = $"TokenPet {shape} Sprite";
            Sprites[shape] = cached;
            return cached;
        }

        private static bool InsideStar(float x, float y)
        {
            float angle = Mathf.Atan2(y, x) + Mathf.PI * 0.5f;
            float radius = Mathf.Sqrt(x * x + y * y);
            float sector = Mathf.Repeat(angle, Mathf.PI * 0.4f);
            float edge = Mathf.Lerp(0.42f, 0.96f,
                Mathf.Abs(sector - Mathf.PI * 0.2f) / (Mathf.PI * 0.2f));
            return radius <= edge;
        }
    }

    internal static class TokenPetArtStyle
    {
        public static readonly Color Ink = new Color32(80, 54, 37, 255);
        public static readonly Color Paper = new Color32(255, 249, 237, 255);
        public static readonly Color Border = new Color32(213, 191, 164, 255);
        public static readonly Color Muted = new Color32(134, 112, 87, 255);

        public static void RoundRect(Rect rect, Color color, float radius = 8f)
        {
            GUI.DrawTexture(rect, Texture2D.whiteTexture, ScaleMode.StretchToFill,
                true, 0f, color, 0f, radius);
        }

        public static void Panel(Rect rect, float radius = 10f, bool shadow = true)
        {
            if (shadow)
            {
                RoundRect(new Rect(rect.x - 2f, rect.y + 3f, rect.width + 4f, rect.height),
                    new Color(0.16f, 0.10f, 0.06f, 0.06f), radius + 2f);
                RoundRect(new Rect(rect.x, rect.y + 2f, rect.width, rect.height),
                    new Color(0.16f, 0.10f, 0.06f, 0.10f), radius);
            }
            RoundRect(rect, Border, radius);
            RoundRect(new Rect(rect.x + 1f, rect.y + 1f, rect.width - 2f, rect.height - 2f),
                Paper, Mathf.Max(0f, radius - 1f));
        }
    }
}
