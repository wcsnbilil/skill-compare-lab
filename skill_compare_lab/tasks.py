"""Versioned, dependency-free tasks. Tests are never included in model prompts."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    contract: str
    starter: str
    tests: str
    reference: str | None = None


TASKS = (
    Task(
        "chunks",
        "Keep the final batch",
        "Repair chunks(items, size). Return a list of lists in input order, including the "
        "final partial batch. Accept any iterable, including one-shot generators. Empty input "
        "returns []. size must be an integer greater than zero; reject booleans, non-integers, "
        "zero and negative sizes with ValueError. Do not mutate the input.",
        "def chunks(items, size):\n"
        "    return [items[i:i + size] for i in range(0, len(items) - size + 1, size)]\n",
        """class Contract(unittest.TestCase):
    def test_partial(self):
        self.assertEqual(chunks([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]])
    def test_generator(self):
        self.assertEqual(chunks((x for x in range(3)), 2), [[0, 1], [2]])
    def test_empty(self):
        self.assertEqual(chunks([], 2), [])
    def test_large_size(self):
        self.assertEqual(chunks([1], 9), [[1]])
    def test_invalid(self):
        for size in (0, -1, True, 1.5, "2", None):
            with self.subTest(size=size), self.assertRaises(ValueError):
                chunks([], size)
    def test_unchanged(self):
        items = [1, 2, 3]
        chunks(items, 2)
        self.assertEqual(items, [1, 2, 3])
""",
        """def chunks(items, size):
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise ValueError("size must be a positive integer")
    result, batch = [], []
    for item in items:
        batch.append(item)
        if len(batch) == size:
            result.append(batch)
            batch = []
    if batch:
        result.append(batch)
    return result
""",
    ),
    Task(
        "unique",
        "Preserve the first record",
        "Repair unique_by(records, key). Keep the first dictionary for each distinct hashable "
        "key value, preserving input order and object identity. Accept any iterable. Keep every "
        "record missing the key; a missing key is different from an explicit None value. "
        "Do not mutate records.",
        "def unique_by(records, key):\n"
        "    return list({record.get(key): record for record in records}.values())\n",
        """class Contract(unittest.TestCase):
    def test_first(self):
        a, b, c = {"id": 1, "v": "a"}, {"id": 1, "v": "b"}, {"id": 2}
        result = unique_by([a, b, c], "id")
        self.assertEqual(result, [a, c])
        self.assertIs(result[0], a)
    def test_missing_and_none(self):
        a, b, c, d = {}, {"v": 1}, {"id": None}, {"id": None, "v": 3}
        self.assertEqual(unique_by([a, c, b, d], "id"), [a, c, b])
    def test_generator(self):
        self.assertEqual(unique_by(({"id": x} for x in [2, 1, 2]), "id"),
                         [{"id": 2}, {"id": 1}])
    def test_empty(self):
        self.assertEqual(unique_by([], "id"), [])
    def test_unchanged(self):
        records = [{"id": 1}, {"id": 1}]
        unique_by(records, "id")
        self.assertEqual(records, [{"id": 1}, {"id": 1}])
""",
        """def unique_by(records, key):
    seen, result = set(), []
    for record in records:
        if key not in record:
            result.append(record)
        elif record[key] not in seen:
            seen.add(record[key])
            result.append(record)
    return result
""",
    ),
    Task(
        "intervals",
        "Merge without side effects",
        "Repair merge_intervals(intervals). Input is a list of [start, end] integer pairs, "
        "possibly unsorted. Return sorted merged lists, merging overlapping or touching "
        "intervals (inclusive endpoints). Allow zero-length intervals; reject start > end "
        "with ValueError. Return [] for empty input. Preserve the input and return "
        "new inner lists.",
        """def merge_intervals(intervals):
    intervals.sort()
    result = [intervals[0]]
    for start, end in intervals[1:]:
        if start < result[-1][1]:
            result[-1][1] = end
        else:
            result.append([start, end])
    return result
""",
        """class Contract(unittest.TestCase):
    def test_unsorted_touching(self):
        self.assertEqual(merge_intervals([[5, 8], [1, 3], [3, 6]]), [[1, 8]])
    def test_nested(self):
        self.assertEqual(merge_intervals([[1, 10], [2, 3]]), [[1, 10]])
    def test_empty(self):
        self.assertEqual(merge_intervals([]), [])
    def test_zero_length(self):
        self.assertEqual(merge_intervals([[2, 2], [1, 1]]), [[1, 1], [2, 2]])
    def test_invalid(self):
        with self.assertRaises(ValueError):
            merge_intervals([[4, 2]])
    def test_unchanged_and_unaliased(self):
        items = [[5, 6], [1, 3], [2, 4]]
        result = merge_intervals(items)
        self.assertEqual(items, [[5, 6], [1, 3], [2, 4]])
        result[0][0] = 99
        self.assertEqual(items, [[5, 6], [1, 3], [2, 4]])
""",
        """def merge_intervals(intervals):
    if any(start > end for start, end in intervals):
        raise ValueError("start must not exceed end")
    result = []
    for start, end in sorted(intervals):
        if result and start <= result[-1][1]:
            result[-1][1] = max(result[-1][1], end)
        else:
            result.append([start, end])
    return result
""",
    ),
)
