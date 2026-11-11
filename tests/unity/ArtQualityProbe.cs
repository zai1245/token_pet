// Test-only checks of the real DWM-composited window on controlled backgrounds.
using System;
using System.Collections;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using UnityEngine;

namespace TokenPet
{
    public sealed class ArtQualityProbe : MonoBehaviour
    {
        [StructLayout(LayoutKind.Sequential)] private struct NativeRect { public int left, top, right, bottom; }
        [StructLayout(LayoutKind.Sequential)] private struct NativePoint { public int x, y; }
        [StructLayout(LayoutKind.Sequential)] private struct BitmapInfo
        {
            public uint size; public int width, height; public ushort planes, bits;
            public uint compression, imageSize; public int x, y; public uint used, important;
        }
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern IntPtr CreateWindowEx(
            uint ex, string cls, string title, uint style, int x, int y, int width, int height,
            IntPtr parent, IntPtr menu, IntPtr instance, IntPtr parameter);
        [DllImport("user32.dll")] private static extern bool DestroyWindow(IntPtr window);
        [DllImport("user32.dll")] private static extern bool UpdateWindow(IntPtr window);
        [DllImport("user32.dll")] private static extern bool SetWindowPos(IntPtr window, IntPtr after, int x, int y, int width, int height, uint flags);
        [DllImport("user32.dll")] private static extern IntPtr GetDC(IntPtr window);
        [DllImport("user32.dll")] private static extern int ReleaseDC(IntPtr window, IntPtr dc);
        [DllImport("user32.dll")] private static extern int FillRect(IntPtr dc, ref NativeRect rect, IntPtr brush);
        [DllImport("user32.dll")] private static extern IntPtr WindowFromPoint(NativePoint point);
        [DllImport("user32.dll")] private static extern bool SetCursorPos(int x, int y);
        [DllImport("user32.dll")] private static extern bool GetCursorPos(out NativePoint point);
        [DllImport("user32.dll")] private static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extra);
        [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr window, out uint pid);
        [DllImport("gdi32.dll")] private static extern IntPtr GetStockObject(int index);
        [DllImport("gdi32.dll")] private static extern IntPtr CreateCompatibleDC(IntPtr dc);
        [DllImport("gdi32.dll")] private static extern IntPtr CreateDIBSection(IntPtr dc, ref BitmapInfo info, uint usage, out IntPtr data, IntPtr section, uint offset);
        [DllImport("gdi32.dll")] private static extern IntPtr SelectObject(IntPtr dc, IntPtr value);
        [DllImport("gdi32.dll")] private static extern bool DeleteObject(IntPtr value);
        [DllImport("gdi32.dll")] private static extern bool DeleteDC(IntPtr dc);
        [DllImport("gdi32.dll")] private static extern bool BitBlt(IntPtr target, int x, int y, int width, int height, IntPtr source, int sx, int sy, uint operation);
        [DllImport("dwmapi.dll")] private static extern int DwmFlush();

        private const int Width = 850, Height = 430;
        private int left, top, checks;
        private IntPtr backdrop;
        private static readonly BindingFlags Private = BindingFlags.Instance | BindingFlags.NonPublic;

        private void Check(bool condition, string message)
        {
            if (!condition)
            {
                File.WriteAllText(Environment.GetEnvironmentVariable("TOKENPET_ART_PROBE_RESULT"), message);
                Application.Quit(1);
                throw new Exception(message);
            }
            checks++;
        }

        private IEnumerator Start()
        {
            TokenPetWindowsOverlay overlay = FindAnyObjectByType<TokenPetWindowsOverlay>();
            while (overlay != null && !overlay.IsReady) yield return null;
            yield return new WaitForSecondsRealtime(0.4f);
            string result = Environment.GetEnvironmentVariable("TOKENPET_ART_PROBE_RESULT");
            string output = Path.GetDirectoryName(result);
            try
            {
                Check(overlay != null && overlay.IsDesktopStage, "desktop stage missing");
                Camera camera = Camera.main;
                Check(camera.backgroundColor == Color.clear, "camera still uses an opaque/color-key matte");
                left = overlay.StageOrigin.x + Mathf.Min(360, Mathf.Max(0, overlay.StageSize.x - Width));
                top = overlay.StageOrigin.y + Mathf.Min(260, Mathf.Max(0, overlay.StageSize.y - Height));
                IntPtr hwnd = (IntPtr)typeof(TokenPetWindowsOverlay).GetField("windowHandle", Private).GetValue(overlay);
                TokenPetPocBootstrap pet = FindAnyObjectByType<TokenPetPocBootstrap>();
                pet.enabled = false;
                overlay.MoveTo(left + 60, top + 40);
                typeof(TokenPetPocBootstrap).GetMethod("RefreshDesktopStageLayout", Private).Invoke(pet, null);
                typeof(TokenPetPocBootstrap).GetMethod("Animate", Private).Invoke(pet, new object[] { 0f });
                FindAnyObjectByType<TokenPetEquipmentController>().Equip("head", "scholar_cap");
                FindAnyObjectByType<TokenPetStatusHud>().SetUsage(12.34, "live");
                TokenPetFurnitureStage furniture = FindAnyObjectByType<TokenPetFurnitureStage>();
                furniture.Sync(JsonUtility.ToJson(new TokenPetFurniturePayload { items = new[] {
                    new TokenPetFurnitureItem { id = "lazy_sofa", x = left + 290, y = top + 140, width = 220, height = 150 },
                    new TokenPetFurnitureItem { id = "night_lamp", x = left + 540, y = top + 140, width = 150, height = 160 }
                }}));
                yield return new WaitForEndOfFrame();

                LineRenderer limb = GameObject.Find("Arm_Left").GetComponent<LineRenderer>();
                Check(limb.sharedMaterial.color == Color.white, "limb tint is applied twice");
                Check(limb.startColor.r > 0.3f, "limb ink is too dark");
                foreach (string id in new[] { "lazy_sofa", "night_lamp" })
                {
                    Transform root = GameObject.Find("Furniture_" + id).transform;
                    SpriteRenderer art = root.Find("Visual").GetComponentInChildren<SpriteRenderer>();
                    Bounds visible = TokenPetProceduralArt.VisibleBounds(art, root);
                    float seat = root.Find("Contact shadow").localPosition.y;
                    Check(Mathf.Abs(seat - visible.min.y) < 0.05f, "shadow floats below " + id);
                }
                typeof(TokenPetPocBootstrap).GetMethod("CachePetInteractiveRect", Private).Invoke(pet, null);
                if (uint.TryParse(Environment.GetEnvironmentVariable("TOKENPET_ART_FOREIGN_PID"), out uint foreignPid))
                    yield return ClickOtherWindow(hwnd, foreignPid);

                // Capture only this application's fixture, backed by a window
                // owned by the probe, so no personal desktop contents are read.
                for (int phase = 0; phase < 2; phase++)
                {
                    ShowBackdrop(hwnd, phase == 0);
                    yield return new WaitForSecondsRealtime(0.18f);
                    yield return new WaitForEndOfFrame();
                    DwmFlush();
                    Color32[] pixels = CaptureDesktop(Path.Combine(output, phase == 0 ? "art-dark.png" : "art-light.png"));
                    Color32 corner = pixels[0];
                    Check(phase == 0 ? corner.r == 0 && corner.g == 0 && corner.b == 0 :
                        corner.r == 255 && corner.g == 255 && corner.b == 255,
                        "DWM does not reveal the controlled backdrop");
                    int magenta = 0;
                    foreach (Color32 pixel in pixels)
                        if (pixel.r > 110 && pixel.b > 110 && pixel.g < Math.Min(pixel.r, pixel.b) * 0.6f) magenta++;
                    Check(magenta == 0, $"matte-colored edge pixels remain: {magenta}");
                    DestroyBackdrop();
                }

                yield return new WaitForEndOfFrame();
                RenderTexture frame = new(Screen.width, Screen.height, 0, RenderTextureFormat.ARGB32);
                ScreenCapture.CaptureScreenshotIntoRenderTexture(frame);
                RenderTexture previous = RenderTexture.active;
                RenderTexture.active = frame;
                Texture2D rgba = new(Screen.width, Screen.height, TextureFormat.RGBA32, false);
                rgba.ReadPixels(new Rect(0, 0, Screen.width, Screen.height), 0, 0); rgba.Apply();
                Color32[] alpha = rgba.GetPixels32();
                int transparent = 0, partial = 0;
                foreach (Color32 pixel in alpha)
                {
                    if (pixel.a == 0) transparent++;
                    else if (pixel.a < 255) partial++;
                }
                Check(transparent > alpha.Length / 2, "framebuffer lost its transparent background");
                Check(partial > 100, "antialiased edges/shadows lost fractional alpha");
                RenderTexture.active = previous; Destroy(rgba); frame.Release(); Destroy(frame);

                TokenPetShopPanel shop = FindAnyObjectByType<TokenPetShopPanel>();
                shop.Show("{\"coins\":125,\"items\":[{\"id\":\"crown\",\"name\":\"小小皇冠\",\"description\":\"暖金色的小皇冠，今天也要閃閃發亮。\",\"category\":\"accessory\",\"price\":50},{\"id\":\"scholar_cap\",\"name\":\"學士帽\",\"description\":\"把每天累積的小進步，戴在頭上。\",\"category\":\"accessory\",\"price\":30},{\"id\":\"cat_ears\",\"name\":\"貓咪耳朵\",\"description\":\"柔軟的暖粉色耳朵。\",\"category\":\"accessory\",\"price\":40}]}");
                ShowBackdrop(hwnd, false);
                yield return new WaitForSecondsRealtime(0.18f);
                yield return new WaitForEndOfFrame(); DwmFlush();
                CaptureDesktop(Path.Combine(output, "art-shop.png"));
                DestroyBackdrop();
                if (foreignPid != 0)
                {
                    shop.Hide(false);
                    yield return DragPet(hwnd, overlay, pet);
                    yield return ClickOtherWindow(hwnd, foreignPid);
                }
                File.WriteAllText(result, $"PASS: {checks} native art/alpha checks, dark and light desktop captures");
                Application.Quit(0);
            }
            finally
            {
                DestroyBackdrop();
            }
        }

        private IEnumerator ClickOtherWindow(IntPtr hwnd, uint foreignPid)
        {
            string clicked = Environment.GetEnvironmentVariable("TOKENPET_ART_CLICK_RESULT");
            File.Delete(clicked);
            GetCursorPos(out NativePoint original);
            int x = left + 14, y = top + 14;
            SetWindowPos(hwnd, new IntPtr(-1), 0, 0, 0, 0, 0x0013);
            SetCursorPos(x, y);
            try
            {
                yield return new WaitForSecondsRealtime(0.12f);
                IntPtr candidate = WindowFromPoint(new NativePoint { x = x, y = y });
                GetWindowThreadProcessId(candidate, out uint candidatePid);
                Check(CursorAt(x, y) && (candidatePid == foreignPid || candidate == hwnd),
                    "test cursor or foreign fixture is covered by an unrelated window");
                mouse_event(0x0002, 0, 0, 0, UIntPtr.Zero);
                mouse_event(0x0004, 0, 0, 0, UIntPtr.Zero);
                yield return new WaitForSecondsRealtime(0.25f);
                Check(File.Exists(clicked), "transparent stage swallowed a real mouse click to the other application");
            }
            finally
            {
                if (CursorAt(x, y)) SetCursorPos(original.x, original.y);
            }
        }

        private IEnumerator DragPet(IntPtr hwnd, TokenPetWindowsOverlay overlay, TokenPetPocBootstrap pet)
        {
            GetCursorPos(out NativePoint original);
            Vector2Int originalPosition = overlay.GetPosition();
            int x = left + 230, y = top + 245;
            FieldInfo pointerDown = typeof(TokenPetPocBootstrap).GetField("pointerDown", Private);
            bool pressed = false;
            SetWindowPos(hwnd, new IntPtr(-1), 0, 0, 0, 0, 0x0013);
            SetCursorPos(x, y);
            try
            {
                yield return new WaitForSecondsRealtime(0.12f);
                Check(CursorAt(x, y) && WindowFromPoint(new NativePoint { x = x, y = y }) == hwnd,
                    "the visible pet cannot receive mouse input");
                mouse_event(0x0008, 0, 0, 0, UIntPtr.Zero);
                mouse_event(0x0010, 0, 0, 0, UIntPtr.Zero);
                yield return new WaitForSecondsRealtime(0.12f);
                Check(overlay.TryConsumeContextClick(out _), "the pet did not receive a right click");

                Check(CursorAt(x, y), "test cursor moved off the pet");
                pet.enabled = true;
                mouse_event(0x0002, 0, 0, 0, UIntPtr.Zero);
                pressed = true;
                yield return new WaitForSecondsRealtime(0.12f);
                Check((bool)pointerDown.GetValue(pet), "the pet did not receive the first mouse-down");
                x -= 140;
                SetCursorPos(x, y);
                yield return new WaitForSecondsRealtime(0.12f);
                Check(overlay.GetPosition().x == originalPosition.x - 140,
                    "drag did not follow the cursor outside the original pet bounds");
                mouse_event(0x0004, 0, 0, 0, UIntPtr.Zero);
                pressed = false;
                yield return new WaitForSecondsRealtime(0.12f);
                Check(!(bool)pointerDown.GetValue(pet), "drag kept intercepting input after mouse-up");
            }
            finally
            {
                if (pressed) mouse_event(0x0004, 0, 0, 0, UIntPtr.Zero);
                pet.enabled = false;
                if (CursorAt(x, y)) SetCursorPos(original.x, original.y);
            }
        }

        private static bool CursorAt(int x, int y)
        {
            return GetCursorPos(out NativePoint current) && current.x == x && current.y == y;
        }

        private void ShowBackdrop(IntPtr hwnd, bool dark)
        {
            DestroyBackdrop();
            backdrop = CreateWindowEx(0x88, "STATIC", "TokenPet art test backdrop", 0x90000000,
                left, top, Width, Height, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero);
            if (backdrop == IntPtr.Zero) throw new Exception("test backdrop creation failed");
            UpdateWindow(backdrop);
            IntPtr dc = GetDC(backdrop);
            NativeRect fill = new() { right = Width, bottom = Height };
            FillRect(dc, ref fill, GetStockObject(dark ? 4 : 0));
            ReleaseDC(backdrop, dc);
            SetWindowPos(hwnd, new IntPtr(-1), 0, 0, 0, 0, 0x13);
        }

        private void DestroyBackdrop()
        {
            if (backdrop != IntPtr.Zero) { DestroyWindow(backdrop); backdrop = IntPtr.Zero; }
        }

        private Color32[] CaptureDesktop(string path)
        {
            IntPtr dc = GetDC(IntPtr.Zero), memory = CreateCompatibleDC(dc);
            BitmapInfo info = new() { size = 40, width = Width, height = Height, planes = 1, bits = 32 };
            IntPtr bitmap = CreateDIBSection(dc, ref info, 0, out IntPtr data, IntPtr.Zero, 0);
            IntPtr original = SelectObject(memory, bitmap);
            try
            {
                if (!BitBlt(memory, 0, 0, Width, Height, dc, left, top, 0x40CC0020))
                    throw new Exception("test backdrop capture failed");
                byte[] bytes = new byte[Width * Height * 4];
                Marshal.Copy(data, bytes, 0, bytes.Length);
                for (int i = 3; i < bytes.Length; i += 4) bytes[i] = 255;
                Texture2D image = new(Width, Height, TextureFormat.BGRA32, false);
                image.LoadRawTextureData(bytes); image.Apply();
                File.WriteAllBytes(path, image.EncodeToPNG());
                Color32[] pixels = image.GetPixels32(); Destroy(image);
                return pixels;
            }
            finally
            {
                SelectObject(memory, original); DeleteObject(bitmap); DeleteDC(memory); ReleaseDC(IntPtr.Zero, dc);
            }
        }
    }
}
