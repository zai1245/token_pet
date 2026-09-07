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
            public float offset_x;
            public float offset_y;
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
            foreach (SpriteRenderer renderer in instance.GetComponentsInChildren<SpriteRenderer>(true))
                renderer.sortingOrder = definition.sorting_order;

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

        private static GameObject CreateAccessory(AccessoryDefinition definition)
        {
            if (definition.resource == "procedural:crown")
                return CreatePocCrown();

            GameObject prefab = Resources.Load<GameObject>(definition.resource);
            if (prefab == null)
            {
                Debug.LogWarning($"Missing accessory prefab Resources/{definition.resource}");
                return null;
            }
            return Instantiate(prefab);
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
    }
}
