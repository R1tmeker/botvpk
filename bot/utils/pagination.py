from __future__ import annotations

from typing import Iterable, List, Sequence, TypeVar

T = TypeVar("T")


def chunked(sequence: Sequence[T], size: int) -> list[list[T]]:
    return [list(sequence[i : i + size]) for i in range(0, len(sequence), size)]


def chunked_iterable(iterable: Iterable[T], size: int) -> list[list[T]]:
    buffer: list[T] = []
    pages: list[list[T]] = []
    for item in iterable:
        buffer.append(item)
        if len(buffer) == size:
            pages.append(buffer)
            buffer = []
    if buffer:
        pages.append(buffer)
    return pages

