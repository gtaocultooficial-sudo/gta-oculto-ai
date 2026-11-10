import app
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from trend_brain import TrendBrain


class TrendBrainTests(unittest.TestCase):
    def test_radar_and_autonomous_engine_share_one_editorial_brain(self):
        if app.AUTONOMOUS_ENGINE is None or app.TREND_BRAIN is None:
            self.skipTest("Autonomous engine or TrendBrain unavailable in this test environment")
        self.assertIs(app.AUTONOMOUS_ENGINE.trend_brain, app.TREND_BRAIN)

    def test_supabase_memory_loads_and_persists_productions(self):
        with tempfile.TemporaryDirectory() as td:
            local_path = Path(td) / "trend_brain.json"
            local_path.write_text(
                json.dumps({"topics": {}, "videos": {}, "patterns": {}}),
                encoding="utf-8",
            )
            remote_data = {
                "topics": {"remembered-topic": {"seen": 1, "best": 80}},
                "videos": {},
                "patterns": {},
            }
            get_response = unittest.mock.Mock()
            get_response.raise_for_status.return_value = None
            get_response.json.return_value = [{"data": remote_data}]
            post_response = unittest.mock.Mock()
            post_response.raise_for_status.return_value = None

            with (
                patch.dict(os.environ, {
                    "GTA_SUPABASE_URL": "https://gta-test.supabase.co",
                    "GTA_SUPABASE_SERVICE_ROLE_KEY": "sb_secret_test-key",
                }),
                patch("trend_brain.requests.get", return_value=get_response) as remote_get,
                patch("trend_brain.requests.post", return_value=post_response) as remote_post,
            ):
                brain = TrendBrain(td)
                self.assertEqual(brain._read()["topics"], remote_data["topics"])
                brain.record_production(
                    {"title": "A pauta persistida no Supabase"},
                    {"editorial_text": "Uma história original para testar a persistência."},
                    quality=90,
                )

                self.assertTrue(remote_get.called)
                self.assertTrue(remote_post.called)
                request_headers = remote_post.call_args.kwargs["headers"]
                self.assertEqual(request_headers["apikey"], "sb_secret_test-key")
                self.assertNotIn("Authorization", request_headers)
                sent = remote_post.call_args.kwargs["json"]["data"]
                self.assertIn("remembered-topic", sent["topics"])
                self.assertEqual(len(sent["videos"]), 1)
                self.assertTrue(brain.status()["persistent_storage"]["connected"])

    def test_legacy_service_role_jwt_keeps_bearer_header(self):
        brain = object.__new__(TrendBrain)
        brain.supabase_key = "eyJ.legacy-service-role-jwt"
        headers = brain._remote_headers()
        self.assertEqual(headers["apikey"], brain.supabase_key)
        self.assertEqual(headers["Authorization"], f"Bearer {brain.supabase_key}")

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
            self.assertEqual(production_rows[0]["quality_score"], 92.0)
            self.assertEqual(production_rows[0]["performance_score"], 0.0)
            self.assertEqual(production_rows[0]["hook_type"], "")

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



    def test_historical_video_titles_can_train_title_patterns_without_inventing_hooks(self):
        with tempfile.TemporaryDirectory() as td:
            brain = TrendBrain(td)
            result = {
                "ok": True,
                "headers": [
                    {"name": "video"}, {"name": "views"}, {"name": "likes"},
                    {"name": "comments"}, {"name": "subscribersGained"},
                    {"name": "averageViewDuration"}, {"name": "estimatedMinutesWatched"},
                    {"name": "publishedAt"}, {"name": "duration"}, {"name": "title"},
                ],
                "rows": [
                    ["yt-1", 15000, 700, 30, 4, 28, 800, "2026-10-01T00:00:00Z", "PT31S", "GTA 6 tem um segredo escondido?"],
                    ["yt-2", 12000, 500, 25, 3, 27, 700, "2026-10-02T00:00:00Z", "PT32S", "GTA 6 pode revelar um detalhe secreto?"],
                    ["yt-3", 9000, 400, 18, 2, 26, 600, "2026-10-03T00:00:00Z", "PT30S", "O que a Rockstar confirmou sobre GTA 6?"],
                ],
            }

            learned = brain.learn(result)
            profile = brain.recommend_editorial_profile()
            data = brain._read()

            self.assertTrue(learned["ok"])
            self.assertTrue(profile["learned"])
            self.assertEqual(profile["sample_size"], 3)
            self.assertEqual(profile["preferred_title_pattern"]["pattern"], "PERGUNTA")
            self.assertIsNone(profile["preferred_hook_type"])
            self.assertEqual(data["videos"]["yt-1"]["hook_type"], "")
            self.assertEqual(data["videos"]["yt-1"]["title"], "GTA 6 tem um segredo escondido?")
            self.assertLess(data["videos"]["yt-1"]["updated"], 1790000000)

    def test_editor_chief_skips_recent_story_with_a_renamed_headline(self):
        with tempfile.TemporaryDirectory() as td:
            brain = TrendBrain(td)
            brain.record_production(
                {"title": "Jason e Lucia trabalham para ganhar dinheiro em Vice City"},
                {
                    "editorial_text": (
                        "Jason e Lucia procuram trabalhos para ganhar dinheiro "
                        "em Vice City e construir uma vida melhor."
                    )
                },
                quality=90,
            )
            candidates = [
                {
                    "id": "repeat",
                    "title": "Jason e Lucia buscam empregos e dinheiro em Vice City",
                    "score": 98,
                    "trend_score": 98,
                    "confidence": 95,
                    "source_count": 3,
                    "mentions": 4,
                },
                {
                    "id": "fresh",
                    "title": "GTA 6 no PS5 Pro: desempenho e resolução",
                    "score": 78,
                    "trend_score": 78,
                    "confidence": 85,
                    "source_count": 2,
                    "mentions": 2,
                },
            ]

            with patch.object(app, "TREND_BRAIN", brain):
                selected = app.editor_chief_select(candidates, history=[])

            self.assertIsNotNone(selected)
            self.assertEqual(selected["id"], "fresh")

    def test_editor_chief_returns_no_pick_when_all_topics_are_recent_repeats(self):
        with tempfile.TemporaryDirectory() as td:
            brain = TrendBrain(td)
            brain.record_production(
                {"title": "Jason e Lucia trabalham para ganhar dinheiro em Vice City"},
                {
                    "editorial_text": (
                        "Jason e Lucia procuram trabalhos para ganhar dinheiro "
                        "em Vice City."
                    )
                },
                quality=90,
            )
            repeated = {
                "id": "repeat",
                "title": "Jason e Lucia buscam empregos em Vice City",
                "score": 99,
                "trend_score": 99,
                "confidence": 95,
            }

            with patch.object(app, "TREND_BRAIN", brain):
                selected = app.editor_chief_select([repeated], history=[])

            self.assertIsNone(selected)

    def test_manual_custom_topic_is_rejected_when_recently_used(self):
        with (
            patch.object(app, "_load_radar", return_value={"opportunities": []}),
            patch.object(app, "_topic_recently_used", return_value=True),
        ):
            response = app.APP.test_client().post(
                "/api/produce",
                json={"topic": "Jason e Lucia buscam empregos em Vice City"},
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["code"], "RECENT_TOPIC_DUPLICATE")

if __name__ == "__main__":
    unittest.main()
