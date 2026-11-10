import copy
import tempfile
import threading
import unittest

from novela_engine import NovelaEngine


class FakeMemory:
    def __init__(self):
        self.data = {"topics": {}, "videos": {}, "patterns": {}}
        self.lock = threading.RLock()

    def _read(self):
        return copy.deepcopy(self.data)

    def _write(self, value):
        self.data = copy.deepcopy(value)

    def status(self):
        return {"persistent_storage": {"connected": True}}


class NovelaEngineTests(unittest.TestCase):
    def test_season_is_seeded_with_canon_cast_and_eight_distinct_episodes(self):
        engine = NovelaEngine(FakeMemory())
        state = engine.state()
        self.assertEqual(state["series"]["title"], "VICE CITY: O PREÇO DO NEON")
        self.assertEqual(state["season"]["episode_count"], 8)
        names = {person["name"] for person in state["characters"]}
        self.assertIn("Jason Duval", names)
        self.assertIn("Lucia Caminos", names)
        self.assertEqual(state["next_episode_number"], 1)
        self.assertFalse(state["video_generation_enabled"])

    def test_episode_generation_is_idempotent_and_persists_between_instances(self):
        memory = FakeMemory()
        first = NovelaEngine(memory)
        one = first.generate_episode(1)
        retry = first.generate_episode(1)
        second_instance = NovelaEngine(memory)
        loaded = second_instance.get_episode(1)
        self.assertEqual(one["episode_id"], retry["episode_id"])
        self.assertEqual(one["script"], retry["script"])
        self.assertEqual(one["script"], loaded["script"])
        self.assertEqual(second_instance.state()["generated_count"], 1)
        self.assertEqual(second_instance.state()["next_episode_number"], 2)

    def test_cannot_skip_episode_or_generate_out_of_order(self):
        engine = NovelaEngine(FakeMemory())
        with self.assertRaisesRegex(ValueError, "CONTINUITY_GUARD"):
            engine.generate_episode(2)
        engine.generate_episode(1)
        engine.generate_episode(2)
        with self.assertRaisesRegex(ValueError, "CONTINUITY_GUARD"):
            engine.generate_episode(4)

    def test_all_eight_episodes_have_unique_conflicts_reveals_and_cliffhangers(self):
        engine = NovelaEngine(FakeMemory())
        episodes = [engine.generate_episode(n) for n in range(1, 9)]
        self.assertEqual(len({tuple(ep["novelty_keys"]) for ep in episodes}), 8)
        self.assertEqual(len({ep["conflict"] for ep in episodes}), 8)
        self.assertEqual(len({ep["revelation"] for ep in episodes}), 8)
        self.assertEqual(len({ep["cliffhanger"] for ep in episodes}), 8)
        self.assertTrue(all(ep["word_count"] > 80 for ep in episodes))
        self.assertEqual(engine.state()["next_episode_number"], None)
        self.assertTrue(engine.state()["season_complete"])

    def test_dialogue_is_not_reused_between_episodes(self):
        engine = NovelaEngine(FakeMemory())
        first = engine.generate_episode(1)
        second = engine.generate_episode(2)
        lines_a = {
            " ".join(line.lower().split())
            for scene in first["scenes"] for _, line in scene["dialogue"]
        }
        lines_b = {
            " ".join(line.lower().split())
            for scene in second["scenes"] for _, line in scene["dialogue"]
        }
        self.assertFalse(lines_a & lines_b)

    def test_script_creation_never_queues_video_job(self):
        engine = NovelaEngine(FakeMemory())
        episode = engine.generate_episode(1)
        self.assertFalse(episode["video_job_created"])
        self.assertEqual(episode["status"], "SCRIPT_READY")
        self.assertFalse(engine.state()["video_generation_enabled"])


if __name__ == "__main__":
    unittest.main()
