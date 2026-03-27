"""Searching algorithm implementations.

Strengths demonstrated
----------------------
* Clear pre-condition documentation (binary search requires sorted input)
* Correct handling of edge cases (empty list, target not found)
"""

from __future__ import annotations
from typing import Any, List, Optional


def linear_search(arr: List[Any], target: Any) -> int:
    """Search *arr* for *target*, returning its index or ``-1``.

    Works on any list regardless of order — O(n).

    Parameters
    ----------
    arr:
        The list to search.
    target:
        The value to find.

    Returns
    -------
    int
        Zero-based index of the first occurrence of *target*,
        or ``-1`` if not present.
    """
    for index, value in enumerate(arr):
        if value == target:
            return index
    return -1


def binary_search(arr: List[Any], target: Any) -> int:
    """Search a **sorted** *arr* for *target* — O(log n).

    Uses the iterative (non-recursive) approach to avoid call-stack
    overhead on large lists.

    Parameters
    ----------
    arr:
        A sorted list to search.
    target:
        The value to find.

    Returns
    -------
    int
        Zero-based index of *target*, or ``-1`` if not present.
    """
    low, high = 0, len(arr) - 1
    while low <= high:
        mid = (low + high) // 2
        if arr[mid] == target:
            return mid
        if arr[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return -1
