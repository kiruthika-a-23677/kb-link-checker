from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
    Error as PlaywrightError,
)

from kb_selectors import ARTICLE_CONTENT_SELECTOR

from config import (
    HEADLESS,
    WAIT_TIME,
    ELEMENT_TIMEOUT,
)


class KBCrawler:

    def __init__(self):

        self.playwright = sync_playwright().start()
        self.browser = None
        self.page = None

        self._launch_browser()

    # --------------------------------------------------
    # Launch browser and create page
    # --------------------------------------------------

    def _launch_browser(self):

        print("\n[DEBUG] Launching Chromium...")

        self.browser = self.playwright.chromium.launch(
            headless=HEADLESS
        )

        self.page = self.browser.new_page()

        self._register_page_events()

        print("[DEBUG] Chromium is ready.")

    # --------------------------------------------------
    # Register browser events
    # --------------------------------------------------

    def _register_page_events(self):

        self.browser.on(
            "disconnected",
            lambda: print(
                "\n[DEBUG] Chromium disconnected."
            )
        )

        self.page.on(
            "close",
            lambda: print(
                "\n[DEBUG] Browser page closed."
            )
        )

        self.page.on(
            "crash",
            lambda: print(
                "\n[DEBUG] Browser page crashed."
            )
        )

    # --------------------------------------------------
    # Check browser availability
    # --------------------------------------------------

    def is_available(self):

        return (
            self.browser is not None
            and self.browser.is_connected()
            and self.page is not None
            and not self.page.is_closed()
        )

    # --------------------------------------------------
    # Recover browser or page
    # --------------------------------------------------

    def recover(self):

        print("\n[DEBUG] Attempting browser recovery...")

        try:

            if (
                self.browser is None
                or not self.browser.is_connected()
            ):

                self._launch_browser()

            elif (
                self.page is None
                or self.page.is_closed()
            ):

                print(
                    "[DEBUG] Creating a replacement browser page..."
                )

                self.page = self.browser.new_page()

                self._register_page_events()

            if not self.is_available():

                raise RuntimeError(
                    "Browser recovery could not be completed."
                )

            print("[DEBUG] Browser recovery successful.")

            return True

        except Exception as e:

            print(
                f"[DEBUG] Browser recovery failed: {e}"
            )

            return False

    # --------------------------------------------------
    # Open URL with one recovery retry
    # --------------------------------------------------

    def open(self, url):

        for attempt in range(2):

            if not self.is_available():

                if not self.recover():
                    raise RuntimeError(
                        "Browser is unavailable. Recovery failed."
                    )

            try:

                print(
                    f"\n[DEBUG] Opening URL: {url}"
                )

                self.page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=30000,
                )

                self.page.wait_for_timeout(
                    WAIT_TIME
                )

                if not self.is_available():

                    raise RuntimeError(
                        "Browser closed after navigation."
                    )

                return

            except PlaywrightTimeoutError:

                print(
                    "[DEBUG] Navigation timed out."
                )

                if self.is_available():
                    return

                print(
                    "[DEBUG] Page closed during timeout."
                )

            except PlaywrightError as e:

                print(
                    f"[DEBUG] Playwright navigation error: {e}"
                )

            except Exception as e:

                print(
                    f"[DEBUG] Navigation error: {e}"
                )

                if self.is_available():
                    raise

            if attempt == 0:

                print(
                    "[DEBUG] Retrying navigation after recovery..."
                )

                if not self.recover():
                    raise RuntimeError(
                        f"Could not recover browser while opening: {url}"
                    )

            else:

                raise RuntimeError(
                    f"Unable to open URL after retry: {url}"
                )

    # --------------------------------------------------
    # Verify a URL using a temporary browser page
    # --------------------------------------------------

    
    
    
    def check_url_in_browser(self, url):

        temporary_page = None

        try:

            if (
                self.browser is None
                or not self.browser.is_connected()
            ):

                if not self.recover():
                    raise RuntimeError(
                        "Browser is unavailable for link verification."
                    )

            print(
                f"[DEBUG] Browser fallback: {url}"
            )

            temporary_page = self.browser.new_page()

            response = temporary_page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=25000,
            )

            if response is None:

                return {
                    "status": None,
                    "final_url": temporary_page.url,
                    "has_article_content": None,
                    "error": "Browser navigation returned no HTTP response.",
                }

            # Wait briefly for client-side rendering.
            temporary_page.wait_for_timeout(2000)

            article_content = temporary_page.locator(
                ARTICLE_CONTENT_SELECTOR
            )

            try:

                article_content.wait_for(
                    state="visible",
                    timeout=5000,
                )

                has_article_content = True

            except PlaywrightTimeoutError:

                has_article_content = False

            return {
                "status": response.status,
                "final_url": temporary_page.url,
                "has_article_content": has_article_content,
                "error": "",
            }

        except PlaywrightTimeoutError as e:

            return {
                "status": None,
                "final_url": (
                    temporary_page.url
                    if temporary_page and not temporary_page.is_closed()
                    else ""
                ),
                "has_article_content": None,
                "error": f"Browser verification timed out: {e}",
            }

        except Exception as e:

            return {
                "status": None,
                "final_url": "",
                "has_article_content": None,
                "error": str(e),
            }

        finally:

            if (
                temporary_page is not None
                and not temporary_page.is_closed()
            ):

                try:
                    temporary_page.close()

                except Exception:
                    pass

    # --------------------------------------------------
    # Wait for an element
    # --------------------------------------------------

    def wait_for_selector(
        self,
        selector,
        timeout=ELEMENT_TIMEOUT,
    ):

        if not self.is_available():

            if not self.recover():
                return False

        try:

            self.page.wait_for_selector(
                selector,
                timeout=timeout,
            )

            return True

        except PlaywrightTimeoutError:

            return False

        except PlaywrightError as e:

            print(
                f"[DEBUG] Selector wait failed: {e}"
            )

            return False

    # --------------------------------------------------
    # Go back
    # --------------------------------------------------

    def back(self):

        if not self.is_available():

            if not self.recover():
                raise RuntimeError(
                    "Browser unavailable during back navigation."
                )

        try:

            self.page.go_back(
                wait_until="domcontentloaded",
                timeout=30000,
            )

            self.page.wait_for_timeout(
                WAIT_TIME
            )

        except PlaywrightTimeoutError:

            print(
                "[DEBUG] Back navigation timed out."
            )

        except PlaywrightError as e:

            print(
                f"[DEBUG] Back navigation failed: {e}"
            )

            if not self.recover():
                raise

    # --------------------------------------------------
    # Close browser
    # --------------------------------------------------

    def close(self):

        print(
            "\n[DEBUG] Starting browser cleanup..."
        )

        try:

            if (
                self.browser is not None
                and self.browser.is_connected()
            ):

                self.browser.close()

        except Exception as e:

            print(
                f"[DEBUG] Browser cleanup warning: {e}"
            )

        finally:

            if self.playwright is not None:

                try:
                    self.playwright.stop()

                except Exception as e:

                    print(
                        f"[DEBUG] Playwright cleanup warning: {e}"
                    )

        print(
            "[DEBUG] Browser cleanup completed."
        )