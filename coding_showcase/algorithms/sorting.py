"""Sorting algorithm implementations.

Strengths demonstrated
----------------------
* Recursive thinking (merge sort)
* Understanding of time / space complexity trade-offs

Known weakness / area to improve
---------------------------------
* Advanced sorts (heap sort, radix sort) are not yet implemented here
  — they are listed as learning goals in the README.
"""

from __future__ import annotations
from typing import List


def bubble_sort(arr: List[int]) -> List[int]:
    """Sort *arr* in ascending order using bubble sort — O(n²).

    A simple but inefficient sort, included to show understanding of
    the basic comparison-swap pattern.

    Parameters
    ----------
    arr:
        The list to sort.  The original list is **not** modified.

    Returns
    -------
    list
        A new sorted list.
    """
    result = list(arr)
    n = len(result)
    for i in range(n):
        swapped = False
        for j in range(0, n - i - 1):
            if result[j] > result[j + 1]:
                result[j], result[j + 1] = result[j + 1], result[j]
                swapped = True
        if not swapped:
            # Already sorted — early exit optimisation.
            break
    return result


def merge_sort(arr: List[int]) -> List[int]:
    """Sort *arr* in ascending order using merge sort — O(n log n).

    Demonstrates comfort with the divide-and-conquer paradigm and
    recursive problem decomposition.

    Parameters
    ----------
    arr:
        The list to sort.  The original list is **not** modified.

    Returns
    -------
    list
        A new sorted list.
    """
    if len(arr) <= 1:
        return list(arr)

    mid = len(arr) // 2
    left = merge_sort(arr[:mid])
    right = merge_sort(arr[mid:])
    return _merge(left, right)


def _merge(left: List[int], right: List[int]) -> List[int]:
    """Merge two sorted lists into one sorted list."""
    merged: List[int] = []
    i = j = 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            merged.append(left[i])
            i += 1
        else:
            merged.append(right[j])
            j += 1
    merged.extend(left[i:])
    merged.extend(right[j:])
    return merged
