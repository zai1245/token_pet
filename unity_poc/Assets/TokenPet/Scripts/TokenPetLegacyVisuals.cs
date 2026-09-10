using System;
using System.Collections.Generic;
using UnityEngine;

namespace TokenPet
{
    /// <summary>
    /// Recreates the legacy Canvas props, buffs and furniture as modular Unity
    /// layers. Python remains authoritative; this component only presents the
    /// latest snapshot and never mutates game economy or save data.
    /// </summary>
    public sealed class TokenPetLegacyVisuals : MonoBehaviour
    {
        private static readonly Color Ink = new Color32(82, 35, 17, 255);
        private static readonly Color Cream = new Color32(255, 244, 210, 255);
        private static readonly Color Gold = new Color32(249, 196, 79, 255);
        private static readonly Color Pink = new Color32(244, 143, 177, 255);
        private static readonly Color Blue = new Color32(116, 199, 236, 255);
        private static readonly Color Green = new Color32(166, 227, 161, 255);

        private SpriteRenderer bodyRenderer;
        private Transform foodRoot;
        private Transform furnitureRoot;
        private Transform coffeeRoot;
        private Transform balloonRoot;
        private Transform boardRoot;
        private Transform rabbitRoot;
        private TextMesh boardText;
        private readonly List<SpriteRenderer> particles = new();
        private string state = "idle";
        private string eatType = "";
        private string furniture = "";
        private string effects = "";
        private string accessory = "";
        private string builtFood = "";
        private string builtFurniture = "";
        private bool showBoard;
        private bool overtime;

        public void Initialize(Transform visualParent, SpriteRenderer characterBody)
        {
            bodyRenderer = characterBody;
            foodRoot = NewRoot(visualParent, "Legacy_Food");
            furnitureRoot = NewRoot(visualParent, "Legacy_Furniture");
            coffeeRoot = NewRoot(visualParent, "Legacy_Coffee");
            balloonRoot = NewRoot(visualParent, "Legacy_Balloon");
            boardRoot = NewRoot(visualParent, "Legacy_Board");
            rabbitRoot = NewRoot(visualParent, "Legacy_Rabbit");
            BuildCoffee();
            BuildBalloon();
            BuildBoard();
            BuildRabbit();
            BuildParticlePool(visualParent);
        }

        public void ApplySnapshot(RendererCommand command)
        {
            state = command.state ?? "idle";
            eatType = command.eat_type ?? "";
            furniture = command.furniture ?? "";
            effects = command.effects ?? "";
            accessory = command.item ?? "";
            showBoard = command.show_board;
            overtime = command.overtime;
            if (boardText != null)
                boardText.text = string.IsNullOrWhiteSpace(command.board_text)
                    ? "地瓜球努力中！"
                    : command.board_text;
        }

        public void Tick(float time)
        {
            EnsureFood();
            EnsureFurniture();
            bool eating = state == "eat" || state == "memo_eat";
            bool drinking = state == "drink";
            bool ballooning = state == "balloon";
            foodRoot.gameObject.SetActive(eating);
            coffeeRoot.gameObject.SetActive(drinking);
            balloonRoot.gameObject.SetActive(ballooning);
            furnitureRoot.gameObject.SetActive(NeedsFurniture());
            boardRoot.gameObject.SetActive(showBoard);
            float rabbitPhase = Mathf.Repeat(time, 5.5f);
            bool rabbitVisible = accessory == "gentleman_hat" && rabbitPhase > 4.25f;
            rabbitRoot.gameObject.SetActive(rabbitVisible);
            if (rabbitVisible)
            {
                float pop = Mathf.Sin((rabbitPhase - 4.25f) / 1.25f * Mathf.PI);
                rabbitRoot.localPosition = new Vector3(0f, 1.70f + pop * 0.38f, 0f);
                rabbitRoot.localScale = Vector3.one * Mathf.Lerp(0.65f, 1f, pop);
            }

            foodRoot.localPosition = new Vector3(0.68f, -0.28f + Mathf.Sin(time * 11f) * 0.035f, 0f);
            foodRoot.localRotation = Quaternion.Euler(0f, 0f, Mathf.Sin(time * 8f) * 8f);
            coffeeRoot.localPosition = new Vector3(0.68f, -0.26f + Mathf.Sin(time * 7f) * 0.025f, 0f);
            balloonRoot.localPosition = new Vector3(0f, Mathf.Sin(time * 1.8f) * 0.10f, 0f);
            if (eatType == "balloon_toy")
            {
                float toyPulse = 1f + Mathf.Sin(time * 4f) * 0.05f;
                balloonRoot.localScale = Vector3.one * toyPulse;
                balloonRoot.localRotation = Quaternion.Euler(0f, 0f, Mathf.Sin(time * 3f) * 4f);
            }
            else if (eatType == "balloon")
            {
                balloonRoot.localScale = Vector3.one;
                balloonRoot.localRotation = Quaternion.identity;
            }
            furnitureRoot.localPosition = new Vector3(0f, Mathf.Sin(time * 2.2f) * 0.018f, 0f);
            AnimateFurniture(time);
            boardRoot.localRotation = Quaternion.Euler(0f, 0f, Mathf.Sin(time * 2.4f) * 1.8f);
            UpdateBodyTint(time);
            UpdateParticles(time);
        }

        private static Transform NewRoot(Transform parent, string name)
        {
            Transform root = new GameObject(name).transform;
            root.SetParent(parent, false);
            return root;
        }

        private void EnsureFood()
        {
            string desired = string.IsNullOrWhiteSpace(eatType) ? "ramen" : eatType;
            if (desired == builtFood)
                return;
            Clear(foodRoot);
            builtFood = desired;
            BuildFood(desired);
        }

        private void BuildFood(string id)
        {
            switch (id)
            {
                case "pizza":
                    TokenPetProceduralArt.Outlined(foodRoot, "Pizza", TokenPetShape.Triangle,
                        Vector2.zero, new Vector2(0.52f, 0.56f), Gold, Ink, 31, -18f);
                    Dot(foodRoot, new Vector2(-0.08f, 0.03f), 0.08f, Color.red, 33);
                    Dot(foodRoot, new Vector2(0.10f, -0.08f), 0.07f, Color.red, 33);
                    break;
                case "popsicle":
                    TokenPetProceduralArt.Outlined(foodRoot, "Ice", TokenPetShape.Square,
                        new Vector2(0f, 0.06f), new Vector2(0.27f, 0.50f), Blue, Ink, 31, -10f);
                    TokenPetProceduralArt.Shape(foodRoot, "Stick", TokenPetShape.Square,
                        new Vector2(0f, -0.31f), new Vector2(0.07f, 0.24f), new Color32(180, 120, 70, 255), 30, -10f);
                    break;
                case "lollipop":
                    Dot(foodRoot, new Vector2(0f, 0.12f), 0.34f, Pink, 32);
                    Dot(foodRoot, new Vector2(0f, 0.12f), 0.20f, Blue, 33);
                    TokenPetProceduralArt.Line(foodRoot, "Stick", new Vector2(0f, -0.04f),
                        new Vector2(0f, -0.42f), 0.055f, Cream, 31);
                    break;
                case "candy":
                    TokenPetProceduralArt.Outlined(foodRoot, "Candy", TokenPetShape.Circle,
                        Vector2.zero, new Vector2(0.32f, 0.23f), Pink, Ink, 31);
                    TokenPetProceduralArt.Shape(foodRoot, "WrapL", TokenPetShape.Triangle,
                        new Vector2(-0.24f, 0f), new Vector2(0.22f, 0.25f), Pink, 31, 90f);
                    TokenPetProceduralArt.Shape(foodRoot, "WrapR", TokenPetShape.Triangle,
                        new Vector2(0.24f, 0f), new Vector2(0.22f, 0.25f), Pink, 31, -90f);
                    break;
                case "bubble_tea":
                    TokenPetProceduralArt.Outlined(foodRoot, "Cup", TokenPetShape.Square,
                        Vector2.zero, new Vector2(0.38f, 0.48f), new Color32(205, 158, 105, 255), Ink, 31);
                    for (int i = 0; i < 4; i++)
                        Dot(foodRoot, new Vector2(-0.12f + i * 0.08f, -0.14f), 0.055f, Ink, 33);
                    TokenPetProceduralArt.Line(foodRoot, "Straw", new Vector2(0.05f, 0.18f),
                        new Vector2(0.12f, 0.48f), 0.045f, Pink, 34);
                    break;
                case "matcha_parfait":
                    TokenPetProceduralArt.Outlined(foodRoot, "Parfait", TokenPetShape.Triangle,
                        Vector2.zero, new Vector2(0.42f, 0.52f), Green, Ink, 31, 180f);
                    Dot(foodRoot, new Vector2(0f, 0.22f), 0.22f, Cream, 33);
                    Dot(foodRoot, new Vector2(0.10f, 0.32f), 0.10f, Pink, 34);
                    break;
                case "souffle_pancake":
                    for (int i = 0; i < 3; i++)
                        TokenPetProceduralArt.Outlined(foodRoot, $"Pancake{i}", TokenPetShape.Circle,
                            new Vector2(0f, -0.12f + i * 0.13f), new Vector2(0.48f, 0.18f),
                            new Color32(241, 193, 104, 255), Ink, 31 + i * 2);
                    break;
                case "bandage":
                    TokenPetProceduralArt.Outlined(foodRoot, "Bandage", TokenPetShape.Square,
                        Vector2.zero, new Vector2(0.52f, 0.18f), new Color32(245, 224, 190, 255), Ink, 31, -18f);
                    Dot(foodRoot, Vector2.zero, 0.12f, Pink, 33);
                    break;
                default:
                    BuildBowl(id == "spicy_ramen");
                    break;
            }
        }

        private void BuildBowl(bool spicy)
        {
            Color broth = spicy ? new Color32(235, 82, 64, 255) : Gold;
            TokenPetProceduralArt.Outlined(foodRoot, "Bowl", TokenPetShape.Circle,
                new Vector2(0f, -0.08f), new Vector2(0.58f, 0.31f), Cream, Ink, 31);
            TokenPetProceduralArt.Shape(foodRoot, "Broth", TokenPetShape.Circle,
                new Vector2(0f, 0.02f), new Vector2(0.48f, 0.16f), broth, 33);
            for (int i = 0; i < 3; i++)
                TokenPetProceduralArt.Line(foodRoot, $"Noodle{i}",
                    new Vector2(-0.16f + i * 0.16f, 0.02f),
                    new Vector2(-0.10f + i * 0.13f, 0.26f), 0.035f, Gold, 34);
        }

        private void EnsureFurniture()
        {
            string desired = ResolveFurniture();
            if (desired == builtFurniture)
                return;
            Clear(furnitureRoot);
            builtFurniture = desired;
            BuildFurniture(desired);
        }

        private string ResolveFurniture()
        {
            if (!string.IsNullOrWhiteSpace(furniture))
                return furniture;
            return state switch
            {
                "sleep_futon" => "futon",
                "work_laptop" => "laptop",
                "relax_sofa" => "lazy_sofa",
                "warm_kotatsu" => "kotatsu",
                "watch_tv" => "pixel_tv",
                "meditate_lamp" => "night_lamp",
                "water_plant" => "succulent_pot",
                "memo_perch" or "memo_read" or "memo_eat" => "memo",
                _ => ""
            };
        }

        private bool NeedsFurniture() => !string.IsNullOrEmpty(ResolveFurniture());

        private void BuildFurniture(string id)
        {
            switch (id)
            {
                case "futon":
                    TokenPetProceduralArt.Outlined(furnitureRoot, "Quilt", TokenPetShape.Square,
                        new Vector2(0.25f, -0.76f), new Vector2(1.65f, 0.48f), Blue, Ink, 8);
                    TokenPetProceduralArt.Outlined(furnitureRoot, "Pillow", TokenPetShape.Circle,
                        new Vector2(-0.70f, -0.67f), new Vector2(0.55f, 0.34f), Cream, Ink, 9);
                    for (int i = 0; i < 4; i++)
                        TokenPetProceduralArt.Shape(furnitureRoot, $"QuiltStar{i}", TokenPetShape.Star,
                            new Vector2(-0.15f + i * 0.28f, -0.75f), Vector2.one * 0.11f, Cream, 11);
                    break;
                case "laptop":
                    TokenPetProceduralArt.Outlined(furnitureRoot, "Screen", TokenPetShape.Square,
                        new Vector2(0.78f, -0.38f), new Vector2(0.72f, 0.58f), new Color32(38, 38, 55, 255), Ink, 23, -5f);
                    TokenPetProceduralArt.Line(furnitureRoot, "Code1", new Vector2(0.52f, -0.28f), new Vector2(0.86f, -0.25f), 0.035f, Green, 25);
                    TokenPetProceduralArt.Line(furnitureRoot, "Code2", new Vector2(0.55f, -0.39f), new Vector2(0.95f, -0.35f), 0.035f, Pink, 25);
                    TokenPetProceduralArt.Line(furnitureRoot, "LaptopCursor", new Vector2(0.91f, -0.48f), new Vector2(0.91f, -0.36f), 0.035f, Green, 26);
                    TokenPetProceduralArt.Outlined(furnitureRoot, "Keyboard", TokenPetShape.Square,
                        new Vector2(0.55f, -0.77f), new Vector2(0.95f, 0.20f), new Color32(69, 71, 90, 255), Ink, 24, -5f);
                    break;
                case "trampoline":
                    TokenPetProceduralArt.Outlined(furnitureRoot, "Mat", TokenPetShape.Circle,
                        new Vector2(0f, -0.88f), new Vector2(1.45f, 0.28f), new Color32(40, 42, 54, 255), Pink, 8);
                    TokenPetProceduralArt.Line(furnitureRoot, "LegL", new Vector2(-0.48f, -0.92f), new Vector2(-0.62f, -1.12f), 0.08f, Ink, 7);
                    TokenPetProceduralArt.Line(furnitureRoot, "LegR", new Vector2(0.48f, -0.92f), new Vector2(0.62f, -1.12f), 0.08f, Ink, 7);
                    Transform shockwave = NewRoot(furnitureRoot, "Shockwave");
                    for (int i = 0; i < 16; i++)
                    {
                        float angle = i / 16f * Mathf.PI * 2f;
                        TokenPetProceduralArt.Shape(shockwave, $"Ripple{i}", TokenPetShape.Circle,
                            new Vector2(Mathf.Cos(angle) * 0.68f, -0.88f + Mathf.Sin(angle) * 0.12f),
                            Vector2.one * 0.055f, Gold, 10);
                    }
                    break;
                case "night_lamp":
                    TokenPetProceduralArt.Shape(furnitureRoot, "LampGlow", TokenPetShape.Circle,
                        new Vector2(0.83f, -0.35f), Vector2.one * 0.72f,
                        new Color(1f, 0.88f, 0.40f, 0.22f), 5);
                    TokenPetProceduralArt.Outlined(furnitureRoot, "LampCap", TokenPetShape.Triangle,
                        new Vector2(0.83f, -0.32f), new Vector2(0.65f, 0.48f), Pink, Ink, 15);
                    TokenPetProceduralArt.Line(furnitureRoot, "LampStem", new Vector2(0.83f, -0.50f), new Vector2(0.83f, -0.98f), 0.10f, Ink, 14);
                    break;
                case "succulent_pot":
                    TokenPetProceduralArt.Outlined(furnitureRoot, "Pot", TokenPetShape.Square,
                        new Vector2(0.78f, -0.82f), new Vector2(0.55f, 0.38f), Cream, Ink, 14);
                    for (int i = 0; i < 5; i++)
                        TokenPetProceduralArt.Outlined(furnitureRoot, $"Leaf{i}", TokenPetShape.Circle,
                            new Vector2(0.78f + (i - 2) * 0.12f, -0.50f + Mathf.Abs(i - 2) * 0.04f),
                            new Vector2(0.20f, 0.34f), i == 2 ? Pink : Green, Ink, 15 + i, (i - 2) * 20f);
                    break;
                case "lazy_sofa":
                    TokenPetProceduralArt.Outlined(furnitureRoot, "Sofa", TokenPetShape.Circle,
                        new Vector2(0f, -0.66f), new Vector2(1.72f, 0.70f), new Color32(242, 205, 205, 255), Ink, 7);
                    TokenPetProceduralArt.Outlined(furnitureRoot, "Seat", TokenPetShape.Circle,
                        new Vector2(0f, -0.55f), new Vector2(1.18f, 0.42f), Pink, Ink, 8);
                    for (int i = 0; i < 5; i++)
                        TokenPetProceduralArt.Shape(furnitureRoot, $"Sakura{i}", TokenPetShape.Circle,
                            new Vector2(-0.48f + i * 0.24f, -0.57f + Mathf.Abs(2 - i) * 0.035f),
                            Vector2.one * 0.07f, i % 2 == 0 ? Cream : Pink, 11);
                    break;
                case "pixel_tv":
                    TokenPetProceduralArt.Outlined(furnitureRoot, "TV", TokenPetShape.Square,
                        new Vector2(0.86f, -0.54f), new Vector2(0.90f, 0.72f), new Color32(90, 61, 40, 255), Ink, 14);
                    TokenPetProceduralArt.Shape(furnitureRoot, "Screen", TokenPetShape.Square,
                        new Vector2(0.78f, -0.53f), new Vector2(0.55f, 0.43f), new Color32(30, 30, 46, 255), 16);
                    Dot(furnitureRoot, new Vector2(1.18f, -0.48f), 0.09f, Gold, 17);
                    TokenPetProceduralArt.Line(furnitureRoot, "AntennaL", new Vector2(0.78f, -0.17f), new Vector2(0.58f, 0.10f), 0.035f, Cream, 13);
                    TokenPetProceduralArt.Line(furnitureRoot, "AntennaR", new Vector2(0.78f, -0.17f), new Vector2(1.00f, 0.10f), 0.035f, Cream, 13);
                    TextMesh channel = new GameObject("TvChannel").AddComponent<TextMesh>();
                    channel.transform.SetParent(furnitureRoot, false);
                    channel.transform.localPosition = new Vector3(0.78f, -0.54f, 0f);
                    channel.anchor = TextAnchor.MiddleCenter;
                    channel.alignment = TextAlignment.Center;
                    channel.fontSize = 22;
                    channel.characterSize = 0.030f;
                    channel.color = Cream;
                    channel.GetComponent<MeshRenderer>().sortingOrder = 18;
                    break;
                case "kotatsu":
                    TokenPetProceduralArt.Outlined(furnitureRoot, "Blanket", TokenPetShape.Triangle,
                        new Vector2(0f, -0.70f), new Vector2(1.65f, 0.76f), new Color32(250, 179, 135, 255), Ink, 7, 180f);
                    TokenPetProceduralArt.Outlined(furnitureRoot, "Table", TokenPetShape.Square,
                        new Vector2(0f, -0.41f), new Vector2(1.35f, 0.16f), new Color32(91, 61, 40, 255), Ink, 12);
                    Dot(furnitureRoot, new Vector2(-0.24f, -0.27f), 0.16f, new Color32(254, 100, 11, 255), 14);
                    TokenPetProceduralArt.Outlined(furnitureRoot, "Tea", TokenPetShape.Square,
                        new Vector2(0.30f, -0.27f), new Vector2(0.18f, 0.16f), Cream, Ink, 14);
                    TokenPetProceduralArt.Line(furnitureRoot, "Steam1", new Vector2(0.26f, -0.16f), new Vector2(0.20f, 0.08f), 0.025f, Color.white, 16);
                    TokenPetProceduralArt.Line(furnitureRoot, "Steam2", new Vector2(0.34f, -0.16f), new Vector2(0.40f, 0.06f), 0.025f, Color.white, 16);
                    break;
                default:
                    TokenPetProceduralArt.Outlined(furnitureRoot, "Memo", TokenPetShape.Square,
                        new Vector2(0.72f, -0.30f), new Vector2(0.70f, 0.70f), new Color32(249, 226, 175, 255), Ink, 20, -5f);
                    TokenPetProceduralArt.Line(furnitureRoot, "MemoLine", new Vector2(0.51f, -0.20f), new Vector2(0.89f, -0.20f), 0.035f, Ink, 22);
                    break;
            }
        }

        private void AnimateFurniture(float time)
        {
            if (string.IsNullOrEmpty(builtFurniture))
                return;
            if (builtFurniture == "futon")
            {
                Transform quilt = furnitureRoot.Find("Quilt");
                if (quilt != null)
                    quilt.localScale = new Vector3(1f + Mathf.Sin(time * 2f) * 0.012f,
                        1f + Mathf.Sin(time * 2f) * 0.025f, 1f);
            }
            else if (builtFurniture == "laptop")
            {
                Transform cursor = furnitureRoot.Find("LaptopCursor");
                if (cursor != null)
                    cursor.gameObject.SetActive(Mathf.Repeat(time, 0.65f) < 0.36f);
                Transform screen = furnitureRoot.Find("Screen");
                if (screen != null)
                    screen.localRotation = Quaternion.Euler(0f, 0f, -5f + Mathf.Sin(time * 1.8f) * 0.7f);
            }
            else if (builtFurniture == "trampoline")
            {
                Transform mat = furnitureRoot.Find("Mat");
                if (mat != null)
                {
                    float depress = (state == "fall" || state == "backflip")
                        ? Mathf.Abs(Mathf.Sin(time * 9f)) * 0.13f : 0f;
                    mat.localScale = new Vector3(1f + depress * 0.35f, 1f - depress, 1f);
                }
                Transform wave = furnitureRoot.Find("Shockwave");
                if (wave != null)
                {
                    bool activeWave = state == "fall" || state == "backflip";
                    wave.gameObject.SetActive(activeWave);
                    float pulse = 0.75f + Mathf.Repeat(time * 1.7f, 1f) * 0.75f;
                    wave.localScale = Vector3.one * pulse;
                }
            }
            else if (builtFurniture == "night_lamp")
            {
                Transform glow = furnitureRoot.Find("LampGlow");
                if (glow != null)
                {
                    float pulse = 1f + Mathf.Sin(time * 2.2f) * 0.10f;
                    glow.localScale = Vector3.one * pulse;
                    SpriteRenderer renderer = glow.GetComponent<SpriteRenderer>();
                    if (renderer != null)
                        renderer.color = new Color(1f, 0.88f, 0.40f,
                            0.18f + (Mathf.Sin(time * 2.2f) + 1f) * 0.06f);
                }
            }
            else if (builtFurniture == "lazy_sofa")
            {
                Transform seat = furnitureRoot.Find("Seat");
                if (seat != null)
                    seat.localScale = new Vector3(1f + Mathf.Sin(time * 1.7f) * 0.02f,
                        1f - Mathf.Sin(time * 1.7f) * 0.025f, 1f);
            }
            else if (builtFurniture == "pixel_tv")
            {
                Transform screen = furnitureRoot.Find("Screen");
                if (screen != null)
                {
                    Color[] channels =
                    {
                        new Color32(30, 30, 46, 255), new Color32(40, 75, 96, 255),
                        new Color32(82, 54, 86, 255), new Color32(71, 80, 60, 255)
                    };
                    screen.GetComponent<SpriteRenderer>().color = channels[(int)(time / 4f) % channels.Length];
                }
                Transform label = furnitureRoot.Find("TvChannel");
                if (label != null)
                {
                    TextMesh mesh = label.GetComponent<TextMesh>();
                    string[] programs = { "• • 🍠", "26°C", "♥", "▥▥▥" };
                    mesh.text = programs[(int)(time / 4f) % programs.Length];
                }
            }
            else if (builtFurniture == "kotatsu")
            {
                Transform steam1 = furnitureRoot.Find("Steam1");
                Transform steam2 = furnitureRoot.Find("Steam2");
                if (steam1 != null)
                    steam1.localPosition = new Vector3(Mathf.Sin(time * 2.8f) * 0.035f, Mathf.Repeat(time * 0.12f, 0.10f), 0f);
                if (steam2 != null)
                    steam2.localPosition = new Vector3(Mathf.Cos(time * 2.5f) * 0.035f, Mathf.Repeat(time * 0.11f, 0.10f), 0f);
            }
            else if (builtFurniture == "succulent_pot")
            {
                for (int i = 0; i < 5; i++)
                {
                    Transform leaf = furnitureRoot.Find($"Leaf{i}");
                    if (leaf != null)
                        leaf.localRotation = Quaternion.Euler(0f, 0f,
                            (i - 2) * 20f + Mathf.Sin(time * 1.8f + i) * 3f);
                }
            }
        }

        private void BuildCoffee()
        {
            TokenPetProceduralArt.Outlined(coffeeRoot, "Cup", TokenPetShape.Square,
                Vector2.zero, new Vector2(0.38f, 0.38f), Cream, Ink, 31);
            TokenPetProceduralArt.Outlined(coffeeRoot, "Handle", TokenPetShape.Circle,
                new Vector2(0.24f, 0f), new Vector2(0.20f, 0.23f), Cream, Ink, 30);
            TokenPetProceduralArt.Line(coffeeRoot, "Steam1", new Vector2(-0.08f, 0.22f), new Vector2(-0.02f, 0.48f), 0.035f, Cream, 34);
            TokenPetProceduralArt.Line(coffeeRoot, "Steam2", new Vector2(0.08f, 0.22f), new Vector2(0.15f, 0.43f), 0.035f, Cream, 34);
        }

        private void BuildBalloon()
        {
            TokenPetProceduralArt.Outlined(balloonRoot, "Balloon", TokenPetShape.Circle,
                new Vector2(0.92f, 1.35f), new Vector2(0.72f, 0.88f), Pink, Ink, 31);
            TokenPetProceduralArt.Shape(balloonRoot, "Tie", TokenPetShape.Triangle,
                new Vector2(0.92f, 0.88f), new Vector2(0.18f, 0.16f), Pink, 31, 180f);
            TokenPetProceduralArt.Line(balloonRoot, "String", new Vector2(0.92f, 0.86f), new Vector2(0.62f, -0.12f), 0.025f, Ink, 29);
        }

        private void BuildBoard()
        {
            TokenPetProceduralArt.Outlined(boardRoot, "Board", TokenPetShape.Square,
                new Vector2(0f, 1.52f), new Vector2(2.40f, 0.62f), Cream, Ink, 40);
            boardText = new GameObject("BoardText").AddComponent<TextMesh>();
            boardText.transform.SetParent(boardRoot, false);
            boardText.transform.localPosition = new Vector3(0f, 1.50f, 0f);
            boardText.anchor = TextAnchor.MiddleCenter;
            boardText.alignment = TextAlignment.Center;
            boardText.fontSize = 34;
            boardText.characterSize = 0.035f;
            boardText.color = Ink;
            boardText.GetComponent<MeshRenderer>().sortingOrder = 42;
            try
            {
                Font font = Font.CreateDynamicFontFromOSFont(
                    new[] { "Microsoft JhengHei UI", "Microsoft JhengHei", "Arial" }, 34);
                if (font != null)
                {
                    boardText.font = font;
                    boardText.GetComponent<MeshRenderer>().sharedMaterial = font.material;
                }
            }
            catch (Exception) { }
        }

        private void BuildRabbit()
        {
            Dot(rabbitRoot, Vector2.zero, 0.42f, Cream, 43);
            TokenPetProceduralArt.Outlined(rabbitRoot, "EarL", TokenPetShape.Circle,
                new Vector2(-0.12f, 0.28f), new Vector2(0.14f, 0.42f), Cream, Ink, 42, -8f);
            TokenPetProceduralArt.Outlined(rabbitRoot, "EarR", TokenPetShape.Circle,
                new Vector2(0.12f, 0.28f), new Vector2(0.14f, 0.42f), Cream, Ink, 42, 8f);
            Dot(rabbitRoot, new Vector2(-0.08f, 0.03f), 0.055f, Ink, 45);
            Dot(rabbitRoot, new Vector2(0.08f, 0.03f), 0.055f, Ink, 45);
        }

        private void BuildParticlePool(Transform parent)
        {
            Transform root = NewRoot(parent, "Legacy_Particles");
            for (int i = 0; i < 18; i++)
            {
                GameObject particle = TokenPetProceduralArt.Shape(root, $"Particle_{i}",
                    i % 5 == 0 ? TokenPetShape.Star : TokenPetShape.Circle,
                    Vector2.zero, Vector2.one * 0.10f, Color.white, 36);
                particles.Add(particle.GetComponent<SpriteRenderer>());
            }
        }

        private void UpdateBodyTint(float time)
        {
            if (bodyRenderer == null)
                return;
            Color tint = Color.white;
            if (Has("spicy"))
                tint = Color.Lerp(Color.white, new Color32(255, 115, 95, 255), 0.42f + Mathf.Sin(time * 13f) * 0.08f);
            else if (Has("ice"))
                tint = Color.Lerp(Color.white, new Color32(158, 224, 255, 255), 0.48f);
            else if (accessory == "rainbow")
                tint = Color.HSVToRGB(Mathf.Repeat(time * 0.10f, 1f), 0.22f, 1f);
            else if (overtime)
                tint = Color.Lerp(Color.white, new Color32(207, 186, 235, 255), 0.20f);
            bodyRenderer.color = tint;
        }

        private void UpdateParticles(float time)
        {
            string kind = PrimaryEffect();
            bool active = !string.IsNullOrEmpty(kind) || accessory == "clover_sprout" ||
                accessory == "char_mask" || accessory == "crown" || accessory == "rainbow";
            for (int i = 0; i < particles.Count; i++)
            {
                SpriteRenderer particle = particles[i];
                particle.enabled = active && i < (kind == "fever" ? 12 : 18);
                if (!particle.enabled)
                    continue;
                float phase = time * (kind == "spicy" ? 2.7f : 1.25f) + i * 0.67f;
                float lane = ((i % 6) - 2.5f) * 0.34f;
                float rise = Mathf.Repeat(phase + i * 0.13f, 2.4f) - 0.9f;
                particle.transform.localPosition = new Vector3(
                    lane + Mathf.Sin(phase * 1.7f) * 0.10f,
                    rise,
                    0f);
                float pulse = 0.07f + (Mathf.Sin(phase * 3f) + 1f) * 0.025f;
                particle.transform.localScale = Vector3.one * pulse;
                particle.color = ParticleColor(kind, i);
            }
        }

        private string PrimaryEffect()
        {
            foreach (string candidate in new[] { "spicy", "ice", "fever", "bubble_tea", "candy", "matcha", "coffee", "singing" })
                if (Has(candidate)) return candidate;
            return "";
        }

        private bool Has(string effect)
        {
            foreach (string value in effects.Split(','))
                if (string.Equals(value.Trim(), effect, StringComparison.OrdinalIgnoreCase))
                    return true;
            return false;
        }

        private static Color ParticleColor(string kind, int index)
        {
            return kind switch
            {
                "spicy" => index % 2 == 0 ? new Color32(255, 82, 72, 255) : Gold,
                "ice" => index % 2 == 0 ? Blue : Color.white,
                "fever" => index % 2 == 0 ? Pink : new Color32(255, 105, 125, 255),
                "bubble_tea" => index % 2 == 0 ? Blue : Green,
                "candy" => index % 3 == 0 ? Pink : (index % 3 == 1 ? Blue : Gold),
                "matcha" => index % 2 == 0 ? Green : Cream,
                "singing" => index % 2 == 0 ? Pink : Gold,
                _ => index % 2 == 0 ? Gold : Cream,
            };
        }

        private static void Dot(Transform parent, Vector2 position, float size, Color color, int order)
        {
            TokenPetProceduralArt.Shape(parent, "Dot", TokenPetShape.Circle,
                position, Vector2.one * size, color, order);
        }

        private static void Clear(Transform root)
        {
            for (int index = root.childCount - 1; index >= 0; index--)
            {
                GameObject child = root.GetChild(index).gameObject;
                child.SetActive(false);
                Destroy(child);
            }
        }
    }
}
