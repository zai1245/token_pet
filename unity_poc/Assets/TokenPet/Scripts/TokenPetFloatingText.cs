using System;
using System.Collections.Generic;
using UnityEngine;

namespace TokenPet
{
    /// <summary>
    /// Unity replacement for the hidden Canvas text_popups layer.
    /// Coordinates keep the original 340x300 top-left Canvas convention.
    /// </summary>
    public sealed class TokenPetFloatingText : MonoBehaviour
    {
        private sealed class Popup
        {
            public Transform root;
            public TextMesh[] meshes;
            public float age;
            public float duration;
            public Vector3 origin;
        }

        private readonly List<Popup> active = new();
        private Camera targetCamera;
        private TokenPetWindowsOverlay overlay;
        private Font font;

        public void Initialize(Camera camera, TokenPetWindowsOverlay windowsOverlay)
        {
            targetCamera = camera;
            overlay = windowsOverlay;
            try
            {
                font = Font.CreateDynamicFontFromOSFont(
                    new[] { "Microsoft JhengHei UI", "Microsoft JhengHei", "Arial" }, 28);
            }
            catch (Exception)
            {
                font = null;
            }
        }

        public void Show(string value, float canvasX, float canvasY, string htmlColor, float duration)
        {
            if (targetCamera == null || string.IsNullOrWhiteSpace(value))
                return;

            GameObject rootObject = new("FloatingText");
            Transform root = rootObject.transform;
            float screenX;
            float screenY;
            if (overlay != null && overlay.IsDesktopStage)
            {
                screenX = overlay.PetPosition.x - overlay.StageOrigin.x + canvasX;
                screenY = Screen.height -
                    (overlay.PetPosition.y - overlay.StageOrigin.y + canvasY);
            }
            else
            {
                screenX = canvasX / 340f * Screen.width;
                screenY = (300f - canvasY) / 300f * Screen.height;
            }
            Vector3 world = targetCamera.ScreenToWorldPoint(new Vector3(screenX, screenY, 10f));
            world.z = 0f;
            root.position = world;

            Color fill = ParseColor(htmlColor, new Color32(249, 226, 175, 255));
            Vector2[] outlineOffsets =
            {
                new(-0.025f, 0f), new(0.025f, 0f),
                new(0f, -0.025f), new(0f, 0.025f)
            };
            TextMesh[] meshes = new TextMesh[5];
            for (int i = 0; i < meshes.Length; i++)
            {
                GameObject textObject = new(i == 4 ? "Fill" : $"Outline{i}");
                textObject.transform.SetParent(root, false);
                if (i < 4)
                    textObject.transform.localPosition = outlineOffsets[i];
                TextMesh mesh = textObject.AddComponent<TextMesh>();
                mesh.text = value;
                mesh.anchor = TextAnchor.MiddleCenter;
                mesh.alignment = TextAlignment.Center;
                mesh.fontSize = 28;
                mesh.characterSize = 0.040f;
                mesh.color = i == 4 ? fill : new Color32(48, 24, 15, 255);
                if (font != null)
                {
                    mesh.font = font;
                    mesh.GetComponent<MeshRenderer>().sharedMaterial = font.material;
                }
                mesh.GetComponent<MeshRenderer>().sortingOrder = i == 4 ? 81 : 80;
                meshes[i] = mesh;
            }

            active.Add(new Popup
            {
                root = root,
                meshes = meshes,
                duration = Mathf.Max(0.25f, duration),
                origin = world
            });
        }

        private void Update()
        {
            float delta = Time.unscaledDeltaTime;
            for (int i = active.Count - 1; i >= 0; i--)
            {
                Popup popup = active[i];
                popup.age += delta;
                float progress = Mathf.Clamp01(popup.age / popup.duration);
                popup.root.position = popup.origin + Vector3.up * progress * 0.42f;
                float alpha = 1f - Mathf.SmoothStep(0.65f, 1f, progress);
                foreach (TextMesh mesh in popup.meshes)
                {
                    Color color = mesh.color;
                    color.a = alpha;
                    mesh.color = color;
                }
                if (progress >= 1f)
                {
                    Destroy(popup.root.gameObject);
                    active.RemoveAt(i);
                }
            }
        }

        private static Color ParseColor(string html, Color fallback)
        {
            if (!string.IsNullOrWhiteSpace(html) && ColorUtility.TryParseHtmlString(html, out Color parsed))
                return parsed;
            return fallback;
        }
    }
}
