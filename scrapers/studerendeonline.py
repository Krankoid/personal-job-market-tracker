"""
Scraper for studerendeonline.dk/studiejob/

The site is server-rendered. Job cards sit in a listing page; each card
links to a detail page with the full description.

Selectors may need updating if the site changes its HTML — run with
DEBUG_SCREENSHOT=true and HEADLESS=false to inspect the page visually.
"""
import config
from scrapers.base import BaseScraper

SITE_KEY = "studerendeonline"

# CSS selectors — confirmed by inspecting studerendeonline.dk
_CARD_SELECTOR = "div.job-item"
_TITLE_SELECTOR = ".job-header"
_TEASER_SELECTOR = ".job-teaser"   # "Studiejob hos COMPANY, LOCATION"
_LINK_SELECTOR = "div.job-content a"
_DESCRIPTION_SELECTOR = "article, .job-description, .description, main"
_NEXT_PAGE_SELECTOR = "a[rel='next'], .pagination .next, a.next-page"


class StuderendeOnlineScraper(BaseScraper):
    async def scrape(self) -> list[dict]:
        context, page = await self._get_page()
        jobs: list[dict] = []

        try:
            url = config.STUDERENDEONLINE_BASE_URL
            pages_scraped = 0

            # Dismiss cookie popup on first page load
            print(f"[studerendeonline] Fetching listing page 1: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            await self._dismiss_cookies(page)
            await self._screenshot(page, "debug_so_after_cookies.png")

            while url and pages_scraped < config.SCRAPE_LIMIT:
                if pages_scraped > 0:
                    print(f"[studerendeonline] Fetching listing page {pages_scraped + 1}: {url}")
                    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                await self._screenshot(page, f"debug_so_listing_{pages_scraped}.png")

                # Collect job cards on the current listing page
                cards = await page.query_selector_all(_CARD_SELECTOR)
                if not cards:
                    print("[studerendeonline] No job cards found — check selector or page structure.")
                    break

                card_data = []
                for card in cards:
                    title = await self._safe_inner_text_el(card, _TITLE_SELECTOR)
                    teaser = await self._safe_inner_text_el(card, _TEASER_SELECTOR)
                    # teaser format: "Studiejob hos COMPANY, LOCATION"
                    company = teaser.split("hos ")[-1].split(",")[0].strip() if "hos " in teaser else ""
                    link_el = await card.query_selector(_LINK_SELECTOR)
                    href = await link_el.get_attribute("href") if link_el else None
                    if not href:
                        continue
                    if href.startswith("/"):
                        href = "https://studerendeonline.dk" + href
                    card_data.append({"title": title, "company": company, "url": href})

                # Fetch description for each card
                for card in card_data:
                    desc = await self._fetch_description(page, card["url"])
                    jobs.append({
                        "title": card["title"],
                        "company": card["company"],
                        "url": card["url"],
                        "description": desc,
                        "site": SITE_KEY,
                    })
                    await self._random_delay()

                pages_scraped += 1

                # Check for next page
                next_el = await page.query_selector(_NEXT_PAGE_SELECTOR)
                if next_el:
                    url = await next_el.get_attribute("href")
                    if url and url.startswith("/"):
                        url = "https://studerendeonline.dk" + url
                else:
                    url = None

        finally:
            await context.close()

        print(f"[studerendeonline] Done. Collected {len(jobs)} jobs.")
        return jobs

    async def _dismiss_cookies(self, page) -> None:
        """Dismiss the Cookiebot consent banner if it appears."""
        selector = "#cookieAccept"
        try:
            btn = await page.wait_for_selector(selector, timeout=5_000)
            if btn:
                await btn.click()
                print("[studerendeonline] Cookie popup dismissed.")
                await page.wait_for_load_state("domcontentloaded")
        except Exception:
            pass  # No popup — continue normally

    async def _safe_inner_text_el(self, parent, selector: str) -> str:
        """inner_text of first matching child element, or empty string."""
        try:
            el = await parent.query_selector(selector)
            if el:
                return (await el.inner_text()).strip()
        except Exception:
            pass
        return ""

    async def _fetch_description(self, page, url: str) -> str:
        """Navigate to a job detail page and extract the description text."""
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            await self._screenshot(page, "debug_so_detail.png")
            text = await self._safe_inner_text(page, _DESCRIPTION_SELECTOR, timeout=8_000)
            if not text:
                # Fallback: grab all visible body text
                text = await page.inner_text("body")
            return text
        except Exception as e:
            print(f"[studerendeonline] Failed to fetch {url}: {e}")
            return ""
