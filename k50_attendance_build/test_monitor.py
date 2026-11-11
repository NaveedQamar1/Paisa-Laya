import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import monitor


class MonitorStateTests(unittest.TestCase):
    def test_seen_punches_persist_across_restarts(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "monitor-state.json"
            seen = {
                ("2026-11-11 09:00:00", "101", "0"),
                ("2026-11-11 17:00:00", "101", "1"),
            }
            with patch.object(monitor, "STATE", state):
                monitor.save_state("192.168.1.50:4370", seen)
                self.assertEqual(monitor.load_state("192.168.1.50:4370"), seen)

    def test_state_is_not_reused_for_a_different_device(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "monitor-state.json"
            with patch.object(monitor, "STATE", state):
                monitor.save_state("192.168.1.50:4370", {
                    ("2026-11-11 09:00:00", "101", "0")
                })
                self.assertIsNone(monitor.load_state("192.168.1.51:4370"))


if __name__ == "__main__":
    unittest.main()
