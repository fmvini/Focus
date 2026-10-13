"""Pure visual pages of original rule indices, independent of configuration."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RulePage:
    """A zero-based page with positional offsets and unchanged original indices."""

    page: int
    page_count: int
    total: int
    start: int
    stop: int
    indices: tuple[int, ...]


def _nonnegative_int(value: int, name: str) -> None:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be nonnegative")


def _validate(indices: tuple[int, ...], size: int) -> None:
    if not isinstance(indices, tuple):
        raise TypeError("indices must be a tuple")
    _nonnegative_int(size, "size")
    if size == 0:
        raise ValueError("size must be positive")
    for index in indices:
        _nonnegative_int(index, "index")


def rule_page(
    indices: tuple[int, ...], page: int = 0, *, size: int = 25
) -> RulePage:
    """Slice an ordered universe; clamp high pages and retain one empty page.

    ``start`` and exclusive ``stop`` are positions in ``indices``, not rule
    identifiers. Values, order and duplicates in the slice remain unchanged.
    """
    _validate(indices, size)
    _nonnegative_int(page, "page")
    total = len(indices)
    page_count = max(1, (total + size - 1) // size)
    actual_page = min(page, page_count - 1)
    start = actual_page * size
    stop = min(total, start + size)
    return RulePage(actual_page, page_count, total, start, stop, indices[start:stop])


def rule_page_for_index(
    indices: tuple[int, ...], index: int, *, size: int = 25
) -> int | None:
    """Locate the first occurrence of an original index, or return ``None``."""
    _validate(indices, size)
    _nonnegative_int(index, "index")
    try:
        position = indices.index(index)
    except ValueError:
        return None
    return position // size
