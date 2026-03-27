"""Tests for utility helper functions."""

import pytest
from coding_showcase.utils import is_palindrome, count_words, clamp, flatten


class TestIsPalindrome:
    def test_simple_palindrome(self):
        assert is_palindrome("racecar") is True

    def test_simple_non_palindrome(self):
        assert is_palindrome("hello") is False

    def test_classic_palindrome_with_punctuation(self):
        assert is_palindrome("A man, a plan, a canal: Panama") is True

    def test_case_insensitive(self):
        assert is_palindrome("Racecar") is True

    def test_single_character(self):
        assert is_palindrome("a") is True

    def test_empty_string(self):
        assert is_palindrome("") is True

    def test_numeric_string(self):
        assert is_palindrome("12321") is True


class TestCountWords:
    def test_simple_sentence(self):
        assert count_words("hello world") == 2

    def test_single_word(self):
        assert count_words("hello") == 1

    def test_empty_string(self):
        assert count_words("") == 0

    def test_extra_whitespace(self):
        assert count_words("  hello   world  ") == 2


class TestClamp:
    def test_value_in_range(self):
        assert clamp(50, 0, 100) == 50

    def test_value_above_max(self):
        assert clamp(150, 0, 100) == 100

    def test_value_below_min(self):
        assert clamp(-5, 0, 100) == 0

    def test_value_equals_min(self):
        assert clamp(0, 0, 100) == 0

    def test_value_equals_max(self):
        assert clamp(100, 0, 100) == 100

    def test_invalid_range_raises(self):
        with pytest.raises(ValueError):
            clamp(50, 100, 0)

    def test_float_values(self):
        assert clamp(0.5, 0.0, 1.0) == 0.5


class TestFlatten:
    def test_already_flat(self):
        assert flatten([1, 2, 3]) == [1, 2, 3]

    def test_one_level_nested(self):
        assert flatten([1, [2, 3]]) == [1, 2, 3]

    def test_deeply_nested(self):
        assert flatten([1, [2, [3, [4]]]]) == [1, 2, 3, 4]

    def test_empty_list(self):
        assert flatten([]) == []

    def test_nested_empty_lists(self):
        assert flatten([[], [1], []]) == [1]

    def test_mixed_types(self):
        assert flatten([1, ["a", [True]]]) == [1, "a", True]
