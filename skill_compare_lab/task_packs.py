"""Load portable task packs as data; listing a pack never executes its Python."""

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path, PureWindowsPath

from .tasks import TASKS, Task

MAX_FILE_BYTES = 100_000
TASK_ID = re.compile(r"[a-z][a-z0-9_-]{0,63}")


@dataclass(frozen=True)
class TaskPack:
    name: str
    tasks: tuple[Task, ...]
    source: str

    def snapshot(self):
        return {
            "name": self.name,
            "source": self.source,
            "tasks": [asdict(task) for task in self.tasks],
        }

    def sha256(self):
        payload = json.dumps(self.snapshot(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}: expected a non-empty string.")
    return value


def _read_source(root: Path, value, label):
    name = _text(value, label)
    relative = Path(name)
    if (
        relative.is_absolute()
        or PureWindowsPath(name).drive
        or "\\" in name
        or ".." in relative.parts
        or relative.suffix != ".py"
    ):
        raise ValueError(f"{label}: use a relative .py path inside the pack, with forward slashes.")
    source = (root / relative).resolve()
    if not source.is_relative_to(root):
        raise ValueError(f"{label}: file resolves outside the task pack.")
    if not source.is_file():
        raise ValueError(f"{label}: Python file not found: {name}")
    if source.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"{label}: Python files must be at most {MAX_FILE_BYTES} bytes.")
    return _text(source.read_text(encoding="utf-8-sig"), label)


def _check_python(source, label):
    try:
        compile(source, label, "exec")
    except SyntaxError as exc:
        raise ValueError(f"{label}: invalid Python at line {exc.lineno}: {exc.msg}") from None


def _unique_fields(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"Duplicate JSON field: {key}")
        value[key] = item
    return value


def load_task_pack(path: Path | None = None):
    if path is None:
        return TaskPack("Bundled Python repairs", TASKS, "bundled")
    path = Path(path).resolve()
    if path.stat().st_size > 1_000_000:
        raise ValueError("Task pack JSON exceeds 1 MB.")
    data = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique_fields)
    if not isinstance(data, dict):
        raise ValueError("Task pack must be a JSON object.")
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("Task pack schema_version must be 1.")
    unknown = data.keys() - {"schema_version", "name", "tasks"}
    if unknown:
        raise ValueError(f"Unknown task pack fields: {', '.join(sorted(unknown))}")
    name = _text(data.get("name"), "name")
    entries = data.get("tasks")
    if not isinstance(entries, list) or not 1 <= len(entries) <= 100:
        raise ValueError("tasks must be a list containing 1 to 100 tasks.")
    tasks, ids = [], set()
    for index, entry in enumerate(entries):
        label = f"tasks[{index}]"
        if not isinstance(entry, dict):
            raise ValueError(f"{label}: expected an object.")
        unknown = entry.keys() - {"id", "title", "contract", "starter", "tests", "reference"}
        if unknown:
            raise ValueError(f"{label}: unknown fields: {', '.join(sorted(unknown))}")
        task_id = _text(entry.get("id"), f"{label}.id")
        if not TASK_ID.fullmatch(task_id):
            raise ValueError(
                f"{label}.id: use 1–64 lowercase letters, digits, hyphens or "
                "underscores, starting with a letter."
            )
        if task_id in ids:
            raise ValueError(f"Duplicate task ID: {task_id}")
        ids.add(task_id)
        title = _text(entry.get("title"), f"{label}.title")
        contract = _text(entry.get("contract"), f"{label}.contract")
        starter = _read_source(path.parent, entry.get("starter"), f"{label}.starter")
        tests = _read_source(path.parent, entry.get("tests"), f"{label}.tests")
        _check_python(tests, f"{label}.tests")
        reference = None
        if "reference" in entry:
            reference = _read_source(path.parent, entry["reference"], f"{label}.reference")
            _check_python(reference, f"{label}.reference")
        tasks.append(Task(task_id, title, contract, starter, tests, reference))
    return TaskPack(name, tuple(tasks), "custom")


def select_tasks(pack: TaskPack, task_ids=()):
    unknown = set(task_ids) - {t.id for t in pack.tasks}
    if unknown:
        raise ValueError(f"Unknown task IDs in {pack.name}: {', '.join(sorted(unknown))}")
    return [t for t in pack.tasks if not task_ids or t.id in task_ids]
