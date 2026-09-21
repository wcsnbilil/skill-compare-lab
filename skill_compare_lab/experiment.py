"""Paired experiments: fresh inputs, shuffled order, retained failures and artifacts."""

import hashlib
import json
import platform
import random
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .grading import check_executor, grade
from .report import write_report
from .runners import codex_run, demo_run
from .tasks import TASKS, Task


def digest(text: str):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json(path: Path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_skill(path: Path):
    if path.is_dir():
        path = path / "SKILL.md"
    if path.name != "SKILL.md":
        raise ValueError("Each skill must be a SKILL.md file or its containing directory.")
    if path.stat().st_size > 100_000:
        raise ValueError(f"{path}: SKILL.md exceeds the first version's 100 KB limit.")
    content = path.read_text(encoding="utf-8-sig")
    if not content.strip():
        raise ValueError(f"{path}: empty SKILL.md.")
    return {"label": path.parent.name, "text": content, "sha256": digest(content)}


def make_prompt(task: Task, skill_text: str):
    return (
        "Repair the following Python function to satisfy its entire contract. "
        "Return a JSON object with one field, code, containing the complete corrected module. "
        "This is a self-contained code-response task: all task inputs are below. "
        "No tools, repository files, network access, or installed skills are needed. "
        "Use Python's standard library only. Preserve the function signature.\n\n"
        + (
            f"Apply these skill instructions while solving the task:\n<skill>\n{skill_text}"
            "\n</skill>\n\n"
            if skill_text
            else ""
        )
        + f"Contract:\n{task.contract}\n\nInitial module:\n<code>\n{task.starter}</code>\n"
    )


def schedule(tasks, variant_count: int, repeats: int, seed: int):
    rng = random.Random(seed)
    jobs = []
    for repeat in range(repeats):
        task_order = list(tasks)
        rng.shuffle(task_order)
        for task in task_order:
            order = list(range(variant_count))
            rng.shuffle(order)
            jobs.extend((task, index, repeat) for index in order)
    return jobs


def run_experiment(
    output: Path,
    skills=(),
    repeats=3,
    seed=42,
    model=None,
    timeout=180,
    executor="docker",
    mode="live",
    task_ids=(),
    progress=print,
):
    if mode not in {"live", "demo"} or executor not in {"local", "docker"}:
        raise ValueError("Unsupported mode or executor.")
    if not 1 <= repeats <= 10:
        raise ValueError("repeats must be between 1 and 10.")
    if timeout <= 0:
        raise ValueError("timeout must be positive.")
    if mode == "live" and (not model or not model.strip()):
        raise ValueError("Choose an explicit --model for a reproducible live comparison.")
    if output.exists():
        raise ValueError(f"Output already exists: {output}. Choose a new directory.")
    unknown = set(task_ids) - {t.id for t in TASKS}
    if unknown:
        raise ValueError(f"Unknown task IDs: {', '.join(sorted(unknown))}")
    tasks = [t for t in TASKS if not task_ids or t.id in task_ids]
    variants = [{"label": "No injected skill", "text": "", "sha256": digest("")}]
    if mode == "demo":
        variants += [
            {"label": "Demo A · mixed fixtures", "text": "Scripted demo A", "sha256": None},
            {"label": "Demo B · reference fixtures", "text": "Scripted demo B", "sha256": None},
        ]
        executor = "local"
    else:
        variants += [load_skill(Path(path)) for path in skills]
        if not 2 <= len(variants) <= 7:
            raise ValueError("Provide between 1 and 6 --skill paths.")
        if len({v["label"] for v in variants}) != len(variants):
            raise ValueError("Skill folder names must be unique and differ from the baseline.")
    runner_version = "scripted fixtures"
    if mode == "live":
        check_executor(executor)
        try:
            version = subprocess.run(
                ["codex", "--version"], capture_output=True, text=True, timeout=15, check=True
            )
            runner_version = version.stdout.strip()
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError("Install and authenticate Codex CLI before running live.") from exc
    output.mkdir(parents=True)
    output = output.resolve()
    jobs = schedule(tasks, len(variants), repeats, seed)
    manifest = {
        "schema_version": 1,
        "tool_version": __version__,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "model": model if mode == "live" else "scripted fixtures",
        "runner_version": runner_version,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "executor": executor,
        "repeats": repeats,
        "seed": seed,
        "timeout_seconds": timeout,
        "planned_trials": len(jobs),
        "skill_loading": "SKILL.md text injected into task prompt; no native skill discovery",
        "configuration": (
            "Codex user configuration is inherited; use the same setup across conditions."
        ),
        "variants": [
            {"id": f"v{i}", "label": v["label"], "sha256": v["sha256"]}
            for i, v in enumerate(variants)
        ],
        "tasks": [
            {"id": t.id, "title": t.title, "sha256": digest(json.dumps(asdict(t), sort_keys=True))}
            for t in tasks
        ],
        "status": "running",
    }
    if executor == "docker":
        from .grading import DOCKER_IMAGE

        image = subprocess.run(
            ["docker", "image", "inspect", "--format", "{{.Id}}", DOCKER_IMAGE],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        manifest["docker_image"] = DOCKER_IMAGE
        manifest["docker_image_id"] = image.stdout.strip()
    write_json(output / "manifest.json", manifest)
    for i, variant in enumerate(variants):
        (output / f"v{i}-skill.md").write_text(variant["text"], encoding="utf-8")
    rows = []
    try:
        for number, (task, index, repeat) in enumerate(jobs, 1):
            run_id = f"{task.id}-v{index}-r{repeat + 1}"
            folder = output / run_id
            folder.mkdir()
            prompt = make_prompt(task, variants[index]["text"])
            (folder / "prompt.txt").write_text(prompt, encoding="utf-8")
            (folder / "starter.py").write_text(task.starter, encoding="utf-8")
            row = {
                "id": run_id,
                "task": task.id,
                "variant": f"v{index}",
                "repeat": repeat + 1,
                "status": "error",
                "usage": None,
                "runner_seconds": None,
                "prompt_sha256": digest(prompt),
                "grade": None,
                "error": None,
            }
            progress(
                f"[{number}/{len(jobs)}] {task.id} / {variants[index]['label']} "
                f"/ repeat {repeat + 1}",
                flush=True,
            )
            try:
                if mode == "demo":
                    code, usage, seconds = demo_run(task, index, repeat)
                else:
                    code, usage, seconds = codex_run(prompt, folder, model, timeout)
                row.update(usage=usage, runner_seconds=seconds, code_sha256=digest(code))
                (folder / "solution.py").write_text(code, encoding="utf-8")
                row["grade"] = grade(task, code, folder / "grading", executor)
                row["status"] = (
                    "timeout"
                    if row["grade"]["timed_out"]
                    else "passed"
                    if row["grade"]["passed"]
                    else "failed"
                )
            except TimeoutError as exc:
                row.update(status="timeout", error=str(exc))
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                row.update(status="error", error=str(exc))
            rows.append(row)
            write_json(folder / "trial.json", row)
            write_json(output / "results.json", rows)
            if row["status"] == "error":
                manifest["status"] = "stopped_on_error"
                break
        else:
            manifest["status"] = "complete"
    except KeyboardInterrupt:
        manifest["status"] = "interrupted"
    finally:
        write_json(output / "manifest.json", manifest)
        write_json(output / "results.json", rows)
        write_report(output)
    return output, manifest["status"]
