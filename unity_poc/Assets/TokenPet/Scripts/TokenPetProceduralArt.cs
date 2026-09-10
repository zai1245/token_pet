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
}
