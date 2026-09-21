import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skill_compare_lab.cli import main
from skill_compare_lab.experiment import (
    load_skill,
    make_prompt,
    run_experiment,
    schedule,
    write_json,
)
from skill_compare_lab.grading import grade
from skill_compare_lab.process import execute
from skill_compare_lab.report import summarize, write_report
from skill_compare_lab.runners import codex_run, read_usage
from skill_compare_lab.tasks import TASKS


class WorkspaceCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def skill(self, name="example", content="Check edge cases."):
        folder = self.root / name
        folder.mkdir()
        (folder / "SKILL.md").write_text(content, encoding="utf-8")
        return folder

    def demo(self):
        output, status = run_experiment(
            self.root / "demo",
            mode="demo",
            repeats=2,
            progress=lambda *a, **kw: None,
        )
        self.assertEqual(status, "complete")
        return output


class TaskTests(WorkspaceCase):
    def test_reference_passes_and_starter_fails_every_contract(self):
        for task in TASKS:
            with self.subTest(task=task.id):
                good = grade(task, task.reference, self.root / (task.id + "-good"), "local")
                bad = grade(task, task.starter, self.root / (task.id + "-bad"), "local")
                self.assertTrue(good["passed"])
                self.assertEqual(good["tests_run"], good["tests_expected"])
                self.assertFalse(bad["passed"])

    def test_syntax_error_and_early_exit_are_not_passes(self):
        for index, code in enumerate(("def broken(", "raise SystemExit(0)")):
            result = grade(TASKS[0], code, self.root / str(index), "local")
            self.assertFalse(result["passed"])
            self.assertEqual(result["tests_run"], 0)

    def test_hanging_submission_has_a_deadline(self):
        result = grade(TASKS[0], "while True: pass", self.root / "hang", "local", timeout=0.2)
        self.assertTrue(result["timed_out"])
        self.assertFalse(result["passed"])

    def test_prompt_contains_contract_and_skill_but_not_grading_tests(self):
        task = TASKS[0]
        prompt = make_prompt(task, "MY_SKILL")
        self.assertIn(task.contract, prompt)
        self.assertIn(task.starter, prompt)
        self.assertIn("MY_SKILL", prompt)
        self.assertNotIn(task.tests, prompt)
        self.assertNotIn(task.reference, prompt)
        self.assertNotIn("<skill>", make_prompt(task, ""))


class ExperimentTests(WorkspaceCase):
    def test_paired_schedule_is_complete_reproducible_and_shuffled(self):
        jobs = schedule(TASKS, 3, 3, 42)
        self.assertEqual(jobs, schedule(TASKS, 3, 3, 42))
        self.assertNotEqual(jobs, schedule(TASKS, 3, 3, 43))
        self.assertEqual(len(jobs), 27)
        self.assertEqual(len({(t.id, v, r) for t, v, r in jobs}), 27)

    def test_load_skill_accepts_directory_or_file_with_same_hash(self):
        folder = self.skill()
        self.assertEqual(load_skill(folder), load_skill(folder / "SKILL.md"))
        self.assertEqual(len(load_skill(folder)["sha256"]), 64)

    def test_empty_skill_rejected(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            load_skill(self.skill(content=""))

    def test_invalid_options_leave_no_output(self):
        for options in (
            {"repeats": 0},
            {"repeats": 11},
            {"timeout": 0},
            {"task_ids": ["unknown"]},
            {"mode": "bogus"},
        ):
            with self.subTest(options=options), self.assertRaises(ValueError):
                run_experiment(self.root / "invalid", **options)
        self.assertFalse((self.root / "invalid").exists())

    def test_existing_results_are_never_overwritten(self):
        output = self.demo()
        original = (output / "results.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "already exists"):
            run_experiment(output, mode="demo")
        self.assertEqual(original, (output / "results.json").read_bytes())

    def test_demo_has_real_test_results_without_fake_usage(self):
        output = self.demo()
        manifest = json.loads((output / "manifest.json").read_text())
        rows = json.loads((output / "results.json").read_text())
        summaries = summarize(manifest, rows)
        self.assertEqual([r["passed"] for r in summaries], [0, 3, 6])
        self.assertEqual([r["attempted"] for r in summaries], [6, 6, 6])
        self.assertTrue(all(r["usage"] is None for r in rows))
        self.assertTrue(all(r["grade"]["tests_run"] > 0 for r in rows))
        self.assertEqual(summaries[2]["wins"], 6)
        self.assertIn("Scripted demo", (output / "report.html").read_text(encoding="utf-8"))

    def test_first_runner_error_keeps_evidence_and_stops_with_partial_report(self):
        skill = self.skill()
        version = subprocess.CompletedProcess([], 0, stdout="codex test\n")
        with (
            patch("skill_compare_lab.experiment.subprocess.run", return_value=version),
            patch("skill_compare_lab.experiment.codex_run", side_effect=ValueError("auth failed")),
        ):
            output, status = run_experiment(
                self.root / "failed",
                skills=[skill],
                model="test",
                executor="local",
                progress=lambda *a, **kw: None,
            )
        self.assertEqual(status, "stopped_on_error")
        rows = json.loads((output / "results.json").read_text())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "error")
        report = (output / "report.html").read_text(encoding="utf-8")
        self.assertIn("Incomplete experiment", report)
        self.assertIn("not run", report)

    def test_cli_demo_and_report(self):
        output = self.root / "cli"
        self.assertEqual(
            main(["demo", "--output", str(output), "--repeats", "1", "--task", "chunks"]), 0
        )
        self.assertEqual(main(["report", str(output)]), 0)


class ReportTests(WorkspaceCase):
    def test_missing_usage_is_unknown_and_cache_is_not_double_counted(self):
        manifest = {"variants": [{"id": "v0", "label": "baseline"}]}
        rows = [
            {
                "task": "chunks",
                "repeat": 1,
                "variant": "v0",
                "status": "passed",
                "runner_seconds": 1,
                "usage": {"input_tokens": 100, "cached_input_tokens": 80, "output_tokens": 20},
            },
            {
                "task": "chunks",
                "repeat": 2,
                "variant": "v0",
                "status": "error",
                "runner_seconds": None,
                "usage": None,
            },
        ]
        result = summarize(manifest, rows)[0]
        self.assertEqual(result["tokens"], 120)
        self.assertEqual(result["usage_coverage"], 1)
        self.assertEqual(result["errors"], 1)
        self.assertEqual(result["attempted"], 2)
        self.assertEqual(result["paired"], 1)
        self.assertIsNone(summarize(manifest, rows[1:])[0]["tokens"])

    def test_html_escapes_skill_labels_and_code(self):
        output = self.demo()
        manifest = json.loads((output / "manifest.json").read_text())
        manifest["variants"][1]["label"] = "<script>alert(1)</script>"
        write_json(output / "manifest.json", manifest)
        (output / "chunks-v1-r1" / "solution.py").write_text(
            '</pre><script>alert("code")</script>',
            encoding="utf-8",
        )
        text = write_report(output).read_text(encoding="utf-8")
        self.assertNotIn("<script>alert", text)
        self.assertIn("&lt;script&gt;", text)

    def test_report_rejects_path_traversal(self):
        output = self.demo()
        rows = json.loads((output / "results.json").read_text())
        rows[0]["id"] = "../../private"
        write_json(output / "results.json", rows)
        with self.assertRaisesRegex(ValueError, "Invalid trial ID"):
            write_report(output)


class RunnerTests(WorkspaceCase):
    def events(self, values):
        path = self.root / "events.jsonl"
        path.write_text("\n".join(json.dumps(v) for v in values), encoding="utf-8")
        return path

    def test_usage_accumulates_completed_turns(self):
        usage = {"input_tokens": 12, "cached_input_tokens": 3, "output_tokens": 4}
        path = self.events([{"type": "turn.completed", "usage": usage}] * 2)
        self.assertEqual(
            read_usage(path), {"input_tokens": 24, "cached_input_tokens": 6, "output_tokens": 8}
        )

    def test_missing_usage_remains_unknown(self):
        self.assertIsNone(read_usage(self.events([{"type": "turn.completed"}])))

    def test_failed_or_unfinished_turn_rejected(self):
        for events in (
            [{"type": "turn.failed"}],
            [{"type": "thread.started"}],
            [{"type": "turn.completed"}, {"type": "turn.failed"}],
        ):
            with self.subTest(events=events), self.assertRaises(ValueError):
                read_usage(self.events(events))

    def test_codex_adapter_captures_structured_code_and_usage(self):
        self.root.joinpath("trial").mkdir()
        usage = {"input_tokens": 5, "cached_input_tokens": 0, "output_tokens": 8}

        def fake_execute(argv, cwd, stdout, stderr, timeout, stdin):
            self.assertIn("--sandbox", argv)
            self.assertIn("read-only", argv)
            self.assertIn("--ephemeral", argv)
            self.assertEqual(stdin, "task")
            response = Path(argv[argv.index("--output-last-message") + 1])
            response.write_text(json.dumps({"code": "def f(): return 1\n"}))
            stdout.write_text(json.dumps({"type": "turn.completed", "usage": usage}))
            stderr.write_text("")
            return {"returncode": 0, "timed_out": False, "seconds": 1.5}

        with (
            patch("skill_compare_lab.runners.shutil.which", return_value="codex"),
            patch("skill_compare_lab.runners.execute", side_effect=fake_execute),
        ):
            code, recorded, seconds = codex_run("task", self.root / "trial", "test-model", 10)
        self.assertEqual(recorded, usage)
        self.assertEqual(seconds, 1.5)
        self.assertEqual(code, "def f(): return 1\n")

    def test_subprocess_exit_code_is_retained(self):
        result = execute(
            [sys.executable, "-c", "raise SystemExit(7)"],
            self.root,
            self.root / "out.txt",
            self.root / "err.txt",
            3,
        )
        self.assertEqual(result["returncode"], 7)
        self.assertFalse(result["timed_out"])


if __name__ == "__main__":
    unittest.main()
