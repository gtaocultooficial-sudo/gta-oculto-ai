import unittest

from novela_audio import (
    VOICE_PREFERENCES,
    choose_voice_assignments,
    _srt_time,
    _word_count,
)


class NovelaAudioTests(unittest.TestCase):
    def test_assigns_four_distinct_neural_brazilian_voices(self):
        available = {
            "pt-BR-DonatoNeural",
            "pt-BR-ThalitaMultilingualNeural",
            "pt-BR-AntonioNeural",
            "pt-BR-JulioNeural",
        }
        selected = choose_voice_assignments(available)
        self.assertEqual(set(selected), set(VOICE_PREFERENCES))
        self.assertEqual(len(set(selected.values())), 4)
        self.assertEqual(selected["JASON DUVAL"], "pt-BR-DonatoNeural")
        self.assertEqual(selected["LUCIA CAMINOS"], "pt-BR-ThalitaMultilingualNeural")

    def test_missing_distinct_neural_voice_fails_instead_of_using_robotic_fallback(self):
        available = {"pt-BR-AntonioNeural", "pt-BR-FranciscaNeural"}
        with self.assertRaisesRegex(RuntimeError, "quatro vozes brasileiras distintas"):
            choose_voice_assignments(available)

    def test_subtitle_clock_is_formatted_for_srt(self):
        self.assertEqual(_srt_time(0), "00:00:00,000")
        self.assertEqual(_srt_time(65.432), "00:01:05,432")
        self.assertEqual(_srt_time(3661.007), "01:01:01,007")

    def test_word_counter_handles_portuguese_accents_and_hyphens(self):
        self.assertEqual(_word_count("A embarcação não saiu. Está tudo certo?"), 7)
        self.assertEqual(_word_count("Vozes-neurais em português brasileiro"), 4)

    def test_module_does_not_use_espeak_or_gtts_fallback(self):
        import inspect
        import novela_audio
        source = inspect.getsource(novela_audio)
        self.assertNotIn("espeak", source.lower())
        self.assertNotIn("gtts", source.lower())


if __name__ == "__main__":
    unittest.main()
