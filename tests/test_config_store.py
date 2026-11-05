from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from config_store import JsonConfigStore


class ConfigStoreTests(unittest.TestCase):
    def test_parallel_threads_keep_all_independent_updates(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonConfigStore(Path(directory) / "settings")
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(lambda n: store.update({str(n): n}), range(30)))
            self.assertEqual({str(n): n for n in range(30)}, store.load())

    def test_parallel_processes_keep_the_pet_and_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings"
            store = JsonConfigStore(path)
            store.update({"pet_game": {"coins": 123}})
            source = "from config_store import JsonConfigStore; import sys; JsonConfigStore(sys.argv[1]).update({sys.argv[2]: True})"
            children = [subprocess.Popen([sys.executable, "-c", source, str(path), str(n)]) for n in range(6)]
            for child in children:
                self.assertEqual(0, child.wait(timeout=15))
            self.assertEqual({"pet_game": {"coins": 123}, **{str(n): True for n in range(6)}}, store.load())

    def test_corrupted_primary_recovers_from_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings"
            store = JsonConfigStore(path)
            store.update({"pet_game": {"coins": 123}})
            store.update({"position": 10})
            path.write_text("{broken")
            self.assertEqual({"pet_game": {"coins": 123}}, store.load())

    def test_unrecoverable_save_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings"
            path.write_text("{broken")
            with self.assertRaises(ValueError):
                JsonConfigStore(path).update({"coins": 0})
            self.assertEqual("{broken", path.read_text())

    def test_removing_credentials_also_removes_them_from_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonConfigStore(Path(directory) / "settings")
            store.update({"email": "user", "password": "test", "pet_game": {"coins": 123}})
            store.update({}, remove=("email", "password"))
            for path in (store.path, store.backup):
                self.assertEqual({"pet_game": {"coins": 123}}, json.loads(path.read_text()))

    def test_failed_atomic_replace_preserves_the_primary(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonConfigStore(Path(directory) / "settings")
            store.update({"coins": 123})
            import config_store
            replace = config_store.os.replace
            def fail_primary(source, target):
                if target == store.path:
                    raise OSError("disk unavailable")
                return replace(source, target)
            with mock.patch("config_store.os.replace", side_effect=fail_primary), self.assertRaises(OSError):
                store.update({"coins": 456})
            self.assertEqual({"coins": 123}, store.load())


if __name__ == "__main__":
    unittest.main()
