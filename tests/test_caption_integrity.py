import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import app


class CaptionIntegrityTests(unittest.TestCase):
    def _assert_no_protected_split(self, chunks, phrase):
        clean = [
            [app._caption_clean_word(word) for word in chunk]
            for chunk in chunks
        ]
        for index in range(len(clean) - 1):
            left, right = clean[index], clean[index + 1]
            for left_count in range(1, len(phrase)):
                right_count = len(phrase) - left_count
                split = (
                    len(left) >= left_count
                    and len(right) >= right_count
                    and tuple(left[-left_count:]) == phrase[:left_count]
                    and tuple(right[:right_count]) == phrase[left_count:]
                )
                self.assertFalse(
                    split,
                    f"Protected phrase split across captions: {left} | {right}",
                )

    def test_focused_work_hook_survives_caption_repair_without_dangling_preposition(self):
        hook = app._focused_work_story_hook()
        initial = app._semantic_caption_chunks(hook, min_words=3, max_words=6)
        beats = [
            {"text": " ".join(chunk), "start": index * 2.0, "end": (index + 1) * 2.0}
            for index, chunk in enumerate(initial)
        ]
        repaired = app._repair_caption_beats(beats, duration=12.0, max_words=6)
        audit = app._audit_caption_quality(repaired)

        self.assertEqual([], audit["bad_end"], audit)
        self.assertEqual([], audit["bad_start"], audit)
        clean_chunks = [app._caption_words(item["text"]) for item in repaired]
        self._assert_no_protected_split(clean_chunks, ("jason", "e", "lucia"))

    def test_render_time_repair_reflows_caption_ending_in_situam_a(self):
        # Actual MP4 showed this boundary despite the earlier transcript audit passing.
        rendered_beats = [
            {"text": "O QUE LEVA JASON E LUCIA A BUSCAR TRABALHOS EM VICE CITY?", "start": 0.0, "end": 4.0},
            {"text": "ESSAS CENAS TAMBÉM SITUAM A", "start": 4.0, "end": 6.0},
            {"text": "DUPLA NO AMBIENTE DA CIDADE, ANTES DE SABERMOS QUAIS CONSEQUÊNCIAS ESSA", "start": 6.0, "end": 11.0},
            {"text": "ROTINA TERÁ.", "start": 11.0, "end": 12.0},
        ]
        repaired = app._repair_caption_beats(rendered_beats, duration=12.0, max_words=6)
        audit = app._audit_caption_quality(repaired)

        self.assertEqual([], audit["bad_end"], audit)
        self.assertEqual([], audit["bad_start"], audit)
        self.assertEqual([], audit["protected_splits"], audit)
        self.assertTrue(any("DUPLA" in item["text"] for item in repaired))

    def test_semantic_caption_chunks_keep_vice_city_together(self):
        text = (
            "A Rockstar revelou mais detalhes importantes sobre VICE CITY "
            "e as novidades de GTA 6 em uma apresentação oficial."
        )
        chunks = app._semantic_caption_chunks(text, min_words=3, max_words=6)
        self._assert_no_protected_split(chunks, ("vice", "city"))

    def test_semantic_caption_chunks_keep_jason_and_lucia_together(self):
        text = (
            "A narrativa mostra como Jason e Lucia tentam conseguir dinheiro "
            "enquanto exploram Vice City durante a história principal."
        )
        chunks = app._semantic_caption_chunks(text, min_words=3, max_words=6)
        self._assert_no_protected_split(chunks, ("jason", "e", "lucia"))

    def test_caption_repair_keeps_jason_and_lucia_together(self):
        original = [
            {"text": "A narrativa mostra como Jason e", "start": 0.0, "end": 1.5},
            {"text": "Lucia tentam conseguir dinheiro enquanto exploram Vice City durante a história principal.",
             "start": 1.5, "end": 8.0},
        ]
        repaired = app._repair_caption_beats(original, duration=8.0, max_words=6)
        chunks = [app._caption_words(item["text"]) for item in repaired]
        self._assert_no_protected_split(chunks, ("jason", "e", "lucia"))

    def test_caption_phrase_chunks_keep_vice_city_together(self):
        text = (
            "A Rockstar revelou mais detalhes importantes sobre VICE CITY "
            "e as novidades de GTA 6 em uma apresentação oficial."
        )
        chunks = app._caption_phrase_chunks(text, min_words=3, max_words=7)
        self._assert_no_protected_split(chunks, ("vice", "city"))

    def test_caption_auditor_flags_a_split_vice_city_phrase(self):
        result = app._audit_caption_quality([
            {"text": "A HISTÓRIA SE PASSA EM VICE"},
            {"text": "CITY DURANTE A NOITE"},
        ])
        self.assertIn(
            "vice city",
            {item["phrase"] for item in result["protected_splits"]},
        )


class EdgeTTSIntegrityTests(unittest.IsolatedAsyncioTestCase):
    async def test_edge_tts_without_word_boundaries_falls_back_to_gtts(self):
        seen_voices = []

        class AudioWithoutBoundaries:
            def __init__(self, text, voice, **kwargs):
                self.text = text
                self.voice = voice
                seen_voices.append(voice)

            async def stream(self):
                yield {"type": "audio", "data": b"e" * 2048}

        def fake_gtts(text, lang, tld, slow):
            class FakeTTS:
                def save(self, destination):
                    Path(destination).write_bytes(b"g" * 2048)
            return FakeTTS()

        fake_module = types.ModuleType("gtts")
        fake_module.gTTS = fake_gtts
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "narracao.mp3"
            with (
                patch.object(app, "edge_tts", SimpleNamespace(Communicate=AudioWithoutBoundaries)),
                patch.dict(sys.modules, {"gtts": fake_module}),
            ):
                cues = await app.make_tts(
                    "Esta é uma narração completa e deve terminar corretamente.",
                    target,
                )

            self.assertEqual(cues, [])
            self.assertEqual(len(seen_voices), 2)
            self.assertEqual(target.read_bytes(), b"g" * 2048)


if __name__ == "__main__":
    unittest.main()
