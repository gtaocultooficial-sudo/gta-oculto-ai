import tempfile
import unittest
from pathlib import Path

import app
from PIL import Image, ImageDraw


class EditorialVisualGuardTests(unittest.TestCase):
    def test_focused_work_hook_has_caption_safe_wording(self):
        hook = app._focused_work_story_hook()
        self.assertIn("JASON E LUCIA", hook)
        self.assertIn("VICE CITY", hook)
        self.assertNotIn("TRABALHANDO PARA VÁRIAS PESSOAS", hook)

        chunks = app._semantic_caption_chunks(hook, min_words=3, max_words=6)
        bad_end = {
            "e", "de", "do", "da", "em", "no", "na", "que", "um", "uma",
            "o", "a", "os", "as", "para", "com", "por", "mas", "se", "ou",
            "ao", "à", "às", "dos", "das", "num", "numa", "sobre", "entre",
            "até", "sem",
        }
        for chunk in chunks:
            self.assertNotIn(
                app._caption_clean_word(chunk[-1]),
                bad_end,
                f"Hook caption ends with a dangling word: {chunk}",
            )

    def test_smart_crop_removes_bright_thumbnail_borders_on_portrait_art(self):
        source = Image.new("RGB", (270, 480), (88, 68, 145))
        draw = ImageDraw.Draw(source)
        draw.rectangle((0, 35, 8, 210), fill=(255, 255, 255))
        draw.text((0, 220), "LOOK", fill=(255, 255, 255))
        draw.rectangle((261, 35, 269, 210), fill=(255, 255, 255))
        draw.rectangle((110, 80, 215, 445), fill=(220, 80, 55))

        cropped = app._smart_crop(source, 360, 640)

        self.assertEqual(cropped.size, (360, 640))
        self.assertLess(
            app._edge_white_ratio(cropped),
            0.035,
            "Thumbnail-style white borders/logos must not remain at either frame edge.",
        )

    def test_actual_image_preparation_removes_jpeg_compressed_clipped_source_text(self):
        source = Image.new("RGB", (270, 480), (88, 68, 145))
        draw = ImageDraw.Draw(source)
        # Reproduce the narrow antialiased white edge and source text visible in
        # the real Short; wide, pure-white borders alone did not catch this case.
        draw.line((0, 35, 0, 210), fill=(255, 255, 255), width=2)
        draw.text((-18, 220), "LOOK", fill=(255, 255, 255))
        draw.rectangle((110, 80, 215, 445), fill=(220, 80, 55))

        with tempfile.TemporaryDirectory() as td:
            original = Path(td) / "source.jpg"
            prepared = Path(td) / "prepared.jpg"
            source.save(original, quality=65)
            with Image.open(original) as compressed:
                self.assertGreaterEqual(
                    app._edge_white_ratio(compressed),
                    0.035,
                    "The detector must recognize compressed edge text before cropping.",
                )
            app.prepare_scene(original, prepared, "TEST CAPTION", 0, 1)
            with Image.open(prepared) as result:
                self.assertEqual(result.size, (360, 640))
                self.assertLess(
                    app._edge_white_ratio(result),
                    0.035,
                    "The production image-preparation path must remove compressed frame-edge artifacts.",
                )


if __name__ == "__main__":
    unittest.main()
