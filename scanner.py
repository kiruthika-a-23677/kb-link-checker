"""Reusable scan flow shared by the CLI (main.py) and the web server (server.py).

run_scan() does the work that used to live in main(). Instead of only printing,
it reports progress through an optional ``emit(event_dict)`` callback so a UI
can render it live. A ``cancel`` object (anything with ``is_set()``, e.g.
threading.Event) lets the caller stop the scan between articles.
"""

import os
import time
import traceback
from urllib.parse import urlparse

from crawler import KBCrawler
from discovery import Discovery
from validator import Validator
from reporter import Reporter
from config import REPORT_FOLDER

SCOPE_FOLDER = "folder"    # KB / folder URL: all subfolders and their articles
SCOPE_ARTICLE = "article"  # one single article URL


class ScanCancelled(Exception):
    pass


class ScanLimit(Exception):
    """Raised when a safety limit (article count or time) is reached."""


def get_kb_name(kb_url):
    path_parts = urlparse(kb_url).path.strip("/").split("/")
    kb_name = path_parts[-1] if path_parts and path_parts[-1] else "kb"
    return "".join(
        char if char.isalnum() or char in ("-", "_") else "_"
        for char in kb_name
    ).lower()


def is_valid_url(kb_url):
    parsed = urlparse(kb_url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def save_reports(reporter, folders, articles, results, failed_articles,
                 failed_folders, scan_interrupted=False):
    """Save everything collected so far, including partial scan results."""
    reporter.write("")
    reporter.write("=" * 70)
    reporter.write("GENERATING REPORTS")
    reporter.write("=" * 70)

    reporter.save_articles(articles)
    reporter.save_validation_results(results)

    valid_count = sum(1 for row in results if row.get("type") == "VALID")
    review_count = sum(
        1 for row in results if row.get("type") == "NEEDS REVIEW"
    )

    reporter.write("")
    reporter.write("Validation aggregation check:")
    reporter.write(f"Total links collected: {len(results)}")
    reporter.write(f"VALID: {valid_count}")
    reporter.write(f"NEEDS REVIEW: {review_count}")
    reporter.write(f"Total classified: {valid_count + review_count}")

    reporter.write("")
    reporter.write("Scan Exceptions")
    reporter.write("-" * 20)
    reporter.write(f"Failed articles: {len(failed_articles)}")
    reporter.write(f"Failed folders: {len(failed_folders)}")

    for item in failed_articles:
        reporter.write(f"Article: {item['article']} ({item['folder']})")
        reporter.write(f"Error: {item['error']}")

    for item in failed_folders:
        reporter.write(f"Folder: {item['folder']}")
        reporter.write(f"Error: {item['error']}")

    reporter.print_final_summary(
        folders, articles, results, scan_interrupted=scan_interrupted,
    )

    reporter.write("")
    if scan_interrupted:
        reporter.write("SCAN INTERRUPTED BY USER")
        reporter.write(
            "Partial reports have been saved. Results include only "
            "the folders, articles, and links processed before interruption."
        )
    elif failed_articles or failed_folders:
        reporter.write("SCAN COMPLETED WITH EXCEPTIONS")
        reporter.write(
            "Some folders or articles could not be scanned. "
            "Check result.txt for details."
        )
    else:
        reporter.write("SCAN COMPLETED")

    reporter.write("")
    reporter.write("Generated files:")
    reporter.write(f"- {reporter.result_path}")
    reporter.write(f"- {reporter.articles_path}")
    reporter.write(f"- {reporter.validation_path}")


def run_scan(kb_url, scope=SCOPE_FOLDER, emit=None, cancel=None,
             report_root=REPORT_FOLDER, report_name=None,
             max_articles=None, max_seconds=None):
    """Run a scan and return a summary dict.

    Returned dict: state ("completed" | "completed_with_errors" |
    "cancelled" | "error"), counts, error message, report_dir.
    """
    emit = emit or (lambda event: None)

    started = time.time()
    processed = 0

    def cancelled():
        return bool(cancel and cancel.is_set())

    def check_limits():
        if max_seconds and time.time() - started > max_seconds:
            raise ScanLimit(f"time limit of {max_seconds // 60} min reached")
        if max_articles and processed >= max_articles:
            raise ScanLimit(f"limit of {max_articles} articles reached")

    crawler = None
    reporter = None
    all_articles, all_results = [], []
    failed_articles, failed_folders = [], []
    folders = []
    scan_interrupted = False
    limit_message = None
    scan_error = None
    report_dir = None

    try:
        kb_name = report_name or get_kb_name(kb_url)
        report_dir = os.path.join(report_root, kb_name)
        reporter = Reporter(
            report_dir,
            on_line=lambda text: emit({"type": "log", "text": text}),
        )

        reporter.write("=" * 70)
        reporter.write("KB LINK CHECKER")
        reporter.write("=" * 70)
        reporter.write(f"KB URL: {kb_url}")
        reporter.write(f"Scope: {scope}")
        reporter.write(f"Report folder: {report_dir}")

        emit({"type": "status", "stage": "starting"})
        crawler = KBCrawler()
        crawler.open(kb_url)

        discovery = Discovery(crawler)
        validator = Validator(crawler)

        def process_article(article):
            crawler.open(article["url"])
            article["url"] = crawler.page.url or article["url"]

            emit({
                "type": "article_start",
                "folder": article.get("folder", ""),
                "title": article.get("title", ""),
                "url": article["url"],
            })
            reporter.write(f"URL: {article['url']}")
            reporter.write("Traversing article for links...")

            links = discovery.extract_article_links()
            article["links"] = links
            reporter.write(f"Links found: {len(links)}")
            emit({
                "type": "article_links",
                "title": article.get("title", ""),
                "count": len(links),
            })

            results = validator.validate_article(article)
            all_results.extend(results)

            for number, result in enumerate(results, start=1):
                reporter.write(f"{number}. {result.get('text', '')}")
                reporter.write(f"   {result.get('url', '')}")
                reporter.write_link_status(result)
                # result["type"] is VALID / NEEDS REVIEW, so carry it as
                # "classification" and keep "type" for the event kind.
                emit({**result, "classification": result.get("type", ""),
                      "type": "link"})

            if not results:
                reporter.write("No links found.")

            if validator.interrupted:
                raise KeyboardInterrupt

        # ---------------- single article ----------------
        if scope == SCOPE_ARTICLE:
            emit({"type": "status", "stage": "scanning"})
            title = ""
            try:
                title = discovery.clean_title(crawler.page.title() or "")
            except Exception:
                pass
            article = {
                "folder": "Single article",
                "title": title or kb_url,
                "url": kb_url,
            }
            folders = [{"name": article["folder"], "url": kb_url}]
            all_articles.append(article)
            emit({"type": "folders", "count": 1,
                  "names": [article["folder"]]})
            emit({"type": "articles_found", "folder": article["folder"],
                  "count": 1, "total_so_far": 1})
            try:
                process_article(article)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                failed_articles.append({
                    "folder": article["folder"], "article": article["title"],
                    "url": article["url"], "error": str(exc),
                })
                reporter.write(f"Unable to process article: {exc}")
                emit({"type": "article_error", "title": article["title"],
                      "error": str(exc)})

        # ---------------- folder / whole KB ----------------
        else:
            emit({"type": "status", "stage": "discovering"})
            folders = discovery.discover_folders()
            reporter.write(f"Folders found: {len(folders)}")
            emit({"type": "folders", "count": len(folders),
                  "names": [f["name"] for f in folders]})
            emit({"type": "status", "stage": "scanning"})

            for folder_index, folder in enumerate(folders, start=1):
                if cancelled():
                    raise ScanCancelled()

                reporter.write("")
                reporter.write("=" * 70)
                reporter.write(f"Opening folder: {folder['name']}")
                reporter.write("=" * 70)
                emit({"type": "folder_start", "name": folder["name"],
                      "index": folder_index, "total": len(folders)})

                try:
                    articles = discovery.discover_articles(folder)
                except Exception as exc:
                    failed_folders.append(
                        {"folder": folder["name"], "error": str(exc)}
                    )
                    reporter.write(f"Unable to scan folder: {folder['name']}")
                    reporter.write(f"Error: {exc}")
                    emit({"type": "folder_error", "name": folder["name"],
                          "error": str(exc)})
                    continue

                all_articles.extend(articles)
                reporter.write(f"Articles found: {len(articles)}")
                emit({"type": "articles_found", "folder": folder["name"],
                      "count": len(articles),
                      "total_so_far": len(all_articles)})

                for index, article in enumerate(articles, start=1):
                    if cancelled():
                        raise ScanCancelled()
                    check_limits()

                    reporter.write("")
                    reporter.write("-" * 70)
                    reporter.write(
                        f"Opening article {index}: {article.get('title', '')}"
                    )
                    reporter.write("-" * 70)

                    processed += 1
                    try:
                        process_article(article)
                    except KeyboardInterrupt:
                        raise
                    except Exception as exc:
                        failed_articles.append({
                            "folder": article.get("folder", ""),
                            "article": article.get("title", ""),
                            "url": article.get("url", ""),
                            "error": str(exc),
                        })
                        reporter.write(
                            f"Unable to process article: "
                            f"{article.get('title', '')}"
                        )
                        reporter.write(f"Error: {exc}")
                        reporter.write("Continuing with the next article...")
                        emit({"type": "article_error",
                              "title": article.get("title", ""),
                              "error": str(exc)})

    except ScanLimit as exc:
        scan_interrupted = True
        limit_message = str(exc)
        message = f"[LIMIT] Scan stopped: {limit_message}. Saving partial reports..."
        print("\n" + message)
        if reporter:
            reporter.write(message)

    except (KeyboardInterrupt, ScanCancelled):
        scan_interrupted = True
        message = "[INTERRUPTED] Scan stopped. Saving partial reports..."
        print("\n" + message)
        if reporter:
            reporter.write(message)

    except Exception as exc:
        scan_error = f"{type(exc).__name__}: {exc}"
        if reporter:
            reporter.write("")
            reporter.write("SCAN ERROR")
            reporter.write(scan_error)
        else:
            print(f"\nSCAN ERROR: {scan_error}")
        print("\n========== COMPLETE ERROR TRACEBACK ==========")
        traceback.print_exc()
        print("================================================")

    finally:
        if reporter:
            try:
                save_reports(
                    reporter, folders, all_articles, all_results,
                    failed_articles, failed_folders,
                    scan_interrupted=scan_interrupted,
                )
            except Exception:
                print("\n[ERROR] Could not save one or more reports:")
                traceback.print_exc()
            finally:
                reporter.close()
        if crawler:
            try:
                crawler.close()
            except Exception:
                pass

    valid = sum(1 for r in all_results if r.get("type") == "VALID")
    review = sum(1 for r in all_results if r.get("type") == "NEEDS REVIEW")
    if scan_error:
        state = "error"
    elif limit_message:
        state = "limit_reached"
    elif scan_interrupted:
        state = "cancelled"
    elif failed_articles or failed_folders:
        state = "completed_with_errors"
    else:
        state = "completed"

    summary = {
        "state": state,
        "error": scan_error,
        "limit": limit_message,
        "folders": len(folders),
        "articles": len(all_articles),
        "links": len(all_results),
        "valid": valid,
        "needs_review": review,
        "failed_articles": len(failed_articles),
        "failed_folders": len(failed_folders),
        "report_dir": report_dir,
    }
    emit({"type": "done", "summary": summary})
    return summary
