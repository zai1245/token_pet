using UnityEngine;

namespace TokenPet
{
    /// <summary>
    /// A tiny procedural rig for the four noodle limbs.  The painted body stays
    /// intact while pose changes are computed at runtime, so adding an action
    /// does not require exporting another full-body animation sheet.
    /// </summary>
    public sealed class TokenPetLimbRig : MonoBehaviour
    {
        private static readonly Color LimbColor = new Color32(82, 35, 17, 255);

        private LineRenderer leftArm;
        private LineRenderer rightArm;
        private LineRenderer leftLeg;
        private LineRenderer rightLeg;
        private Material limbMaterial;

        public void Initialize()
        {
            Shader shader = Shader.Find("Sprites/Default");
            if (shader == null)
            {
                Debug.LogWarning("Sprites/Default shader unavailable; procedural limbs disabled.");
                enabled = false;
                return;
            }

            limbMaterial = new Material(shader)
            {
                name = "TokenPet Noodle Limb Material",
                color = LimbColor
            };

            leftArm = CreateLimb("Arm_Left", 0.125f);
            rightArm = CreateLimb("Arm_Right", 0.125f);
            leftLeg = CreateLimb("Leg_Left", 0.140f);
            rightLeg = CreateLimb("Leg_Right", 0.140f);
            ApplyPose("idle", 0f, Vector2.zero, Vector2.zero);
        }

        public void ApplyPose(string state, float time, Vector2 pointerVelocity, Vector2 look)
        {
            if (!enabled || leftArm == null)
                return;

            float armLeft = 218f;
            float armRight = -38f;
            float armLeftBend = -8f;
            float armRightBend = 8f;
            float legLeft = -99f;
            float legRight = -81f;
            float legLeftBend = 8f;
            float legRightBend = -8f;

            switch ((state ?? "idle").ToLowerInvariant())
            {
                case "walk":
                    float stride = Mathf.Sin(time * 8.6f) * 18f;
                    armLeft -= stride * 0.55f;
                    armRight -= stride * 0.55f;
                    legLeft += stride;
                    legRight -= stride;
                    legLeftBend = 13f + Mathf.Max(0f, -stride) * 0.38f;
                    legRightBend = -13f - Mathf.Max(0f, stride) * 0.38f;
                    break;

                case "poke":
                    float recoil = Mathf.Sin(Mathf.Clamp01(time / 0.72f) * Mathf.PI);
                    armLeft = Mathf.Lerp(218f, 162f, recoil);
                    armRight = Mathf.Lerp(-38f, 18f, recoil);
                    armLeftBend = -18f * recoil;
                    armRightBend = 18f * recoil;
                    legLeft -= recoil * 11f;
                    legRight += recoil * 11f;
                    break;

                case "drag":
                    float dragSwing = Mathf.Clamp(pointerVelocity.x / 70f, -18f, 18f);
                    armLeft = 126f - dragSwing;
                    armRight = 54f - dragSwing;
                    armLeftBend = -14f;
                    armRightBend = 14f;
                    legLeft = -98f + Mathf.Sin(time * 7f) * 8f;
                    legRight = -82f + Mathf.Sin(time * 7f + Mathf.PI) * 8f;
                    break;

                case "airborne":
                    float flutter = Mathf.Sin(time * 11f) * 8f;
                    armLeft = 166f + flutter;
                    armRight = 14f + flutter;
                    armLeftBend = -16f;
                    armRightBend = 16f;
                    legLeft = -126f - flutter * 0.35f;
                    legRight = -54f - flutter * 0.35f;
                    legLeftBend = 18f;
                    legRightBend = -18f;
                    break;

                case "land":
                    float settle = Mathf.Exp(-5.0f * time) * Mathf.Cos(time * 18f);
                    armLeft = 188f - settle * 20f;
                    armRight = -8f - settle * 20f;
                    legLeft = -132f + settle * 9f;
                    legRight = -48f - settle * 9f;
                    legLeftBend = 23f;
                    legRightBend = -23f;
                    break;

                default:
                    float idleSway = Mathf.Sin(time * 2.15f) * 5f;
                    float glance = look.x * 3.5f;
                    armLeft += idleSway + glance;
                    armRight += idleSway + glance;
                    legLeft += idleSway * 0.22f;
                    legRight += idleSway * 0.22f;
                    break;
            }

            SetLimb(leftArm, new Vector2(-0.86f, -0.05f), armLeft, armLeftBend, 0.15f, 0.12f);
            SetLimb(rightArm, new Vector2(0.86f, -0.05f), armRight, armRightBend, 0.15f, 0.12f);
            SetLimb(leftLeg, new Vector2(-0.38f, -0.90f), legLeft, legLeftBend, 0.12f, 0.11f);
            SetLimb(rightLeg, new Vector2(0.38f, -0.90f), legRight, legRightBend, 0.12f, 0.11f);
        }

        private LineRenderer CreateLimb(string limbName, float width)
        {
            GameObject limbObject = new(limbName);
            limbObject.transform.SetParent(transform, false);
            LineRenderer line = limbObject.AddComponent<LineRenderer>();
            line.useWorldSpace = false;
            line.alignment = LineAlignment.TransformZ;
            line.textureMode = LineTextureMode.Stretch;
            line.positionCount = 3;
            line.startWidth = width;
            line.endWidth = width * 0.88f;
            line.numCapVertices = 8;
            line.numCornerVertices = 6;
            line.sortingOrder = 6;
            line.sharedMaterial = limbMaterial;
            line.startColor = LimbColor;
            line.endColor = LimbColor;
            return line;
        }

        private static void SetLimb(
            LineRenderer line,
            Vector2 joint,
            float upperAngle,
            float lowerBend,
            float upperLength,
            float lowerLength)
        {
            Vector2 elbow = joint + Direction(upperAngle) * upperLength;
            Vector2 tip = elbow + Direction(upperAngle + lowerBend) * lowerLength;
            line.SetPosition(0, new Vector3(joint.x, joint.y, 0f));
            line.SetPosition(1, new Vector3(elbow.x, elbow.y, 0f));
            line.SetPosition(2, new Vector3(tip.x, tip.y, 0f));
        }

        private static Vector2 Direction(float angleDegrees)
        {
            float radians = angleDegrees * Mathf.Deg2Rad;
            return new Vector2(Mathf.Cos(radians), Mathf.Sin(radians));
        }

        private void OnDestroy()
        {
            if (limbMaterial != null)
                Destroy(limbMaterial);
        }
    }
}
