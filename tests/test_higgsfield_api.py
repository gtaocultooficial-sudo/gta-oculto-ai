import os
import unittest
from unittest.mock import Mock, patch

import higgsfield_api


class HiggsfieldApiTests(unittest.TestCase):
    def test_feature_is_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(higgsfield_api.feature_status()["ready"])
            result = higgsfield_api.submit_scene("Cena teste")
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "HIGGSFIELD_FEATURE_DISABLED")

    def test_action_token_is_compared_without_returning_it(self):
        with patch.dict(os.environ, {
            "HIGGSFIELD_ACTION_TOKEN": "a-long-random-admin-token"
        }, clear=True):
            self.assertTrue(higgsfield_api.action_token_valid("a-long-random-admin-token"))
            self.assertFalse(higgsfield_api.action_token_valid("wrong"))
            self.assertFalse(higgsfield_api.action_token_valid(""))

    def test_invalid_prompt_does_not_submit(self):
        env = {
            "HIGGSFIELD_API_ENABLED": "1",
            "HIGGSFIELD_API_KEY": "fake-id:fake-secret",
            "HIGGSFIELD_ACTION_TOKEN": "admin-token",
        }
        with patch.dict(os.environ, env, clear=True), patch.object(higgsfield_api.requests, "post") as post:
            result = higgsfield_api.submit_scene(" ")
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "PROMPT_REQUIRED")
        post.assert_not_called()

    def test_submit_uses_documented_server_side_credentials_and_low_cost_settings(self):
        env = {
            "HIGGSFIELD_API_ENABLED": "1",
            "HIGGSFIELD_API_KEY": "test-id:test-secret",
            "HIGGSFIELD_ACTION_TOKEN": "admin-token",
        }
        response = Mock()
        response.ok = True
        response.status_code = 200
        response.json.return_value = {"request_id": "req_abc123", "status": "queued"}
        with patch.dict(os.environ, env, clear=True), patch.object(higgsfield_api.requests, "post", return_value=response) as post:
            result = higgsfield_api.submit_scene("Uma avenida fictícia à noite, câmera em movimento.")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["request_id"], "req_abc123")
        args, kwargs = post.call_args
        self.assertTrue(args[0].startswith("https://api.higgsfield.ai/"))
        self.assertEqual(kwargs["headers"]["Authorization"], "Key test-id:test-secret")
        self.assertEqual(kwargs["json"]["duration"], 3)
        self.assertEqual(kwargs["json"]["resolution"], "480p")
        self.assertEqual(kwargs["json"]["aspect_ratio"], "9:16")
        self.assertFalse(kwargs["json"]["generate_audio"])

    def test_status_returns_only_secure_video_urls(self):
        env = {
            "HIGGSFIELD_API_ENABLED": "1",
            "HIGGSFIELD_API_KEY": "test-id:test-secret",
            "HIGGSFIELD_ACTION_TOKEN": "admin-token",
        }
        response = Mock()
        response.ok = True
        response.status_code = 200
        response.json.return_value = {
            "status": "completed",
            "video": {"url": "https://cdn.example.com/video.mp4"},
        }
        with patch.dict(os.environ, env, clear=True), patch.object(higgsfield_api.requests, "get", return_value=response):
            result = higgsfield_api.request_status("req_abc123")
        self.assertTrue(result["ok"])
        self.assertEqual(result["video_url"], "https://cdn.example.com/video.mp4")
        self.assertNotIn("test-secret", str(result))


if __name__ == "__main__":
    unittest.main()
