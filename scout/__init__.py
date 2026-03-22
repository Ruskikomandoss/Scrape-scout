"""
Scout — HTML scraper selector generator.

Stages:
  1. parser.py      — BS4 block extraction
  2. classifier.py  — HF zero-shot classification + NER
  3. reasoner.py    — Claude API selector generation
  4. validator.py   — Selector validation against source HTML
  5. output.py      — JSON config + BS4 snippet generation
"""

from .parser import parse
from .classifier import classify
from .reasoner import reason
from .validator import validate
from .output import build_output

__all__ = ["parse", "classify", "reason", "validate", "build_output"]
