"""
fetcher.py — URL-to-HTML fetching strategies.

Two modes:
  fetch_static()   — plain requests.get(), fast, no JS execution
  fetch_rendered() — Playwright headless Chromium, full JS execution

Both return a raw HTML string suitable for the Scout pipeline.
"""

from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def fetch_static(url: str, timeout: int = 30, **_kwargs) -> str:
    """
    Fetch *url* with a plain HTTP GET request.
    Fast and lightweight — does not execute JavaScript.
    """
    response = requests.get(
        url,
        headers={"User-Agent": _USER_AGENT},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.text


def fetch_rendered(
    url: str,
    wait_until: str = "networkidle",
    timeout: int = 30,
) -> str:
    """
    Fetch *url* using a headless Chromium browser via Playwright.
    JavaScript is fully executed before the DOM is captured.

    Parameters
    ----------
    url        : page to load
    wait_until : Playwright page-load event to wait for before capturing HTML
                 - "networkidle"      — no network activity for 500 ms (best for SPAs)
                 - "load"             — window.load fired (middle ground)
                 - "domcontentloaded" — DOM ready, scripts may still run (fastest)
    timeout    : seconds before giving up (converted to ms internally)
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is not installed. Run: pip install playwright && playwright install chromium"
        ) from exc

    logger.info("Fetching %s with Playwright (wait_until=%s)", url, wait_until)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=_USER_AGENT)
            page.goto(url, wait_until=wait_until, timeout=timeout * 1000)
            html = page.content()
        finally:
            browser.close()

    return html
