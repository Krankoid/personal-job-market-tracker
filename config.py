import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent

DB_URL = f"sqlite:///{BASE_DIR / 'data' / 'jobs.db'}"
SKILLS_FILE = str(BASE_DIR / "extractor" / "skills.yaml")

SCRAPE_LIMIT = int(os.getenv("SCRAPE_LIMIT", "10"))
HEADLESS = os.getenv("HEADLESS", "true").lower() != "false"
DEBUG_SCREENSHOT = os.getenv("DEBUG_SCREENSHOT", "false").lower() == "true"

STUDERENDEONLINE_BASE_URL = "https://studerendeonline.dk/job/?key=&antikey=&cvtype=4&udd=24&amt=2&erf=31&andet=4&virk=&oprettet="
JOBTEASER_BASE_URL = "https://dtu.jobteaser.com"

JOBTEASER_EMAIL = os.getenv("JOBTEASER_EMAIL")
JOBTEASER_PASSWORD = os.getenv("JOBTEASER_PASSWORD")


def require_jobteaser_credentials():
    """Call this before running the JobTeaser scraper."""
    if not JOBTEASER_EMAIL or not JOBTEASER_PASSWORD:
        raise EnvironmentError(
            "Missing JobTeaser credentials. "
            "Set JOBTEASER_EMAIL and JOBTEASER_PASSWORD in your .env file."
        )
