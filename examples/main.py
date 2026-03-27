"""
Coding Showcase – interactive demo
===================================
Run this script to see all modules in action:

    python examples/main.py
"""

from coding_showcase.data_structures import LinkedList, Stack
from coding_showcase.algorithms import (
    bubble_sort,
    merge_sort,
    linear_search,
    binary_search,
)
from coding_showcase.utils import is_palindrome, count_words, clamp, flatten


def section(title: str) -> None:
    print(f"\n{'=' * 50}")
    print(f"  {title}")
    print("=" * 50)


def demo_linked_list() -> None:
    section("Linked List")
    ll = LinkedList()
    for value in [10, 20, 30, 40]:
        ll.append(value)
    print(f"  After appending 10,20,30,40 : {ll}")

    ll.prepend(5)
    print(f"  After prepending 5          : {ll}")

    ll.delete(20)
    print(f"  After deleting 20           : {ll}")

    node = ll.search(30)
    print(f"  search(30) → {node}")

    print(f"  Length: {len(ll)}")


def demo_stack() -> None:
    section("Stack")
    st = Stack()
    for item in ["a", "b", "c"]:
        st.push(item)
    print(f"  Pushed a, b, c → {st}")
    print(f"  peek()         → {st.peek()!r}")
    print(f"  pop()          → {st.pop()!r}")
    print(f"  After pop      → {st}")


def demo_sorting() -> None:
    section("Sorting Algorithms")
    data = [64, 34, 25, 12, 22, 11, 90]
    print(f"  Input              : {data}")
    print(f"  bubble_sort result : {bubble_sort(data)}")
    print(f"  merge_sort result  : {merge_sort(data)}")
    print(f"  Original unchanged : {data}")


def demo_searching() -> None:
    section("Searching Algorithms")
    data = [3, 7, 14, 21, 35, 42, 56]
    target = 21
    print(f"  List              : {data}")
    print(f"  linear_search({target}) → index {linear_search(data, target)}")
    print(f"  binary_search({target}) → index {binary_search(data, target)}")
    print(f"  linear_search(99) → index {linear_search(data, 99)}")


def demo_utils() -> None:
    section("Utility Helpers")

    phrases = [
        "racecar",
        "A man, a plan, a canal: Panama",
        "hello",
    ]
    for phrase in phrases:
        print(f"  is_palindrome({phrase!r}) → {is_palindrome(phrase)}")

    sentence = "The quick brown fox jumps over the lazy dog"
    print(f"\n  count_words({sentence!r})\n  → {count_words(sentence)}")

    print(f"\n  clamp(150, 0, 100) → {clamp(150, 0, 100)}")
    print(f"  clamp(-5,  0, 100) → {clamp(-5, 0, 100)}")
    print(f"  clamp(42,  0, 100) → {clamp(42, 0, 100)}")

    nested = [1, [2, [3, 4]], 5, [[6]]]
    print(f"\n  flatten({nested})\n  → {flatten(nested)}")


if __name__ == "__main__":
    print("\n🚀  Coding Skills Showcase – Vishu-ak")
    demo_linked_list()
    demo_stack()
    demo_sorting()
    demo_searching()
    demo_utils()
    print("\n✅  Demo complete.\n")
