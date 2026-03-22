"""
Stage 1 — parser.py

Parse raw HTML into a list of candidate blocks using BeautifulSoup.
Each block captures tag metadata, depth, text samples, and candidate
CSS selector / XPath strings for downstream stages.
"""

from __future__ import annotations

from typing import List

from bs4 import BeautifulSoup, Tag


# Tags considered as candidate content containers
CANDIDATE_TAGS = [
    "div", "article", "section", "main", "p", "span",
    "header", "footer", "nav", "aside",
]

# Minimum characters of inner text required to keep a block
MIN_TEXT_LENGTH = 20

# Characters to include in text_sample
TEXT_SAMPLE_LENGTH = 200


def _compute_depth(element: Tag) -> int:
    """Count how many parent elements exist above *element* in the tree."""
    depth = 0
    parent = element.parent
    while parent is not None and isinstance(parent, Tag):
        depth += 1
        parent = parent.parent
    return depth


def _build_selector(tag: str, element_id: str | None, classes: List[str]) -> str:
    """
    Generate a CSS selector candidate.
    Priority: tag#id > tag.first-class > tag
    Positional selectors (:nth-child etc.) are never used.
    """
    if element_id:
        return f"{tag}#{element_id}"
    if classes:
        return f"{tag}.{classes[0]}"
    return tag


def _build_xpath(tag: str, element_id: str | None, classes: List[str]) -> str:
    """
    Generate an XPath candidate.
    Priority: @id > contains(@class) > bare tag
    """
    if element_id:
        return f"//{tag}[@id='{element_id}']"
    if classes:
        return f"//{tag}[contains(@class, '{classes[0]}')]"
    return f"//{tag}"


def parse(html: str) -> List[dict]:
    """
    Parse *html* and return a list of block dicts sorted by depth (shallowest first).

    Each block dict contains:
        tag, id, classes, depth, text_sample, full_text, selector, xpath
    """
    soup = BeautifulSoup(html, "lxml")

    blocks: List[dict] = []

    for tag_name in CANDIDATE_TAGS:
        for element in soup.find_all(tag_name):
            if not isinstance(element, Tag):
                continue

            full_text: str = element.get_text(separator=" ", strip=True)

            if len(full_text.strip()) < MIN_TEXT_LENGTH:
                continue

            element_id: str | None = element.get("id") or None
            # Normalise class attribute — it may be a list or a string
            raw_classes = element.get("class", [])
            if isinstance(raw_classes, str):
                classes: List[str] = raw_classes.split()
            else:
                classes = list(raw_classes)

            text_sample = full_text[:TEXT_SAMPLE_LENGTH]
            depth = _compute_depth(element)
            selector = _build_selector(tag_name, element_id, classes)
            xpath = _build_xpath(tag_name, element_id, classes)

            blocks.append(
                {
                    "tag": tag_name,
                    "id": element_id,
                    "classes": classes,
                    "depth": depth,
                    "text_sample": text_sample,
                    "full_text": full_text,
                    "selector": selector,
                    "xpath": xpath,
                }
            )

    # Sort shallowest first; use selector as a stable secondary key
    blocks.sort(key=lambda b: (b["depth"], b["selector"]))

    return blocks
