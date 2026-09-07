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
        private Transform body;
        private Transform headSocket;
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
            body = new GameObject("Body").transform;
            body.SetParent(rigRoot, false);

            Texture2D texture = Resources.Load<Texture2D>("tokenpet_stylized");
            if (texture == null)
            {
                Debug.LogError("Missing Resources/tokenpet_stylized.png");
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
            float scale = CharacterWidth / sprite.bounds.size.x;
            body.localScale = Vector3.one * scale;

            hitCollider = rigRoot.gameObject.AddComponent<CircleCollider2D>();
            hitCollider.radius = 1.32f;
            hitCollider.offset = new Vector2(0f, -0.02f);

            headSocket = new GameObject("Socket_Head").transform;
            headSocket.SetParent(rigRoot, false);
            headSocket.localPosition = new Vector3(0f, 1.35f, 0f);

            equipment = rigRoot.gameObject.AddComponent<TokenPetEquipmentController>();
            equipment.RegisterSocket("head", headSocket);
            equipment.LoadCatalog();

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
                version = "unity-poc-0.1"
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
            Vector3 scale = Vector3.one;
            float rotation = 0f;
            float horizontal = 0f;
            float vertical = 0f;

            switch (motion)
            {
                case MotionState.Idle:
                    vertical = Mathf.Sin(motionTime * 2.2f) * 0.035f;
                    scale.x = 1f + Mathf.Sin(motionTime * 2.2f) * 0.018f;
                    scale.y = 1f - Mathf.Sin(motionTime * 2.2f) * 0.022f;
                    if (!externallyDriven && autonomousTimer > 4.5f)
                    {
                        autonomousTimer = 0f;
                        EnterState(MotionState.Walk);
                    }
                    break;

                case MotionState.Walk:
                    vertical = Mathf.Abs(Mathf.Sin(motionTime * 8f)) * 0.08f;
                    horizontal = Mathf.Sin(motionTime * 4f) * 0.055f;
                    rotation = Mathf.Sin(motionTime * 8f) * 4.2f;
                    scale.y = 1f + Mathf.Abs(Mathf.Sin(motionTime * 8f)) * 0.035f;
                    if (!externallyDriven && autonomousTimer > 4f)
                    {
                        autonomousTimer = 0f;
                        EnterState(MotionState.Idle);
                    }
                    break;

                case MotionState.Poke:
                    float poke = Mathf.Clamp01(motionTime / 0.58f);
                    vertical = Mathf.Sin(poke * Mathf.PI) * 0.22f;
                    rotation = Mathf.Sin(poke * Mathf.PI * 4f) * (1f - poke) * 13f;
                    scale.x = 1f + Mathf.Sin(poke * Mathf.PI * 3f) * 0.10f;
                    scale.y = 1f - Mathf.Sin(poke * Mathf.PI * 3f) * 0.10f;
                    if (poke >= 1f)
                    {
                        ipc.Send(new RendererEvent { event_name = "action_finished", action = "poke" });
                        EnterState(MotionState.Idle);
                    }
                    break;

                case MotionState.Drag:
                    rotation = Mathf.Clamp(-pointerVelocity.x * 0.012f, -14f, 14f);
                    scale.x = 0.94f;
                    scale.y = 1.08f;
                    break;

                case MotionState.Airborne:
                    airborneVelocity.y -= 5.5f * deltaTime;
                    airborneHeight += airborneVelocity.y * deltaTime;
                    vertical = Mathf.Clamp(airborneHeight, 0f, 0.72f);
                    horizontal = Mathf.Clamp(airborneVelocity.x * 0.08f, -0.20f, 0.20f);
                    rotation = Mathf.Repeat(motionTime * 280f, 360f);
                    if (airborneHeight <= 0f && airborneVelocity.y < 0f)
                    {
                        airborneHeight = 0f;
                        EnterState(MotionState.Land);
                    }
                    break;

                case MotionState.Land:
                    float land = Mathf.Clamp01(motionTime / 0.42f);
                    float impact = Mathf.Sin(land * Mathf.PI) * (1f - land);
                    scale.x = 1f + impact * 0.35f;
                    scale.y = 1f - impact * 0.30f;
                    if (land >= 1f)
                    {
                        ipc.Send(new RendererEvent { event_name = "action_finished", action = "land" });
                        EnterState(MotionState.Idle);
                    }
                    break;
            }

            // The native desktop window owns global movement. Keep the rig fixed and
            // limit visual secondary motion to a safe inset so no animation can hit
            // the 512x512 Unity viewport and clip the character.
            rigRoot.position = RigRestPosition;
            body.localPosition = new Vector3(horizontal, vertical, 0f);
            body.localRotation = Quaternion.Euler(0f, 0f, rotation);

            SpriteRenderer spriteRenderer = body.GetComponent<SpriteRenderer>();
            float baseScale = CharacterWidth / spriteRenderer.sprite.bounds.size.x;
            body.localScale = new Vector3(baseScale * scale.x, baseScale * scale.y, baseScale);
            headSocket.localPosition = new Vector3(horizontal, 1.35f + vertical * 0.5f, 0f);
            headSocket.localRotation = Quaternion.Euler(0f, 0f, rotation * 0.65f);
            ClampVisualInsideViewport();
        }

        private void ClampVisualInsideViewport()
        {
            SpriteRenderer[] renderers = rigRoot.GetComponentsInChildren<SpriteRenderer>();
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
                body.position += correction;
                headSocket.position += correction;
            }
        }

        private void EnterState(MotionState next)
        {
            motion = next;
            motionTime = 0f;
            if (next == MotionState.Airborne)
                airborneHeight = 0f;
            if (next == MotionState.Idle || next == MotionState.Walk)
                externallyDriven = false;
        }

        private void OnCommand(RendererCommand command)
        {
            switch (command.command)
            {
                case "snapshot":
                    ApplyLegacyState(command.state);
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
