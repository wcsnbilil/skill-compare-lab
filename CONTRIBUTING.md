# Contributing

Keep changes small enough to inspect. Open an issue for new runner protocols or task-pack redesigns; focused bug fixes can go directly to a pull request.

Install Python 3.11+, then:

```sh
python -m pip install -e .
python -m pip install ruff==0.11.13
python -m unittest discover -s tests -v
ruff check .
ruff format --check .
```

New tasks need a written contract, a starter that fails it, and a reference implementation that passes every check. Cover behavior rather than the exact spelling of the solution. Keep grading data out of model prompts.

For runner changes, include a protocol test for failure as well as success. Never replace missing usage with zero, drop failed trials, mix demo and live results, or weaken grading to make a model pass.

UI changes should preserve keyboard access, mobile table scrolling, HTML escaping and offline operation. Generated run folders and private logs stay out of commits. Explain which checks you actually ran; label mocked and live validation separately.
