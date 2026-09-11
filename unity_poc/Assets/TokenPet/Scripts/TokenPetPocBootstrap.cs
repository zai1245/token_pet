using System;
using System.Collections;
using UnityEngine;

namespace TokenPet
{
    public sealed class TokenPetPocBootstrap : MonoBehaviour
    {
        public const string RendererVersion = "0.8.0-preview";

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
        private const float LegacyCanvasWidth = 340f;
        private const float LegacyCanvasHeight = 300f;
        private const float LegacyBodyPixelWidth = 104f;
        private const float LegacyAnchorX = 170f;
        private const float LegacyAnchorYFromTop = 205f;
        private const float WorldUnitsPerPixel = CharacterWidth / LegacyBodyPixelWidth;
        private static readonly Vector3 InitialRigRestPosition = new(0f, -0.12f, 0f);
        private Vector3 rigRestPosition = InitialRigRestPosition;
        private Camera petCamera;
        private Transform rigRoot;
        private Transform motionRoot;
        private Transform body;
        private Transform headSocket;
        private TokenPetLimbRig limbRig;
        private TokenPetExpressionRig expressionRig;
        private TokenPetStatusHud statusHud;
        private TokenPetMotionProfiles motionProfiles;
        private TokenPetEquipmentController equipment;
        private TokenPetLegacyVisuals legacyVisuals;
        private TokenPetFloatingText floatingText;
        private TokenPetShopPanel shopPanel;
        private TokenPetFurnitureStage furnitureStage;
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
        private int lastDragDirection;
        private int shakeCount;
        private RectInt cachedPetInteractiveRect;
        private float lastContextMenuAt = -10f;
        private float shakeWindowStartedAt;
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
        private string legacyExpression = "normal";
        private string legacyMouth = "normal";
        private string legacyState = "idle";
        private string legacyEffects = "";
        private float legacySatiety = 100f;
        private RectInt lastPublishedWorkArea;

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
            overlay.InteractiveHitTest = IsDesktopInteractive;
            statusHud = gameObject.AddComponent<TokenPetStatusHud>();
            statusHud.Initialize(overlay);
            floatingText = gameObject.AddComponent<TokenPetFloatingText>();
            floatingText.Initialize(petCamera, overlay);
            furnitureStage = gameObject.AddComponent<TokenPetFurnitureStage>();
            furnitureStage.Initialize(ipc, overlay, petCamera);
            shopPanel = gameObject.AddComponent<TokenPetShopPanel>();
            shopPanel.Initialize(ipc, rigRoot.gameObject, statusHud, overlay, petCamera);
            StartCoroutine(AnnounceReady());
        }

        private void SetupCamera()
        {
            GameObject cameraObject = new("Pet Camera");
            petCamera = cameraObject.AddComponent<Camera>();
            petCamera.orthographic = true;
            petCamera.orthographicSize = LegacyCanvasHeight * WorldUnitsPerPixel * 0.5f;
            petCamera.clearFlags = CameraClearFlags.SolidColor;
            // Reserved chroma key used by TokenPetWindowsOverlay. Pure magenta is
            // intentionally absent from the character and accessory palette.
            petCamera.backgroundColor = new Color32(255, 0, 255, 255);
            petCamera.allowHDR = false;
            petCamera.allowMSAA = false;
            // Match the original 340x300 Canvas exactly: a 104 px body centered
            // at the legacy (170, 205-from-top) character anchor.
            float anchorFromBottom = LegacyCanvasHeight - LegacyAnchorYFromTop;
            float cameraX = InitialRigRestPosition.x -
                (LegacyAnchorX - LegacyCanvasWidth * 0.5f) * WorldUnitsPerPixel;
            float cameraY = InitialRigRestPosition.y -
                (anchorFromBottom - LegacyCanvasHeight * 0.5f) * WorldUnitsPerPixel;
            petCamera.transform.position = new Vector3(cameraX, cameraY, -10f);
            petCamera.tag = "MainCamera";
        }

        private bool SetupCharacter()
        {
            rigRoot = new GameObject("TokenPetRig").transform;
            motionRoot = new GameObject("MotionRoot").transform;
            motionRoot.SetParent(rigRoot, false);
            body = new GameObject("Body").transform;
            body.SetParent(motionRoot, false);

            // The round body is the Unity art direction. Keep the earlier,
            // slightly irregular painted body and full sprite as fallbacks.
            Texture2D texture = Resources.Load<Texture2D>("tokenpet_body_round_clean_faceless");
            if (texture == null)
                texture = Resources.Load<Texture2D>("tokenpet_body_round_faceless");
            if (texture == null)
                texture = Resources.Load<Texture2D>("tokenpet_body_faceless");
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
            // Head accessories now carry their own artwork-aware mount pivot.
            // Keeping this socket at the character origin prevents every hat
            // from inheriting the old one-size-fits-all floating offset.
            headSocket.localPosition = Vector3.zero;

            equipment = rigRoot.gameObject.AddComponent<TokenPetEquipmentController>();
            equipment.RegisterSocket("head", headSocket);
            equipment.RegisterSocket("face", motionRoot);
            equipment.RegisterSocket("neck", motionRoot);
            equipment.RegisterSocket("body", motionRoot);
            equipment.LoadCatalog();
            legacyVisuals = rigRoot.gameObject.AddComponent<TokenPetLegacyVisuals>();
            legacyVisuals.Initialize(motionRoot, renderer);
            motionProfiles = TokenPetMotionProfiles.Load();

            rigRoot.position = InitialRigRestPosition;
            return true;
        }

        private IEnumerator AnnounceReady()
        {
            while (!overlay.IsReady)
                yield return null;

            RefreshDesktopStageLayout();
            PublishDesktopMetrics(true);

            ipc.Send(new RendererEvent
            {
                event_name = "ready",
                state = "idle",
                version = $"unity-poc-{RendererVersion}"
            });
        }

        private void Update()
        {
            if (rigRoot == null)
                return;

            RefreshDesktopStageLayout();

            if (Input.GetKeyDown(KeyCode.Escape))
            {
                if (shopPanel != null && shopPanel.IsVisible)
                {
                    shopPanel.Hide();
                    return;
                }
                ipc.Send(new RendererEvent { event_name = "renderer_closed", action = "escape" });
                Application.Quit();
                return;
            }

            if (shopPanel == null || !shopPanel.IsVisible)
                HandlePointer();
            Animate(Time.unscaledDeltaTime);
            CachePetInteractiveRect();

            if (Input.GetKeyDown(KeyCode.C))
                equipment.Toggle("head", "crown");
            if (Input.GetKeyDown(KeyCode.Space))
                EnterState(MotionState.Poke);
        }

        private void HandlePointer()
        {
            bool nativeContextClick = overlay.TryConsumeContextClick(out Vector2Int nativeCursor);
            if (furnitureStage != null &&
                furnitureStage.HandlePointer(nativeContextClick, nativeCursor))
                return;

            Vector3 world = petCamera.ScreenToWorldPoint(Input.mousePosition);
            bool overPet = hitCollider != null && hitCollider.OverlapPoint(world);

            if ((nativeContextClick || Input.GetMouseButtonDown(1)) &&
                (nativeContextClick || overPet) && Time.unscaledTime - lastContextMenuAt > 0.25f)
            {
                Vector2Int cursor = nativeContextClick ? nativeCursor : overlay.GetCursorPosition();
                lastContextMenuAt = Time.unscaledTime;
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
                lastDragDirection = 0;
                shakeCount = 0;
                shakeWindowStartedAt = Time.unscaledTime;
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
                    ipc.Send(new RendererEvent { event_name = "drag_started", action = "drag" });
                }

                if (pointerDragged)
                {
                    overlay.MoveTo(dragWindowStart.x + Mathf.RoundToInt(mouseDelta.x),
                        dragWindowStart.y + Mathf.RoundToInt(mouseDelta.y));
                    RefreshDesktopStageLayout();
                    Vector2Int frameDelta = cursor - previousCursorPosition;
                    pointerVelocity = Vector2.Lerp(pointerVelocity,
                        new Vector2(frameDelta.x, -frameDelta.y) / Mathf.Max(Time.unscaledDeltaTime, 0.001f), 0.35f);
                    previousCursorPosition = cursor;
                    TrackShake(frameDelta.x);
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
                    externallyDriven = ipc != null && ipc.IsConnected;
                    ipc.Send(new RendererEvent
                    {
                        event_name = "drag_released",
                        action = "fall",
                        x = windowPosition.x,
                        y = windowPosition.y,
                        floor_y = overlay.GetPetWorkArea().yMax - (int)LegacyCanvasHeight,
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

        private void TrackShake(int horizontalDelta)
        {
            if (Mathf.Abs(horizontalDelta) < 2)
                return;
            int direction = horizontalDelta > 0 ? 1 : -1;
            if (Time.unscaledTime - shakeWindowStartedAt > 1.2f)
            {
                shakeWindowStartedAt = Time.unscaledTime;
                shakeCount = 0;
            }
            if (lastDragDirection != 0 && direction != lastDragDirection)
                shakeCount++;
            lastDragDirection = direction;
            if (shakeCount < 4)
                return;

            shakeCount = 0;
            shakeWindowStartedAt = Time.unscaledTime;
            ipc.Send(new RendererEvent
            {
                event_name = "shake",
                action = "roll",
                velocity_x = pointerVelocity.x,
                velocity_y = pointerVelocity.y
            });
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
                    if (externallyDriven)
                    {
                        float tumbleDirection = pointerVelocity.x < -10f ? -1f : 1f;
                        bool forcedSpin = string.Equals(legacyState, "backflip", StringComparison.OrdinalIgnoreCase) ||
                            string.Equals(legacyState, "roll", StringComparison.OrdinalIgnoreCase);
                        if (string.Equals(legacyState, "backflip", StringComparison.OrdinalIgnoreCase))
                            tumbleDirection = -1f;
                        float spinStrength = forcedSpin
                            ? 1f
                            : Mathf.Clamp(Mathf.Abs(pointerVelocity.x) / 900f, 0.04f, 1f);
                        rotation = Mathf.Repeat(
                            motionTime * profile.tilt * tumbleDirection * spinStrength, 360f);
                        float fallPulse = (Mathf.Sin(motionTime * 7f) + 1f) * 0.5f;
                        scale.x = 1f - fallPulse * profile.squash * 0.65f;
                        scale.y = 1f + fallPulse * profile.stretch * 0.65f;
                    }
                    else
                    {
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
            ApplyLegacyPerformance(ref horizontal, ref vertical, ref rotation, ref scale);

            Vector3 targetPosition = new(horizontal, vertical, 0f);
            bool backFacing =
                string.Equals(legacyState, "back_idle", StringComparison.OrdinalIgnoreCase) ||
                string.Equals(legacyState, "turn_to_back", StringComparison.OrdinalIgnoreCase);
            bool sideFacing =
                string.Equals(legacyState, "work_laptop", StringComparison.OrdinalIgnoreCase) ||
                string.Equals(legacyState, "watch_tv", StringComparison.OrdinalIgnoreCase) ||
                string.Equals(legacyState, "water_plant", StringComparison.OrdinalIgnoreCase);
            equipment?.SetBackFacing(backFacing);
            float facingScale = backFacing ? -1f : (sideFacing ? 0.72f : 1f);
            Vector3 targetScale = new(
                Mathf.Max(0.12f, Mathf.Abs(scale.x)) * facingScale,
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
            rigRoot.position = rigRestPosition;
            motionRoot.localPosition = posePosition;
            motionRoot.localRotation = Quaternion.Euler(0f, 0f, poseRotation);
            motionRoot.localScale = poseScale;
            if (limbRig != null)
                limbRig.ApplyPose(motion.ToString(), motionTime, pointerVelocity, lookSmoothed,
                    legacyState, legacyEffects);
            if (expressionRig != null)
            {
                expressionRig.ApplyExpression(
                    motion.ToString(),
                    motionTime,
                    lookSmoothed,
                    legacyExpression,
                    legacyMouth,
                    legacyState,
                    legacySatiety);
                equipment?.SetSlotVisible("face", expressionRig.FaceVisible);
            }
            if (legacyVisuals != null)
                legacyVisuals.Tick(Time.unscaledTime);
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
            if (overlay != null && overlay.IsDesktopStage)
                return;

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

        private void RefreshDesktopStageLayout()
        {
            if (overlay == null || !overlay.IsDesktopStage || petCamera == null)
                return;

            petCamera.orthographicSize = Mathf.Max(1f,
                overlay.StageSize.y * WorldUnitsPerPixel * 0.5f);
            petCamera.transform.position = new Vector3(0f, 0f, -10f);
            Vector2 desktopAnchor = new(
                overlay.PetPosition.x + LegacyAnchorX,
                overlay.PetPosition.y + LegacyAnchorYFromTop);
            rigRestPosition = overlay.DesktopToWorld(desktopAnchor, petCamera);
            if (motionRoot != null && motion != MotionState.Drag)
                rigRoot.position = rigRestPosition;
            furnitureStage?.RefreshLayout();
            PublishDesktopMetrics(false);
        }

        private void PublishDesktopMetrics(bool force)
        {
            if (overlay == null || !overlay.IsDesktopStage || ipc == null || !ipc.IsConnected)
                return;
            RectInt work = overlay.GetPetWorkArea();
            if (!force && work == lastPublishedWorkArea)
                return;
            lastPublishedWorkArea = work;
            ipc.Send(new RendererEvent
            {
                event_name = "desktop_metrics",
                x = work.x,
                y = work.y,
                width = work.width,
                height = work.height,
                floor_y = work.yMax - (int)LegacyCanvasHeight,
                stage_x = overlay.StageOrigin.x,
                stage_y = overlay.StageOrigin.y,
                stage_width = overlay.StageSize.x,
                stage_height = overlay.StageSize.y
            });
        }

        private bool IsDesktopInteractive(Vector2Int cursor)
        {
            if (pointerDown || (furnitureStage != null && furnitureStage.IsDragging))
                return true;
            if (shopPanel != null && shopPanel.HitTestDesktop(cursor))
                return true;
            if (furnitureStage != null && furnitureStage.HitTestDesktop(cursor))
                return true;
            return cachedPetInteractiveRect.Contains(cursor);
        }

        private void CachePetInteractiveRect()
        {
            if (hitCollider == null || petCamera == null || overlay == null || !overlay.IsDesktopStage)
                return;

            Bounds bounds = hitCollider.bounds;
            Vector3 screenMin = petCamera.WorldToScreenPoint(
                new Vector3(bounds.min.x, bounds.min.y, 0f));
            Vector3 screenMax = petCamera.WorldToScreenPoint(
                new Vector3(bounds.max.x, bounds.max.y, 0f));
            const int padding = 10;
            int left = overlay.StageOrigin.x + Mathf.FloorToInt(Mathf.Min(screenMin.x, screenMax.x)) - padding;
            int right = overlay.StageOrigin.x + Mathf.CeilToInt(Mathf.Max(screenMin.x, screenMax.x)) + padding;
            int top = overlay.StageOrigin.y + overlay.StageSize.y -
                Mathf.CeilToInt(Mathf.Max(screenMin.y, screenMax.y)) - padding;
            int bottom = overlay.StageOrigin.y + overlay.StageSize.y -
                Mathf.FloorToInt(Mathf.Min(screenMin.y, screenMax.y)) + padding;
            cachedPetInteractiveRect = new RectInt(left, top,
                Mathf.Max(1, right - left), Mathf.Max(1, bottom - top));
        }

        private void OnCommand(RendererCommand command)
        {
            switch (command.command)
            {
                case "snapshot":
                    string previousLegacyState = legacyState;
                    legacyExpression = string.IsNullOrEmpty(command.emotion)
                        ? "normal"
                        : command.emotion;
                    legacyMouth = string.IsNullOrEmpty(command.mouth)
                        ? "normal"
                        : command.mouth;
                    legacyState = string.IsNullOrEmpty(command.state)
                        ? "idle"
                        : command.state;
                    legacySatiety = Mathf.Clamp(command.satiety, 0f, 100f);
                    legacyEffects = command.effects ?? "";
                    legacyVisuals?.ApplySnapshot(command);
                    bool wasFalling = previousLegacyState == "fall" ||
                        previousLegacyState == "backflip" || previousLegacyState == "roll";
                    bool isFalling = legacyState == "fall" ||
                        legacyState == "backflip" || legacyState == "roll";
                    if (wasFalling && !isFalling && motion == MotionState.Airborne && externallyDriven)
                    {
                        externallyDriven = false;
                        EnterState(MotionState.Land);
                    }
                    ApplyLegacyState(command.state);
                    lookTarget = new Vector2(
                        Mathf.Clamp(command.look_x / 12f, -1f, 1f),
                        Mathf.Clamp(-command.look_y / 6f, -1f, 1f));
                    bool hasSlotSnapshot = command.head_item != null ||
                        command.face_item != null ||
                        command.neck_item != null ||
                        command.body_item != null;
                    if (hasSlotSnapshot)
                    {
                        equipment.SyncSlots(
                            command.head_item,
                            command.face_item,
                            command.neck_item,
                            command.body_item);
                    }
                    else
                    {
                        equipment.SyncItem(command.item);
                    }
                    statusHud.SetStatus(
                        command.level,
                        command.xp,
                        command.xp_max,
                        command.satiety,
                        command.coins);
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
                    if (string.IsNullOrWhiteSpace(command.slot))
                        equipment.SyncItem(command.item);
                    else
                        equipment.Equip(command.slot, command.item);
                    break;
                case "set_visible":
                    rigRoot.gameObject.SetActive(command.visible);
                    overlay.SetVisible(command.visible);
                    break;
                case "set_status_visible":
                    statusHud.SetVisible(command.visible);
                    break;
                case "move_window":
                    overlay.MoveTo(Mathf.RoundToInt(command.x), Mathf.RoundToInt(command.y));
                    RefreshDesktopStageLayout();
                    break;
                case "popup":
                    floatingText.Show(command.text, command.x, command.y,
                        command.color, command.duration);
                    break;
                case "show_shop":
                    shopPanel.Show(command.payload);
                    break;
                case "hide_shop":
                    shopPanel.Hide();
                    break;
                case "sync_furniture":
                    furnitureStage.Sync(command.payload);
                    break;
                case "trigger_furniture":
                    furnitureStage.Trigger(command.item, command.action);
                    break;
            }
        }

        private void ApplyLegacyState(string legacyState)
        {
            if (string.IsNullOrEmpty(legacyState) ||
                motion == MotionState.Poke ||
                motion == MotionState.Drag ||
                (motion == MotionState.Airborne && !externallyDriven) ||
                motion == MotionState.Land)
                return;

            MotionState desired = MotionState.Idle;
            if (legacyState == "walk" || legacyState == "chase_mouse" ||
                legacyState == "return_home" || legacyState == "approach_furniture")
            {
                desired = MotionState.Walk;
            }
            else if (legacyState == "fall" || legacyState == "backflip" ||
                     legacyState == "roll")
            {
                desired = MotionState.Airborne;
            }

            if (desired != motion)
                EnterState(desired);
            externallyDriven = true;
        }

        private void ApplyLegacyPerformance(
            ref float horizontal, ref float vertical, ref float rotation, ref Vector3 scale)
        {
            string state = (legacyState ?? "idle").ToLowerInvariant();
            float time = Time.unscaledTime;
            switch (state)
            {
                case "sleep":
                case "sleep_futon":
                    vertical -= 0.20f;
                    rotation = -7f;
                    scale.x *= 1.10f + Mathf.Sin(time * 2.2f) * 0.015f;
                    scale.y *= 0.82f + Mathf.Sin(time * 2.2f) * 0.010f;
                    break;
                case "eat":
                case "memo_eat":
                    float chew = Mathf.Abs(Mathf.Sin(time * 10f));
                    vertical += chew * 0.035f;
                    scale.x *= 1f + chew * 0.045f;
                    scale.y *= 1f - chew * 0.035f;
                    break;
                case "drink":
                    rotation = -5f + Mathf.Sin(time * 4f) * 1.5f;
                    horizontal += 0.04f;
                    break;
                case "balloon":
                    vertical += 0.42f + Mathf.Sin(time * 1.8f) * 0.11f;
                    rotation = Mathf.Sin(time * 1.2f) * 4f;
                    scale.y *= 1.03f;
                    break;
                case "work_laptop":
                    vertical -= 0.10f;
                    rotation = Mathf.Sin(time * 12f) * 0.8f;
                    break;
                case "relax_sofa":
                    vertical -= 0.22f;
                    rotation = -4f;
                    scale.x *= 1.08f;
                    scale.y *= 0.90f;
                    break;
                case "warm_kotatsu":
                    vertical -= 0.25f;
                    scale.y *= 0.88f;
                    break;
                case "watch_tv":
                    horizontal -= 0.08f;
                    rotation = -2f;
                    break;
                case "meditate_lamp":
                    vertical += Mathf.Sin(time * 2f) * 0.03f;
                    scale.x *= 0.98f;
                    scale.y *= 1.02f;
                    break;
                case "water_plant":
                    horizontal -= 0.10f;
                    rotation = -7f + Mathf.Sin(time * 5f) * 2f;
                    break;
                case "memo_perch":
                    vertical += 0.10f + Mathf.Abs(Mathf.Sin(time * 4f)) * 0.035f;
                    break;
                case "memo_read":
                    rotation = -3f;
                    horizontal -= 0.05f;
                    break;
                case "turn_to_back":
                case "turn_to_front":
                case "back_idle":
                    break;
            }

            if (HasLegacyEffect("spicy"))
            {
                horizontal += Mathf.Sin(time * 18f) * 0.07f;
                rotation += Mathf.Sin(time * 24f) * 3f;
            }
            else if (HasLegacyEffect("ice"))
            {
                horizontal += Mathf.Sin(time * 30f) * 0.012f;
                rotation += Mathf.Sin(time * 27f) * 0.7f;
            }
            else if (HasLegacyEffect("coffee") || HasLegacyEffect("candy"))
            {
                vertical += Mathf.Abs(Mathf.Sin(time * 8f)) * 0.055f;
            }

            if (HasLegacyEffect("doze"))
            {
                rotation += Mathf.Sin(time * 2.2f) * 5f;
                scale.y *= 0.96f;
            }
            if (HasLegacyEffect("bubble"))
            {
                float puff = (Mathf.Sin(time * 3f) + 1f) * 0.025f;
                scale.x *= 1f + puff;
                scale.y *= 1f + puff;
            }
            if (HasLegacyEffect("stretch"))
            {
                float stretch = Mathf.Abs(Mathf.Sin(time * 2.8f)) * 0.13f;
                scale.x *= 1f - stretch * 0.55f;
                scale.y *= 1f + stretch;
            }
            if (HasLegacyEffect("singing"))
            {
                horizontal += Mathf.Sin(time * 5f) * 0.06f;
                rotation += Mathf.Sin(time * 5f) * 4f;
            }
        }

        private bool HasLegacyEffect(string effect)
        {
            foreach (string value in (legacyEffects ?? "").Split(','))
            {
                if (string.Equals(value.Trim(), effect, StringComparison.OrdinalIgnoreCase))
                    return true;
            }
            return false;
        }
    }
}
