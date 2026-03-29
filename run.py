"""
CLI entry point for the job market tracker.

Usage:
    python run.py scrape                      # scrape all sites
    python run.py scrape --site jobteaser     # scrape one site
    python run.py scrape --site studerendeonline
    python run.py dashboard                   # launch Streamlit
"""
import argparse
import asyncio
import subprocess
import sys
from datetime import datetime

from playwright.async_api import async_playwright
from sqlalchemy import select

import config
from extractor.matcher import extract_skills
from scrapers.jobteaser import JobTeaserScraper
from scrapers.studerendeonline import StuderendeOnlineScraper
from storage.db import init_db, get_session
from storage.models import Job, JobSkill


async def run_scrape(site: str | None):
    init_db()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=config.HEADLESS,
            slow_mo=100 if not config.HEADLESS else 0,
            args=["--disable-features=Translate"],
        )
        try:
            scrapers = []
            if site in (None, "studerendeonline"):
                scrapers.append(StuderendeOnlineScraper(browser))
            if site in (None, "jobteaser"):
                scrapers.append(JobTeaserScraper(browser))

            all_jobs: list[dict] = []
            for scraper in scrapers:
                jobs = await scraper.scrape()
                all_jobs.extend(jobs)
        finally:
            await browser.close()

    new_count = 0
    skill_count = 0

    with get_session() as session:
        for job_data in all_jobs:
            # Check if this URL already exists
            existing = session.execute(
                select(Job).where(Job.url == job_data["url"])
            ).scalar_one_or_none()

            if existing:
                continue  # Skip duplicates

            job = Job(
                site=job_data["site"],
                title=job_data["title"] or "(no title)",
                company=job_data.get("company") or "",
                url=job_data["url"],
                description=job_data.get("description") or "",
                scraped_at=datetime.utcnow(),
                processed=False,
            )
            session.add(job)
            session.flush()  # get job.id before extracting skills

            # Extract and store skills
            skills = extract_skills(job.description)
            for s in skills:
                session.add(JobSkill(
                    job_id=job.id,
                    skill_name=s["skill"],
                    category=s["category"],
                ))
            job.processed = True
            new_count += 1
            skill_count += len(skills)

    print(f"\nScrape complete.")
    print(f"  New jobs inserted : {new_count}")
    print(f"  Duplicate URLs skipped: {len(all_jobs) - new_count}")
    print(f"  Skill records created : {skill_count}")


def cmd_scrape(args):
    asyncio.run(run_scrape(args.site))


def cmd_dashboard(_args):
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", "dashboard/app.py"],
        check=True,
    )


def main():
    parser = argparse.ArgumentParser(description="Job market tracker")
    sub = parser.add_subparsers(dest="command", required=True)

    scrape_parser = sub.add_parser("scrape", help="Scrape job listings")
    scrape_parser.add_argument(
        "--site",
        choices=["jobteaser", "studerendeonline"],
        default=None,
        help="Scrape a single site (default: all)",
    )

    sub.add_parser("dashboard", help="Launch the Streamlit dashboard")

    args = parser.parse_args()
    if args.command == "scrape":
        cmd_scrape(args)
    elif args.command == "dashboard":
        cmd_dashboard(args)


if __name__ == "__main__":
    main()
