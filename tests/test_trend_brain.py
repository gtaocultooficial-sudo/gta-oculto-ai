import json
import tempfile
import unittest
from pathlib import Path

from trend_brain import TrendBrain


class TrendBrainTests(unittest.TestCase):
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
