import tempfile
import unittest

from trend_brain import TrendBrain


class PublishSlotLearningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.brain = TrendBrain(self.tmp.name)
        self.headers = [
            {"name": "video"},
            {"name": "views"},
            {"name": "likes"},
            {"name": "comments"},
            {"name": "subscribersGained"},
            {"name": "averageViewDuration"},
            {"name": "estimatedMinutesWatched"},
            {"name": "publishedAt"},
        ]

    def tearDown(self):
        self.tmp.cleanup()

    def analytics(self, video_id, views):
        return {
            "ok": True,
            "headers": self.headers,
            "rows": [[video_id, views, 10, 2, 1, 15, 40, ""]],
        }

    def test_repeated_analytics_polls_count_one_sample_per_video(self):
        self.brain.record_publication(
            {"title": "GTA 6 novidade"}, {"publish_slot": "18:30"}, "video-1", "18:30"
        )

        self.brain.learn(self.analytics("video-1", 100))
        self.brain.learn(self.analytics("video-1", 300))
        data = self.brain._read()

        self.assertEqual(data["patterns"]["publish_slot_samples"]["18:30"], 1)
        self.assertEqual(
            data["patterns"]["publish_slots"]["18:30"],
            data["videos"]["video-1"]["performance_score"],
        )

    def test_distinct_videos_count_as_distinct_slot_samples(self):
        for video_id in ("video-1", "video-2"):
            self.brain.record_publication(
                {"title": f"GTA 6 novidade {video_id}"},
                {"publish_slot": "20:30"},
                video_id,
                "20:30",
            )
            self.brain.learn(self.analytics(video_id, 100))

        data = self.brain._read()
        self.assertEqual(data["patterns"]["publish_slot_samples"]["20:30"], 2)

    def test_reservations_are_future_and_do_not_collide(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        now = datetime(2026, 10, 13, 8, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
        first = self.brain.reserve_publish_slot("job-1", now=now)
        second = self.brain.reserve_publish_slot("job-2", now=now)

        self.assertNotEqual(first["publish_at"], second["publish_at"])
        self.assertGreater(datetime.fromisoformat(first["publish_at"]), now)
        self.assertEqual(first["timezone"], "America/Sao_Paulo")

    def test_failed_job_releases_only_its_own_reservation(self):
        first = self.brain.reserve_publish_slot("job-1")
        second = self.brain.reserve_publish_slot("job-2")

        released = self.brain.release_publish_slot("job-1", first["publish_at"])
        reserved = self.brain._read()["scheduled_slots"]

        self.assertEqual(released["released"], [first["publish_at"]])
        self.assertNotIn(first["publish_at"], reserved)
        self.assertEqual(reserved[second["publish_at"]], "job-2")


if __name__ == "__main__":
    unittest.main()
