"""Authentication and statistics failure paths, without company requests."""
import json
import threading
import unittest
from unittest import mock

import requests
import usage_widget as usage
import emojinoko_monitor as app


def response(status, data):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(data).encode()
    return result


class AuthRefreshTests(unittest.TestCase):
    def root(self):
        root = mock.Mock()
        root.after.side_effect = lambda delay, callback, *args: callback(*args)
        return root

    def widget(self):
        widget = usage.UsageWidget.__new__(usage.UsageWidget)
        widget.root = self.root()
        widget.TOKEN, widget.PHISON_TOKEN = "old", "old-key"
        widget.email, widget.password = "test", "test"
        widget._usage_data, widget._auth_data = [{"price": 12}], {}
        widget._refresh_lock = threading.Lock()
        widget._update_ui = mock.Mock()
        widget._show_error = mock.Mock()
        return widget

    def test_remember_checkbox_controls_persistence(self):
        login = usage.LoginWindow.__new__(usage.LoginWindow)
        login.root = self.root()
        login.on_login_success = mock.Mock()
        for remember in (False, True):
            with self.subTest(remember=remember), \
                    mock.patch.object(usage, "_request_with_retry", return_value=response(200, {
                        "token": "session", "phison_token": "usage", "name": "test"
                    })), mock.patch.object(usage, "save_credentials") as save, \
                    mock.patch.object(usage, "delete_credentials") as delete:
                login._try_login("test", "test", remember)
                self.assertEqual(remember, save.called)
                self.assertEqual(not remember, delete.called)
        self.assertEqual(2, login.on_login_success.call_count)

    def test_partial_login_never_persists_or_enters_app(self):
        login = usage.LoginWindow.__new__(usage.LoginWindow)
        login.root = self.root()
        login.on_login_success, login._login_failed = mock.Mock(), mock.Mock()
        with mock.patch.object(usage, "_request_with_retry", return_value=response(200, {"token": "only"})), \
                mock.patch.object(usage, "save_credentials") as save:
            login._try_login("test", "test", True)
        login.on_login_success.assert_not_called()
        login._login_failed.assert_called_once()
        save.assert_not_called()

    def test_expired_statistics_session_retries_with_new_tokens_once(self):
        widget = self.widget()
        monthly_tokens = []

        def request(method, url, **kwargs):
            if url.endswith("/ldap"):
                return response(200, {"token": "new", "phison_token": "new-key"})
            if url.endswith("/monthly"):
                monthly_tokens.append((kwargs["headers"]["Authorization"], kwargs["json"]["key"]))
                return response(401, {}) if len(monthly_tokens) == 1 else response(200, [])
            if url.endswith("/auths/"):
                raise requests.Timeout("profile unavailable")
            return response(200, {})

        with mock.patch.object(usage, "_request_with_retry", side_effect=request), \
                mock.patch.object(usage, "save_credentials") as save:
            widget._fetch_and_update()
        self.assertEqual([("Bearer old", "old-key"), ("Bearer new", "new-key")], monthly_tokens)
        widget._update_ui.assert_called_once_with([], {})
        widget._show_error.assert_not_called()
        save.assert_not_called()

    def test_persistent_unauthorized_stops_and_keeps_cached_usage(self):
        widget = self.widget()
        widget._auto_relogin = mock.Mock(return_value=True)
        with mock.patch.object(usage, "_request_with_retry", return_value=response(401, {})) as request:
            widget._fetch_and_update()
        self.assertEqual(4, request.call_count)  # two cache + two monthly calls
        widget._auto_relogin.assert_called_once()
        widget._show_error.assert_called_once()
        self.assertEqual([{"price": 12}], widget._usage_data)
        self.assertFalse(widget._refresh_lock.locked())

    def test_overlapping_refresh_does_not_issue_second_request(self):
        widget = self.widget()
        widget._refresh_lock.acquire()
        with mock.patch.object(usage, "_request_with_retry") as request:
            widget._fetch_and_update()
        request.assert_not_called()
        widget._refresh_lock.release()

    def test_malformed_relogin_reports_error_in_both_clients(self):
        for cls, error_method in ((usage.UsageWidget, "_show_error"), (app.EmojinokoMonitor, "_show_fetch_error")):
            client = cls.__new__(cls)
            client.root = self.root()
            client.email, client.password = "test", "test"
            setattr(client, error_method, mock.Mock())
            with self.subTest(cls=cls.__name__), \
                    mock.patch.object(usage, "_request_with_retry", return_value=response(200, [])), \
                    mock.patch.object(app, "_request_with_retry", return_value=response(200, [])):
                self.assertFalse(client._auto_relogin())
            getattr(client, error_method).assert_called_once()

    def test_invalid_usage_never_changes_cached_statistics(self):
        for rows in ({"error": "invalid"}, [{"price": "NaN"}], [{"prompt_tokens": -1}], [{"complete_tokens": 1.5}]):
            widget = self.widget()
            with self.subTest(rows=rows), \
                    mock.patch.object(usage, "_request_with_retry", return_value=response(200, rows)):
                widget._fetch_and_update()
            widget._update_ui.assert_not_called()
            widget._show_error.assert_called_once()
            self.assertEqual([{"price": 12}], widget._usage_data)

    def test_closed_root_ignores_late_worker_results(self):
        root = self.root()
        root._tokenpet_closed = True
        callback = mock.Mock()
        self.assertFalse(usage.post_to_ui(root, callback))
        callback.assert_not_called()
        root.after.assert_not_called()


if __name__ == "__main__":
    unittest.main()
