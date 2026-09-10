using UnityEngine;

namespace TokenPet
{
    /// <summary>
    /// Runtime facial rig built from a small set of reusable shapes.  It keeps
    /// gaze, blink, brows, and mouth independent from the painted body layer.
    /// </summary>
    public sealed class TokenPetExpressionRig : MonoBehaviour
    {
        private static readonly Color FaceColor = new Color32(65, 27, 15, 255);
        private static readonly Color TongueColor = new Color32(255, 116, 105, 255);
        private static readonly Color BlushColor = new Color32(255, 111, 92, 205);

        private Transform faceRoot;
        private Transform leftEyeRoot;
        private Transform rightEyeRoot;
        private LineRenderer leftEye;
        private LineRenderer rightEye;
        private LineRenderer leftHighlight;
        private LineRenderer rightHighlight;
        private LineRenderer mouthFill;
        private LineRenderer tongue;
        private LineRenderer leftBrow;
        private LineRenderer rightBrow;
        private LineRenderer leftBlush;
        private LineRenderer rightBlush;
        private LineRenderer philtrum;
        private LineRenderer mouthLine;
        private LineRenderer leftCrossA;
        private LineRenderer leftCrossB;
        private LineRenderer rightCrossA;
        private LineRenderer rightCrossB;
        private LineRenderer leftStar;
        private LineRenderer rightStar;
        private Material lineMaterial;
        private float nextBlinkAt;
        private float blinkStartedAt = -10f;
        private string previousLegacyState = "";
        private float legacyStateStartedAt;

        public bool FaceVisible { get; private set; } = true;

        public void Initialize()
        {
            Shader shader = Shader.Find("Sprites/Default");
            if (shader == null)
            {
                Debug.LogWarning("Sprites/Default shader unavailable; expression rig disabled.");
                enabled = false;
                return;
            }

            lineMaterial = new Material(shader)
            {
                name = "TokenPet Face Line Material",
                color = Color.white
            };
            faceRoot = new GameObject("FaceRoot").transform;
            faceRoot.SetParent(transform, false);
            faceRoot.localPosition = new Vector3(0f, 0f, -0.05f);

            leftEyeRoot = CreateEye("Eye_Left", out leftEye, out leftHighlight);
            rightEyeRoot = CreateEye("Eye_Right", out rightEye, out rightHighlight);
            leftBrow = CreateLine("Brow_Left", 0.050f, 24);
            rightBrow = CreateLine("Brow_Right", 0.050f, 24);
            leftBlush = CreateLine("Blush_Left", 0.18f, 22, null, BlushColor);
            rightBlush = CreateLine("Blush_Right", 0.18f, 22, null, BlushColor);
            SetBlush(leftBlush, -0.52f);
            SetBlush(rightBlush, 0.52f);
            philtrum = CreateLine("Philtrum", 0.060f, 25);
            mouthLine = CreateLine("Mouth_Line", 0.060f, 25);

            leftCrossA = CreateLine("Eye_Left_X_A", 0.060f, 25);
            leftCrossB = CreateLine("Eye_Left_X_B", 0.060f, 25);
            rightCrossA = CreateLine("Eye_Right_X_A", 0.060f, 25);
            rightCrossB = CreateLine("Eye_Right_X_B", 0.060f, 25);
            leftStar = CreateLine("Eye_Left_Star", 0.052f, 25);
            rightStar = CreateLine("Eye_Right_Star", 0.052f, 25);

            mouthFill = CreateLine("Mouth_Open", 0.060f, 25);
            tongue = CreateLine("Tongue", 0.045f, 26, null, TongueColor);
            ScheduleBlink();
            ApplyExpression("idle", 0f, Vector2.zero);
        }

        public void ApplyExpression(
            string state,
            float stateTime,
            Vector2 look,
            string emotion = "normal",
            string mouthState = "normal",
            string legacyState = "idle",
            float satiety = 100f)
        {
            if (!enabled || faceRoot == null)
                return;

            string expression = (state ?? "idle").ToLowerInvariant();
            string sourceState = (legacyState ?? "idle").ToLowerInvariant();
            if (sourceState != previousLegacyState)
            {
                previousLegacyState = sourceState;
                legacyStateStartedAt = Time.unscaledTime;
            }
            float sourceStateTime = Time.unscaledTime - legacyStateStartedAt;
            bool faceVisible = sourceState != "back_idle";
            float faceYawScale = 1f;
            if (sourceState == "turn_to_back")
            {
                float progress = Mathf.Clamp01(sourceStateTime / 0.25f);
                faceYawScale = Mathf.Max(0.04f, Mathf.Cos(progress * Mathf.PI * 0.5f));
                faceVisible = progress < 0.96f;
            }
            else if (sourceState == "turn_to_front")
            {
                float progress = Mathf.Clamp01(sourceStateTime / 0.25f);
                faceYawScale = Mathf.Max(0.04f, Mathf.Sin(progress * Mathf.PI * 0.5f));
                faceVisible = progress > 0.04f;
            }
            else if (sourceState == "work_laptop" ||
                     sourceState == "watch_tv" ||
                     sourceState == "water_plant")
            {
                faceYawScale = 0.68f;
            }
            FaceVisible = faceVisible;
            faceRoot.gameObject.SetActive(faceVisible);
            if (!faceVisible)
                return;
            faceRoot.localScale = new Vector3(faceYawScale, 1f, 1f);

            bool motionOwnsFace = expression == "poke" || expression == "drag" ||
                expression == "airborne" || expression == "land";
            if (!motionOwnsFace)
            {
                string sourceEmotion = (emotion ?? "normal").ToLowerInvariant();
                if (sourceState == "sleep" || sourceState == "sleep_futon")
                    expression = "sleep";
                else if (satiety <= 20f && sourceEmotion == "normal")
                    expression = "hungry";
                else if (sourceEmotion == "happy" || sourceEmotion == "blink" ||
                         sourceEmotion == "dizzy" || sourceEmotion == "star")
                    expression = sourceEmotion;
            }
            Vector2 gaze = Vector2.ClampMagnitude(look, 1f);
            float blink = expression == "idle" || expression == "walk"
                ? UpdateBlink()
                : 0f;
            Vector2 eyeScale = new(1f, Mathf.Max(0.07f, 1f - blink * 0.95f));
            Vector2 eyeOffset = new(gaze.x * 0.045f, gaze.y * 0.030f);

            SetCrossEyes(false);
            SetStarEyes(false);
            SetNormalEyes(true);
            SetRoundEyeShape();
            SetBrowsVisible(true);
            ShowOpenMouth(false, 0f, 0f, false);
            mouthLine.enabled = true;
            philtrum.enabled = true;
            SetPhiltrum(-0.15f);
            faceRoot.localPosition = new Vector3(gaze.x * 0.018f, gaze.y * 0.008f, -0.05f);

            switch (expression)
            {
                case "walk":
                    float step = Mathf.Sin(stateTime * 8.6f);
                    eyeScale.y *= 0.82f + Mathf.Abs(step) * 0.18f;
                    SetBrows(0.015f, -4f, 4f);
                    SetDorkyCatMouth(0.15f, 0.078f + Mathf.Abs(step) * 0.008f);
                    break;

                case "poke":
                    float surprise = Mathf.Sin(Mathf.Clamp01(stateTime / 0.72f) * Mathf.PI);
                    eyeScale = Vector2.one * (1f + surprise * 0.40f);
                    eyeOffset = Vector2.zero;
                    SetBrows(0.08f * surprise, 10f, -10f);
                    mouthLine.enabled = false;
                    SetPhiltrum(-0.105f);
                    ShowOpenMouth(true, 0.10f + surprise * 0.06f, 0.13f + surprise * 0.08f, false);
                    break;

                case "drag":
                    eyeScale.y = 0.63f;
                    SetBrows(0.025f, -17f, 17f);
                    SetWorryMouth(stateTime);
                    break;

                case "airborne":
                    SetNormalEyes(false);
                    SetCrossEyes(true);
                    SetBrows(0.055f, 13f, -13f);
                    philtrum.enabled = false;
                    mouthLine.enabled = false;
                    ShowOpenMouth(true, 0.16f, 0.22f, true);
                    break;

                case "land":
                    float recover = Mathf.Clamp01(stateTime / 0.68f);
                    eyeScale.y = Mathf.Lerp(0.08f, 1f, Mathf.SmoothStep(0f, 1f, recover));
                    SetBrows(Mathf.Lerp(-0.035f, 0f, recover), -12f * (1f - recover), 12f * (1f - recover));
                    if (recover < 0.62f)
                        SetFlatMouth(Mathf.Lerp(0.14f, 0.10f, recover));
                    else
                        SetDorkyCatMouth(0.15f, 0.078f);
                    break;

                case "happy":
                    SetHappyEyeShape();
                    SetBrowsVisible(false);
                    SetDorkyCatMouth(0.16f, 0.088f);
                    break;

                case "blink":
                    SetClosedEyeShape();
                    SetBrows(0.005f, -3f, 3f);
                    SetDorkyCatMouth(0.15f, 0.074f);
                    break;

                case "dizzy":
                    SetNormalEyes(false);
                    SetCrossEyes(true);
                    SetBrowsVisible(false);
                    SetWorryMouth(stateTime);
                    break;

                case "star":
                    SetNormalEyes(false);
                    SetStarEyes(true);
                    SetBrowsVisible(false);
                    mouthLine.enabled = false;
                    SetPhiltrum(-0.105f);
                    ShowOpenMouth(true, 0.14f, 0.17f, true);
                    break;

                case "sleep":
                    SetClosedEyeShape();
                    SetBrowsVisible(false);
                    eyeScale.y = 0.85f;
                    SetDorkyCatMouth(0.12f, 0.052f);
                    break;

                case "hungry":
                    eyeScale.y = 0.56f;
                    SetBrows(-0.025f, 15f, -15f);
                    SetWorryMouth(stateTime * 0.28f);
                    break;

                default:
                    SetBrows(0f, -3f + gaze.y * 2f, 3f - gaze.y * 2f);
                    float smilePulse = (Mathf.Sin(stateTime * 2.15f) + 1f) * 0.5f;
                    SetDorkyCatMouth(0.15f, 0.078f + smilePulse * 0.006f);
                    break;
            }

            if (!motionOwnsFace &&
                string.Equals(mouthState, "open", System.StringComparison.OrdinalIgnoreCase) &&
                expression != "sleep" && expression != "star")
            {
                mouthLine.enabled = false;
                SetPhiltrum(-0.105f);
                ShowOpenMouth(true, 0.13f, 0.16f, expression == "happy");
            }

            ApplyEyePose(leftEyeRoot, new Vector2(-0.31f, 0.10f) + eyeOffset, eyeScale);
            ApplyEyePose(rightEyeRoot, new Vector2(0.31f, 0.10f) + eyeOffset, eyeScale);
        }

        private Transform CreateEye(
            string eyeName,
            out LineRenderer eyeRenderer,
            out LineRenderer highlightRenderer)
        {
            Transform root = new GameObject(eyeName).transform;
            root.SetParent(faceRoot, false);
            eyeRenderer = CreateLine(eyeName + "_Dark", 0.145f, 23, root);
            eyeRenderer.positionCount = 2;
            eyeRenderer.SetPosition(0, new Vector3(0f, -0.055f, 0f));
            eyeRenderer.SetPosition(1, new Vector3(0f, 0.055f, 0f));

            highlightRenderer = CreateLine(
                eyeName + "_Highlight", 0.040f, 24, root, Color.white);
            highlightRenderer.positionCount = 2;
            highlightRenderer.SetPosition(0, new Vector3(-0.025f, 0.038f, 0f));
            highlightRenderer.SetPosition(1, new Vector3(-0.024f, 0.039f, 0f));
            return root;
        }

        private static void SetBlush(LineRenderer blush, float centerX)
        {
            blush.loop = false;
            blush.positionCount = 2;
            blush.SetPosition(0, new Vector3(centerX - 0.085f, -0.10f, 0f));
            blush.SetPosition(1, new Vector3(centerX + 0.085f, -0.10f, 0f));
        }

        private LineRenderer CreateLine(
            string lineName,
            float width,
            int sortingOrder,
            Transform parent = null,
            Color? color = null)
        {
            GameObject lineObject = new(lineName);
            lineObject.transform.SetParent(parent != null ? parent : faceRoot, false);
            LineRenderer line = lineObject.AddComponent<LineRenderer>();
            Color lineColor = color ?? FaceColor;
            line.useWorldSpace = false;
            line.alignment = LineAlignment.TransformZ;
            line.textureMode = LineTextureMode.Stretch;
            line.startWidth = width;
            line.endWidth = width;
            line.numCapVertices = 8;
            line.numCornerVertices = 8;
            line.sortingOrder = sortingOrder;
            line.sharedMaterial = lineMaterial;
            line.startColor = lineColor;
            line.endColor = lineColor;
            return line;
        }

        private void SetRoundEyeShape()
        {
            SetEyeStroke(leftEye, new Vector2(0f, -0.055f), new Vector2(0f, 0.055f), 0.145f);
            SetEyeStroke(rightEye, new Vector2(0f, -0.055f), new Vector2(0f, 0.055f), 0.145f);
            leftHighlight.enabled = true;
            rightHighlight.enabled = true;
        }

        private void SetClosedEyeShape()
        {
            SetEyeStroke(leftEye, new Vector2(-0.085f, 0f), new Vector2(0.085f, 0f), 0.060f);
            SetEyeStroke(rightEye, new Vector2(-0.085f, 0f), new Vector2(0.085f, 0f), 0.060f);
            leftHighlight.enabled = false;
            rightHighlight.enabled = false;
        }

        private void SetHappyEyeShape()
        {
            SetHappyArc(leftEye);
            SetHappyArc(rightEye);
            leftHighlight.enabled = false;
            rightHighlight.enabled = false;
        }

        private static void SetEyeStroke(
            LineRenderer line, Vector2 start, Vector2 end, float width)
        {
            line.enabled = true;
            line.loop = false;
            line.positionCount = 2;
            line.startWidth = width;
            line.endWidth = width;
            line.SetPosition(0, start);
            line.SetPosition(1, end);
        }

        private static void SetHappyArc(LineRenderer line)
        {
            line.enabled = true;
            line.loop = false;
            line.positionCount = 5;
            line.startWidth = 0.060f;
            line.endWidth = 0.060f;
            for (int index = 0; index < 5; index++)
            {
                float normalized = index / 4f;
                float x = Mathf.Lerp(-0.10f, 0.10f, normalized);
                float y = Mathf.Sin(normalized * Mathf.PI) * 0.065f;
                line.SetPosition(index, new Vector3(x, y, 0f));
            }
        }

        private void SetBrowsVisible(bool visible)
        {
            leftBrow.enabled = visible;
            rightBrow.enabled = visible;
        }

        private void SetStarEyes(bool visible)
        {
            leftStar.enabled = visible;
            rightStar.enabled = visible;
            if (!visible)
                return;
            SetStar(leftStar, new Vector2(-0.31f, 0.10f), 0.13f);
            SetStar(rightStar, new Vector2(0.31f, 0.10f), 0.13f);
        }

        private static void SetStar(LineRenderer line, Vector2 center, float radius)
        {
            const int points = 10;
            line.loop = true;
            line.positionCount = points;
            for (int index = 0; index < points; index++)
            {
                float angle = Mathf.PI * 0.5f + index * Mathf.PI / 5f;
                float pointRadius = index % 2 == 0 ? radius : radius * 0.43f;
                line.SetPosition(index, center + new Vector2(
                    Mathf.Cos(angle) * pointRadius,
                    Mathf.Sin(angle) * pointRadius));
            }
        }

        private void SetBrows(float lift, float leftTilt, float rightTilt)
        {
            SetBrow(leftBrow, new Vector2(-0.31f, 0.35f + lift), leftTilt);
            SetBrow(rightBrow, new Vector2(0.31f, 0.35f + lift), rightTilt);
        }

        private static void SetBrow(LineRenderer line, Vector2 center, float tilt)
        {
            float radians = tilt * Mathf.Deg2Rad;
            Vector2 along = new(Mathf.Cos(radians), Mathf.Sin(radians));
            Vector2 normal = new(-along.y, along.x);
            line.positionCount = 5;
            line.loop = false;
            for (int index = 0; index < 5; index++)
            {
                float normalized = index / 4f;
                float across = Mathf.Lerp(-0.10f, 0.10f, normalized);
                float arch = Mathf.Sin(normalized * Mathf.PI) * 0.025f;
                line.SetPosition(index, center + along * across + normal * arch);
            }
        }

        private void SetPhiltrum(float endY)
        {
            philtrum.loop = false;
            philtrum.positionCount = 3;
            philtrum.SetPosition(0, new Vector3(0f, 0.015f, 0f));
            philtrum.SetPosition(1, new Vector3(-0.004f, Mathf.Lerp(0.015f, endY, 0.56f), 0f));
            philtrum.SetPosition(2, new Vector3(0f, endY, 0f));
        }

        private void SetDorkyCatMouth(float halfWidth, float depth)
        {
            mouthLine.loop = false;
            mouthLine.positionCount = 5;
            mouthLine.SetPosition(0, new Vector3(-halfWidth, -0.165f, 0f));
            mouthLine.SetPosition(1, new Vector3(-halfWidth * 0.64f, -0.15f - depth, 0f));
            mouthLine.SetPosition(2, new Vector3(0f, -0.15f, 0f));
            mouthLine.SetPosition(3, new Vector3(halfWidth * 0.64f, -0.15f - depth, 0f));
            mouthLine.SetPosition(4, new Vector3(halfWidth, -0.165f, 0f));
        }

        private void SetSmileMouth(float halfWidth, float depth)
        {
            mouthLine.loop = false;
            mouthLine.positionCount = 5;
            for (int index = 0; index < 5; index++)
            {
                float normalized = index / 4f;
                float x = Mathf.Lerp(-halfWidth, halfWidth, normalized);
                float y = -0.14f - Mathf.Sin(normalized * Mathf.PI) * depth;
                mouthLine.SetPosition(index, new Vector3(x, y, 0f));
            }
        }

        private void SetWorryMouth(float time)
        {
            mouthLine.loop = false;
            mouthLine.positionCount = 5;
            for (int index = 0; index < 5; index++)
            {
                float x = Mathf.Lerp(-0.14f, 0.14f, index / 4f);
                float y = -0.18f + Mathf.Sin(index * Mathf.PI + time * 7f) * 0.025f;
                mouthLine.SetPosition(index, new Vector3(x, y, 0f));
            }
        }

        private void SetFlatMouth(float halfWidth)
        {
            mouthLine.loop = false;
            mouthLine.positionCount = 3;
            mouthLine.SetPosition(0, new Vector3(-halfWidth, -0.18f, 0f));
            mouthLine.SetPosition(1, new Vector3(0f, -0.20f, 0f));
            mouthLine.SetPosition(2, new Vector3(halfWidth, -0.18f, 0f));
        }

        private void ShowOpenMouth(bool visible, float width, float height, bool showTongue)
        {
            mouthFill.enabled = visible;
            tongue.enabled = visible && showTongue;
            if (!visible)
                return;

            const int segments = 16;
            mouthFill.loop = true;
            mouthFill.positionCount = segments;
            for (int index = 0; index < segments; index++)
            {
                float angle = index / (float)segments * Mathf.PI * 2f;
                mouthFill.SetPosition(index, new Vector3(
                    Mathf.Cos(angle) * width * 0.50f,
                    -0.18f + Mathf.Sin(angle) * height * 0.50f,
                    0f));
            }

            if (showTongue)
            {
                tongue.loop = false;
                tongue.positionCount = 3;
                tongue.SetPosition(0, new Vector3(-width * 0.22f, -0.18f - height * 0.16f, 0f));
                tongue.SetPosition(1, new Vector3(0f, -0.18f - height * 0.24f, 0f));
                tongue.SetPosition(2, new Vector3(width * 0.22f, -0.18f - height * 0.16f, 0f));
            }
        }

        private void SetNormalEyes(bool visible)
        {
            leftEye.enabled = visible;
            rightEye.enabled = visible;
            leftHighlight.enabled = visible;
            rightHighlight.enabled = visible;
        }

        private void SetCrossEyes(bool visible)
        {
            leftCrossA.enabled = visible;
            leftCrossB.enabled = visible;
            rightCrossA.enabled = visible;
            rightCrossB.enabled = visible;
            if (!visible)
                return;

            SetCross(leftCrossA, leftCrossB, new Vector2(-0.31f, 0.10f), 0.105f);
            SetCross(rightCrossA, rightCrossB, new Vector2(0.31f, 0.10f), 0.105f);
        }

        private static void SetCross(
            LineRenderer first,
            LineRenderer second,
            Vector2 center,
            float radius)
        {
            first.positionCount = 2;
            second.positionCount = 2;
            first.SetPosition(0, center + new Vector2(-radius, -radius));
            first.SetPosition(1, center + new Vector2(radius, radius));
            second.SetPosition(0, center + new Vector2(-radius, radius));
            second.SetPosition(1, center + new Vector2(radius, -radius));
        }

        private static void ApplyEyePose(Transform root, Vector2 position, Vector2 scale)
        {
            root.localPosition = new Vector3(position.x, position.y, 0f);
            root.localScale = new Vector3(scale.x, scale.y, 1f);
        }

        private float UpdateBlink()
        {
            float now = Time.unscaledTime;
            if (now >= nextBlinkAt)
            {
                blinkStartedAt = now;
                ScheduleBlink();
            }

            float elapsed = now - blinkStartedAt;
            if (elapsed < 0f || elapsed > 0.16f)
                return 0f;
            return Mathf.Sin(elapsed / 0.16f * Mathf.PI);
        }

        private void ScheduleBlink()
        {
            nextBlinkAt = Time.unscaledTime + Random.Range(1.7f, 4.2f);
        }

        private void OnDestroy()
        {
            if (lineMaterial != null)
                Destroy(lineMaterial);
        }
    }
}
