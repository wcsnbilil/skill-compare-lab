"""Check task authoring without model calls; execute only through the chosen grader."""

import json
from pathlib import Path

from .grading import check_executor, grade
from .task_packs import load_task_pack, select_tasks


def validate_pack(path: Path, output: Path, executor="docker", task_ids=()):
    pack = load_task_pack(path)
    tasks = select_tasks(pack, task_ids)
    missing = [t.id for t in tasks if t.reference is None]
    if missing:
        raise ValueError("validate-pack requires reference files for: " + ", ".join(missing))
    if output.exists():
        raise ValueError(f"Output already exists: {output}. Choose a new directory.")
    check_executor(executor)
    output.mkdir(parents=True)
    output = output.resolve()
    results = []
    evidence = {
        "pack": pack.name,
        "sha256": pack.sha256(),
        "executor": executor,
        "valid": False,
        "tasks": results,
    }
    try:
        for task in tasks:
            folder = output / task.id
            folder.mkdir()
            reference = grade(task, task.reference, folder / "reference", executor)
            starter = grade(task, task.starter, folder / "starter", executor)
            valid = (
                reference["passed"]
                and not starter["passed"]
                and not starter["timed_out"]
                and starter["returncode"] != 0
            )
            results.append(
                {"id": task.id, "valid": valid, "reference": reference, "starter": starter}
            )
        evidence["valid"] = all(row["valid"] for row in results)
    finally:
        (output / "validation.json").write_text(
            json.dumps(evidence, indent=2) + "\n",
            encoding="utf-8",
        )
    return evidence
