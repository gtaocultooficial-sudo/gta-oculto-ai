import unittest

from novela_audio import (
    VOICE_PREFERENCES,
    choose_voice_assignments,
    _srt_time,
    _word_count,
    supported_portuguese_voices,
)


class NovelaAudioTests(unittest.TestCase):
    def test_assigns_four_distinct_catalogue_backed_voices_that_speak_pt_br(self):
        available = {
            "pt-BR-AntonioNeural",
            "pt-BR-ThalitaMultilingualNeural",
            "pt-BR-FranciscaNeural",
            "en-US-AndrewMultilingualNeural",
            "en-US-BrianMultilingualNeural",
        }
        selected = choose_voice_assignments(available)
        self.assertEqual(set(selected), set(VOICE_PREFERENCES))
        self.assertEqual(len(set(selected.values())), 4)
        self.assertEqual(selected["JASON DUVAL"], "pt-BR-AntonioNeural")
        self.assertEqual(selected["LUCIA CAMINOS"], "pt-BR-ThalitaMultilingualNeural")
        self.assertEqual(selected["BRIAN HEDER"], "en-US-BrianMultilingualNeural")
        self.assertEqual(selected["CAL HAMPTON"], "en-US-AndrewMultilingualNeural")

    def test_catalogue_filter_keeps_pt_br_and_verified_multilingual_voices(self):
        catalogue = [
            {"ShortName": "pt-BR-AntonioNeural", "Locale": "pt-BR"},
            {"ShortName": "pt-BR-ThalitaMultilingualNeural", "Locale": "pt-BR"},
            {"ShortName": "en-US-AndrewMultilingualNeural", "Locale": "en-US"},
            {"ShortName": "en-US-BrianMultilingualNeural", "Locale": "en-US"},
            {"ShortName": "en-US-AvaMultilingualNeural", "Locale": "en-US"},
            {"ShortName": "fr-FR-RemyMultilingualNeural", "Locale": "fr-FR"},
            {"ShortName": "pt-BR-ImaginaryNeural", "Locale": "pt-BR"},
        ]
        available = supported_portuguese_voices(catalogue)
        self.assertIn("pt-BR-AntonioNeural", available)
        self.assertIn("en-US-AndrewMultilingualNeural", available)
        self.assertIn("en-US-BrianMultilingualNeural", available)
        self.assertIn("en-US-AvaMultilingualNeural", available)
        self.assertNotIn("fr-FR-RemyMultilingualNeural", available)

    def test_missing_neural_voice_reports_actual_catalogue_instead_of_claiming_four_pt_br_voices(self):
        available = {"pt-BR-AntonioNeural", "pt-BR-FranciscaNeural"}
        with self.assertRaisesRegex(RuntimeError, "Catálogo compatível recebido"):
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
