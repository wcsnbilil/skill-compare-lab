"""Grade captured code against fresh tests outside the model's working directory."""

import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from .process import execute
from .tasks import Task

DOCKER_IMAGE = "python:3.12-slim"


def grade(task: Task, code: str, folder: Path, executor: str, timeout=15):
    if executor not in {"docker", "local"}:
        raise ValueError("executor must be docker or local.")
    folder.mkdir()
    (folder / "solution.py").write_text(code, encoding="utf-8")
    (folder / "contract_tests.py").write_text(task.tests, encoding="utf-8")
    shutil.copyfile(Path(__file__).with_name("_grade_submission.py"), folder / "check.py")
    container_name = "skill-compare-" + uuid.uuid4().hex
    if executor == "docker":
        argv = [
            "docker",
            "run",
            "--rm",
            "--name",
            container_name,
            "--network",
            "none",
            "--read-only",
            "--memory",
            "128m",
            "--cpus",
            "1",
            "--pids-limit",
            "64",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--user",
            "65534:65534",
            "--mount",
            f"type=bind,source={folder.resolve()},target=/work,readonly",
            DOCKER_IMAGE,
            "python",
            "-I",
            "-B",
            "/work/check.py",
        ]
    else:
        argv = [sys.executable, "-I", "-B", "check.py"]
    # Do not pass API keys, CLI credentials, or the user's full environment to submitted code.
    env = {
        k: v
        for k, v in os.environ.items()
        if k.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}
    }
    if executor == "docker":
        # The Docker client may need its context; it is not passed into the container.
        env.update(
            {
                k: v
                for k, v in os.environ.items()
                if k.startswith("DOCKER_") or k in {"HOME", "USERPROFILE"}
            }
        )
    try:
        execution = execute(
            argv, folder, folder / "stdout.txt", folder / "stderr.txt", timeout, env=env
        )
    finally:
        if executor == "docker":
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                capture_output=True,
                timeout=15,
                check=False,
                env=env,
            )
    if executor == "docker" and execution["returncode"] in {125, 126, 127}:
        raise ValueError("Docker grading could not start; see grading/stderr.txt.")
    # Read unittest's actual discovery/execution counts, not indentation or stderr wording.
    summary = None
    fields = {
        "tests_expected",
        "tests_run",
        "failures",
        "errors",
        "skipped",
        "expected_failures",
        "unexpected_successes",
    }
    for line in (folder / "stdout.txt").read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("SKILL_COMPARE_GRADE="):
            try:
                value = json.loads(line.removeprefix("SKILL_COMPARE_GRADE="))
            except json.JSONDecodeError:
                continue
            if (
                isinstance(value, dict)
                and value.keys() == fields
                and all(type(v) is int and v >= 0 for v in value.values())
            ):
                summary = value
    expected = summary["tests_expected"] if summary else None
    ran = summary["tests_run"] if summary else 0
    passed = (
        not execution["timed_out"]
        and execution["returncode"] == 0
        and expected is not None
        and expected > 0
        and ran == expected
        and all(summary[key] == 0 for key in fields - {"tests_expected", "tests_run"})
    )
    result = {
        **execution,
        "passed": passed,
        "tests_run": ran,
        "tests_expected": expected,
        "executor": executor,
        "summary": summary,
    }
    (folder / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def check_executor(executor: str):
    if executor not in {"docker", "local"}:
        raise ValueError("executor must be docker or local.")
    if executor == "docker":
        if not shutil.which("docker"):
            raise ValueError(
                "Docker is required for live grading. Install Docker, or use "
                "--executor local only in a disposable, trusted environment."
            )
        check = subprocess.run(
            ["docker", "image", "inspect", DOCKER_IMAGE], capture_output=True, timeout=20
        )
        if check.returncode:
            raise ValueError(f"Start Docker and run: docker pull {DOCKER_IMAGE}")
