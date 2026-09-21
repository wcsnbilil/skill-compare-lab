"""Codex JSONL adapter and deliberately scripted offline demo."""

import json
import shutil
import tempfile
from pathlib import Path

from .process import execute
from .tasks import Task

SCHEMA = {
    "type": "object",
    "properties": {"code": {"type": "string"}},
    "required": ["code"],
    "additionalProperties": False,
}


def read_usage(events: Path):
    total = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
    completed = 0
    complete_usage = True
    for line in events.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") in {"turn.failed", "error"}:
            raise ValueError("Codex reported a failed turn; see runner events.")
        if event.get("type") == "turn.completed":
            completed += 1
            usage = event.get("usage")
            if not isinstance(usage, dict):
                complete_usage = False
                continue
            for key in total:
                value = usage.get(key)
                if type(value) is not int or value < 0:
                    complete_usage = False
                else:
                    total[key] += value
    if not completed:
        raise ValueError("Codex did not emit a completed turn; see runner events.")
    return total if complete_usage else None


def codex_run(prompt: str, folder: Path, model: str, timeout: float):
    executable = shutil.which("codex")
    if not executable:
        raise ValueError("codex was not found. Install and authenticate Codex CLI first.")
    # A fresh working directory contains only the output schema, never grading tests.
    with tempfile.TemporaryDirectory(prefix="skill-compare-agent-") as scratch:
        work = Path(scratch)
        schema = work / "response-schema.json"
        schema.write_text(json.dumps(SCHEMA), encoding="utf-8")
        response = work / "response.json"
        argv = [
            executable,
            "exec",
            "--json",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--color",
            "never",
            "--model",
            model,
            "--output-schema",
            str(schema),
            "--output-last-message",
            str(response),
            "-C",
            str(work),
            "-",
        ]
        events = folder / "events.jsonl"
        result = execute(argv, work, events, folder / "runner-stderr.txt", timeout, prompt)
        if result["timed_out"]:
            raise TimeoutError(f"Codex exceeded {timeout:g} seconds.")
        if result["returncode"]:
            raise ValueError(f"Codex exited with {result['returncode']}; see runner-stderr.txt.")
        usage = read_usage(events)
        if not response.exists() or response.stat().st_size > 1_000_000:
            raise ValueError("Codex response is missing or exceeds 1 MB.")
        raw = response.read_text(encoding="utf-8")
        (folder / "response.json").write_text(raw, encoding="utf-8")
        parsed = json.loads(raw)
        if not isinstance(parsed, dict) or not isinstance(parsed.get("code"), str):
            raise ValueError("Expected a structured response containing a code string.")
        if not parsed["code"].strip():
            raise ValueError("Codex returned empty code.")
        return parsed["code"], usage, result["seconds"]


def demo_run(task: Task, variant_index: int, repeat: int):
    """Choose fixtures, never claim a model produced them or a skill caused a gain."""
    use_reference = variant_index == 2 or (variant_index == 1 and repeat % 2 == 0)
    return task.reference if use_reference else task.starter, None, 0.0
