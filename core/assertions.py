from __future__ import annotations

from pathlib import Path
from typing import Any


def assert_true(condition: Any, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def assert_equal(actual: Any, expected: Any, message: str | None = None) -> None:
    if actual != expected:
        raise AssertionError(message or f"expected {expected!r}, got {actual!r}")


def assert_contains(container: Any, item: Any, message: str | None = None) -> None:
    if item not in container:
        raise AssertionError(message or f"{item!r} was not found in {container!r}")


def assert_file_exists(path: str | Path, message: str | None = None) -> None:
    file_path = Path(path)
    if not file_path.is_file():
        raise AssertionError(message or f"file does not exist: {file_path}")


def assert_dir_exists(path: str | Path, message: str | None = None) -> None:
    dir_path = Path(path)
    if not dir_path.is_dir():
        raise AssertionError(message or f"directory does not exist: {dir_path}")
