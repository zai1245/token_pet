"""Optional Unity renderer process bridge for TokenPet.

The legacy Tkinter pet remains the default and source of truth.  This module is
stdlib-only so importing it never adds a runtime dependency to the existing
application or PyInstaller build.
"""

from __future__ import annotations

from collections import deque
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from typing import Any


UNITY_WINDOW_WIDTH = 340
UNITY_WINDOW_HEIGHT = 300


class UnityRendererBridge:
    """Launch and communicate with the opt-in Unity renderer."""

    def __init__(
        self,
        executable: str | os.PathLike[str] | None = None,
        start_position: tuple[int, int] | None = None,
    ) -> None:
        self.executable = self.resolve_executable(executable)
        self.start_position = start_position
        self.process: subprocess.Popen[bytes] | None = None
        self._server: socket.socket | None = None
        self._connection: socket.socket | None = None
        self._reader = None
        self._events: deque[dict[str, Any]] = deque()
        self._events_lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._connected_event = threading.Event()
        self._last_snapshot: str | None = None
        self._last_snapshot_at = 0.0
        self._exit_reported = False

    @staticmethod
    def resolve_executable(
        configured: str | os.PathLike[str] | None = None,
    ) -> Path:
        if configured:
            # An explicit path is authoritative, including when it is missing.
            # Silently falling back would hide a deployment/configuration error.
            return Path(configured).expanduser().resolve()

        environment_path = os.environ.get("TOKENPET_UNITY_RENDERER")
        if environment_path:
            return Path(environment_path).expanduser().resolve()

        source_root = Path(__file__).resolve().parent
        candidates: list[Path] = [
            source_root / "unity_poc" / "Build" / "TokenPetUnity.exe"
        ]

        if getattr(sys, "frozen", False):
            executable_root = Path(sys.executable).resolve().parent
            candidates.append(executable_root / "renderer" / "TokenPetUnity.exe")
            candidates.append(executable_root / "TokenPetUnity.exe")

        for candidate in candidates:
            expanded = candidate.expanduser().resolve()
            if expanded.is_file():
                return expanded

        return candidates[0].expanduser().resolve() if candidates else (
            source_root / "unity_poc" / "Build" / "TokenPetUnity.exe"
        )

    @property
    def connected(self) -> bool:
        return self._connected_event.is_set()

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self) -> bool:
        """Start the player and listener. Return False without side effects if absent."""
        if not self.executable.is_file():
            self._queue_event(
                {
                    "event_name": "start_failed",
                    "message": f"Unity renderer not found: {self.executable}",
                }
            )
            return False

        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("127.0.0.1", 0))
        self._server.listen(1)
        self._server.settimeout(0.5)
        port = self._server.getsockname()[1]

        command = [
            str(self.executable),
            "-popupwindow",
            "-screen-fullscreen",
            "0",
            "-screen-width",
            str(UNITY_WINDOW_WIDTH),
            "-screen-height",
            str(UNITY_WINDOW_HEIGHT),
            f"--tokenpet-port={port}",
        ]
        if os.environ.get("TOKENPET_DEBUG_WINDOW") == "1":
            command.append("--tokenpet-debug-window")
        if self.start_position is not None:
            command.extend(
                [
                    f"--tokenpet-x={int(self.start_position[0])}",
                    f"--tokenpet-y={int(self.start_position[1])}",
                ]
            )
        try:
            self.process = subprocess.Popen(
                command,
                cwd=str(self.executable.parent),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            self._queue_event({"event_name": "start_failed", "message": str(exc)})
            self._close_server()
            return False

        threading.Thread(
            target=self._accept_and_read,
            daemon=True,
            name="TokenPet Unity bridge",
        ).start()
        return True

    def send(self, payload: dict[str, Any]) -> bool:
        connection = self._connection
        if connection is None:
            return False

        data = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode(
            "utf-8"
        )
        try:
            with self._send_lock:
                connection.sendall(data)
            return True
        except OSError as exc:
            self._queue_event({"event_name": "connection_lost", "message": str(exc)})
            self._connected_event.clear()
            return False

    def send_snapshot(
        self,
        *,
        state: str,
        emotion: str,
        accessory: str | None,
        look_x: float,
        look_y: float,
        equipment: dict[str, str] | None = None,
        mouth: str = "normal",
        level: int = 1,
        xp: float = 0.0,
        xp_max: float = 100.0,
        satiety: float = 100.0,
        coins: int = 0,
        eat_type: str = "",
        furniture: str = "",
        effects: str = "",
        show_board: bool = False,
        board_text: str = "",
        overtime: bool = False,
    ) -> bool:
        payload = {
            "command": "snapshot",
            "state": state,
            "emotion": emotion,
            "mouth": mouth,
            "item": accessory or "",
            "head_item": (equipment or {}).get("head", ""),
            "face_item": (equipment or {}).get("face", ""),
            "neck_item": (equipment or {}).get("neck", ""),
            "body_item": (equipment or {}).get("body", ""),
            "look_x": round(float(look_x), 3),
            "look_y": round(float(look_y), 3),
            "level": max(1, int(level)),
            "xp": round(max(0.0, float(xp)), 2),
            "xp_max": round(max(1.0, float(xp_max)), 2),
            "satiety": round(max(0.0, min(100.0, float(satiety))), 2),
            "coins": max(0, int(coins)),
            "eat_type": eat_type or "",
            "furniture": furniture or "",
            "effects": effects or "",
            "show_board": bool(show_board),
            "board_text": board_text or "",
            "overtime": bool(overtime),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        now = time.monotonic()
        if encoded == self._last_snapshot and now - self._last_snapshot_at < 1.0:
            return True
        self._last_snapshot = encoded
        self._last_snapshot_at = now
        return self.send(payload)

    def move_window(self, x: float, y: float) -> bool:
        """Move the native Unity overlay to a Python-owned desktop position."""
        return self.send(
            {
                "command": "move_window",
                "x": int(round(x)),
                "y": int(round(y)),
            }
        )

    def show_popup(
        self,
        text: str,
        x: float,
        y: float,
        color: str = "#f9e2af",
        duration: float = 0.8,
    ) -> bool:
        """Render legacy feedback text on the visible Unity surface."""
        return self.send(
            {
                "command": "popup",
                "text": str(text),
                "x": round(float(x), 2),
                "y": round(float(y), 2),
                "color": color,
                "duration": max(0.25, float(duration)),
            }
        )

    def show_shop(self, payload: dict[str, Any]) -> bool:
        """Open or refresh the shop inside the Unity renderer surface."""
        return self.send(
            {
                "command": "show_shop",
                "payload": json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            }
        )

    def sync_furniture(self, items: list[dict[str, Any]]) -> bool:
        """Mirror Python-owned furniture state into the Unity desktop stage."""
        return self.send(
            {
                "command": "sync_furniture",
                "payload": json.dumps(
                    {"items": items},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            }
        )

    def trigger_furniture(self, item: str, action: str) -> bool:
        return self.send(
            {
                "command": "trigger_furniture",
                "item": str(item),
                "action": str(action),
            }
        )

    def poll_events(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        with self._events_lock:
            while self._events:
                events.append(self._events.popleft())

        if self.process is not None and self.process.poll() is not None and not self._exit_reported:
            self._exit_reported = True
            events.append(
                {
                    "event_name": "process_exit",
                    "return_code": self.process.returncode,
                }
            )
        return events

    def stop(self) -> None:
        self._stop_event.set()
        if self.connected:
            self.send({"command": "shutdown"})

        process = self.process
        if process is not None and process.poll() is None:
            try:
                process.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    process.kill()

        self._connected_event.clear()
        try:
            if self._reader is not None:
                self._reader.close()
        except OSError:
            pass
        try:
            if self._connection is not None:
                self._connection.close()
        except OSError:
            pass
        self._close_server()

    def _accept_and_read(self) -> None:
        assert self._server is not None
        try:
            while not self._stop_event.is_set():
                if self.process is not None and self.process.poll() is not None:
                    return
                try:
                    connection, _address = self._server.accept()
                    break
                except socket.timeout:
                    continue
            else:
                return

            connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._connection = connection
            self._reader = connection.makefile("r", encoding="utf-8", newline="\n")
            self._connected_event.set()

            for line in self._reader:
                if self._stop_event.is_set():
                    break
                try:
                    payload = json.loads(line)
                    if isinstance(payload, dict):
                        self._queue_event(payload)
                except json.JSONDecodeError as exc:
                    self._queue_event({"event_name": "protocol_error", "message": str(exc)})

            if not self._stop_event.is_set():
                self._queue_event(
                    {
                        "event_name": "connection_lost",
                        "message": "Unity renderer closed the IPC connection",
                    }
                )
        except OSError as exc:
            if not self._stop_event.is_set():
                self._queue_event({"event_name": "connection_lost", "message": str(exc)})
        finally:
            self._connected_event.clear()
            self._close_server()

    def _queue_event(self, payload: dict[str, Any]) -> None:
        with self._events_lock:
            self._events.append(payload)

    def _close_server(self) -> None:
        try:
            if self._server is not None:
                self._server.close()
        except OSError:
            pass
        self._server = None


def unity_renderer_requested(config: dict[str, Any] | None = None) -> bool:
    """Return True only for the explicit flag or saved opt-in backend."""
    if "--unity-poc" in sys.argv:
        return True
    return bool(config and config.get("renderer_backend") == "unity")
