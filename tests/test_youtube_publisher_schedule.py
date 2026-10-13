import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from youtube_publisher import YouTubePublisher


class YouTubePublisherScheduleValidationTests(unittest.TestCase):
    def publisher(self):
        with patch.dict(os.environ, {
            "YOUTUBE_AUTO_PUBLISH": "1",
            "YOUTUBE_TOKEN_JSON": "configured-for-validation-only",
        }):
            return YouTubePublisher()

    def test_missing_video_file_is_rejected_before_upload(self):
        result = self.publisher().upload("/path/that/does/not/exist.mp4", {})
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "VIDEO_FILE_MISSING_OR_EMPTY")

    def test_schedule_without_timezone_is_rejected(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4") as video:
            video.write(b"test")
            video.flush()
            result = self.publisher().upload(
                video.name, {"publish_at": "2099-01-01T12:00:00"}
            )
        self.assertFalse(result["ok"])
        self.assertIn("fuso horário", result["reason"])

    def test_past_schedule_is_rejected(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4") as video:
            video.write(b"test")
            video.flush()
            past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            result = self.publisher().upload(video.name, {"publish_at": past})
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "PUBLISH_AT_NOT_IN_FUTURE: horário agendado já passou")


    def test_future_schedule_uploads_private_with_publish_at(self):
        from unittest.mock import MagicMock

        service = MagicMock()
        service.videos.return_value.insert.return_value.execute.return_value = {
            "id": "scheduled-video-id"
        }
        publisher = self.publisher()
        publisher._service = lambda: service

        future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        with tempfile.NamedTemporaryFile(suffix=".mp4") as video:
            video.write(b"valid-enough-for-mocked-upload")
            video.flush()
            with patch("googleapiclient.http.MediaFileUpload"):
                result = publisher.upload(
                    video.name,
                    {"title": "Teste de agendamento", "publish_at": future},
                )

        self.assertTrue(result["ok"], result)
        self.assertTrue(result["scheduled"])
        self.assertEqual(result["privacy"], "private")
        self.assertEqual(result["scheduled_at"], future)
        body = service.videos.return_value.insert.call_args.kwargs["body"]
        self.assertEqual(body["status"]["privacyStatus"], "private")
        self.assertEqual(body["status"]["publishAt"], future)
        self.assertEqual(body["snippet"]["title"], "Teste de agendamento")

    def test_missing_title_is_rejected(self):
        from unittest.mock import MagicMock

        publisher = self.publisher()
        publisher._service = lambda: MagicMock()
        with tempfile.NamedTemporaryFile(suffix=".mp4") as video:
            video.write(b"video")
            video.flush()
            with patch("googleapiclient.http.MediaFileUpload"):
                result = publisher.upload(video.name, {"publish_at": ""})

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "VIDEO_TITLE_MISSING")


if __name__ == "__main__":
    unittest.main()
