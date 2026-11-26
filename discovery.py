import re
from urllib.parse import urljoin, urlsplit, urlunsplit

from config import BASE_URL
from kb_selectors import (
    FOLDER_SELECTOR,
    ARTICLE_CONTENT_SELECTOR,
)


class Discovery:
    def __init__(self, crawler):
        self.crawler = crawler
        self.seen_folders = set()
        self.seen_articles = set()

    # --------------------------------------------------
    # Normalize URLs without discarding query parameters
    # --------------------------------------------------

    def normalize_url(self, url):
        parts = urlsplit(url)
        return urlunsplit((
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/"),
            parts.query,
            "",
        ))

    # --------------------------------------------------
    # Get folders from current page
    # --------------------------------------------------

    def get_folder_links(self, parent_name=""):
        try:
            self.crawler.wait_for_selector(
                FOLDER_SELECTOR,
                timeout=10000,
            )
        except Exception:
            # A page without child-folder links may itself be the folder
            # listing. Do not abort discovery just because this selector
            # is absent on that page.
            return []

        links = self.crawler.page.locator(FOLDER_SELECTOR)
        folders = []

        for i in range(links.count()):
            link = links.nth(i)
            href = link.get_attribute("href")

            if not href:
                continue

            name = link.inner_text().strip()
            if not name:
                continue

            url = urljoin(self.crawler.page.url or BASE_URL, href)

            if (
                urlsplit(url).netloc.lower()
                != urlsplit(BASE_URL).netloc.lower()
            ):
                continue

            normalized_url = self.normalize_url(url)
            if normalized_url in self.seen_folders:
                continue

            self.seen_folders.add(normalized_url)
            full_name = (
                f"{parent_name} > {name}" if parent_name else name
            )

            folders.append({"name": full_name, "url": url})

        return folders

    # --------------------------------------------------
    # Discover folders recursively
    # --------------------------------------------------

    def discover_folders(self):
        all_folders = []
        pending_folders = self.get_folder_links()

        # If the entered URL is itself a folder, scan it directly.
        if not pending_folders:
            current_url = self.crawler.page.url
            path_parts = urlsplit(current_url).path.strip("/").split("/")
            folder_name = (
                path_parts[-1].replace("-", " ").title()
                if path_parts and path_parts[-1]
                else "Knowledge Base"
            )

            print("\n[DISCOVERY] No child folders found.")
            print(
                f"[DISCOVERY] Treating entered URL as folder: {folder_name}"
            )

            self.seen_folders.add(self.normalize_url(current_url))
            return [{"name": folder_name, "url": current_url}]

        while pending_folders:
            folder = pending_folders.pop(0)
            all_folders.append(folder)

            print(f"\n[DISCOVERY] Folder found: {folder['name']}")

            try:
                self.crawler.open(folder["url"])
                nested_folders = self.get_folder_links(folder["name"])

                if nested_folders:
                    print(
                        f"[DISCOVERY] {len(nested_folders)} nested folder(s) found."
                    )
                    pending_folders.extend(nested_folders)

            except Exception as e:
                print(
                    f"[DISCOVERY] Unable to inspect nested folders "
                    f"inside '{folder['name']}': {e}"
                )

        print(
            f"\n[DISCOVERY] Total unique folders found: {len(all_folders)}"
        )
        return all_folders

    # --------------------------------------------------
    # Collect articles from current listing page
    # --------------------------------------------------

    def collect_page_articles(self, folder):
        articles = []
        anchors = self.crawler.page.locator("a[href*='/articles/']")

        print(f"[DEBUG] Article anchors detected: {anchors.count()}")

        for i in range(anchors.count()):
            anchor = anchors.nth(i)

            try:
                # Use the browser-resolved href. This preserves the complete
                # URL, including query strings, when present in the DOM.
                url = anchor.evaluate("element => element.href")
            except Exception:
                href = anchor.get_attribute("href")
                if not href:
                    continue
                url = urljoin(self.crawler.page.url or BASE_URL, href.strip())

            if not url:
                continue

            parts = urlsplit(url)
            if parts.scheme.lower() not in ("http", "https"):
                continue

            # Remove only the fragment. Keep the query string intact.
            url = urlunsplit((
                parts.scheme,
                parts.netloc,
                parts.path,
                parts.query,
                "",
            ))

            normalized_url = self.normalize_url(url)
            if normalized_url in self.seen_articles:
                print(f"[DEBUG] Skipping previously discovered: {url}")
                continue

            title = anchor.inner_text().strip()
            if not title:
                title = (
                    anchor.get_attribute("aria-label")
                    or anchor.get_attribute("title")
                    or url.rstrip("/").split("/")[-1]
                    or "Untitled article"
                ).strip()

            self.seen_articles.add(normalized_url)
            articles.append({
                "folder": folder["name"],
                "title": title,
                "url": url,
            })

        print(
            f"[DEBUG] New articles collected on this page: {len(articles)}"
        )
        return articles

    # --------------------------------------------------
    # Find Next pagination control
    # --------------------------------------------------

    def find_next_button(self):
        candidates = self.crawler.page.locator("a, button")

        for i in range(candidates.count()):
            candidate = candidates.nth(i)
            try:
                if not candidate.is_visible():
                    continue

                text = candidate.inner_text().strip()
                if not re.match(
                    r"^next(?:\b|\s|>|›|→)",
                    text,
                    re.IGNORECASE,
                ):
                    continue

                aria_disabled = candidate.get_attribute("aria-disabled")
                disabled = candidate.get_attribute("disabled")
                class_name = (
                    candidate.get_attribute("class") or ""
                ).lower()

                if aria_disabled == "true":
                    continue
                if disabled is not None:
                    continue
                if "disabled" in class_name:
                    continue

                return candidate
            except Exception:
                continue

        return None

    # --------------------------------------------------
    # Discover articles across listing pages
    # --------------------------------------------------

    def discover_articles(self, folder):
        self.crawler.open(folder["url"])
        articles = []
        current_url = self.crawler.page.url

        # Folder URL may directly open an article.
        if "/articles/" in current_url.lower():
            normalized_url = self.normalize_url(current_url)
            if normalized_url in self.seen_articles:
                return []

            title = self.clean_title(self.crawler.page.title())
            self.seen_articles.add(normalized_url)
            return [{
                "folder": folder["name"],
                "title": title,
                "url": current_url,
            }]

        page_number = 1
        visited_pages = set()

        while True:
            current_page_url = self.crawler.page.url
            normalized_page_url = self.normalize_url(current_page_url)

            if normalized_page_url in visited_pages:
                print(
                    "[DISCOVERY] Previously visited listing page. "
                    "Stopping pagination."
                )
                break

            visited_pages.add(normalized_page_url)
            print(
                f"\n[DISCOVERY] Reading listing page {page_number}: "
                f"{folder['name']}"
            )

            self.crawler.wait_for_selector(
                "a[href*='/articles/']",
                timeout=15000,
            )
            self.crawler.page.wait_for_timeout(1000)

            page_articles = self.collect_page_articles(folder)
            articles.extend(page_articles)
            print(
                f"[DISCOVERY] Articles collected on page {page_number}: "
                f"{len(page_articles)}"
            )

            next_button = self.find_next_button()
            if next_button is None:
                print("[DISCOVERY] No enabled Next button found.")
                break

            before_urls = {
                self.normalize_url(url)
                for url in self.crawler.page.locator(
                    "a[href*='/articles/']"
                ).evaluate_all("elements => elements.map(e => e.href)")
            }

            try:
                next_button.click(timeout=10000)
                self.crawler.page.wait_for_timeout(1500)

                after_urls = {
                    self.normalize_url(url)
                    for url in self.crawler.page.locator(
                        "a[href*='/articles/']"
                    ).evaluate_all("elements => elements.map(e => e.href)")
                }

                if before_urls == after_urls:
                    self.crawler.page.wait_for_timeout(2000)
                    after_urls = {
                        self.normalize_url(url)
                        for url in self.crawler.page.locator(
                            "a[href*='/articles/']"
                        ).evaluate_all(
                            "elements => elements.map(e => e.href)"
                        )
                    }

                if before_urls == after_urls:
                    print(
                        "[DISCOVERY] Listing did not change after clicking Next."
                    )
                    break

                page_number += 1

            except Exception as e:
                print(f"[DISCOVERY] Pagination failed: {e}")
                break

        print(
            f"\n[DISCOVERY] Total articles found in '{folder['name']}': "
            f"{len(articles)}"
        )
        return articles

    # --------------------------------------------------
    # Extract links from currently open article
    # --------------------------------------------------

    def extract_article_links(self):
        self.crawler.wait_for_selector(
            ARTICLE_CONTENT_SELECTOR,
            timeout=15000,
        )

        content = self.crawler.page.locator(ARTICLE_CONTENT_SELECTOR)
        if content.count() == 0:
            return []

        anchors = content.locator("a[href]")
        links = []
        seen = set()

        for i in range(anchors.count()):
            anchor = anchors.nth(i)

            try:
                # element.href returns the fully resolved URL and retains
                # query parameters such as ?id=com.zoho.accounts.oneauth.
                url = anchor.evaluate("element => element.href")
            except Exception:
                href = anchor.get_attribute("href")
                if not href:
                    continue
                url = urljoin(self.crawler.page.url or BASE_URL, href.strip())

            if not url:
                continue

            url = url.strip()
            parts = urlsplit(url)

            if parts.scheme.lower() not in ("http", "https"):
                continue

            # Remove the fragment only. Never strip the query string.
            url = urlunsplit((
                parts.scheme,
                parts.netloc,
                parts.path,
                parts.query,
                "",
            ))

            if "/kb/tags/" in url.lower():
                continue

            normalized_url = self.normalize_url(url)
            if normalized_url in seen:
                continue

            text = anchor.inner_text().strip()
            if not text:
                text = (
                    anchor.get_attribute("aria-label")
                    or anchor.get_attribute("title")
                    or url
                       ).strip()

            seen.add(normalized_url)
            links.append({
                "text": text,
                "url": url,
            })
            print(f"[LINK EXTRACTED] {text}: {url}")

        return links

    # --------------------------------------------------
    # Clean article title
    # --------------------------------------------------

    def clean_title(self, title):
        if not title:
            return ""

        title = title.strip()
        suffixes = (
            " | OneAuth",
            " | Accounts",
            " - OneAuth",
        )

        for suffix in suffixes:
            if title.endswith(suffix):
                title = title[:-len(suffix)].strip()
                break

        return title
