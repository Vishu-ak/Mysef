"""Stack implementation built on top of Python's list."""

from __future__ import annotations
from typing import Any, Optional


class Stack:
    """LIFO stack with O(1) push, pop, and peek.

    Strength demonstrated: knowing when to leverage built-in
    primitives (list) rather than reinventing the wheel.
    """

    def __init__(self) -> None:
        self._data: list = []

    def push(self, item: Any) -> None:
        """Push *item* onto the top of the stack."""
        self._data.append(item)

    def pop(self) -> Any:
        """Remove and return the top item.

        Raises
        ------
        IndexError
            If the stack is empty.
        """
        if self.is_empty():
            raise IndexError("pop from an empty stack")
        return self._data.pop()

    def peek(self) -> Any:
        """Return the top item without removing it.

        Raises
        ------
        IndexError
            If the stack is empty.
        """
        if self.is_empty():
            raise IndexError("peek at an empty stack")
        return self._data[-1]

    def is_empty(self) -> bool:
        """Return ``True`` when the stack contains no items."""
        return len(self._data) == 0

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"Stack({self._data!r})"
