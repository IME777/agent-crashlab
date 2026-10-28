"""Small, versioned repair tasks and independent acceptance tests.

Solutions exist only for the explicitly labelled offline fixture provider. Never
include them in prompts sent to a model or public task-list responses.
"""

from copy import deepcopy
from textwrap import dedent


def _code(value: str) -> str:
    return dedent(value).lstrip()


_TASKS = {
    "capped-backoff": {
        "id": "capped-backoff",
        "title": "Keep retry backoff inside its cap",
        "description": (
            "Repair capped_backoff(attempt, base_seconds, cap_seconds). attempt is a "
            "non-negative integer. base_seconds and cap_seconds are non-negative "
            "numbers. Return base_seconds * 2**attempt, capped at cap_seconds, "
            "including attempt zero. Reject negative values with ValueError. "
            "Handle very large attempts without overflow."
        ),
        "starter": _code('''
            def capped_backoff(attempt, base_seconds, cap_seconds):
                return min(base_seconds, cap_seconds) * (2 ** attempt)
        '''),
        "solution": _code('''
            def capped_backoff(attempt, base_seconds, cap_seconds):
                if attempt < 0 or base_seconds < 0 or cap_seconds < 0:
                    raise ValueError("backoff values must be non-negative")
                delay = min(base_seconds, cap_seconds)
                if delay == 0:
                    return delay
                for _ in range(attempt):
                    delay = min(cap_seconds, delay * 2)
                    if delay == cap_seconds:
                        break
                return delay
        '''),
        "tests": _code('''
            import unittest
            from solution import capped_backoff

            class BackoffAcceptance(unittest.TestCase):
                def test_initial_and_growth(self):
                    self.assertEqual(capped_backoff(0, 2, 10), 2)
                    self.assertEqual(capped_backoff(2, 2, 10), 8)

                def test_cap_applies_after_growth(self):
                    self.assertEqual(capped_backoff(3, 2, 10), 10)
                    self.assertEqual(capped_backoff(0, 20, 10), 10)

                def test_zero_and_large_attempt(self):
                    self.assertEqual(capped_backoff(10000, 0, 10), 0)
                    self.assertEqual(capped_backoff(10000, 1, 10), 10)
                    self.assertEqual(capped_backoff(3, 2, 0), 0)

                def test_negative_values_rejected(self):
                    for values in [(-1, 1, 10), (1, -1, 10), (1, 1, -1)]:
                        with self.subTest(values=values), self.assertRaises(ValueError):
                            capped_backoff(*values)
        '''),
    },
    "page-slices": {
        "id": "page-slices",
        "title": "Repair half-open pagination ranges",
        "description": (
            "Repair page_slices(total_items, page_size). Return contiguous (start, "
            "end) half-open index ranges, covering every item once. Never create "
            "an empty page or let end exceed total_items. Zero items returns []. "
            "Both inputs are integers; reject negative total_items and non-positive "
            "page_size with ValueError."
        ),
        "starter": _code('''
            def page_slices(total_items, page_size):
                return [(start, start + page_size)
                        for start in range(0, total_items + 1, page_size)]
        '''),
        "solution": _code('''
            def page_slices(total_items, page_size):
                if total_items < 0 or page_size <= 0:
                    raise ValueError("invalid pagination bounds")
                return [(start, min(start + page_size, total_items))
                        for start in range(0, total_items, page_size)]
        '''),
        "tests": _code('''
            import unittest
            from solution import page_slices

            class PaginationAcceptance(unittest.TestCase):
                def test_zero_and_exact_multiple(self):
                    self.assertEqual(page_slices(0, 4), [])
                    self.assertEqual(page_slices(8, 4), [(0, 4), (4, 8)])

                def test_partial_and_large_page(self):
                    self.assertEqual(page_slices(9, 4), [(0, 4), (4, 8), (8, 9)])
                    self.assertEqual(page_slices(3, 8), [(0, 3)])

                def test_exact_coverage(self):
                    for total in range(20):
                        for size in range(1, 8):
                            ranges = page_slices(total, size)
                            actual = [i for start, end in ranges for i in range(start, end)]
                            self.assertEqual(actual, list(range(total)))
                            self.assertTrue(all(start < end <= total for start, end in ranges))

                def test_invalid_bounds(self):
                    for values in [(-1, 4), (5, 0), (5, -2)]:
                        with self.subTest(values=values), self.assertRaises(ValueError):
                            page_slices(*values)
        '''),
    },
    "token-budget": {
        "id": "token-budget",
        "title": "Validate token reservations at the budget boundary",
        "description": (
            "Repair fits_budget(used_tokens, requested_tokens, max_tokens). All "
            "inputs must be non-negative integers, with bool rejected as TypeError. "
            "Reject other types with TypeError and negative integers with ValueError. "
            "Return whether used_tokens + requested_tokens <= max_tokens; an exact "
            "budget match is allowed. Do not mutate inputs or round numbers."
        ),
        "starter": _code('''
            def fits_budget(used_tokens, requested_tokens, max_tokens):
                return used_tokens + requested_tokens < max_tokens
        '''),
        "solution": _code('''
            def fits_budget(used_tokens, requested_tokens, max_tokens):
                values = (used_tokens, requested_tokens, max_tokens)
                if any(type(value) is not int for value in values):
                    raise TypeError("token counts must be integers")
                if any(value < 0 for value in values):
                    raise ValueError("token counts must be non-negative")
                return used_tokens + requested_tokens <= max_tokens
        '''),
        "tests": _code('''
            import unittest
            from solution import fits_budget

            class TokenBudgetAcceptance(unittest.TestCase):
                def test_budget_boundaries(self):
                    self.assertIs(fits_budget(7, 3, 10), True)
                    self.assertIs(fits_budget(7, 4, 10), False)
                    self.assertIs(fits_budget(0, 0, 0), True)
                    self.assertIs(fits_budget(4, 0, 3), False)

                def test_invalid_types(self):
                    for values in [(True, 1, 3), (0, 1.0, 3), (0, 1, "3")]:
                        with self.subTest(values=values), self.assertRaises(TypeError):
                            fits_budget(*values)

                def test_negative_values(self):
                    for values in [(-1, 2, 3), (1, -2, 3), (1, 2, -3)]:
                        with self.subTest(values=values), self.assertRaises(ValueError):
                            fits_budget(*values)

                def test_large_integer_precision(self):
                    self.assertIs(fits_budget(10**30, 1, 10**30 + 1), True)
                    self.assertIs(fits_budget(10**30, 2, 10**30 + 1), False)
        '''),
    },
}


def list_tasks() -> list[dict]:
    """Return only public catalogue metadata, never solutions or test source."""
    return [{key: task[key] for key in ("id", "title", "description")}
            for task in _TASKS.values()]


def get_task(task_id: str) -> dict:
    """Return a detached task definition. Unknown task IDs raise KeyError."""
    if task_id not in _TASKS:
        raise KeyError(f"Unknown repair task: {task_id}")
    return deepcopy(_TASKS[task_id])
