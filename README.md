# Mysef – Coding Skills Showcase

A personal Python project that demonstrates my current coding strengths and highlights the areas I am actively working to improve.

---

## Project structure

```
coding_showcase/
├── data_structures/
│   ├── linked_list.py   # Singly-linked list (O(1) prepend, O(n) append)
│   └── stack.py         # LIFO stack built on Python's list
├── algorithms/
│   ├── sorting.py       # Bubble sort (O(n²)) and merge sort (O(n log n))
│   └── searching.py     # Linear search and iterative binary search
└── utils/
    └── helpers.py       # is_palindrome, count_words, clamp, flatten

examples/
└── main.py              # Interactive demo – run this to see everything

tests/
├── test_data_structures.py
├── test_algorithms.py
└── test_utils.py
```

---

## 💪 Strengths

| Area | Evidence in this project |
|------|--------------------------|
| **Data structures** | Clean `LinkedList` with full pointer manipulation, iterator protocol, and `__len__`/`__repr__`. |
| **Divide-and-conquer** | `merge_sort` correctly splits and merges with O(n log n) complexity. |
| **Edge-case handling** | Every function handles empty inputs, single elements, and boundary values. |
| **Type hints & docs** | Every public function has parameter/return type hints and a docstring. |
| **Testing** | 67 unit tests across 3 modules covering happy paths, edge cases, and error paths. |
| **Composable design** | Small, single-purpose functions that are easy to combine (`flatten`, `clamp`, …). |

---

## 🌱 Areas to Improve (honest weaknesses)

| Area | Current gap | Learning goal |
|------|-------------|---------------|
| **Advanced sorting** | Heap sort and radix sort are not yet implemented. | Implement and benchmark both. |
| **Graph algorithms** | BFS, DFS, Dijkstra are missing from this showcase. | Add a `graphs/` module. |
| **Concurrency** | No async or multi-threaded code shown yet. | Add a concurrent data-fetching example. |
| **Performance tuning** | `is_palindrome` uses a character-level Python loop instead of a compiled regex. | Profile and replace with `re` for large inputs. |
| **System design** | Individual functions are clean but there is no larger architecture example. | Add a small REST API or CLI tool to show end-to-end design. |

---

## Running the demo

```bash
# From the repository root
PYTHONPATH=. python examples/main.py
```

## Running the tests

```bash
pip install pytest
pytest
```
