import os

# --------------------------------------------------
# KB configuration
# --------------------------------------------------

BASE_URL = "https://help.zoho.com"

KB_HOME = (
    "https://help.zoho.com/portal/en/kb/accounts/oneauth"
)

# --------------------------------------------------
# Browser settings
# --------------------------------------------------

# CLI keeps a visible browser by default; the web server sets KB_HEADLESS=1.
HEADLESS = os.environ.get("KB_HEADLESS", "0") == "1"

# Playwright wait_for_timeout() uses milliseconds
WAIT_TIME = 3000

# Maximum time to wait for selectors/elements
ELEMENT_TIMEOUT = 15000

# --------------------------------------------------
# HTTP settings
# --------------------------------------------------

REQUEST_TIMEOUT = 15

FOLLOW_REDIRECTS = True

VERIFY_SSL = True

USER_AGENT = (
    "Mozilla/5.0 "
    "(Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/142.0.0.0 Safari/537.36"
)

# --------------------------------------------------
# Reports
# --------------------------------------------------

REPORT_FOLDER = "reports"

ARTICLES_REPORT = "articles.csv"

VALIDATION_REPORT = "validation_results.csv"

RESULT_REPORT = "result.txt"