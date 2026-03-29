"""Abstract base scraper using Playwright."""
import asyncio
import random
from abc import ABC, abstractmethod

from playwright.async_api import Browser, BrowserContext, Page, TimeoutError as PWTimeout

import config

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class BaseScraper(ABC):
    def __init__(self, browser: Browser):
        self.browser = browser

    async def _get_page(self) -> tuple[BrowserContext, Page]:
        """Create a new browser context with realistic headers."""
        context = await self.browser.new_context(
            user_agent=_USER_AGENT,
            locale="da-DK",
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()
        return context, page

    async def _safe_inner_text(self, page: Page, selector: str, timeout: int = 5000) -> str:
        """Return inner text of selector, or empty string on timeout/missing."""
        try:
            el = await page.wait_for_selector(selector, timeout=timeout)
            if el:
                return (await el.inner_text()).strip()
        except PWTimeout:
            pass
        except Exception:
            pass
        return ""

    async def _random_delay(self, lo: float = 1.0, hi: float = 3.0):
        await asyncio.sleep(random.uniform(lo, hi))

    async def _screenshot(self, page: Page, name: str = "debug.png"):
        if config.DEBUG_SCREENSHOT:
            await page.screenshot(path=name)

    @abstractmethod
    async def scrape(self) -> list[dict]:
        """
        Scrape job listings and return a list of dicts with keys:
            title, company, url, description, site
        """
