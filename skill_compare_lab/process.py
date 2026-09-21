"""Run owned subprocesses with deadlines and file-backed output."""

import os
import signal
import subprocess
import time
from pathlib import Path


def execute(argv, cwd: Path, stdout: Path, stderr: Path, timeout: float, stdin=None, env=None):
    started = time.monotonic()
    options = {"start_new_session": True} if os.name != "nt" else {}
    with stdout.open("w", encoding="utf-8") as out, stderr.open("w", encoding="utf-8") as err:
        with subprocess.Popen(
            argv,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=out,
            stderr=err,
            text=True,
            encoding="utf-8",
            env=env,
            **options,
        ) as process:
            timed_out = False
            try:
                process.communicate(stdin, timeout=timeout)
            except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
                timed_out = isinstance(exc, subprocess.TimeoutExpired)
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                else:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                if process.poll() is None:
                    process.kill()
                process.communicate()
                if not timed_out:
                    raise
            return {
                "returncode": process.returncode,
                "timed_out": timed_out,
                "seconds": round(time.monotonic() - started, 3),
            }
