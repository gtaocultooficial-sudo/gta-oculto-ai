import unittest

from app import _editorial_topic_alignment


class EditorialAlignmentTests(unittest.TestCase):
    def test_broad_listicle_title_is_rejected_for_focused_story(self):
        result = _editorial_topic_alignment(
            "GTA 6: 50 novidades confirmadas no novo jogo da Rockstar",
            "Jason e Lucia tentam ganhar dinheiro em Vice City. A matéria destaca a rotina dos protagonistas.",
            ["Jason e Lucia tentam ganhar dinheiro em Vice City."],
            "GTA 6: 50 novidades confirmadas no novo jogo da Rockstar",
        )
        self.assertFalse(result["ok"])
        self.assertIn("headline_listicle_promise_not_delivered", result["issues"])

    def test_focused_title_supported_by_script_passes(self):
        result = _editorial_topic_alignment(
            "GTA 6 — Jason e Lucia trabalham para ganhar dinheiro",
            "Jason e Lucia tentam ganhar dinheiro em Vice City. A matéria destaca a rotina dos protagonistas.",
            ["Jason e Lucia tentam ganhar dinheiro em Vice City."],
            "Jason e Lucia trabalham para ganhar dinheiro",
        )
        self.assertTrue(result["ok"], result)

    def test_named_entity_missing_from_body_is_rejected(self):
        result = _editorial_topic_alignment(
            "GTA 6 — Jason e Lucia em Vice City",
            "A matéria fala sobre uma nova mecânica do jogo e seus detalhes.",
            ["A matéria fala sobre uma nova mecânica do jogo e seus detalhes."],
            "Jason e Lucia em Vice City",
        )
        self.assertFalse(result["ok"])
        self.assertTrue(any(x.startswith("headline_entity_missing:") for x in result["issues"]))


if __name__ == "__main__":
    unittest.main()
