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
            self.assertFalse(
                len(left) >= 1 and len(right) >= 1
                and tuple(left[-1:]) == phrase[:1]
                and tuple(right[:1]) == phrase[1:],
                f"Protected phrase split across captions: {left} | {right}",
            )

    def test_semantic_caption_chunks_keep_vice_city_together(self):
        text = (
            "A Rockstar revelou mais detalhes importantes sobre VICE CITY "
            "e as novidades de GTA 6 em uma apresentação oficial."
        )
        chunks = app._semantic_caption_chunks(text, min_words=3, max_words=6)
        self._assert_no_protected_split(chunks, ("vice", "city"))

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
