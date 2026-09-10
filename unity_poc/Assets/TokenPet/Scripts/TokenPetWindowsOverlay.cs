using System;
using System.Collections;
using System.Diagnostics;
using System.Runtime.InteropServices;
using UnityEngine;

namespace TokenPet
{
    public sealed class TokenPetWindowsOverlay : MonoBehaviour
    {
#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
        private const int GwlStyle = -16;
        private const int GwlExStyle = -20;
        private const int GwlWndProc = -4;
        private const uint WmNcHitTest = 0x0084;
        private const uint WmRButtonUp = 0x0205;
        private const int HtClient = 1;
        private const int HtTransparent = -1;
        private const long WsCaption = 0x00C00000L;
        private const long WsThickFrame = 0x00040000L;
        private const long WsExLayered = 0x00080000L;
        private const long WsExToolWindow = 0x00000080L;
        private const long WsExAppWindow = 0x00040000L;
        private const long WsExTransparent = 0x00000020L;
        private const uint LwaColorKey = 0x00000001;
        private const uint TransparentColorKey = 0x00FF00FF;
        private const int DwmwaNcRenderingPolicy = 2;
        private const int DwmncrpDisabled = 1;
        private const uint SwpNoSize = 0x0001;
        private const uint SwpNoMove = 0x0002;
        private const uint SwpFrameChanged = 0x0020;
        private const uint MonitorDefaultToNearest = 0x00000002;
        private const int SwHide = 0;
        private const int SwShowNoActivate = 4;
        private const int SmXVirtualScreen = 76;
        private const int SmYVirtualScreen = 77;
        private const int SmCxVirtualScreen = 78;
        private const int SmCyVirtualScreen = 79;
        private static readonly IntPtr HwndTopmost = new IntPtr(-1);

        [StructLayout(LayoutKind.Sequential)]
        private struct Rect
        {
            public int Left;
            public int Top;
            public int Right;
            public int Bottom;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct Point
        {
            public int X;
            public int Y;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct MonitorInfo
        {
            public uint Size;
            public Rect Monitor;
            public Rect Work;
            public uint Flags;
        }

        private delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

        [UnmanagedFunctionPointer(CallingConvention.Winapi)]
        private delegate IntPtr WindowProc(IntPtr hWnd, uint message, IntPtr wParam, IntPtr lParam);

        [DllImport("user32.dll")]
        private static extern bool EnumWindows(EnumWindowsProc enumProc, IntPtr lParam);

        [DllImport("user32.dll")]
        private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

        [DllImport("user32.dll")]
        private static extern bool IsWindowVisible(IntPtr hWnd);

        [DllImport("user32.dll", EntryPoint = "GetWindowLongPtr")]
        private static extern IntPtr GetWindowLongPtr64(IntPtr hWnd, int index);

        [DllImport("user32.dll", EntryPoint = "SetWindowLongPtr")]
        private static extern IntPtr SetWindowLongPtr64(IntPtr hWnd, int index, IntPtr value);

        [DllImport("user32.dll")]
        private static extern IntPtr CallWindowProc(IntPtr previousWindowProc, IntPtr hWnd,
            uint message, IntPtr wParam, IntPtr lParam);

        [DllImport("user32.dll", SetLastError = true)]
        private static extern bool SetLayeredWindowAttributes(IntPtr hWnd, uint colorKey, byte alpha, uint flags);

        [DllImport("user32.dll")]
        private static extern bool SetWindowPos(IntPtr hWnd, IntPtr insertAfter, int x, int y, int width, int height, uint flags);

        [DllImport("user32.dll")]
        private static extern bool GetWindowRect(IntPtr hWnd, out Rect rect);

        [DllImport("user32.dll")]
        private static extern bool GetCursorPos(out Point point);

        [DllImport("user32.dll")]
        private static extern int GetSystemMetrics(int index);

        [DllImport("user32.dll")]
        private static extern bool ShowWindow(IntPtr hWnd, int command);

        [DllImport("user32.dll")]
        private static extern IntPtr MonitorFromWindow(IntPtr hWnd, uint flags);

        [DllImport("user32.dll")]
        private static extern IntPtr MonitorFromPoint(Point point, uint flags);

        [DllImport("user32.dll")]
        private static extern bool GetMonitorInfo(IntPtr monitor, ref MonitorInfo info);

        [DllImport("dwmapi.dll")]
        private static extern int DwmSetWindowAttribute(IntPtr hWnd, int attribute, ref int value, int valueSize);

        private IntPtr windowHandle;
        private Rect compactWindowRect;
        private bool shopExpanded;
        private WindowProc windowProc;
        private IntPtr previousWindowProc;
        private int pendingContextClick;
        private int pendingContextX;
        private int pendingContextY;
#endif

        public bool IsReady { get; private set; }
        public bool IsDesktopStage { get; private set; }
        public Vector2Int PetPosition { get; private set; }
        public Vector2Int StageOrigin { get; private set; }
        public Vector2Int StageSize { get; private set; } = new(340, 300);
        public Func<Vector2Int, bool> InteractiveHitTest { get; set; }

        private IEnumerator Start()
        {
            Application.runInBackground = true;
            yield return null;
            yield return null;

#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
            windowHandle = FindPlayerWindow();

            if (windowHandle != IntPtr.Zero)
            {
                long style = GetWindowLongPtr64(windowHandle, GwlStyle).ToInt64();
                style &= ~(WsCaption | WsThickFrame);
                SetWindowLongPtr64(windowHandle, GwlStyle, new IntPtr(style));

                long exStyle = GetWindowLongPtr64(windowHandle, GwlExStyle).ToInt64();
                // Keep the player activatable. WS_EX_NOACTIVATE makes Unity's legacy
                // input state unreliable and can make a click look like the window
                // vanished even though the process is still alive.
                exStyle |= WsExLayered;
                if (HasArgument("--tokenpet-debug-window"))
                {
                    exStyle &= ~WsExToolWindow;
                    exStyle |= WsExAppWindow;
                }
                else
                {
                    exStyle |= WsExToolWindow;
                    exStyle &= ~WsExAppWindow;
                }
                // Per-pixel hit testing is handled by WM_NCHITTEST below. Keeping
                // WS_EX_TRANSPARENT set until the next Unity frame can lose the
                // first mouse-down, which made furniture appear non-draggable.
                exStyle &= ~WsExTransparent;
                SetWindowLongPtr64(windowHandle, GwlExStyle, new IntPtr(exStyle));

                windowProc = HandleWindowMessage;
                IntPtr callback = Marshal.GetFunctionPointerForDelegate(windowProc);
                previousWindowProc = SetWindowLongPtr64(windowHandle, GwlWndProc, callback);

                // Unity's player swapchain does not reliably preserve per-pixel alpha
                // on every Windows compositor/GPU combination. A reserved magenta
                // colour key is deterministic with the D3D11 bitblt swapchain and
                // does not punch holes in the character's dark eyes or outline.
                bool colorKeyApplied = SetLayeredWindowAttributes(
                    windowHandle, TransparentColorKey, 255, LwaColorKey);
                int nonClientPolicy = DwmncrpDisabled;
                int shadowResult = DwmSetWindowAttribute(windowHandle,
                    DwmwaNcRenderingPolicy, ref nonClientPolicy, sizeof(int));
                SetWindowPos(windowHandle, HwndTopmost, 0, 0, 0, 0,
                    SwpNoMove | SwpNoSize | SwpFrameChanged);
                UnityEngine.Debug.Log(
                    $"TokenPet overlay initialized. hwnd={windowHandle}, " +
                    $"colorKey={colorKeyApplied}, shadow={shadowResult}, " +
                    $"win32={Marshal.GetLastWin32Error()}");
                int startX = ReadIntArgument("--tokenpet-x=", 0);
                int startY = ReadIntArgument("--tokenpet-y=", 0);
                PetPosition = new Vector2Int(startX, startY);
                SetWindowPos(windowHandle, HwndTopmost, startX, startY, 0, 0, SwpNoSize);

                // One transparent Unity surface now owns the character and all
                // furniture. Empty pixels are click-through, so this behaves like
                // several desktop-pet windows without clipping performances at a
                // 340x300 native window boundary.
                int virtualWidth = GetSystemMetrics(SmCxVirtualScreen);
                int virtualHeight = GetSystemMetrics(SmCyVirtualScreen);
                if (virtualWidth > 0 && virtualHeight > 0)
                {
                    StageOrigin = new Vector2Int(
                        GetSystemMetrics(SmXVirtualScreen),
                        GetSystemMetrics(SmYVirtualScreen));
                    StageSize = new Vector2Int(virtualWidth, virtualHeight);
                    SetWindowPos(windowHandle, HwndTopmost,
                        StageOrigin.x, StageOrigin.y, StageSize.x, StageSize.y,
                        SwpFrameChanged);
                    IsDesktopStage = true;
                }
            }
#endif
            IsReady = true;
        }

#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
        private IntPtr HandleWindowMessage(IntPtr hWnd, uint message, IntPtr wParam, IntPtr lParam)
        {
            if (message == WmNcHitTest && IsDesktopStage)
            {
                long packed = lParam.ToInt64();
                int x = unchecked((short)(packed & 0xffff));
                int y = unchecked((short)((packed >> 16) & 0xffff));
                try
                {
                    bool interactive = InteractiveHitTest != null &&
                        InteractiveHitTest(new Vector2Int(x, y));
                    return new IntPtr(interactive ? HtClient : HtTransparent);
                }
                catch (Exception exception)
                {
                    UnityEngine.Debug.LogWarning($"Overlay hit test failed: {exception.Message}");
                    return new IntPtr(HtTransparent);
                }
            }

            // A full-desktop layered Unity window does not deliver legacy
            // Input.GetMouseButtonUp consistently on every Windows compositor.
            // Capture the native message and let Update consume it on Unity's
            // main thread.  This keeps the Python menu bridge reliable without
            // calling Unity APIs from the Win32 window procedure.
            if (message == WmRButtonUp && IsDesktopStage)
            {
                GetCursorPos(out Point point);
                pendingContextX = point.X;
                pendingContextY = point.Y;
                System.Threading.Interlocked.Exchange(ref pendingContextClick, 1);
            }

            return previousWindowProc != IntPtr.Zero
                ? CallWindowProc(previousWindowProc, hWnd, message, wParam, lParam)
                : IntPtr.Zero;
        }
#endif

        public bool TryConsumeContextClick(out Vector2Int cursor)
        {
#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
            if (System.Threading.Interlocked.Exchange(ref pendingContextClick, 0) != 0)
            {
                cursor = new Vector2Int(pendingContextX, pendingContextY);
                return true;
            }
#endif
            cursor = default;
            return false;
        }

        public Vector2Int GetPosition()
        {
            if (IsDesktopStage)
                return PetPosition;
#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
            if (windowHandle != IntPtr.Zero && GetWindowRect(windowHandle, out Rect rect))
                return new Vector2Int(rect.Left, rect.Top);
#endif
            return Vector2Int.zero;
        }

        public void MoveTo(int x, int y)
        {
            PetPosition = new Vector2Int(x, y);
#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
            if (windowHandle != IntPtr.Zero && !IsDesktopStage)
                SetWindowPos(windowHandle, HwndTopmost, x, y, 0, 0, SwpNoSize);
#endif
        }

        public Vector2 DesktopToScreen(Vector2Int desktopPoint)
        {
            return new Vector2(
                desktopPoint.x - StageOrigin.x,
                StageSize.y - (desktopPoint.y - StageOrigin.y));
        }

        public Vector3 DesktopToWorld(Vector2 desktopPoint, Camera targetCamera)
        {
            Vector2 screen = new(
                desktopPoint.x - StageOrigin.x,
                StageSize.y - (desktopPoint.y - StageOrigin.y));
            Vector3 world = targetCamera.ScreenToWorldPoint(
                new Vector3(screen.x, screen.y, -targetCamera.transform.position.z));
            world.z = 0f;
            return world;
        }

        public RectInt GetPetWorkArea()
        {
#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
            Point point = new()
            {
                X = PetPosition.x + 170,
                Y = PetPosition.y + 205
            };
            IntPtr monitor = MonitorFromPoint(point, MonitorDefaultToNearest);
            MonitorInfo info = new() { Size = (uint)Marshal.SizeOf<MonitorInfo>() };
            if (monitor != IntPtr.Zero && GetMonitorInfo(monitor, ref info))
            {
                return new RectInt(
                    info.Work.Left,
                    info.Work.Top,
                    info.Work.Right - info.Work.Left,
                    info.Work.Bottom - info.Work.Top);
            }
#endif
            return new RectInt(StageOrigin.x, StageOrigin.y, StageSize.x, StageSize.y);
        }

        public Vector2Int GetCursorPosition()
        {
#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
            if (GetCursorPos(out Point point))
                return new Vector2Int(point.X, point.Y);
#endif
            return new Vector2Int(
                Mathf.RoundToInt(Input.mousePosition.x),
                Mathf.RoundToInt(Screen.height - Input.mousePosition.y));
        }

        public void SetVisible(bool visible)
        {
#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
            if (windowHandle != IntPtr.Zero)
            {
                ShowWindow(windowHandle, visible ? SwShowNoActivate : SwHide);
                if (visible)
                    SetWindowPos(windowHandle, HwndTopmost, 0, 0, 0, 0, SwpNoMove | SwpNoSize);
            }
#endif
        }

        public void SetShopExpanded(bool expanded)
        {
            if (IsDesktopStage)
            {
#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
                shopExpanded = expanded;
#endif
                return;
            }
#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
            if (windowHandle == IntPtr.Zero || expanded == shopExpanded)
                return;

            if (expanded)
            {
                if (!GetWindowRect(windowHandle, out compactWindowRect))
                    return;

                const int expandedWidth = 720;
                const int expandedHeight = 300;
                int targetX = compactWindowRect.Left;
                int targetY = compactWindowRect.Top;
                IntPtr monitor = MonitorFromWindow(windowHandle, MonitorDefaultToNearest);
                MonitorInfo info = new() { Size = (uint)Marshal.SizeOf<MonitorInfo>() };
                if (monitor != IntPtr.Zero && GetMonitorInfo(monitor, ref info))
                {
                    targetX = Math.Max(info.Work.Left,
                        Math.Min(targetX, info.Work.Right - expandedWidth));
                    targetY = Math.Max(info.Work.Top,
                        Math.Min(targetY, info.Work.Bottom - expandedHeight));
                }
                SetWindowPos(windowHandle, HwndTopmost, targetX, targetY,
                    expandedWidth, expandedHeight, SwpFrameChanged);
            }
            else
            {
                int width = compactWindowRect.Right - compactWindowRect.Left;
                int height = compactWindowRect.Bottom - compactWindowRect.Top;
                SetWindowPos(windowHandle, HwndTopmost,
                    compactWindowRect.Left, compactWindowRect.Top,
                    width, height, SwpFrameChanged);
            }
            shopExpanded = expanded;
#endif
        }

        private static int ReadIntArgument(string prefix, int fallback)
        {
            foreach (string argument in Environment.GetCommandLineArgs())
            {
                if (argument.StartsWith(prefix, StringComparison.OrdinalIgnoreCase) &&
                    int.TryParse(argument.Substring(prefix.Length), out int value))
                {
                    return value;
                }
            }
            return fallback;
        }

        private static bool HasArgument(string expected)
        {
            foreach (string argument in Environment.GetCommandLineArgs())
            {
                if (string.Equals(argument, expected, StringComparison.OrdinalIgnoreCase))
                    return true;
            }
            return false;
        }

        private void OnDestroy()
        {
#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
            if (windowHandle != IntPtr.Zero && previousWindowProc != IntPtr.Zero)
            {
                SetWindowLongPtr64(windowHandle, GwlWndProc, previousWindowProc);
                previousWindowProc = IntPtr.Zero;
            }
            windowProc = null;
#endif
        }

#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
        private static IntPtr FindPlayerWindow()
        {
            uint currentProcessId = (uint)Process.GetCurrentProcess().Id;
            IntPtr result = IntPtr.Zero;
            EnumWindows((candidate, _) =>
            {
                GetWindowThreadProcessId(candidate, out uint candidateProcessId);
                if (candidateProcessId == currentProcessId && IsWindowVisible(candidate))
                {
                    result = candidate;
                    return false;
                }
                return true;
            }, IntPtr.Zero);

            if (result == IntPtr.Zero)
                result = Process.GetCurrentProcess().MainWindowHandle;
            return result;
        }
#endif
    }
}
