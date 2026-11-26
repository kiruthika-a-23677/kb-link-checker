# Changelog

All notable changes to the **KB Link Checker** project are documented here.

---

## Milestone 1 - Project Setup & Discovery
**Date:** 12-Aug-2026

### 🎯 Objective
Build the project foundation and discover all Knowledge Base articles.

### ✅ Completed

#### Project Setup
- Created project structure
- Configured Python virtual environment
- Installed Playwright
- Installed Chromium browser
- Organized project into separate modules

#### Project Architecture
Created the following modules:
- `config.py`
- `selectors.py`
- `crawler.py`
- `discovery.py`
- `validator.py`
- `reporter.py`
- `main.py`

#### Browser Automation
- Implemented Playwright browser launcher
- Added browser open and close functionality
- Added generic page navigation
- Centralized configuration in `config.py`

#### Folder Discovery
- Implemented folder discovery from OneAuth KB homepage
- Successfully discovered all **7** folders

| Folder | Status |
|---------|--------|
| Get started | ✅ |
| Secure Zoho account with MFA | ✅ |
| Secure non-Zoho accounts with 2FA | ✅ |
| Use OneAuth on smartwatches | ✅ |
| Security in OneAuth | ✅ |
| FAQs | ✅ |
| Troubleshooting | ✅ |

#### Article Discovery
Implemented logic to handle two folder types:

- Single article folders
- Multi-article folders

Successfully discovered all **23** articles.

| Folder | Articles |
|---------|---------:|
| Get started | 1 |
| Secure Zoho account with MFA | 7 |
| Secure non-Zoho accounts with 2FA | 8 |
| Use OneAuth on smartwatches | 1 |
| Security in OneAuth | 2 |
| FAQs | 2 |
| Troubleshooting | 2 |
| **Total** | **23** |

### 🏗 Current Architecture

```
main.py
    │
    ▼
crawler.py
    │
    ▼
discovery.py
```

### 📌 Pending

- Extract hyperlinks from article content
- Validate internal links
- Validate external links
- Detect broken links
- Detect redirects
- Generate CSV reports
- Generate Excel report
- Add logging
- Add screenshots for failed pages (optional)

---

## Upcoming Milestone 2 - Link Validation

### Planned Work

- Build `validator.py`
- Extract hyperlinks from each article
- Validate URLs
- Capture HTTP status codes
- Store validation results

Expected output:

- `validation_results.csv`
- `broken_links.csv`

---

## Upcoming Milestone 3 - Reporting

### Planned Work

- Build `reporter.py`
- Generate Excel report
- Summary statistics
- Broken link dashboard