using System;
using System.Collections.Generic;
using UnityEngine;

namespace TokenPet
{
    /// <summary>
    /// Owns equipment sockets and resolves item ids from a small data catalog.
    /// Character animation never needs to know how a hat or prop is built.
    /// Production items can point at Resources prefabs; the procedural crown is
    /// kept only as a self-contained PoC example.
    /// </summary>
    public sealed class TokenPetEquipmentController : MonoBehaviour
    {
        [Serializable]
        private sealed class AccessoryCatalog
        {
            public AccessoryDefinition[] items;
        }

        [Serializable]
        private sealed class AccessoryDefinition
        {
            public string id;
            public string slot;
            public string resource;
            public string back_resource;
            public float offset_x;
            public float offset_y;
            // Painted accessories use a full transparent canvas.  Keeping the
            // mount pivot in data lets hats sit on the head rim, helmets wrap
            // the face, and floating ornaments keep their own baseline.
            public float pivot_x = 0.5f;
            public float pivot_y = 0.5f;
            public float scale = 1f;
            public int sorting_order = 20;
        }

        private readonly Dictionary<string, Transform> sockets = new(StringComparer.OrdinalIgnoreCase);
        private readonly Dictionary<string, AccessoryDefinition> catalog = new(StringComparer.OrdinalIgnoreCase);
        private readonly Dictionary<string, GameObject> equippedObjects = new(StringComparer.OrdinalIgnoreCase);
        private readonly Dictionary<string, string> equippedIds = new(StringComparer.OrdinalIgnoreCase);

        public void RegisterSocket(string slot, Transform socket)
        {
            if (!string.IsNullOrWhiteSpace(slot) && socket != null)
                sockets[slot] = socket;
        }

        public void LoadCatalog()
        {
            catalog.Clear();
            TextAsset json = Resources.Load<TextAsset>("accessory_catalog");
            if (json == null)
            {
                Debug.LogWarning("Missing Resources/accessory_catalog.json");
                return;
            }

            AccessoryCatalog parsed = JsonUtility.FromJson<AccessoryCatalog>(json.text);
            if (parsed?.items == null)
                return;

            foreach (AccessoryDefinition item in parsed.items)
            {
                if (item != null && !string.IsNullOrWhiteSpace(item.id))
                    catalog[item.id] = item;
            }
        }

        public bool Equip(string slot, string itemId)
        {
            if (string.IsNullOrWhiteSpace(slot) || !sockets.TryGetValue(slot, out Transform socket))
                return false;

            string normalizedId = itemId ?? string.Empty;
            if (equippedIds.TryGetValue(slot, out string currentId) &&
                string.Equals(currentId, normalizedId, StringComparison.OrdinalIgnoreCase))
                return true;

            Unequip(slot);
            if (string.IsNullOrWhiteSpace(normalizedId) || normalizedId == "none")
                return true;

            if (!catalog.TryGetValue(normalizedId, out AccessoryDefinition definition) ||
                !string.Equals(definition.slot, slot, StringComparison.OrdinalIgnoreCase))
            {
                Debug.LogWarning($"Unknown accessory '{normalizedId}' for slot '{slot}'.");
                return false;
            }

            GameObject instance = CreateAccessory(definition);
            if (instance == null)
                return false;

            instance.name = $"Accessory_{definition.id}";
            instance.transform.SetParent(socket, false);
            instance.transform.localPosition = new Vector3(definition.offset_x, definition.offset_y, 0f);
            instance.transform.localScale = Vector3.one * definition.scale;
            SpriteRenderer[] renderers = instance.GetComponentsInChildren<SpriteRenderer>(true);
            int minimumOrder = int.MaxValue;
            foreach (SpriteRenderer renderer in renderers)
                minimumOrder = Math.Min(minimumOrder, renderer.sortingOrder);
            foreach (SpriteRenderer renderer in renderers)
                renderer.sortingOrder = definition.sorting_order +
                    (minimumOrder == int.MaxValue ? 0 : renderer.sortingOrder - minimumOrder);

            equippedObjects[slot] = instance;
            equippedIds[slot] = definition.id;
            return true;
        }

        public void Toggle(string slot, string itemId)
        {
            if (equippedIds.TryGetValue(slot, out string currentId) &&
                string.Equals(currentId, itemId, StringComparison.OrdinalIgnoreCase))
                Unequip(slot);
            else
                Equip(slot, itemId);
        }

        public void SyncItem(string itemId)
        {
            string normalized = itemId ?? string.Empty;
            foreach (KeyValuePair<string, string> equipped in equippedIds)
            {
                if (string.Equals(equipped.Value, normalized, StringComparison.OrdinalIgnoreCase))
                    return;
            }

            foreach (string slot in new List<string>(equippedIds.Keys))
                Unequip(slot);
            if (string.IsNullOrWhiteSpace(normalized) || normalized == "none")
                return;
            if (catalog.TryGetValue(normalized, out AccessoryDefinition definition))
                Equip(definition.slot, normalized);
        }

        public void SyncSlots(
            string headItem, string faceItem, string neckItem, string bodyItem)
        {
            Equip("head", headItem ?? string.Empty);
            Equip("face", faceItem ?? string.Empty);
            Equip("neck", neckItem ?? string.Empty);
            Equip("body", bodyItem ?? string.Empty);
        }

        public void Unequip(string slot)
        {
            if (equippedObjects.TryGetValue(slot, out GameObject current) && current != null)
            {
                current.SetActive(false);
                Destroy(current);
            }
            equippedObjects.Remove(slot);
            equippedIds.Remove(slot);
        }

        public void SetSlotVisible(string slot, bool visible)
        {
            if (equippedObjects.TryGetValue(slot, out GameObject current) && current != null &&
                current.activeSelf != visible)
            {
                current.SetActive(visible);
            }
        }

        public void SetBackFacing(bool backFacing)
        {
            foreach (GameObject current in equippedObjects.Values)
            {
                if (current == null)
                    continue;
                Transform front = current.transform.Find("FrontArtwork");
                Transform back = current.transform.Find("BackArtwork");
                if (front == null || back == null)
                    continue;
                if (front.gameObject.activeSelf == backFacing)
                    front.gameObject.SetActive(!backFacing);
                if (back.gameObject.activeSelf != backFacing)
                    back.gameObject.SetActive(backFacing);
            }
        }

        private static GameObject CreateAccessory(AccessoryDefinition definition)
        {
            if (string.IsNullOrWhiteSpace(definition.resource))
                return null;

            if (definition.resource.StartsWith("procedural:", StringComparison.OrdinalIgnoreCase))
                return CreateProceduralAccessory(definition.id);

            if (definition.resource.StartsWith("sprite:", StringComparison.OrdinalIgnoreCase))
                return CreatePaintedAccessory(definition);

            GameObject prefab = Resources.Load<GameObject>(definition.resource);
            if (prefab == null)
            {
                Debug.LogWarning($"Missing accessory prefab Resources/{definition.resource}");
                return null;
            }
            return Instantiate(prefab);
        }

        private static GameObject CreatePaintedAccessory(AccessoryDefinition definition)
        {
            string resourcePath = definition.resource.Substring("sprite:".Length);
            Sprite frontSprite = LoadPaintedSprite(resourcePath, definition,
                $"{definition.id}_front");
            if (frontSprite == null)
            {
                Debug.LogWarning(
                    $"Missing painted accessory Resources/{resourcePath}; using procedural fallback.");
                return CreateProceduralAccessory(definition.id);
            }

            GameObject root = new($"Painted {definition.id}");
            CreateArtwork(root.transform, "FrontArtwork", frontSprite, true);

            if (!string.IsNullOrWhiteSpace(definition.back_resource) &&
                definition.back_resource.StartsWith("sprite:", StringComparison.OrdinalIgnoreCase))
            {
                string backPath = definition.back_resource.Substring("sprite:".Length);
                Sprite backSprite = LoadPaintedSprite(backPath, definition,
                    $"{definition.id}_back");
                if (backSprite != null)
                    CreateArtwork(root.transform, "BackArtwork", backSprite, false);
                else
                    Debug.LogWarning($"Missing rear accessory Resources/{backPath}; using front view.");
            }
            return root;
        }

        private static Sprite LoadPaintedSprite(string resourcePath,
            AccessoryDefinition definition, string spriteName)
        {
            Texture2D texture = Resources.Load<Texture2D>(resourcePath);
            if (texture == null)
                return null;
            texture.filterMode = FilterMode.Bilinear;
            texture.wrapMode = TextureWrapMode.Clamp;
            Sprite sprite = Sprite.Create(texture,
                new Rect(0f, 0f, texture.width, texture.height),
                new Vector2(
                    Mathf.Clamp01(definition.pivot_x),
                    Mathf.Clamp01(definition.pivot_y)),
                400f, 0u, SpriteMeshType.FullRect);
            sprite.name = spriteName;
            return sprite;
        }

        private static void CreateArtwork(Transform parent, string name,
            Sprite sprite, bool visible)
        {
            GameObject artwork = new(name);
            artwork.transform.SetParent(parent, false);
            SpriteRenderer renderer = artwork.AddComponent<SpriteRenderer>();
            renderer.sprite = sprite;
            artwork.SetActive(visible);
        }

        private static GameObject CreatePocCrown()
        {
            const int width = 128;
            const int height = 72;
            Texture2D texture = new(width, height, TextureFormat.RGBA32, false)
            {
                filterMode = FilterMode.Bilinear,
                wrapMode = TextureWrapMode.Clamp,
                name = "PoC Crown"
            };
            Color clear = Color.clear;
            Color gold = new(1f, 0.78f, 0.12f, 1f);
            Color rim = new(0.35f, 0.16f, 0.02f, 1f);
            Color[] pixels = new Color[width * height];
            Array.Fill(pixels, clear);

            for (int y = 8; y < 58; y++)
            {
                for (int x = 12; x < 116; x++)
                {
                    float normalizedX = (x - 12f) / 104f;
                    float top;
                    if (normalizedX < 0.33f)
                        top = Mathf.Lerp(52f, 12f, normalizedX / 0.33f);
                    else if (normalizedX < 0.66f)
                        top = Mathf.Lerp(12f, 47f, (normalizedX - 0.33f) / 0.33f);
                    else
                        top = Mathf.Lerp(47f, 14f, (normalizedX - 0.66f) / 0.34f);

                    if (y <= top || y < 14)
                    {
                        bool border = y < 12 || x < 15 || x > 112 || Mathf.Abs(y - top) < 2f;
                        pixels[y * width + x] = border ? rim : gold;
                    }
                }
            }
            texture.SetPixels(pixels);
            texture.Apply();

            Sprite sprite = Sprite.Create(texture, new Rect(0, 0, width, height),
                new Vector2(0.5f, 0f), 100f);
            GameObject crown = new("Crown");
            crown.AddComponent<SpriteRenderer>().sprite = sprite;
            return crown;
        }

        private static GameObject CreateProceduralAccessory(string id)
        {
            if (id == "crown")
                return CreatePocCrown();

            GameObject root = new($"Procedural {id}");
            Transform p = root.transform;
            Color ink = new Color32(82, 35, 17, 255);
            Color pink = new Color32(244, 143, 177, 255);
            Color gold = new Color32(249, 196, 79, 255);
            Color purple = new Color32(137, 102, 190, 255);
            Color green = new Color32(120, 190, 105, 255);
            Color dark = new Color32(34, 35, 50, 255);
            Color white = new Color32(255, 247, 235, 255);

            switch (id)
            {
                case "sunglasses":
                    Lens(p, -0.31f, dark, ink); Lens(p, 0.31f, dark, ink);
                    TokenPetProceduralArt.Line(p, "Bridge", new Vector2(-0.13f, 0f), new Vector2(0.13f, 0f), 0.07f, ink, 25);
                    break;
                case "star_sunglasses":
                    TokenPetProceduralArt.Outlined(p, "StarL", TokenPetShape.Star, new Vector2(-0.31f, 0f), new Vector2(0.42f, 0.42f), gold, ink, 24);
                    TokenPetProceduralArt.Outlined(p, "StarR", TokenPetShape.Star, new Vector2(0.31f, 0f), new Vector2(0.42f, 0.42f), pink, ink, 24);
                    TokenPetProceduralArt.Line(p, "Bridge", new Vector2(-0.12f, 0f), new Vector2(0.12f, 0f), 0.06f, ink, 25);
                    break;
                case "cat_ears":
                    Ear(p, -0.48f, 12f, pink, ink); Ear(p, 0.48f, -12f, pink, ink);
                    break;
                case "demon_horns":
                    Ear(p, -0.48f, 20f, new Color32(220, 65, 70, 255), ink);
                    Ear(p, 0.48f, -20f, new Color32(220, 65, 70, 255), ink);
                    break;
                case "halo":
                    for (int i = 0; i < 14; i++)
                    {
                        float angle = i / 14f * Mathf.PI * 2f;
                        Dot(p, new Vector2(Mathf.Cos(angle) * 0.50f, Mathf.Sin(angle) * 0.095f),
                            0.13f, gold, 25);
                    }
                    break;
                case "scholar_cap":
                    TokenPetProceduralArt.Outlined(p, "Board", TokenPetShape.Diamond, new Vector2(0f, 0.12f), new Vector2(1.05f, 0.48f), dark, ink, 24);
                    TokenPetProceduralArt.Outlined(p, "Cap", TokenPetShape.Square, new Vector2(0f, -0.04f), new Vector2(0.58f, 0.32f), dark, ink, 23);
                    TokenPetProceduralArt.Line(p, "Tassel", new Vector2(0.18f, 0.12f), new Vector2(0.48f, -0.28f), 0.035f, gold, 26);
                    break;
                case "gentleman_hat":
                    TokenPetProceduralArt.Outlined(p, "Brim", TokenPetShape.Circle, new Vector2(0f, -0.12f), new Vector2(1.12f, 0.26f), dark, ink, 24);
                    TokenPetProceduralArt.Outlined(p, "Top", TokenPetShape.Square, new Vector2(0f, 0.20f), new Vector2(0.68f, 0.64f), dark, ink, 25);
                    TokenPetProceduralArt.Line(p, "Ribbon", new Vector2(-0.33f, 0f), new Vector2(0.33f, 0f), 0.12f, pink, 27);
                    break;
                case "wizard_hat":
                    TokenPetProceduralArt.Outlined(p, "Hat", TokenPetShape.Triangle, new Vector2(0f, 0.28f), new Vector2(0.92f, 1.05f), purple, ink, 24, -5f);
                    TokenPetProceduralArt.Outlined(p, "Brim", TokenPetShape.Circle, new Vector2(0f, -0.18f), new Vector2(1.14f, 0.25f), purple, ink, 25);
                    TokenPetProceduralArt.Shape(p, "Star", TokenPetShape.Star, new Vector2(0.10f, 0.28f), new Vector2(0.20f, 0.20f), gold, 27);
                    break;
                case "char_mask":
                    TokenPetProceduralArt.Outlined(p, "Helmet", TokenPetShape.Circle, new Vector2(0f, 0.08f), new Vector2(1.20f, 1.12f), white, ink, 24);
                    TokenPetProceduralArt.Shape(p, "Face", TokenPetShape.Square, new Vector2(0f, -0.05f), new Vector2(0.72f, 0.48f), dark, 26);
                    TokenPetProceduralArt.Shape(p, "Crest", TokenPetShape.Triangle, new Vector2(0f, 0.70f), new Vector2(0.38f, 0.48f), new Color32(210, 52, 58, 255), 27);
                    break;
                case "bowtie":
                    TokenPetProceduralArt.Outlined(p, "Left", TokenPetShape.Triangle, new Vector2(-0.19f, 0f), new Vector2(0.42f, 0.38f), pink, ink, 24, -90f);
                    TokenPetProceduralArt.Outlined(p, "Right", TokenPetShape.Triangle, new Vector2(0.19f, 0f), new Vector2(0.42f, 0.38f), pink, ink, 24, 90f);
                    TokenPetProceduralArt.Shape(p, "Knot", TokenPetShape.Circle, Vector2.zero, new Vector2(0.18f, 0.18f), gold, 27);
                    break;
                case "sakura_hairpin":
                    for (int i = 0; i < 5; i++)
                    {
                        float a = i * Mathf.PI * 0.4f;
                        TokenPetProceduralArt.Shape(p, $"Petal{i}", TokenPetShape.Circle,
                            new Vector2(Mathf.Cos(a), Mathf.Sin(a)) * 0.13f,
                            new Vector2(0.20f, 0.12f), pink, 25, -a * Mathf.Rad2Deg);
                    }
                    TokenPetProceduralArt.Shape(p, "Center", TokenPetShape.Circle, Vector2.zero, Vector2.one * 0.11f, gold, 27);
                    break;
                case "gamer_headset":
                    TokenPetProceduralArt.Line(p, "BandL", new Vector2(-0.62f, 0.22f), new Vector2(0f, 0.55f), 0.10f, purple, 24);
                    TokenPetProceduralArt.Line(p, "BandR", new Vector2(0f, 0.55f), new Vector2(0.62f, 0.22f), 0.10f, purple, 24);
                    TokenPetProceduralArt.Outlined(p, "EarL", TokenPetShape.Square, new Vector2(-0.63f, 0f), new Vector2(0.24f, 0.42f), dark, Blue(), 25);
                    TokenPetProceduralArt.Outlined(p, "EarR", TokenPetShape.Square, new Vector2(0.63f, 0f), new Vector2(0.24f, 0.42f), dark, pink, 25);
                    TokenPetProceduralArt.Line(p, "Mic", new Vector2(0.62f, -0.08f), new Vector2(0.36f, -0.28f), 0.045f, ink, 27);
                    break;
                case "clover_sprout":
                    TokenPetProceduralArt.Line(p, "Stem", new Vector2(0f, -0.15f), new Vector2(0f, 0.42f), 0.07f, green, 24);
                    Dot(p, new Vector2(-0.12f, 0.39f), 0.26f, green, 25);
                    Dot(p, new Vector2(0.12f, 0.39f), 0.26f, green, 25);
                    Dot(p, new Vector2(0f, 0.55f), 0.26f, green, 25);
                    Dot(p, new Vector2(0f, 0.27f), 0.26f, green, 25);
                    break;
                case "bandage":
                    TokenPetProceduralArt.Outlined(p, "Bandage", TokenPetShape.Square,
                        Vector2.zero, new Vector2(0.62f, 0.22f), new Color32(245, 224, 190, 255), ink, 24, -18f);
                    Dot(p, Vector2.zero, 0.12f, pink, 27);
                    break;
                case "rainbow":
                    // Body tint and sparkles are animated by TokenPetLegacyVisuals.
                    break;
                default:
                    TokenPetProceduralArt.Shape(p, "Charm", TokenPetShape.Star, Vector2.zero, Vector2.one * 0.35f, gold, 24);
                    break;
            }
            return root;
        }

        private static void Lens(Transform parent, float x, Color fill, Color outline)
        {
            TokenPetProceduralArt.Outlined(parent, "Lens", TokenPetShape.Circle,
                new Vector2(x, 0f), new Vector2(0.45f, 0.34f), fill, outline, 24);
        }

        private static void Ear(Transform parent, float x, float rotation, Color fill, Color outline)
        {
            TokenPetProceduralArt.Outlined(parent, "Ear", TokenPetShape.Triangle,
                new Vector2(x, 0f), new Vector2(0.48f, 0.62f), fill, outline, 24, rotation);
        }

        private static void Dot(Transform parent, Vector2 position, float size, Color color, int order)
        {
            TokenPetProceduralArt.Shape(parent, "Dot", TokenPetShape.Circle,
                position, Vector2.one * size, color, order);
        }

        private static Color Blue() => new Color32(116, 199, 236, 255);
    }
}
