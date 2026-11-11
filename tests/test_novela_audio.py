import unittest

from novela_audio import (
    VOICE_PREFERENCES,
    choose_voice_assignments,
    voice_candidates_for_speaker,
    _srt_time,
    _word_count,
    supported_portuguese_voices,
)


class NovelaAudioTests(unittest.TestCase):
    def test_assigns_four_distinct_catalogue_backed_native_pt_br_voices(self):
        available = {
            "pt-BR-DonatoNeural",
            "pt-BR-FabioNeural",
            "pt-BR-FranciscaNeural",
            "pt-BR-AntonioNeural",
            "pt-BR-HumbertoNeural",
        }
        selected = choose_voice_assignments(available)
        self.assertEqual(set(selected), set(VOICE_PREFERENCES))
        self.assertEqual(len(set(selected.values())), 4)
        self.assertEqual(selected["JASON DUVAL"], "pt-BR-DonatoNeural")
        self.assertEqual(selected["LUCIA CAMINOS"], "pt-BR-FranciscaNeural")
        self.assertEqual(selected["BRIAN HEDER"], "pt-BR-AntonioNeural")
        self.assertEqual(selected["CAL HAMPTON"], "pt-BR-FabioNeural")

    def test_catalogue_filter_rejects_non_brazilian_multilingual_voices(self):
        catalogue = [
            {"ShortName": "pt-BR-AntonioNeural", "Locale": "pt-BR"},
            {"ShortName": "pt-BR-FranciscaNeural", "Locale": "pt-BR"},
            {"ShortName": "en-US-AndrewMultilingualNeural", "Locale": "en-US"},
            {"ShortName": "en-US-BrianMultilingualNeural", "Locale": "en-US"},
            {"ShortName": "fr-FR-RemyMultilingualNeural", "Locale": "fr-FR"},
            {"ShortName": "pt-BR-ImaginaryNeural", "Locale": "pt-BR"},
        ]
        available = supported_portuguese_voices(catalogue)
        self.assertEqual(available, {
            "pt-BR-AntonioNeural",
            "pt-BR-FranciscaNeural",
            "pt-BR-ImaginaryNeural",
        })
        self.assertNotIn("en-US-AndrewMultilingualNeural", available)
        self.assertNotIn("en-US-BrianMultilingualNeural", available)

    def test_catalogue_shortage_reuses_native_voice_instead_of_switching_language(self):
        available = {"pt-BR-AntonioNeural", "pt-BR-FranciscaNeural"}
        selected = choose_voice_assignments(available)
        self.assertEqual(set(selected), set(VOICE_PREFERENCES))
        self.assertEqual(set(selected.values()), available)

    def test_fallback_order_is_character_specific_and_stays_within_live_catalogue(self):
        available = {"pt-BR-FabioNeural", "pt-BR-JulioNeural", "pt-BR-NicolauNeural"}
        candidates = voice_candidates_for_speaker("CAL HAMPTON", available)
        self.assertEqual(candidates, [
            "pt-BR-FabioNeural",
            "pt-BR-JulioNeural",
            "pt-BR-NicolauNeural",
        ])
        self.assertEqual(
            voice_candidates_for_speaker("CAL HAMPTON", available, current="pt-BR-JulioNeural"),
            ["pt-BR-JulioNeural", "pt-BR-FabioNeural", "pt-BR-NicolauNeural"],
        )

    def test_unknown_character_has_no_voice_assignment(self):
        with self.assertRaisesRegex(RuntimeError, "sem mapa de voz"):
            voice_candidates_for_speaker("UNKNOWN", {"pt-BR-AntonioNeural"})

    def test_subtitle_clock_is_formatted_for_srt(self):
        self.assertEqual(_srt_time(0), "00:00:00,000")
        self.assertEqual(_srt_time(65.432), "00:01:05,432")
        self.assertEqual(_srt_time(3661.007), "01:01:01,007")

    def test_word_counter_handles_portuguese_accents_and_hyphens(self):
        self.assertEqual(_word_count("A embarcação não saiu. Está tudo certo?"), 7)
        self.assertEqual(_word_count("Vozes-neurais em português brasileiro"), 4)

    def test_module_does_not_use_local_robotic_fallback(self):
        import inspect
        import novela_audio
        source = inspect.getsource(novela_audio)
        self.assertNotIn("espeak", source.lower())
        self.assertNotIn("gtts", source.lower())
        for candidates in VOICE_PREFERENCES.values():
            self.assertTrue(candidates)
            self.assertTrue(all(name.startswith("pt-BR-") for name in candidates))


if __name__ == "__main__":
    unittest.main()
