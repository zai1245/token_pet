using System;
using System.Collections;
using UnityEngine;

namespace TokenPet
{
    public sealed class TokenPetPocBootstrap : MonoBehaviour
    {
        private enum MotionState
        {
            Idle,
            Walk,
            Poke,
            Drag,
            Airborne,
            Land
        }

        private const float CharacterWidth = 2.20f;
        private static readonly Vector3 RigRestPosition = new(0f, -0.12f, 0f);
        private Camera petCamera;
        private Transform rigRoot;
        private Transform motionRoot;
        private Transform body;
        private Transform headSocket;
        private TokenPetLimbRig limbRig;
        private TokenPetExpressionRig expressionRig;
        private TokenPetMotionProfiles motionProfiles;
        private TokenPetEquipmentController equipment;
        private CircleCollider2D hitCollider;
        private TokenPetIpcClient ipc;
        private TokenPetWindowsOverlay overlay;
        private MotionState motion = MotionState.Idle;
        private float motionTime;
        private float autonomousTimer;
        private Vector2 airborneVelocity;
        private float airborneHeight;
        private bool pointerDown;
        private bool pointerDragged;
        private Vector2Int dragWindowStart;
        private Vector2Int dragCursorStart;
        private Vector2Int previousCursorPosition;
        private Vector2 pointerVelocity;
        private float lastClickTime = -10f;
        private bool externallyDriven;
        private float baseBodyScale;
        private Vector3 posePosition;
        private Vector3 posePositionVelocity;
        private Vector3 poseScale = Vector3.one;
        private Vector3 poseScaleVelocity;
        private float poseRotation;
        private float poseRotationVelocity;
        private Vector2 lookTarget;
        private Vector2 lookSmoothed;
        private Vector2 lookVelocity;
        private float nextIdleGestureAt = 1.5f;
        private float idleGestureDirection = 1f;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void CreateRuntime()
        {
            if (FindFirstObjectByType<TokenPetPocBootstrap>() == null)
                new GameObject("TokenPet Unity PoC").AddComponent<TokenPetPocBootstrap>();
        }

        private void Awake()
        {
            DontDestroyOnLoad(gameObject);
            Application.targetFrameRate = 60;
            Application.runInBackground = true;
            QualitySettings.vSyncCount = 0;
            SetupCamera();
            if (!SetupCharacter())
            {
                enabled = false;
                Application.Quit();
                return;
            }

            ipc = new GameObject("TokenPet IPC").AddComponent<TokenPetIpcClient>();
            ipc.CommandReceived += OnCommand;
            overlay = gameObject.AddComponent<TokenPetWindowsOverlay>();
            StartCoroutine(AnnounceReady());
        }

        private void SetupCamera()
        {
            GameObject cameraObject = new("Pet Camera");
            petCamera = cameraObject.AddComponent<Camera>();
            petCamera.orthographic = true;
            petCamera.orthographicSize = 2.45f;
            petCamera.clearFlags = CameraClearFlags.SolidColor;
            // Reserved chroma key used by TokenPetWindowsOverlay. Pure magenta is
            // intentionally absent from the character and accessory palette.
            petCamera.backgroundColor = new Color32(255, 0, 255, 255);
            petCamera.allowHDR = false;
            petCamera.allowMSAA = false;
            // Keep the character near the same (170, 205) anchor used by the
            // legacy 340x300 Canvas while allowing a larger transparent player.
            petCamera.transform.position = new Vector3(0.82f, -0.61f, -10f);
            petCamera.tag = "MainCamera";
        }

        private bool SetupCharacter()
        {
            rigRoot = new GameObject("TokenPetRig").transform;
            motionRoot = new GameObject("MotionRoot").transform;
            motionRoot.SetParent(rigRoot, false);
            body = new GameObject("Body").transform;
            body.SetParent(motionRoot, false);

            Texture2D texture = Resources.Load<Texture2D>("tokenpet_body_faceless");
            bool usingFacelessBody = texture != null;
            if (texture == null)
                texture = Resources.Load<Texture2D>("tokenpet_body");
            bool usingRigBody = texture != null;
            if (texture == null)
                texture = Resources.Load<Texture2D>("tokenpet_stylized");
            if (texture == null)
            {
                Debug.LogError("Missing both Resources/tokenpet_body.png and tokenpet_stylized.png");
                Destroy(rigRoot.gameObject);
                rigRoot = null;
                return false;
            }

            Sprite sprite = Sprite.Create(texture,
                new Rect(0, 0, texture.width, texture.height),
                new Vector2(0.5f, 0.5f), 100f, 0, SpriteMeshType.Tight);
            SpriteRenderer renderer = body.gameObject.AddComponent<SpriteRenderer>();
            renderer.sprite = sprite;
            renderer.sortingOrder = 10;
            baseBodyScale = CharacterWidth / sprite.bounds.size.x;
            body.localScale = Vector3.one * baseBodyScale;

            if (usingRigBody)
            {
                limbRig = motionRoot.gameObject.AddComponent<TokenPetLimbRig>();
                limbRig.Initialize();
                if (usingFacelessBody)
                {
                    expressionRig = motionRoot.gameObject.AddComponent<TokenPetExpressionRig>();
                    expressionRig.Initialize();
                }
            }
            else
            {
                Debug.LogWarning("Rig body unavailable; using original full-body sprite fallback.");
            }

            hitCollider = rigRoot.gameObject.AddComponent<CircleCollider2D>();
            hitCollider.radius = 1.32f;
            hitCollider.offset = new Vector2(0f, -0.02f);

            headSocket = new GameObject("Socket_Head").transform;
            headSocket.SetParent(motionRoot, false);
            headSocket.localPosition = new Vector3(0f, 1.35f, 0f);

            equipment = rigRoot.gameObject.AddComponent<TokenPetEquipmentController>();
            equipment.RegisterSocket("head", headSocket);
            equipment.LoadCatalog();
            motionProfiles = TokenPetMotionProfiles.Load();

            rigRoot.position = RigRestPosition;
            return true;
        }

        private IEnumerator AnnounceReady()
        {
            while (!overlay.IsReady)
                yield return null;

            ipc.Send(new RendererEvent
            {
                event_name = "ready",
                state = "idle",
                version = "unity-poc-0.4.2"
            });
        }

        private void Update()
        {
            if (rigRoot == null)
                return;

            HandlePointer();
            Animate(Time.unscaledDeltaTime);

            if (Input.GetKeyDown(KeyCode.C))
                equipment.Toggle("head", "crown");
            if (Input.GetKeyDown(KeyCode.Space))
                EnterState(MotionState.Poke);
        }

        private void HandlePointer()
        {
            Vector3 world = petCamera.ScreenToWorldPoint(Input.mousePosition);
            bool overPet = hitCollider != null && hitCollider.OverlapPoint(world);

            if (Input.GetMouseButtonDown(1) && overPet)
            {
                Vector2Int cursor = overlay.GetCursorPosition();
                ipc.Send(new RendererEvent
                {
                    event_name = "context_menu",
                    x = cursor.x,
                    y = cursor.y
                });
            }

            if (Input.GetMouseButtonDown(0) && overPet)
            {
                pointerDown = true;
                pointerDragged = false;
                dragCursorStart = overlay.GetCursorPosition();
                previousCursorPosition = dragCursorStart;
                dragWindowStart = overlay.GetPosition();
                pointerVelocity = Vector2.zero;
            }

            if (pointerDown && Input.GetMouseButton(0))
            {
                Vector2Int cursor = overlay.GetCursorPosition();
                Vector2Int mouseDelta = cursor - dragCursorStart;
                // Use the desktop cursor delta rather than camera/world coordinates.
                // Moving the native window changes Input.mousePosition relative to
                // that window and otherwise creates a feedback loop during dragging.
                if (!pointerDragged && mouseDelta.sqrMagnitude > 36)
                {
                    pointerDragged = true;
                    EnterState(MotionState.Drag);
                }

                if (pointerDragged)
                {
                    overlay.MoveTo(dragWindowStart.x + Mathf.RoundToInt(mouseDelta.x),
                        dragWindowStart.y + Mathf.RoundToInt(mouseDelta.y));
                    Vector2Int frameDelta = cursor - previousCursorPosition;
                    pointerVelocity = Vector2.Lerp(pointerVelocity,
                        new Vector2(frameDelta.x, -frameDelta.y) / Mathf.Max(Time.unscaledDeltaTime, 0.001f), 0.35f);
                    previousCursorPosition = cursor;
                }
            }

            if (pointerDown && Input.GetMouseButtonUp(0))
            {
                pointerDown = false;
                Vector2Int windowPosition = overlay.GetPosition();
                if (pointerDragged)
                {
                    airborneVelocity = new Vector2(
                        Mathf.Clamp(pointerVelocity.x * 0.0007f, -2.4f, 2.4f),
                        Mathf.Clamp(pointerVelocity.y * 0.0007f + 1.5f, 0.8f, 3.2f));
                    EnterState(MotionState.Airborne);
                    ipc.Send(new RendererEvent
                    {
                        event_name = "drag_released",
                        action = "fall",
                        x = windowPosition.x,
                        y = windowPosition.y,
                        velocity_x = pointerVelocity.x,
                        velocity_y = pointerVelocity.y
                    });
                }
                else
                {
                    bool doubleClick = Time.unscaledTime - lastClickTime < 0.35f;
                    lastClickTime = Time.unscaledTime;
                    if (doubleClick)
                    {
                        ipc.Send(new RendererEvent { event_name = "double_click", action = "chat" });
                    }
                    else
                    {
                        EnterState(MotionState.Poke);
                        ipc.Send(new RendererEvent { event_name = "poke", action = "poke" });
                    }
                }
            }
        }

        private void Animate(float deltaTime)
        {
            motionTime += deltaTime;
            autonomousTimer += deltaTime;
            TokenPetMotionProfile profile = motionProfiles.Get(motion.ToString());
            UpdateLook(deltaTime);

            Vector3 scale = Vector3.one;
            float rotation = 0f;
            float horizontal = 0f;
            float vertical = 0f;

            switch (motion)
            {
                case MotionState.Idle:
                    float breath = Mathf.Sin(motionTime * profile.frequency);
                    float slowSway = Mathf.Sin(motionTime * profile.frequency * 0.47f + 0.8f);
                    float gesture = BellPulse((motionTime - nextIdleGestureAt) / 0.9f);
                    vertical = breath * profile.bob + gesture * 0.055f;
                    horizontal = slowSway * profile.sway + gesture * idleGestureDirection * 0.045f;
                    rotation = slowSway * profile.tilt - gesture * idleGestureDirection * 3.8f;
                    scale.x = 1f + breath * profile.stretch + gesture * 0.025f;
                    scale.y = 1f - breath * profile.squash + gesture * 0.045f;
                    if (motionTime > nextIdleGestureAt + 0.9f)
                        ScheduleIdleGesture(motionTime);
                    if (!externallyDriven && autonomousTimer > profile.duration)
                    {
                        autonomousTimer = 0f;
                        EnterState(MotionState.Walk);
                    }
                    break;

                case MotionState.Walk:
                    float step = Mathf.Sin(motionTime * profile.frequency);
                    float lift = Mathf.Abs(step);
                    float contact = 1f - lift;
                    vertical = lift * profile.bob - contact * 0.018f;
                    horizontal = Mathf.Sin(motionTime * profile.frequency * 0.5f) * profile.sway;
                    rotation = step * profile.tilt;
                    scale.x = 1f + contact * profile.squash - lift * profile.squash * 0.25f;
                    scale.y = 1f - contact * profile.squash + lift * profile.stretch;
                    if (!externallyDriven && autonomousTimer > profile.duration)
                    {
                        autonomousTimer = 0f;
                        EnterState(MotionState.Idle);
                    }
                    break;

                case MotionState.Poke:
                    float poke = Mathf.Clamp01(motionTime / profile.duration);
                    float anticipation = 1f - Mathf.SmoothStep(0f, 1f, Mathf.Clamp01(poke / 0.16f));
                    float recoil = Mathf.Sin(Mathf.Clamp01((poke - 0.10f) / 0.90f) * Mathf.PI);
                    float pokeWobble = Mathf.Sin(poke * Mathf.PI * 5f) * (1f - poke);
                    vertical = recoil * profile.bob - anticipation * 0.07f;
                    horizontal = pokeWobble * profile.sway;
                    rotation = pokeWobble * profile.tilt;
                    scale.x = 1f + anticipation * profile.squash + pokeWobble * profile.stretch;
                    scale.y = 1f - anticipation * profile.squash + recoil * profile.stretch - pokeWobble * profile.squash;
                    if (poke >= 1f)
                    {
                        ipc.Send(new RendererEvent { event_name = "action_finished", action = "poke" });
                        EnterState(MotionState.Idle);
                    }
                    break;

                case MotionState.Drag:
                    float dragSpeed = Mathf.Clamp01(pointerVelocity.magnitude / 1800f);
                    vertical = Mathf.Sin(motionTime * profile.frequency) * profile.bob;
                    horizontal = Mathf.Clamp(pointerVelocity.x / 5000f, -profile.sway, profile.sway);
                    rotation = Mathf.Clamp(-pointerVelocity.x * 0.012f, -profile.tilt, profile.tilt);
                    scale.x = 1f - profile.squash - dragSpeed * 0.035f;
                    scale.y = 1f + profile.stretch + dragSpeed * 0.055f;
                    break;

                case MotionState.Airborne:
                    airborneVelocity.y -= 5.5f * deltaTime;
                    airborneHeight += airborneVelocity.y * deltaTime;
                    vertical = Mathf.Clamp(airborneHeight, 0f, profile.bob);
                    horizontal = Mathf.Clamp(airborneVelocity.x * 0.08f, -profile.sway, profile.sway);
                    rotation = Mathf.Repeat(motionTime * profile.tilt, 360f);
                    float flightStretch = Mathf.Clamp01(Mathf.Abs(airborneVelocity.y) / 3.2f);
                    scale.x = 1f - flightStretch * profile.squash;
                    scale.y = 1f + flightStretch * profile.stretch;
                    if (airborneHeight <= 0f && airborneVelocity.y < 0f)
                    {
                        airborneHeight = 0f;
                        EnterState(MotionState.Land);
                    }
                    break;

                case MotionState.Land:
                    float land = Mathf.Clamp01(motionTime / profile.duration);
                    float impact = Mathf.Sin(land * Mathf.PI * profile.frequency) * Mathf.Exp(-3.2f * land);
                    vertical = -Mathf.Abs(impact) * profile.bob;
                    rotation = Mathf.Sin(land * Mathf.PI * 2f) * profile.tilt * (1f - land);
                    scale.x = 1f + impact * profile.squash;
                    scale.y = 1f - impact * profile.stretch;
                    if (land >= 1f)
                    {
                        ipc.Send(new RendererEvent { event_name = "action_finished", action = "land" });
                        EnterState(MotionState.Idle);
                    }
                    break;
            }

            float lookWeight = motion == MotionState.Drag || motion == MotionState.Airborne ? 0.25f : 1f;
            horizontal += lookSmoothed.x * 0.045f * lookWeight;
            vertical += lookSmoothed.y * 0.018f * lookWeight;
            rotation -= lookSmoothed.x * 2.4f * lookWeight;

            Vector3 targetPosition = new(horizontal, vertical, 0f);
            Vector3 targetScale = new(
                Mathf.Max(0.65f, scale.x),
                Mathf.Max(0.65f, scale.y),
                1f);
            float smoothTime = Mathf.Max(0.01f, profile.smoothing);
            posePosition = Vector3.SmoothDamp(
                posePosition, targetPosition, ref posePositionVelocity,
                smoothTime, Mathf.Infinity, deltaTime);
            poseScale = Vector3.SmoothDamp(
                poseScale, targetScale, ref poseScaleVelocity,
                smoothTime, Mathf.Infinity, deltaTime);
            poseRotation = Mathf.SmoothDampAngle(
                poseRotation, rotation, ref poseRotationVelocity,
                smoothTime, Mathf.Infinity, deltaTime);

            // The native desktop window owns global movement. MotionRoot owns the
            // local performance so body and all equipment share one coherent pose.
            rigRoot.position = RigRestPosition;
            motionRoot.localPosition = posePosition;
            motionRoot.localRotation = Quaternion.Euler(0f, 0f, poseRotation);
            motionRoot.localScale = poseScale;
            if (limbRig != null)
                limbRig.ApplyPose(motion.ToString(), motionTime, pointerVelocity, lookSmoothed);
            if (expressionRig != null)
                expressionRig.ApplyExpression(motion.ToString(), motionTime, lookSmoothed);
            ClampVisualInsideViewport();
        }

        private void UpdateLook(float deltaTime)
        {
            if (ipc == null || !ipc.IsConnected)
            {
                Vector3 cursorWorld = petCamera.ScreenToWorldPoint(Input.mousePosition);
                Vector2 direction = cursorWorld - body.position;
                lookTarget = new Vector2(
                    Mathf.Clamp(direction.x / 1.7f, -1f, 1f),
                    Mathf.Clamp(direction.y / 1.7f, -1f, 1f));
            }

            lookSmoothed = Vector2.SmoothDamp(
                lookSmoothed, lookTarget, ref lookVelocity,
                0.14f, Mathf.Infinity, deltaTime);
        }

        private static float BellPulse(float normalizedTime)
        {
            if (normalizedTime <= 0f || normalizedTime >= 1f)
                return 0f;
            float sine = Mathf.Sin(normalizedTime * Mathf.PI);
            return sine * sine;
        }

        private void ScheduleIdleGesture(float fromTime = 0f)
        {
            nextIdleGestureAt = fromTime + UnityEngine.Random.Range(1.4f, 3.2f);
            idleGestureDirection = UnityEngine.Random.value < 0.5f ? -1f : 1f;
        }

        private void ClampVisualInsideViewport()
        {
            Renderer[] renderers = rigRoot.GetComponentsInChildren<Renderer>();
            if (renderers.Length == 0)
                return;

            Bounds visualBounds = renderers[0].bounds;
            for (int index = 1; index < renderers.Length; index++)
                visualBounds.Encapsulate(renderers[index].bounds);

            const float safeInset = 0.08f;
            float halfHeight = petCamera.orthographicSize;
            float halfWidth = halfHeight * petCamera.aspect;
            Vector3 cameraPosition = petCamera.transform.position;
            float minX = cameraPosition.x - halfWidth + safeInset;
            float maxX = cameraPosition.x + halfWidth - safeInset;
            float minY = cameraPosition.y - halfHeight + safeInset;
            float maxY = cameraPosition.y + halfHeight - safeInset;

            Vector3 correction = Vector3.zero;
            if (visualBounds.min.x < minX)
                correction.x = minX - visualBounds.min.x;
            else if (visualBounds.max.x > maxX)
                correction.x = maxX - visualBounds.max.x;

            if (visualBounds.min.y < minY)
                correction.y = minY - visualBounds.min.y;
            else if (visualBounds.max.y > maxY)
                correction.y = maxY - visualBounds.max.y;

            if (correction.sqrMagnitude > 0f)
            {
                motionRoot.position += correction;
                posePosition = motionRoot.localPosition;
            }
        }

        private void EnterState(MotionState next)
        {
            motion = next;
            motionTime = 0f;
            if (next == MotionState.Airborne)
                airborneHeight = 0f;
            if (next == MotionState.Idle)
                ScheduleIdleGesture();
            if (next == MotionState.Idle || next == MotionState.Walk)
                externallyDriven = false;
        }

        private void OnCommand(RendererCommand command)
        {
            switch (command.command)
            {
                case "snapshot":
                    ApplyLegacyState(command.state);
                    lookTarget = new Vector2(
                        Mathf.Clamp(command.look_x / 12f, -1f, 1f),
                        Mathf.Clamp(-command.look_y / 6f, -1f, 1f));
                    equipment.Equip("head", command.item);
                    break;
                case "trigger":
                    if (string.Equals(command.action, "poke", StringComparison.OrdinalIgnoreCase))
                        EnterState(MotionState.Poke);
                    else if (string.Equals(command.action, "fall", StringComparison.OrdinalIgnoreCase))
                    {
                        airborneVelocity = new Vector2(0f, 2.0f);
                        EnterState(MotionState.Airborne);
                    }
                    break;
                case "equip":
                    equipment.Equip(command.slot, command.item);
                    break;
                case "set_visible":
                    rigRoot.gameObject.SetActive(command.visible);
                    overlay.SetVisible(command.visible);
                    break;
            }
        }

        private void ApplyLegacyState(string legacyState)
        {
            if (string.IsNullOrEmpty(legacyState) ||
                motion == MotionState.Poke ||
                motion == MotionState.Drag ||
                motion == MotionState.Airborne ||
                motion == MotionState.Land)
                return;

            MotionState desired = MotionState.Idle;
            if (legacyState == "walk" || legacyState == "chase_mouse" ||
                legacyState == "return_home" || legacyState == "approach_furniture")
            {
                desired = MotionState.Walk;
            }
            else if (legacyState == "fall" || legacyState == "backflip" ||
                     legacyState == "roll" || legacyState == "balloon")
            {
                desired = MotionState.Airborne;
            }

            if (desired != motion)
                EnterState(desired);
            externallyDriven = true;
        }
    }
}
