"""Tests for data structure implementations."""

import pytest
from coding_showcase.data_structures import LinkedList, Stack


# ---------------------------------------------------------------------------
# LinkedList
# ---------------------------------------------------------------------------

class TestLinkedList:
    def test_empty_list(self):
        ll = LinkedList()
        assert len(ll) == 0
        assert ll.to_list() == []

    def test_append(self):
        ll = LinkedList()
        ll.append(1)
        ll.append(2)
        ll.append(3)
        assert ll.to_list() == [1, 2, 3]
        assert len(ll) == 3

    def test_prepend(self):
        ll = LinkedList()
        ll.prepend(3)
        ll.prepend(2)
        ll.prepend(1)
        assert ll.to_list() == [1, 2, 3]

    def test_delete_existing(self):
        ll = LinkedList()
        for v in [1, 2, 3]:
            ll.append(v)
        assert ll.delete(2) is True
        assert ll.to_list() == [1, 3]
        assert len(ll) == 2

    def test_delete_head(self):
        ll = LinkedList()
        ll.append(1)
        ll.append(2)
        assert ll.delete(1) is True
        assert ll.to_list() == [2]

    def test_delete_missing(self):
        ll = LinkedList()
        ll.append(1)
        assert ll.delete(99) is False
        assert len(ll) == 1

    def test_delete_from_empty(self):
        ll = LinkedList()
        assert ll.delete(5) is False

    def test_search_found(self):
        ll = LinkedList()
        for v in [10, 20, 30]:
            ll.append(v)
        node = ll.search(20)
        assert node is not None
        assert node.data == 20

    def test_search_not_found(self):
        ll = LinkedList()
        ll.append(1)
        assert ll.search(99) is None

    def test_iteration(self):
        ll = LinkedList()
        for v in [4, 5, 6]:
            ll.append(v)
        assert list(ll) == [4, 5, 6]

    def test_repr(self):
        ll = LinkedList()
        ll.append(1)
        ll.append(2)
        assert "1" in repr(ll)
        assert "2" in repr(ll)


# ---------------------------------------------------------------------------
# Stack
# ---------------------------------------------------------------------------

class TestStack:
    def test_empty_stack(self):
        st = Stack()
        assert st.is_empty() is True
        assert len(st) == 0

    def test_push_and_peek(self):
        st = Stack()
        st.push(10)
        assert st.peek() == 10
        assert len(st) == 1

    def test_push_multiple(self):
        st = Stack()
        for item in [1, 2, 3]:
            st.push(item)
        assert st.peek() == 3
        assert len(st) == 3

    def test_pop(self):
        st = Stack()
        st.push("x")
        st.push("y")
        assert st.pop() == "y"
        assert st.pop() == "x"
        assert st.is_empty()

    def test_pop_empty_raises(self):
        st = Stack()
        with pytest.raises(IndexError):
            st.pop()

    def test_peek_empty_raises(self):
        st = Stack()
        with pytest.raises(IndexError):
            st.peek()

    def test_repr(self):
        st = Stack()
        st.push(42)
        assert "42" in repr(st)
