import io
import json
from types import SimpleNamespace
import unittest
from unittest import mock

import emojinoko_monitor as app
from emojinoko_game import AIChatWindow


class ImmediateThread:
    def __init__(self, target, **kwargs):
        self.target = target

    def start(self):
        self.target()


class Response(io.BytesIO):
    def __exit__(self, *args):
        self.close()


class AiChatTests(unittest.TestCase):
    def monitor(self):
        pet = app.EmojinokoMonitor.__new__(app.EmojinokoMonitor)
        pet.pet_data = {"ai_config": {"ccr_url": "http://localhost/chat", "api_key": "test-key"}}
        pet.user_name, pet.monthly_price_str = "test", "$1.00 USD"
        pet.root = mock.Mock()
        pet.root.after.side_effect = lambda delay, callback, *args: callback(*args)
        return pet

    def test_chat_falls_back_to_secondary_model_after_timeout(self):
        pet = self.monitor()
        callback = mock.Mock()
        result = Response(json.dumps({"choices": [{"message": {"content": "hello"}}]}).encode())
        with mock.patch.object(app.threading, "Thread", ImmediateThread), \
                mock.patch.object(app.urllib.request, "urlopen", side_effect=[TimeoutError(), result]) as request:
            pet.send_ai_chat_message("test", callback)
        callback.assert_called_once_with("hello", None)
        models = [json.loads(call.args[0].data)["model"] for call in request.call_args_list]
        self.assertEqual("zai-org/GLM-5.3-Flash", models[-1])
        self.assertNotEqual(models[0], models[-1])

    def test_offline_reply_is_reported_as_offline(self):
        pet = self.monitor()
        callback = mock.Mock()
        with mock.patch.object(app.threading, "Thread", ImmediateThread), \
                mock.patch.object(app.urllib.request, "urlopen", side_effect=TimeoutError()):
            pet.send_ai_chat_message("test", callback)
        reply, error = callback.call_args.args
        self.assertTrue(reply)
        self.assertIn("離線", error)

    def test_missing_internal_key_explains_configuration_without_request(self):
        pet = self.monitor()
        pet.pet_data["ai_config"] = {}
        callback = mock.Mock()
        with mock.patch.object(app.threading, "Thread", ImmediateThread), \
                mock.patch.dict(app.os.environ, {"TOKENPET_AI_API_KEY": ""}), \
                mock.patch.object(app.urllib.request, "urlopen") as request:
            pet.send_ai_chat_message("test", callback)
        request.assert_not_called()
        self.assertIn("API Key", callback.call_args.args[1])

    def test_pending_chat_cannot_be_submitted_again_with_enter(self):
        chat = AIChatWindow.__new__(AIChatWindow)
        chat._sending = True
        chat.entry = mock.Mock()
        chat.monitor = SimpleNamespace(send_ai_chat_message=mock.Mock())
        chat._on_send()
        chat.entry.get.assert_not_called()
        chat.monitor.send_ai_chat_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
