"""The reference scorer: `answer(query, tiles)`, the Python side of spec #27's primary seam."""

from ciao_sun.reference.contract import Answer, Interval, Query, Spot, Window
from ciao_sun.reference.scorer import answer
from ciao_sun.reference.world import load_tiles

__all__ = ["Answer", "Interval", "Query", "Spot", "Window", "answer", "load_tiles"]
