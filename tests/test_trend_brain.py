import app
import json
import tempfile
import unittest
from pathlib import Path

from trend_brain import TrendBrain


class TrendBrainTests(unittest.TestCase):
    def test_radar_and_autonomous_engine_share_one_editorial_brain(self):
        if app.AUTONOMOUS_ENGINE is None or app.TREND_BRAIN is None:
            self.skipTest("Autonomous engine or TrendBrain unavailable in this test environment")
        self.assertIs(app.AUTONOMOUS_ENGINE.trend_brain, app.TREND_BRAIN)

    def test_rank_is_deterministic_and_adds_signal(self):
        with tempfile.TemporaryDirectory() as td:
            brain = TrendBrain(td)
            topics = [
                {"id": "a", "title": "GTA 6 trailer novidades", "score": 90, "confidence": 90, "mentions": 3},
                {"id": "b", "title": "Outro assunto", "score": 50, "confidence": 60, "mentions": 1},
            ]
            ranked = brain.rank(topics)
            self.assertEqual(len(ranked), 2)
            self.assertIn("trend_score", ranked[0])
            self.assertIn(ranked[0]["trend_signal"], {"FORTE", "MÉDIO", "FRACO"})
            self.assertGreaterEqual(ranked[0]["trend_score"], ranked[1]["trend_score"])

    def test_completed_production_is_remembered_without_youtube_upload(self):
        with tempfile.TemporaryDirectory() as td:
            brain = TrendBrain(td)
            topic = {
                "id": "vice-city-story",
                "title": "A história de GTA 6 vai muito além de Vice City",
            }
            metadata = {
                "title": "Jason e Lucia trabalham para ganhar dinheiro",
                "editorial_text": "Jason e Lucia buscam trabalhos para ganhar dinheiro em Vice City.",
            }
            brain.record_production(topic, metadata, quality=92)
            data = brain._read()

            production_rows = [
                value for key, value in data["videos"].items()
                if key.startswith("production:")
            ]
            self.assertEqual(len(production_rows), 1)
            self.assertIn("Jason", production_rows[0]["story_text"])

            renamed_story = {
                "title": "Jason e Lucia procuram trabalhos e dinheiro em Vice City"
            }
            self.assertGreaterEqual(
                brain._repetition_penalty(renamed_story, data),
                100,
            )

    def test_unrelated_topic_is_not_blocked_by_story_memory(self):
        with tempfile.TemporaryDirectory() as td:
            brain = TrendBrain(td)
            brain.record_production(
                {"title": "A história de Jason e Lucia em Vice City"},
                {"editorial_text": "Os dois protagonistas procuram trabalhos na cidade."},
                quality=90,
            )
            data = brain._read()

            unrelated = {"title": "GTA 6 no PS5 Pro: desempenho e resolução"}
            self.assertEqual(brain._repetition_penalty(unrelated, data), 0)

    def test_publication_and_analytics_learning(self):
        with tempfile.TemporaryDirectory() as td:
            brain = TrendBrain(td)
            topic = {
                "id": "gta6",
                "title": "GTA 6 trailer novidades",
                "editorial_hook": "O detalhe que quase ninguém percebeu",
                "editorial_angle": "investigativo",
            }
            brain.record_publication(topic, {}, "vid-1")
            result = {
                "ok": True,
                "headers": [
                    {"name": "video"},
                    {"name": "views"},
                    {"name": "likes"},
                    {"name": "subscribersGained"},
                ],
                "rows": [["vid-1", "10000", "500", "12"]],
            }
            learned = brain.learn(result)
            self.assertTrue(learned["ok"])
            self.assertEqual(learned["videos_learned"], 1)
            data = json.loads((Path(td) / "trend_brain.json").read_text(encoding="utf-8"))
            self.assertGreater(data["videos"]["vid-1"]["performance_score"], 0)
            self.assertTrue(data["videos"]["vid-1"]["topic_key"])


if __name__ == "__main__":
    unittest.main()
