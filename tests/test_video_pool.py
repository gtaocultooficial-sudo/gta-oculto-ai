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


    def test_extracts_unique_frames_from_official_footage_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            clips = []
            for index in range(4):
                clip = root / f"official_{index}.mp4"
                clip.write_bytes(b"source")
                clips.append(clip)

            def write_frame(command, timeout=240):
                Path(command[-1]).write_bytes(b"f" * 5001)

            frame_dir = root / "frames"
            frame_dir.mkdir()

            with (
                patch.object(app, "_probe_media", return_value={"duration": 8.5}),
                patch.object(app, "_ffmpeg_executable", return_value="ffmpeg"),
                patch.object(app, "run_cmd", side_effect=write_frame),
            ):
                actual = app._augment_scenes_with_real_video_frames(
                    clips, [], frame_dir, target=18
                )

            self.assertEqual(len(actual), 18)
            self.assertEqual(len({Path(p).name for p in actual}), 18)
            self.assertTrue(all(Path(p).stat().st_size > 4000 for p in actual))
            self.assertTrue(all(Path(p).name.startswith("official_frame_") for p in actual))

    def test_downloads_four_safe_official_clips_when_cache_is_short(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            entries = [
                {"name": f"Jason_official_{index}.mp4", "compression": 0,
                 "compressed": 30000, "size": 30000, "local": index}
                for index in range(4)
            ]

            def write_raw(_url, _entry, target):
                target.write_bytes(b"r" * 30000)

            def write_proxy(command, timeout=240):
                Path(command[-1]).write_bytes(b"p" * 30000)

            with (
                patch.object(app, "WORK", root),
                patch.object(app, "_remote_zip_entries", return_value=(120000, entries)),
                patch.object(app, "_remote_zip_extract", side_effect=write_raw),
                patch.object(app, "_ffmpeg_executable", return_value="ffmpeg"),
                patch.object(app, "run_cmd", side_effect=write_proxy),
                patch.object(app, "_video_contains_rating_disclaimer", return_value=False),
            ):
                actual = app.download_official_video_clips(root / "job")

            self.assertEqual(len(actual), 4)
            self.assertEqual(len({Path(p).name for p in actual}), 4)
            self.assertTrue(all(Path(p).stat().st_size > 20000 for p in actual))


if __name__ == "__main__":
    unittest.main()
