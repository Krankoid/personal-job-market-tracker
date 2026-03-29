"""
Scraper for dtu.jobteaser.com

Flow:
  1. Navigate to the DTU JobTeaser job offers page.
  2. Cloudflare challenge is auto-solved by Playwright's real Chromium.
  3. Click "Log in" and follow the DTU WAYF SSO redirect.
  4. Fill credentials, submit, handle post-login redirect.
  5. Paginate through job offers (URL query param ?page=N).
  6. Fetch each detail page and extract the description.

Run with HEADLESS=false on first use to visually verify the SSO flow.
"""
import config
from scrapers.base import BaseScraper

SITE_KEY = "jobteaser"

# JobTeaser job listing URL with part-time filter for Copenhagen
_LISTING_URL = (
    "https://dtu.jobteaser.com/en/job-offers"
    "?contract=part_time"
    "&localized_location=Copenhagen"
    "&location=Denmark%3A%3ARegion+Hovedstaden%3A%3A%3A%3ACopenhagen"
    "%3A%3AbG9jYWxpdHk6ZGs6Y2l0eTpaVXlwTkRtZGRhRjdaYlMyWkhvMWVGRjNpYjQ9"
    "&radius=30"
)

# CSS selectors — update if JobTeaser changes their markup
_LOGIN_BUTTON_SELECTOR = "button:has-text('Log in with your DTU account'), a:has-text('Log in with your DTU account')"
_USERNAME_SELECTOR = "input[placeholder='User'], input[name='username']"
_PASSWORD_SELECTOR = "input[placeholder='Adgangskode'], input[type='password']"
_JOB_CARD_SELECTOR = "article, [data-testid='job-card'], .job-offer-card, li.job-offer"
_TITLE_SELECTOR = "h2, h3, .job-title, [data-testid='job-title']"
_COMPANY_SELECTOR = ".company-name, .employer, [data-testid='company-name']"
_LINK_SELECTOR = "a"
_DESCRIPTION_SELECTOR = ".job-description, .description, article, main"
_CLOUDFLARE_TITLE = "Security checkup"


class AuthenticationError(Exception):
    pass


class JobTeaserScraper(BaseScraper):
    async def scrape(self) -> list[dict]:
        config.require_jobteaser_credentials()
        context, page = await self._get_page()
        jobs: list[dict] = []

        try:
            await self._login(page)
            jobs = await self._collect_jobs(page)
        finally:
            await context.close()

        print(f"[jobteaser] Done. Collected {len(jobs)} jobs.")
        return jobs

    async def _login(self, page):
        """Navigate to JobTeaser and complete DTU SSO login."""
        print("[jobteaser] Navigating to job listing page...")
        await page.goto(_LISTING_URL, wait_until="domcontentloaded", timeout=45_000)
        await self._wait_for_cloudflare(page)
        await self._screenshot(page, "debug_jt_start.png")

        # If we're already on the job offers page (session cookie), skip login
        if "job-offers" in page.url and await page.query_selector(_JOB_CARD_SELECTOR):
            print("[jobteaser] Already logged in.")
            return

        # Click the login button
        login_btn = await page.query_selector(_LOGIN_BUTTON_SELECTOR)
        if not login_btn:
            raise AuthenticationError(
                "Could not find login button on JobTeaser. "
                "Try HEADLESS=false to inspect the page."
            )
        await login_btn.click()
        await page.wait_for_load_state("domcontentloaded")
        await self._wait_for_cloudflare(page)
        await self._screenshot(page, "debug_jt_loginpage.png")

        # "Log in with your DTU account" takes us directly to the DTU login form
        # (no second WAYF selector needed — the form is already here)
        await self._wait_for_login_form(page)
        await self._screenshot(page, "debug_jt_form.png")

        # Fill credentials
        await page.fill(_USERNAME_SELECTOR, config.JOBTEASER_EMAIL)
        await page.fill(_PASSWORD_SELECTOR, config.JOBTEASER_PASSWORD)

        # Submit — press Enter rather than clicking the button (works on any login form)
        await page.keyboard.press("Enter")

        # Wait for post-login redirect
        try:
            await page.wait_for_load_state("networkidle", timeout=20_000)
        except Exception:
            pass
        await self._screenshot(page, "debug_jt_postlogin.png")

        # Detect MFA page
        page_text = await page.inner_text("body")
        mfa_keywords = ["two-factor", "2fa", "authenticator", "verification code", "one-time"]
        if any(kw in page_text.lower() for kw in mfa_keywords):
            raise AuthenticationError(
                "Multi-factor authentication (MFA) is required for this DTU account. "
                "MFA cannot be automated — please disable MFA for this account or "
                "handle it manually."
            )

        print("[jobteaser] Login successful.")

    async def _wait_for_cloudflare(self, page, timeout: int = 60_000):
        """Wait for Cloudflare challenge to resolve if present."""
        title = await page.title()
        if _CLOUDFLARE_TITLE.lower() in title.lower():
            print("\n[jobteaser] Cloudflare challenge detected!")
            print("[jobteaser] Please solve the challenge in the browser window, then wait...")
            try:
                await page.wait_for_function(
                    f"document.title.toLowerCase().indexOf('{_CLOUDFLARE_TITLE.lower()}') === -1",
                    timeout=timeout,
                )
                print("[jobteaser] Cloudflare challenge solved, continuing...")
            except Exception:
                print("[jobteaser] Warning: Cloudflare may not have resolved. Proceeding anyway.")

    async def _wait_for_login_form(self, page, timeout: int = 15_000):
        """Wait for a username input to appear (handles multi-step SSO redirects)."""
        try:
            await page.wait_for_selector(_USERNAME_SELECTOR, timeout=timeout)
        except Exception:
            raise AuthenticationError(
                "Login form did not appear after clicking DTU SSO. "
                "Run with HEADLESS=false to debug the SSO flow."
            )

    async def _collect_jobs(self, page) -> list[dict]:
        """Paginate through job listings and fetch each detail page."""
        jobs = []
        page_num = 1

        while page_num <= config.SCRAPE_LIMIT:
            url = f"{_LISTING_URL}&page={page_num}"
            print(f"[jobteaser] Fetching listing page {page_num}: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            await self._wait_for_cloudflare(page)

            # Wait for job cards or detect empty page
            try:
                await page.wait_for_selector(_JOB_CARD_SELECTOR, timeout=10_000)
            except Exception:
                print(f"[jobteaser] No job cards on page {page_num} — stopping pagination.")
                break

            await self._screenshot(page, f"debug_jt_listing_{page_num}.png")
            cards = await page.query_selector_all(_JOB_CARD_SELECTOR)
            if not cards:
                break

            card_data = []
            for card in cards:
                title = await self._safe_inner_text_el(card, _TITLE_SELECTOR)
                company = await self._safe_inner_text_el(card, _COMPANY_SELECTOR)
                link_el = await card.query_selector(_LINK_SELECTOR)
                href = await link_el.get_attribute("href") if link_el else None
                if not href:
                    continue
                if href.startswith("/"):
                    href = "https://dtu.jobteaser.com" + href
                card_data.append({"title": title, "company": company, "url": href})

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

            page_num += 1

        return jobs

    async def _safe_inner_text_el(self, parent, selector: str) -> str:
        try:
            el = await parent.query_selector(selector)
            if el:
                return (await el.inner_text()).strip()
        except Exception:
            pass
        return ""

    async def _fetch_description(self, page, url: str) -> str:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            await self._wait_for_cloudflare(page)
            await self._screenshot(page, "debug_jt_detail.png")
            # Wait for JS-rendered content
            try:
                await page.wait_for_selector(_DESCRIPTION_SELECTOR, timeout=8_000)
            except Exception:
                pass
            text = await self._safe_inner_text(page, _DESCRIPTION_SELECTOR, timeout=5_000)
            if not text:
                text = await page.inner_text("body")
            return text
        except Exception as e:
            print(f"[jobteaser] Failed to fetch {url}: {e}")
            return ""
