import requests
from urllib.parse import urlparse

from url_safety import safe_get, UnsafeURL

from config import (
    REQUEST_TIMEOUT,
    FOLLOW_REDIRECTS,
    VERIFY_SSL,
    USER_AGENT,
)


class Validator:
    """Validate links using the original Requests + Playwright approach."""

    VALID = "VALID"
    NEEDS_REVIEW = "NEEDS REVIEW"

    def __init__(self, crawler=None):
        self.crawler = crawler
        self.interrupted = False

    # --------------------------------------------------
    # Identify internal Zoho KB article links
    # --------------------------------------------------

    def is_internal_kb_article(self, url):
        parsed = urlparse(url)

        return (
            parsed.hostname is not None
            and parsed.hostname.lower() == "help.zoho.com"
            and "/portal/en/kb/" in parsed.path.lower()
            and "/articles/" in parsed.path.lower()
        )

    # --------------------------------------------------
    # Verify URL using Playwright
    # --------------------------------------------------

    def browser_fallback(self, url):
        if self.crawler is None:
            return {
                "status": None,
                "final_url": "",
                "has_article_content": None,
                "error": "Playwright crawler was not provided.",
            }

        try:
            result = self.crawler.check_url_in_browser(url)
            return result or {
                "status": None,
                "final_url": "",
                "has_article_content": None,
                "error": "Browser verification returned no result.",
            }

        except Exception as exc:
            return {
                "status": None,
                "final_url": "",
                "has_article_content": None,
                "error": str(exc),
            }

    # --------------------------------------------------
    # Standard result builders
    # --------------------------------------------------

    def valid_result(self, status, final_url=""):
        return {
            "status": status,
            "type": self.VALID,
            "final_url": final_url or "",
            "recommendation": "No action.",
            "error": "",
        }

    def needs_review_result(
        self,
        status=None,
        reason="",
        recommendation=None,
        final_url="",
    ):
        return {
            "status": status,
            "type": self.NEEDS_REVIEW,
            "final_url": final_url or "",
            "recommendation": (
                recommendation or "Verify the destination manually."
            ),
            "error": reason or "Unable to confirm the destination.",
        }

    # --------------------------------------------------
    # Classify browser verification result
    # --------------------------------------------------

    def classify_browser_result(
        self,
        browser_result,
        require_article_content=False,
    ):
        status = browser_result.get("status")
        final_url = browser_result.get("final_url", "")
        has_article_content = browser_result.get("has_article_content")
        error = browser_result.get("error") or ""

        # Confirmed missing destination.
        if status in (404, 410):
            return self.needs_review_result(
                status=status,
                final_url=final_url,
                reason=f"HTTP {status}: the destination may no longer be available.",
                recommendation="Check the destination and update or remove the link if needed.",
            )

        # Successful browser response.
        if status is not None and 200 <= status < 300:
            # Internal Zoho KB articles must contain the article content
            # container. This also catches Zoho's custom 404 page when
            # that page is returned with HTTP 200.
            if require_article_content and has_article_content is not True:
                return self.needs_review_result(
                    status=status,
                    final_url=final_url,
                    reason=(
                        "The page responded successfully, but the expected "
                        "Zoho KB article content could not be verified."
                    ),
                    recommendation=(
                        "Open the article and verify its destination manually."
                    ),
                )

            return self.valid_result(status, final_url)

        if status is not None:
            reason = f"Browser returned HTTP {status}."
        else:
            reason = error or "Browser verification could not confirm the page."

        return self.needs_review_result(
            status=status,
            final_url=final_url,
            reason=reason,
            recommendation=(
                "Verify the destination manually; access restrictions or "
                "temporary failures may affect the check."
            ),
        )

    # --------------------------------------------------
    # Validate one URL
    # --------------------------------------------------

    def validate_link(self, url):
        is_internal = self.is_internal_kb_article(url)

        try:
            response = safe_get(
                url,
                timeout=REQUEST_TIMEOUT,
                follow_redirects=FOLLOW_REDIRECTS,
                verify=VERIFY_SSL,
                headers={"User-Agent": USER_AGENT},
            )

            status = response.status_code
            final_url = response.url

            # --------------------------------------------------
            # Internal Zoho KB articles
            # --------------------------------------------------
            # Keep the original behaviour: verify these in a real
            # browser and confirm the article content container.
            if is_internal:
                print(f"\n[INFO] Checking Zoho KB article: {url}")

                browser_result = self.browser_fallback(url)
                result = self.classify_browser_result(
                    browser_result,
                    require_article_content=True,
                )

                # Preserve the Requests final URL if the browser did not
                # provide one.
                if not result["final_url"]:
                    result["final_url"] = final_url

                print(f"[INFO] Zoho article result: {result['type']}")
                return result

            # --------------------------------------------------
            # 404/410: retry in browser before classification
            # --------------------------------------------------
            if status in (404, 410):
                print(
                    f"\n[INFO] HTTP {status}. "
                    f"Retrying in browser: {url}"
                )

                browser_result = self.browser_fallback(url)
                result = self.classify_browser_result(browser_result)

                if not result["final_url"]:
                    result["final_url"] = final_url

                return result

            # --------------------------------------------------
            # Successful external response
            # --------------------------------------------------
            if 200 <= status < 300:
                return self.valid_result(status, final_url)

            # --------------------------------------------------
            # Ambiguous responses: retry in browser
            # --------------------------------------------------
            if status in (400, 403, 429):
                print(
                    f"\n[INFO] HTTP {status}. "
                    f"Retrying in browser: {url}"
                )

                browser_result = self.browser_fallback(url)
                result = self.classify_browser_result(browser_result)

                if not result["final_url"]:
                    result["final_url"] = final_url

                if result["status"] is None:
                    result["status"] = status

                return result

            # --------------------------------------------------
            # Server-side errors
            # --------------------------------------------------
            if status >= 500:
                return self.needs_review_result(
                    status=status,
                    final_url=final_url,
                    reason=f"HTTP {status}: the server may be temporarily unavailable.",
                    recommendation=(
                        "Verify manually. The server may be temporarily unavailable."
                    ),
                )

            # Other HTTP errors.
            if status >= 400:
                return self.needs_review_result(
                    status=status,
                    final_url=final_url,
                    reason=f"HTTP {status}: the destination may be unavailable.",
                    recommendation="Check the destination and update or remove the link if needed.",
                )

            return self.needs_review_result(
                status=status,
                final_url=final_url,
                reason="Unexpected HTTP response.",
            )

        except UnsafeURL as exc:
            return self.needs_review_result(
                status=None,
                reason=str(exc),
                recommendation="Internal or private links cannot be checked.",
            )

        except (
            requests.exceptions.ProxyError,
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
        ) as exc:
            print(
                f"\n[INFO] Request failed. "
                f"Trying browser verification: {url}"
            )

            browser_result = self.browser_fallback(url)
            return self.classify_browser_result(
                browser_result,
                require_article_content=is_internal,
            )

        except requests.exceptions.RequestException as exc:
            return self.needs_review_result(
                status=None,
                reason=str(exc),
                recommendation="Verify the destination manually.",
            )

        except Exception as exc:
            return self.needs_review_result(
                status=None,
                reason=f"Validation could not be completed: {exc}",
                recommendation="Verify the destination manually.",
            )

    # --------------------------------------------------
    # Validate article links
    # --------------------------------------------------

    def validate_article(self, article):
        results = []
        self.interrupted = False

        try:
            for link in article.get("links", []):
                validation = self.validate_link(link["url"])

                results.append({
                    "folder": article.get("folder", ""),
                    "article": article.get("title", ""),
                    "text": link.get("text", ""),
                    "url": link["url"],
                    "status": validation["status"],
                    "type": validation["type"],
                    "final_url": validation.get("final_url", ""),
                    "recommendation": validation["recommendation"],
                    "error": validation["error"],
                })

        except KeyboardInterrupt:
            self.interrupted = True
            print(
                "\n[INTERRUPTED] Link validation stopped. "
                "Keeping completed results..."
            )

        return results

    # --------------------------------------------------
    # Validate all articles
    # --------------------------------------------------

    def validate_all_articles(self, articles):
        all_results = []

        for article in articles:
            all_results.extend(self.validate_article(article))

            if self.interrupted:
                break

        return all_results
