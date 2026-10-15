import unittest

import app


class EditorialVisualGuardTests(unittest.TestCase):
    def test_focused_work_hook_opens_with_a_question_not_the_job_claim(self):
        hook = app._focused_work_story_hook()
        self.assertIn("ROTINA DE JASON E LUCIA", hook)
        self.assertNotIn("TRABALHANDO PARA VÁRIAS PESSOAS", hook)


if __name__ == "__main__":
    unittest.main()
