# Handoff — custom task packs

Updated: 2026-10-06 (America/Chicago)
Branch: `codex/custom-task-packs`
Base: `origin/main` at `0a89854` (PR #1 merged)

## What changed

- Added JSON task packs so users can supply a contract, initial Python module, unittest tests and an optional reference solution without editing the tool.
- Added `tasks --pack`, `run --pack`, and model-free `validate-pack`. Validation requires a passing reference and a failing, non-timeout starter. Execution still defaults to Docker.
- Pack loading checks schema, duplicate fields/IDs, syntax, file limits and paths confined to the pack directory. Loading/listing executes no pack code.
- Replaced indentation-based test counting with unittest discovery and a structured result from the grading process. Empty suites, skipped tests, expected failures and early exits do not pass.
- Experiments retain a complete task snapshot and content hash. Reports show the pack name and accept safe hyphenated/underscored task IDs; old reports remain readable.
- Added a text-cleanup example, English/Chinese instructions, companion Skill guidance and CI validation on local and Docker graders.

## Verification

- Windows/Python 3.12: 41 automated tests discovered; 39 passed, 2 skipped. Local skips: Docker integration (Docker unavailable) and symlink creation (host privilege restriction).
- Ruff check and format check passed; companion SKILL.md passed quick_validate.
- Text-cleanup validation passed: reference satisfies all five unittest methods; starter fails.
- Wheel built and installed; installed CLI validation passed from outside the source checkout, including the packaged grading helper.
- Model calls were mocked in the custom-pack pipeline test. No new live model comparison was run for this change; the Codex adapter is unchanged.
- Remote CI is checked on the PR after pushing. Its Docker job also validates the custom example; Linux covers symlink containment.

## Reproduce

```sh
python -m unittest discover -s tests -v
ruff check .
ruff format --check .
python -m skill_compare_lab tasks --pack examples/task-packs/text-cleanup/pack.json
python -m skill_compare_lab validate-pack examples/task-packs/text-cleanup/pack.json --output runs/pack-check
```

The final command requires Docker and the `python:3.12-slim` image. Use `--executor local` only for trusted code in a disposable environment. Choose a new output directory for each run.

## Limits and next work

- Tasks remain single-module Python with standard-library unittest. Multi-file projects, pytest and extra dependencies are not supported.
- This is cooperative evaluation, not an adversarially hardened judge. Docker isolates grading; the Codex runner keeps its existing sandbox/configuration behavior.
- Snapshots include all loaded tasks, including unselected tests and references. Review local artifacts before sharing; they are Git-ignored.
- Possible follow-up: comparing saved runs and producing a compact PR report. This is not implemented here.
- User requirement: write or update a handoff file after each completed code change.
