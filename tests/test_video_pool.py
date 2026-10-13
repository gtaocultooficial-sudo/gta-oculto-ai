import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app


class OfficialVideoPoolTests(unittest.TestCase):
    def test_returns_four_distinct_cached_motion_sources_when_available(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cache = root / "official_video_cache"
            cache.mkdir()
            expected = []
            for index in range(4):
                clip = cache / f"rockstar_real_v251_{index}.mp4"
                clip.write_bytes(b"x" * 25001)
                expected.append(clip)

            with patch.object(app, "WORK", root):
                actual = app.download_official_video_clips(root / "job" / "official_videos")

            self.assertEqual(len(actual), 4)
            self.assertEqual([Path(p).name for p in actual],
                             [p.name for p in expected])
            self.assertEqual(len(set(map(str, actual))), 4)


if __name__ == "__main__":
    unittest.main()
