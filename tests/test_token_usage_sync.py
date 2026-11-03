import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

import requests

import emojinoko_monitor as app
from unity_renderer_bridge import UnityRendererBridge


ROOT = Path(__file__).resolve().parents[1]


def response(status, data):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(data).encode("utf-8")
    return result


class TokenUsageSyncTests(unittest.TestCase):
    def setUp(self):
        self.monitor = app.EmojinokoMonitor.__new__(app.EmojinokoMonitor)
        monitor = self.monitor
        monitor.STANDALONE = False
        monitor.TOKEN = "test-session"
        monitor.PHISON_TOKEN = "test-usage-key"
        monitor.pet_data = {"coins": 4}
        monitor.monthly_prompt_tokens = 0
        monitor.monthly_complete_tokens = 0
        monitor.monthly_cost_usd = 0.0
        monitor.usage_status = "loading"
        monitor.is_fetching = False
        monitor.is_manual_refresh = False
        monitor.root = mock.Mock()
        self.callbacks = []
        monitor.root.after.side_effect = lambda delay, callback, *args: self.callbacks.append(
            (callback, args)
        )
        monitor.save_pet_savegame = mock.Mock()
        monitor.create_text_popup = mock.Mock()
        monitor._spawn_token_particle = mock.Mock()
        monitor._auto_relogin = mock.Mock()
        monitor._unity_renderer_active = True
        monitor.pet = SimpleNamespace(
            state="idle", eye_state="normal", mouth_state="normal",
            equipped_accessory=None, look_offset_x=0, look_offset_y=0,
        )
        monitor.unity_renderer = UnityRendererBridge("unused.exe")
        self.socket = mock.Mock()
        monitor.unity_renderer._connection = self.socket
        monitor.unity_renderer._connected_event.set()
        self.log_patch = mock.patch("usage_widget._debug_log")
        self.log_patch.start()
        self.addCleanup(self.log_patch.stop)

    def fetch(self, request):
        with mock.patch("usage_widget.requests.request", side_effect=request), \
                mock.patch("usage_widget.time.sleep"), \
                contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            self.monitor._fetch_usage_api()
        # Apply the callbacks scheduled for the GUI thread.
        for callback, args in self.callbacks:
            callback(*args)
        self.monitor._sync_unity_renderer()
        return json.loads(self.socket.sendall.call_args.args[0])

    def test_slow_monthly_response_reaches_unity_with_all_models_and_64bit_counts(self):
        rows = [
            {"prompt_tokens": 3_000_000_000, "complete_tokens": 22, "price": 1.25},
            {"prompt_tokens": 100, "complete_tokens": 8, "price": 0.75},
        ]

        def request(method, url, **kwargs):
            if method == "get":
                return response(200, {})
            # Model the documented 15-second server latency without sleeping.
            if kwargs["timeout"] < 15:
                raise requests.Timeout("monthly response needs 15 seconds")
            self.assertEqual({"key": "test-usage-key"}, kwargs["json"])
            self.assertEqual("Bearer test-session", kwargs["headers"]["Authorization"])
            return response(200, rows)

        snapshot = self.fetch(request)
        self.assertEqual(3_000_000_100, snapshot["prompt_tokens"])
        self.assertEqual(30, snapshot["complete_tokens"])
        self.assertEqual(2.0, snapshot["cost_usd"])
        self.assertEqual("live", snapshot["usage_status"])
        self.assertIn("$2.00 USD", self.monitor.monthly_price_str)
        self.monitor._spawn_token_particle.assert_not_called()
        self.assertEqual(4, self.monitor.pet_data["coins"])

    def test_cache_timeout_does_not_prevent_monthly_fetch(self):
        def request(method, url, **kwargs):
            if method == "get":
                raise requests.Timeout("cache unavailable")
            return response(200, [{"prompt_tokens": 17, "complete_tokens": 3}])

        snapshot = self.fetch(request)
        self.assertEqual(17, snapshot["prompt_tokens"])
        self.assertEqual(3, snapshot["complete_tokens"])

    def test_transient_monthly_timeout_is_retried(self):
        attempts = []

        def request(method, url, **kwargs):
            if method == "get":
                return response(200, {})
            attempts.append(url)
            if len(attempts) == 1:
                raise requests.Timeout("temporary outage")
            return response(200, [{"prompt_tokens": 42, "complete_tokens": 5}])

        snapshot = self.fetch(request)
        self.assertEqual(2, len(attempts))
        self.assertEqual(42, snapshot["prompt_tokens"])
        self.assertFalse(self.monitor.is_fetching)

    def test_empty_month_clears_previous_month_in_unity_without_rewards(self):
        self.monitor.monthly_prompt_tokens = 10000
        self.monitor.monthly_complete_tokens = 2000
        self.monitor.pet_data.update(last_prompt_baseline=10000, last_complete_baseline=2000)
        snapshot = self.fetch(lambda method, url, **kwargs: response(200, []))
        self.assertEqual(0, snapshot["prompt_tokens"])
        self.assertEqual(0, snapshot["complete_tokens"])
        self.assertEqual(0.0, snapshot["cost_usd"])
        self.assertEqual(0, self.monitor.pet_data["last_prompt_baseline"])
        self.assertEqual(0, self.monitor.pet_data["last_complete_baseline"])
        self.monitor._spawn_token_particle.assert_not_called()
        self.assertEqual(4, self.monitor.pet_data["coins"])

    def test_http_error_is_reported_and_preserves_last_good_counts(self):
        self.monitor.monthly_prompt_tokens = 123
        self.monitor.monthly_cost_usd = 1.25

        def request(method, url, **kwargs):
            return response(503 if method == "post" else 200, {})

        snapshot = self.fetch(request)
        self.assertEqual(123, snapshot["prompt_tokens"])
        self.assertEqual(1.25, snapshot["cost_usd"])
        self.assertEqual("error", snapshot["usage_status"])
        self.monitor.create_text_popup.assert_called_once()
        self.assertIn("HTTPError", self.monitor.create_text_popup.call_args.args[0])
        self.assertFalse(self.monitor.is_fetching)

    def test_expired_token_uses_existing_relogin_flow(self):
        self.fetch(lambda method, url, **kwargs: response(401 if method == "post" else 200, {}))
        self.monitor._auto_relogin.assert_called_once()

    def test_offline_mode_never_requests_company_usage(self):
        self.monitor.STANDALONE = True
        with mock.patch("usage_widget.requests.request") as request:
            self.monitor._fetch_usage_api()
        request.assert_not_called()

    def test_simulation_cannot_replace_company_counters(self):
        self.monitor.monthly_prompt_tokens = 123
        self.monitor.simulate_usage()
        self.assertEqual(123, self.monitor.monthly_prompt_tokens)
        self.monitor.create_text_popup.assert_not_called()
        self.monitor.save_pet_savegame.assert_not_called()

    def test_unity_startup_enters_login_flow_unless_explicitly_offline(self):
        for offline in (False, True):
            with self.subTest(offline=offline), \
                    mock.patch.object(sys, "argv", ["TokenPet", "--unity-poc"] +
                                      (["--standalone"] if offline else [])), \
                    mock.patch.object(app, "check_single_instance", return_value=True), \
                    mock.patch.object(app.tk, "Tk"), \
                    mock.patch.object(app, "LoginWindow") as login, \
                    mock.patch.object(app, "EmojinokoMonitor") as monitor:
                app._start_app()
                self.assertEqual(not offline, login.called)
                self.assertEqual(offline, monitor.called)


@unittest.skipUnless(os.name == "nt", "Windows launcher")
class UnityLauncherTests(unittest.TestCase):
    def test_launcher_defaults_to_company_monitoring_and_keeps_explicit_offline(self):
        # Execute the real .cmd against a recording script, without opening UI
        # or contacting the company service. Also cover the pythonw path.
        for args in ([], ["debug"], ["offline", "debug"], ["debug", "offline"], ["shop", "debug"]):
            with self.subTest(args=args), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                launcher = root / "run_unity_preview.cmd"
                shutil.copy2(ROOT / launcher.name, launcher)
                output = root / "argv.json"
                (root / "emojinoko_monitor.py").write_text(
                    "import json, pathlib, sys\n"
                    "pathlib.Path('argv.json').write_text(json.dumps(sys.argv[1:]))\n",
                    encoding="utf-8",
                )
                environment = os.environ.copy()
                environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + environment["PATH"]
                environment["LOCALAPPDATA"] = directory
                result = subprocess.run(
                    ["cmd.exe", "/d", "/c", str(launcher), *args],
                    cwd=root, env=environment, capture_output=True, timeout=10,
                )
                self.assertEqual(0, result.returncode, result.stderr)
                deadline = time.monotonic() + 5
                while not output.exists() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertTrue(output.exists(), result.stdout)
                actual = json.loads(output.read_text())
                self.assertIn("--unity-poc", actual)
                self.assertEqual("offline" in args, "--standalone" in actual)
                self.assertEqual("shop" in args, "--debug-open-shop" in actual)
