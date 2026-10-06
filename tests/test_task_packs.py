import contextlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from skill_compare_lab.cli import main
from skill_compare_lab.experiment import make_prompt, run_experiment
from skill_compare_lab.grading import grade
from skill_compare_lab.pack_validation import validate_pack
from skill_compare_lab.report import write_report
from skill_compare_lab.task_packs import load_task_pack, select_tasks
from skill_compare_lab.tasks import TASKS


class TaskPackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.pack = self.root / "pack"
        self.pack.mkdir()
        self.starter = "def add(a, b): return a - b\n"
        self.reference = "def add(a, b): return a + b\n"
        self.tests = (
            "import unittest\nfrom solution import add\n"
            "class Contract(unittest.TestCase):\n"
            "  def test_add(self): self.assertEqual(add(2, 3), 5)\n"
        )
        for name, content in (
            ("starter.py", self.starter),
            ("reference.py", self.reference),
            ("tests.py", self.tests),
        ):
            (self.pack / name).write_text(content, encoding="utf-8")
        self.data = {
            "schema_version": 1,
            "name": "My <private> pack",
            "tasks": [
                {
                    "id": "add-numbers_v2",
                    "title": "Add numbers",
                    "contract": "Add two integers.",
                    "starter": "starter.py",
                    "tests": "tests.py",
                    "reference": "reference.py",
                }
            ],
        }
        self.path = self.pack / "pack.json"
        self.save()

    def tearDown(self):
        self.temp.cleanup()

    def save(self):
        self.path.write_text(json.dumps(self.data), encoding="utf-8")

    def test_loads_files_relative_to_manifest_and_optional_reference(self):
        pack = load_task_pack(self.path)
        self.assertEqual(pack.tasks[0].starter, self.starter)
        self.assertEqual(pack.tasks[0].tests, self.tests)
        del self.data["tasks"][0]["reference"]
        self.save()
        self.assertIsNone(load_task_pack(self.path).tasks[0].reference)

    def test_builtin_default_and_selection(self):
        self.assertEqual(load_task_pack().tasks, TASKS)
        pack = load_task_pack(self.path)
        self.assertEqual(select_tasks(pack, ["add-numbers_v2"]), list(pack.tasks))
        with self.assertRaisesRegex(ValueError, "Unknown task IDs"):
            select_tasks(pack, ["chunks"])

    def test_hash_tracks_contents_not_folder_location(self):
        before = load_task_pack(self.path).sha256()
        moved = self.root / "moved"
        shutil.copytree(self.pack, moved)
        self.assertEqual(before, load_task_pack(moved / "pack.json").sha256())
        (self.pack / "tests.py").write_text(self.tests + "\n# Changed contract\n")
        self.assertNotEqual(before, load_task_pack(self.path).sha256())

    def test_duplicate_json_fields_are_rejected(self):
        self.path.write_text('{"schema_version": 1, "schema_version": 2}')
        with self.assertRaisesRegex(ValueError, "Duplicate JSON field"):
            load_task_pack(self.path)

    def test_metadata_errors(self):
        original = json.loads(json.dumps(self.data))
        cases = [
            [],
            {**original, "schema_version": True},
            {**original, "tasks": []},
            {**original, "extra": "typo"},
            {**original, "name": None},
            {**original, "tasks": [False]},
        ]
        for value in cases:
            with self.subTest(value=value):
                self.path.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    load_task_pack(self.path)

    def test_task_ids_and_duplicate_ids_are_rejected(self):
        for task_id in ("../outside", "UPPER", "has space", "", 1, "x" * 65):
            with self.subTest(task_id=task_id):
                self.data["tasks"][0]["id"] = task_id
                self.save()
                with self.assertRaises(ValueError):
                    load_task_pack(self.path)
        self.data["tasks"][0]["id"] = "duplicate"
        self.data["tasks"] *= 2
        self.save()
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            load_task_pack(self.path)

    def test_paths_are_bounded_by_pack_directory(self):
        for filename in (
            "../outside.py",
            "/tmp/outside.py",
            "C:/outside.py",
            "sub\\file.py",
            "https://example.com/file.py",
        ):
            with self.subTest(filename=filename):
                self.data["tasks"][0]["starter"] = filename
                self.save()
                with self.assertRaises(ValueError):
                    load_task_pack(self.path)

    def test_symlink_cannot_read_outside_pack(self):
        outside = self.root / "outside.py"
        outside.write_text("secret = 1\n")
        link = self.pack / "linked.py"
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest("Symlink creation not permitted on this host")
        self.data["tasks"][0]["starter"] = "linked.py"
        self.save()
        with self.assertRaisesRegex(ValueError, "outside"):
            load_task_pack(self.path)

    def test_missing_invalid_and_oversized_sources_fail(self):
        for content in ("", "def invalid(", "x" * 100_001):
            with self.subTest(content=content[:20]):
                (self.pack / "tests.py").write_text(content)
                with self.assertRaises(ValueError):
                    load_task_pack(self.path)
        self.data["tasks"][0]["tests"] = "missing.py"
        self.save()
        with self.assertRaisesRegex(ValueError, "not found"):
            load_task_pack(self.path)

    def test_listing_never_executes_tests_or_reference(self):
        marker = self.root / "executed"
        payload = f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
        (self.pack / "tests.py").write_text(payload)
        (self.pack / "reference.py").write_text(payload)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["tasks", "--pack", str(self.path)]), 0)
        self.assertFalse(marker.exists())

    def test_grader_uses_discovered_tests_with_nonstandard_indentation(self):
        task = load_task_pack(self.path).tasks[0]
        result = grade(task, task.reference, self.root / "grade", "local")
        self.assertTrue(result["passed"])
        self.assertEqual(result["tests_expected"], 1)
        self.assertEqual(result["tests_run"], 1)

    def test_grader_discovers_inherited_tests(self):
        task = load_task_pack(self.path).tasks[0]
        inherited = self.tests + "\nclass Derived(Contract):\n  pass\n"
        result = grade(
            replace(task, tests=inherited), task.reference, self.root / "inherited", "local"
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["tests_run"], 2)

    def test_invalid_executor_never_falls_back_to_local(self):
        with self.assertRaisesRegex(ValueError, "executor"):
            validate_pack(self.path, self.root / "unsafe", "typo")
        self.assertFalse((self.root / "unsafe").exists())

    def test_zero_tests_skips_and_expected_failures_do_not_pass(self):
        task = load_task_pack(self.path).tasks[0]
        cases = [
            "import unittest\n",
            self.tests.replace("  def test_add", '  @unittest.skip("unfinished")\n  def test_add'),
            self.tests.replace(
                "  def test_add", "  @unittest.expectedFailure\n  def test_add"
            ).replace("5)", "999)"),
        ]
        for index, tests in enumerate(cases):
            with self.subTest(index=index):
                result = grade(
                    replace(task, tests=tests), task.reference, self.root / f"grade{index}", "local"
                )
                self.assertFalse(result["passed"])

    def test_validate_pack_and_cli_exit_codes(self):
        result = validate_pack(self.path, self.root / "valid", "local")
        self.assertTrue(result["valid"])
        self.assertTrue(result["tasks"][0]["reference"]["passed"])
        self.assertFalse(result["tasks"][0]["starter"]["passed"])
        (self.pack / "starter.py").write_text(self.reference)
        with contextlib.redirect_stdout(io.StringIO()):
            code = main(
                [
                    "validate-pack",
                    str(self.path),
                    "--executor",
                    "local",
                    "--output",
                    str(self.root / "invalid"),
                ]
            )
        self.assertEqual(code, 2)
        result = json.loads((self.root / "invalid" / "validation.json").read_text())
        self.assertFalse(result["valid"])

    def test_missing_reference_blocks_validation_without_creating_output(self):
        del self.data["tasks"][0]["reference"]
        self.save()
        with self.assertRaisesRegex(ValueError, "requires reference"):
            validate_pack(self.path, self.root / "out", "local")
        self.assertFalse((self.root / "out").exists())

    def test_validation_preserves_existing_results_and_rejects_bad_reference(self):
        output = self.root / "validation"
        validate_pack(self.path, output, "local")
        previous = (output / "validation.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "already exists"):
            validate_pack(self.path, output, "local")
        self.assertEqual(previous, (output / "validation.json").read_bytes())
        (self.pack / "reference.py").write_text(self.starter)
        result = validate_pack(self.path, self.root / "bad-reference", "local")
        self.assertFalse(result["valid"])

    def test_live_pipeline_routes_custom_pack_and_preserves_provenance(self):
        skill = self.root / "my-skill"
        skill.mkdir()
        (skill / "SKILL.md").write_text("Be precise.")
        output = self.root / "live"
        version = subprocess.CompletedProcess([], 0, stdout="codex test\n")
        prompts = []

        def runner(prompt, *args):
            prompts.append(prompt)
            return self.reference, None, 0.1

        with (
            patch("skill_compare_lab.experiment.subprocess.run", return_value=version),
            patch("skill_compare_lab.experiment.codex_run", side_effect=runner),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            code = main(
                [
                    "run",
                    "--pack",
                    str(self.path),
                    "--task",
                    "add-numbers_v2",
                    "--skill",
                    str(skill),
                    "--model",
                    "mock-model",
                    "--repeats",
                    "2",
                    "--executor",
                    "local",
                    "--output",
                    str(output),
                ]
            )
        self.assertEqual(code, 0)
        self.assertEqual(len(prompts), 4)
        for prompt in prompts:
            self.assertIn(self.starter, prompt)
            self.assertNotIn(self.reference, prompt)
            self.assertNotIn(self.tests, prompt)
        manifest = json.loads((output / "manifest.json").read_text())
        self.assertEqual(manifest["planned_trials"], 4)
        self.assertEqual(manifest["task_pack"]["sha256"], load_task_pack(self.path).sha256())
        self.assertTrue((output / "task-snapshot.json").is_file())
        report = write_report(output).read_text(encoding="utf-8")
        self.assertIn("My &lt;private&gt; pack", report)
        self.assertNotIn("My <private> pack", report)

    def test_custom_pack_cannot_silently_use_scripted_demo(self):
        with self.assertRaisesRegex(ValueError, "bundled fixtures only"):
            run_experiment(self.root / "demo", mode="demo", pack_path=self.path)

    def test_prompt_excludes_custom_reference(self):
        task = load_task_pack(self.path).tasks[0]
        prompt = make_prompt(task, "")
        self.assertNotIn(task.reference, prompt)
        self.assertNotIn(task.tests, prompt)


if __name__ == "__main__":
    unittest.main()
