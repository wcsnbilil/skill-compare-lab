# Use your own repair tasks

A task pack lets you evaluate skills against your own definition of a correct repair. Each task still produces one Python module and uses standard-library unittest tests.

## Format

Create a directory with these files:

```text
my-pack/
  pack.json
  starter.py
  contract_tests.py
  reference.py
```

`pack.json`:

```json
{
  "schema_version": 1,
  "name": "My team's repair tasks",
  "tasks": [
    {
      "id": "add-numbers",
      "title": "Add two integers",
      "contract": "Repair add(a, b) to return the sum of two integers.",
      "starter": "starter.py",
      "tests": "contract_tests.py",
      "reference": "reference.py"
    }
  ]
}
```

`starter.py`:

```python
def add(a, b):
    return a - b
```

`contract_tests.py`:

```python
import unittest
from solution import add

class AdditionContract(unittest.TestCase):
    def test_positive(self):
        self.assertEqual(add(2, 3), 5)

    def test_negative(self):
        self.assertEqual(add(-2, -3), -5)
```

`reference.py`:

```python
def add(a, b):
    return a + b
```

The grader names the candidate module `solution.py`. Use `from solution import ...` in your tests. Ordinary unittest discovery, inherited tests, setup/teardown and subtests work; the recorded test count comes from unittest itself. Empty suites, skipped tests and expected failures are not passes. Test discovery and execution happen in the grading process, after model output has been captured.

The `reference` field is optional for live runs and required by `validate-pack`. Every other shown field is required. Unknown fields and duplicate JSON keys are rejected to catch typos. IDs must be unique, start with a lowercase letter, and use up to 64 lowercase letters, digits, hyphens or underscores. A pack contains 1–100 tasks. Text is UTF-8; a UTF-8 BOM is accepted.

All code paths must be relative `.py` paths inside the pack directory, written with forward slashes. Absolute paths, parent traversal and symlinks pointing outside the directory are rejected. Files may be at most 100 KB each; the JSON manifest may be at most 1 MB. Only standard-library dependencies and one solution module are supported in this version.

## Check before spending model usage

```sh
skill-compare tasks --pack my-pack/pack.json
skill-compare validate-pack my-pack/pack.json --output runs/pack-check
```

Listing only loads text and checks syntax; it does not execute the pack. Validation executes both implementations and your tests, but makes no model calls. Exit code 0 means every selected reference passed and every selected starter failed without timing out; exit code 2 means invalid tasks or an execution problem. Inspect `validation.json` and each task's grading logs for details.

Both validation and live runs default to Docker. Prepare it with `docker pull python:3.12-slim`. For a trusted task pack in a disposable development environment, `--executor local` explicitly runs Python on the host. Loading a pack is not a safety audit; treat its code and tests as executable input. The grader is intended for cooperative evaluation, not adversarial submissions.

## Run comparisons

```sh
skill-compare run --pack my-pack/pack.json --skill path/to/skill-a --skill path/to/skill-b --model YOUR_MODEL_ID --repeats 3 --output runs/my-comparison
```

Use repeated `--task TASK_ID` arguments to select a subset from this pack. A custom pack replaces the bundled task set. Invalid IDs or pack contents fail before the runner starts. The number of model calls is selected tasks × (candidate skills + baseline) × repeats.

Only the contract, starter code and selected skill text go into the task prompt. Tests and reference code stay in grading artifacts. `manifest.json` records the pack's content hash; `task-snapshot.json` keeps the complete loaded pack as an inline evidence snapshot, not as a path-based configuration file. The snapshot includes unselected tasks too, so review it before sharing. The report can be rebuilt after the original pack is moved or deleted.

`demo` intentionally uses the bundled scripted fixtures only. Use `validate-pack` to exercise a custom pack offline; do not interpret validation as a model or skill benchmark.

A less trivial example is provided in [examples/task-packs/text-cleanup](../examples/task-packs/text-cleanup/pack.json).
