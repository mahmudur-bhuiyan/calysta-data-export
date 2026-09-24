"""Faster page-ready waits — prefer DOM + selectors over networkidle."""

from playwright.async_api import TimeoutError as PlaywrightTimeoutError


async def goto_ready(page, url, ready_selector=None, timeout=60000, ready_timeout=None):
    """
    Navigate with domcontentloaded, then optionally wait for a selector.

    ready_timeout defaults to min(timeout, 15000) so empty list pages
    (selector never appears) fail fast and callers can treat as empty.
    """
    await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    if not ready_selector:
        return
    wait_ms = ready_timeout if ready_timeout is not None else min(int(timeout), 15000)
    try:
        await page.wait_for_selector(ready_selector, timeout=wait_ms)
    except PlaywrightTimeoutError:
        pass


async def wait_selector(page, selector, timeout=15000):
    """Wait for a selector; return True if found, False on timeout."""
    try:
        await page.wait_for_selector(selector, timeout=timeout)
        return True
    except PlaywrightTimeoutError:
        return False
