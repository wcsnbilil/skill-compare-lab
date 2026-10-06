"""Executed in the grading process, after the candidate and tests are copied."""

import importlib.util
import json
import sys
import unittest
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root))
    import solution

    # Preload names for existing snippet-style contracts; standard imports work too.
    spec = importlib.util.spec_from_file_location("contract_tests", root / "contract_tests.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    module.unittest = unittest
    for name, value in vars(solution).items():
        if not name.startswith("_"):
            setattr(module, name, value)
    spec.loader.exec_module(module)
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
    expected = suite.countTestCases()
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    summary = {
        "tests_expected": expected,
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "expected_failures": len(result.expectedFailures),
        "unexpected_successes": len(result.unexpectedSuccesses),
    }
    print("SKILL_COMPARE_GRADE=" + json.dumps(summary), flush=True)
    success = (
        expected > 0
        and result.testsRun == expected
        and result.wasSuccessful()
        and not result.skipped
        and not result.expectedFailures
    )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
