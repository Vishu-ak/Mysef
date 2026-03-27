"""Tests for algorithm implementations."""

import pytest
from coding_showcase.algorithms import (
    bubble_sort,
    merge_sort,
    linear_search,
    binary_search,
)


# ---------------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------------

SORT_CASES = [
    ([64, 34, 25, 12, 22, 11, 90], [11, 12, 22, 25, 34, 64, 90]),
    ([1], [1]),
    ([], []),
    ([3, 3, 1, 2], [1, 2, 3, 3]),
    ([5, 4, 3, 2, 1], [1, 2, 3, 4, 5]),
    ([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]),
]


class TestBubbleSort:
    @pytest.mark.parametrize("arr, expected", SORT_CASES)
    def test_sort(self, arr, expected):
        assert bubble_sort(arr) == expected

    def test_does_not_mutate_input(self):
        arr = [3, 1, 2]
        bubble_sort(arr)
        assert arr == [3, 1, 2]


class TestMergeSort:
    @pytest.mark.parametrize("arr, expected", SORT_CASES)
    def test_sort(self, arr, expected):
        assert merge_sort(arr) == expected

    def test_does_not_mutate_input(self):
        arr = [3, 1, 2]
        merge_sort(arr)
        assert arr == [3, 1, 2]


# ---------------------------------------------------------------------------
# Searching
# ---------------------------------------------------------------------------

class TestLinearSearch:
    def test_found(self):
        assert linear_search([1, 2, 3, 4], 3) == 2

    def test_not_found(self):
        assert linear_search([1, 2, 3], 99) == -1

    def test_empty(self):
        assert linear_search([], 1) == -1

    def test_first_occurrence(self):
        assert linear_search([1, 2, 2, 3], 2) == 1


class TestBinarySearch:
    def test_found_middle(self):
        assert binary_search([1, 3, 5, 7, 9], 5) == 2

    def test_found_first(self):
        assert binary_search([1, 3, 5, 7, 9], 1) == 0

    def test_found_last(self):
        assert binary_search([1, 3, 5, 7, 9], 9) == 4

    def test_not_found(self):
        assert binary_search([1, 3, 5, 7, 9], 6) == -1

    def test_empty(self):
        assert binary_search([], 1) == -1

    def test_single_element_found(self):
        assert binary_search([42], 42) == 0

    def test_single_element_not_found(self):
        assert binary_search([42], 0) == -1
