import os
import tempfile
import unittest
from pathlib import Path

from skill_compare_lab.grading import check_executor, grade
from skill_compare_lab.tasks import TASKS


@unittest.skipUnless(os.environ.get("SKILL_COMPARE_TEST_DOCKER") == "1", "Docker opt-in test")
class DockerIntegrationTests(unittest.TestCase):
    def test_reference_and_buggy_submission(self):
        check_executor("docker")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            task = TASKS[0]
            good = grade(task, task.reference, root / "good", "docker", timeout=30)
            bad = grade(task, task.starter, root / "bad", "docker", timeout=30)
            self.assertTrue(good["passed"])
            self.assertFalse(bad["passed"])
            self.assertEqual(good["tests_run"], good["tests_expected"])
