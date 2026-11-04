import tempfile
import unittest
from pathlib import Path

from tools import scheduler


class SchedulerTests(unittest.TestCase):
    def test_tasks_created_within_one_second_have_unique_ids(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            old_dir, old_file = scheduler.DATA_DIR, scheduler.SCHEDULE_FILE
            try:
                scheduler.DATA_DIR = temp_dir
                scheduler.SCHEDULE_FILE = str(Path(temp_dir) / "schedules.json")
                scheduler.scheduler_tool({"action": "add", "command": "first", "minutes": 1})
                scheduler.scheduler_tool({"action": "add", "command": "second", "minutes": 1})
                items = scheduler._load_schedules()
                self.assertEqual(len({item["id"] for item in items}), 2)
            finally:
                scheduler.DATA_DIR, scheduler.SCHEDULE_FILE = old_dir, old_file


if __name__ == "__main__":
    unittest.main()
