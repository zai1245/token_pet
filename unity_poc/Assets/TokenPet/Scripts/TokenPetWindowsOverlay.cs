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
        private const long WsCaption = 0x00C00000L;
        private const long WsThickFrame = 0x00040000L;
        private const long WsExLayered = 0x00080000L;
        private const long WsExToolWindow = 0x00000080L;
        private const long WsExAppWindow = 0x00040000L;
        private const uint LwaColorKey = 0x00000001;
        private const uint TransparentColorKey = 0x00FF00FF;
        private const int DwmwaNcRenderingPolicy = 2;
        private const int DwmncrpDisabled = 1;
        private const uint SwpNoSize = 0x0001;
        private const uint SwpNoMove = 0x0002;
        private const uint SwpFrameChanged = 0x0020;
        private const int SwHide = 0;
        private const int SwShowNoActivate = 4;
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

        private delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

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

        [DllImport("user32.dll", SetLastError = true)]
        private static extern bool SetLayeredWindowAttributes(IntPtr hWnd, uint colorKey, byte alpha, uint flags);

        [DllImport("user32.dll")]
        private static extern bool SetWindowPos(IntPtr hWnd, IntPtr insertAfter, int x, int y, int width, int height, uint flags);

        [DllImport("user32.dll")]
        private static extern bool GetWindowRect(IntPtr hWnd, out Rect rect);

        [DllImport("user32.dll")]
        private static extern bool GetCursorPos(out Point point);

        [DllImport("user32.dll")]
        private static extern bool ShowWindow(IntPtr hWnd, int command);

        [DllImport("dwmapi.dll")]
        private static extern int DwmSetWindowAttribute(IntPtr hWnd, int attribute, ref int value, int valueSize);

        private IntPtr windowHandle;
#endif

        public bool IsReady { get; private set; }

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
                SetWindowLongPtr64(windowHandle, GwlExStyle, new IntPtr(exStyle));

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
                int startX = ReadIntArgument("--tokenpet-x=", int.MinValue);
                int startY = ReadIntArgument("--tokenpet-y=", int.MinValue);
                if (startX != int.MinValue && startY != int.MinValue)
                    MoveTo(startX, startY);
            }
#endif
            IsReady = true;
        }

        public Vector2Int GetPosition()
        {
#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
            if (windowHandle != IntPtr.Zero && GetWindowRect(windowHandle, out Rect rect))
                return new Vector2Int(rect.Left, rect.Top);
#endif
            return Vector2Int.zero;
        }

        public void MoveTo(int x, int y)
        {
#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
            if (windowHandle != IntPtr.Zero)
                SetWindowPos(windowHandle, HwndTopmost, x, y, 0, 0, SwpNoSize);
#endif
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
