"""Atomic JSON settings updates shared by the pet and statistics process."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
import threading
import time


_thread_lock = threading.RLock()


class JsonConfigStore:
    def __init__(self, path):
        self.path = Path(path)
        self.backup = self.path.with_name(self.path.name + ".bak")

    @contextmanager
    def _locked(self):
        with _thread_lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(str(self.path) + ".lock", "a+b") as lock:
                if os.fstat(lock.fileno()).st_size == 0:
                    lock.write(b"\0")
                    lock.flush()
                lock.seek(0)
                if os.name == "nt":
                    import msvcrt
                    deadline = time.monotonic() + 5
                    while True:
                        try:
                            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                            break
                        except OSError:
                            if time.monotonic() >= deadline:
                                raise TimeoutError("Settings are locked by another process")
                            time.sleep(0.01)
                else:
                    import fcntl
                    fcntl.flock(lock, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    lock.seek(0)
                    if os.name == "nt":
                        msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(lock, fcntl.LOCK_UN)

    def _read(self):
        if not self.path.exists() and not self.backup.exists():
            return {}
        for path in (self.path, self.backup):
            try:
                with path.open(encoding="utf-8") as source:
                    data = json.load(source)
                if isinstance(data, dict):
                    return data
            except (OSError, ValueError):
                continue
        # Do not silently overwrite the only copy of a damaged savegame.
        raise ValueError("Settings and recovery backup are unreadable")

    def _write(self, path, data):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent,
                prefix=path.name + ".", suffix=".tmp", delete=False,
            ) as output:
                temporary = Path(output.name)
                json.dump(data, output, ensure_ascii=False, indent=2, allow_nan=False)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def load(self):
        with self._locked():
            return self._read()

    def update(self, changes, remove=()):
        with self._locked():
            data = self._read()
            updated = dict(data)
            updated.update(changes)
            for key in remove:
                updated.pop(key, None)
            # Serialize before touching either existing copy.
            json.dumps(updated, allow_nan=False)
            backup = dict(data)
            for key in remove:
                backup.pop(key, None)
            self._write(self.backup, backup)
            self._write(self.path, updated)
