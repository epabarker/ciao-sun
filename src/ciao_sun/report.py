"""Progress reporting for the long-running steps (fetch, build, publish, fixtures)."""

from __future__ import annotations


def silent(message: str) -> None:
    """The default reporter: says nothing."""
    return None
