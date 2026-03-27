"""Singly-linked list implementation."""

from __future__ import annotations
from typing import Any, Iterator, Optional


class Node:
    """A single element in the linked list."""

    def __init__(self, data: Any) -> None:
        self.data = data
        self.next: Optional[Node] = None

    def __repr__(self) -> str:
        return f"Node({self.data!r})"


class LinkedList:
    """A singly-linked list with O(1) prepend and O(n) append/search.

    Strength demonstrated: understanding of pointer manipulation and
    iterator protocol.
    """

    def __init__(self) -> None:
        self._head: Optional[Node] = None
        self._size: int = 0

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def prepend(self, data: Any) -> None:
        """Insert *data* at the front of the list — O(1)."""
        node = Node(data)
        node.next = self._head
        self._head = node
        self._size += 1

    def append(self, data: Any) -> None:
        """Insert *data* at the end of the list — O(n)."""
        node = Node(data)
        if self._head is None:
            self._head = node
        else:
            current = self._head
            while current.next is not None:
                current = current.next
            current.next = node
        self._size += 1

    def delete(self, data: Any) -> bool:
        """Remove the first node whose value equals *data*.

        Returns ``True`` on success, ``False`` if not found.
        """
        if self._head is None:
            return False

        if self._head.data == data:
            self._head = self._head.next
            self._size -= 1
            return True

        current = self._head
        while current.next is not None:
            if current.next.data == data:
                current.next = current.next.next
                self._size -= 1
                return True
            current = current.next
        return False

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def search(self, data: Any) -> Optional[Node]:
        """Return the first node with *data*, or ``None``."""
        current = self._head
        while current is not None:
            if current.data == data:
                return current
            current = current.next
        return None

    def to_list(self) -> list:
        """Return a plain Python list of node values."""
        result: list = []
        current = self._head
        while current is not None:
            result.append(current.data)
            current = current.next
        return result

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return self._size

    def __iter__(self) -> Iterator[Any]:
        current = self._head
        while current is not None:
            yield current.data
            current = current.next

    def __repr__(self) -> str:
        values = " -> ".join(str(v) for v in self)
        return f"LinkedList([{values}])"
