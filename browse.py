"""
Opens a browser and navigates to a URL, then pauses so you can
right-click → Inspect Element to find the exact selectors needed.

Usage:
    uv run python inspect.py https://studerendeonline.dk/studiejob/
"""
import asyncio
import sys
from playwright.async_api import async_playwright


async def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "https://studerendeonline.dk/studiejob/"
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-features=Translate"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        await page.goto(url)
        print(f"Browser open at: {url}")
        print("Inspect the page, then press Enter here to close.")
        input()
        await browser.close()


asyncio.run(main())
