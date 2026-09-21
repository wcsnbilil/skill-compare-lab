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
    folder.mkdir()
    (folder / "solution.py").write_text(code, encoding="utf-8")
    checker = (
        "import sys, unittest\n"
        "sys.path.insert(0, '/work' if sys.platform != 'win32' and "
        "__file__.startswith('/work/') else __import__('os').path.dirname(__file__))\n"
        "from solution import *\n" + task.tests + "\nif __name__ == '__main__':\n"
        "    unittest.main(verbosity=2)\n"
    )
    (folder / "check.py").write_text(checker, encoding="utf-8")
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
    log = (folder / "stderr.txt").read_text(encoding="utf-8", errors="replace")
    if executor == "docker" and execution["returncode"] in {125, 126, 127}:
        raise ValueError("Docker grading could not start; see grading/stderr.txt.")
    # A bare sys.exit(0) is not a passing test run.
    import re

    counts = re.findall(r"^Ran (\d+) tests? in ", log, re.MULTILINE)
    expected = task.tests.count("    def test_")
    ran = int(counts[-1]) if counts else 0
    passed = (
        not execution["timed_out"]
        and execution["returncode"] == 0
        and ran == expected
        and log.rstrip().endswith("OK")
    )
    result = {
        **execution,
        "passed": passed,
        "tests_run": ran,
        "tests_expected": expected,
        "executor": executor,
    }
    (folder / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def check_executor(executor: str):
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
