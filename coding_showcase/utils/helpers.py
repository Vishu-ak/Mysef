"""General-purpose helper utilities.

Strengths demonstrated
----------------------
* Writing small, composable, well-documented functions
* Using type hints consistently

Area to improve
---------------
* Performance-sensitive string operations (e.g. using a compiled regex
  instead of Python-level loops) — marked as TODO below.
"""

from __future__ import annotations
from typing import Any, List


def is_palindrome(text: str) -> bool:
    """Return ``True`` if *text* reads the same forwards and backwards.

    The comparison is case-insensitive and ignores non-alphanumeric
    characters, so ``"A man, a plan, a canal: Panama"`` is a palindrome.

    Parameters
    ----------
    text:
        The string to check.
    """
    # TODO (improvement): replace the character-level loop with a
    # compiled regex for large inputs.
    cleaned = "".join(ch.lower() for ch in text if ch.isalnum())
    return cleaned == cleaned[::-1]


def count_words(text: str) -> int:
    """Return the number of whitespace-delimited words in *text*.

    Parameters
    ----------
    text:
        The string to count words in.
    """
    return len(text.split())


def clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp *value* to the inclusive range [*minimum*, *maximum*].

    Parameters
    ----------
    value:
        The value to clamp.
    minimum:
        Lower bound.
    maximum:
        Upper bound.

    Raises
    ------
    ValueError
        If *minimum* > *maximum*.
    """
    if minimum > maximum:
        raise ValueError(f"minimum ({minimum}) must not exceed maximum ({maximum})")
    return max(minimum, min(value, maximum))


def flatten(nested: List[Any]) -> List[Any]:
    """Recursively flatten a (possibly nested) list into a single list.

    Parameters
    ----------
    nested:
        A list that may contain other lists at any depth.

    Returns
    -------
    list
        A new flat list preserving left-to-right order.

    Examples
    --------
    >>> flatten([1, [2, [3, 4]], 5])
    [1, 2, 3, 4, 5]
    """
    result: List[Any] = []
    for item in nested:
        if isinstance(item, list):
            result.extend(flatten(item))
        else:
            result.append(item)
    return result
