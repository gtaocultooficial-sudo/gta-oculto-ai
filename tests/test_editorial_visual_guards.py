import unittest

import app
from PIL import Image, ImageDraw


class EditorialVisualGuardTests(unittest.TestCase):
    def test_focused_work_hook_opens_with_a_question_not_the_job_claim(self):
        hook = app._focused_work_story_hook()
        self.assertIn("ROTINA DE JASON E LUCIA", hook)
        self.assertNotIn("TRABALHANDO PARA VÁRIAS PESSOAS", hook)

    def test_smart_crop_removes_bright_thumbnail_border_on_portrait_art(self):
        source = Image.new("RGB", (270, 480), (88, 68, 145))
        draw = ImageDraw.Draw(source)
        draw.rectangle((0, 35, 8, 210), fill=(255, 255, 255))
        draw.text((0, 220), "LOOK", fill=(255, 255, 255))
        draw.rectangle((110, 80, 215, 445), fill=(220, 80, 55))

        cropped = app._smart_crop(source, 360, 640)

        self.assertEqual(cropped.size, (360, 640))
        self.assertLess(
            app._edge_white_ratio(cropped),
            0.07,
            "A thumbnail-style white border/logo should not remain at the frame edge.",
        )


if __name__ == "__main__":
    unittest.main()
