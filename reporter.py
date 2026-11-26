import csv
import os
from collections import defaultdict


from config import (
    REPORT_FOLDER,
    ARTICLES_REPORT,
    VALIDATION_REPORT,
    RESULT_REPORT,
)


class Reporter:
    def __init__(self, report_folder=None, on_line=None):
        # on_line: optional callback(text) so a UI can mirror every log line.
        self.on_line = on_line
        self.report_folder = report_folder or REPORT_FOLDER
        os.makedirs(self.report_folder, exist_ok=True)

        self.result_path = os.path.join(self.report_folder, RESULT_REPORT)
        self.articles_path = os.path.join(self.report_folder, ARTICLES_REPORT)
        self.validation_path = os.path.join(self.report_folder, VALIDATION_REPORT)

        self.result_file = open(self.result_path, "w", encoding="utf-8")

    def write(self, text=""):
        print(text)
        if self.on_line:
            try:
                self.on_line(str(text))
            except Exception:
                pass
        if self.result_file and not self.result_file.closed:
            self.result_file.write(str(text) + "\n")
            self.result_file.flush()

    def close(self):
        if self.result_file and not self.result_file.closed:
            self.result_file.close()
        self.result_file = None

    def save_articles(self, articles):
        with open(self.articles_path, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(["Folder", "Article", "URL"])
            for article in articles:
                writer.writerow([
                    article.get("folder", ""),
                    article.get("title", ""),
                    article.get("url", ""),
                ])
        self.write(f"✓ {ARTICLES_REPORT} created")

    def save_validation_results(self, results, articles=None):
        with open(self.validation_path, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow([
                "Folder", "Article", "Link Text", "URL", "Status",
                "Classification", "Final URL", "Recommendation", "Reason",
            ])
            for result in results:
                writer.writerow([
                    result.get("folder", ""),
                    result.get("article", ""),
                    result.get("text", ""),
                    result.get("url", ""),
                    result.get("status", ""),
                    result.get("type", ""),
                    result.get("final_url", ""),
                    result.get("recommendation", ""),
                    result.get("error", ""),
                ])
        self.write(f"✓ {VALIDATION_REPORT} created")


    @staticmethod
    def _counts_for(results):
        valid = sum(1 for row in results if row.get("type") == "VALID")
        review = sum(1 for row in results if row.get("type") == "NEEDS REVIEW")
        return valid, review

    def write_link_status(self, result):
        if result.get("type") == "VALID":
            self.write(f"   ✅ [{result.get('status')}] VALID")
        else:
            self.write(f"   ⚠️ [{result.get('status')}] NEEDS REVIEW")
            if result.get("recommendation"):
                self.write(f"   💡 {result['recommendation']}")
            if result.get("error"):
                self.write(f"   Reason: {result['error']}")

    def print_final_summary(self, folders, articles, results, scan_interrupted=False):
        valid, review = self._counts_for(results)

        self.write("")
        self.write("=" * 70)
        self.write("KB HEALTH SUMMARY")
        self.write("=" * 70)
        self.write(f"Folders discovered       : {len(folders)}")
        self.write(f"Articles discovered      : {len(articles)}")
        self.write(f"Links checked            : {len(results)}")
        self.write(f"VALID                    : {valid}")
        self.write(f"NEEDS REVIEW             : {review}")

        # Per-folder and per-article roll-up.
        self.write("")
        self.write("FOLDER-WISE ARTICLE SUMMARY")
        self.write("-" * 70)

        results_by_article = defaultdict(list)
        for row in results:
            results_by_article[(row.get("folder", ""), row.get("article", ""))].append(row)

        for folder in folders:
            folder_name = folder.get("name", "")
            folder_articles = [a for a in articles if a.get("folder", "") == folder_name]
            folder_rows = [r for r in results if r.get("folder", "") == folder_name]
            f_valid, f_review = self._counts_for(folder_rows)
            self.write(f"\nFolder: {folder_name}")
            self.write(
                f"Articles: {len(folder_articles)} | "
                f"Links: {len(folder_rows)} | VALID: {f_valid} | "
                f"NEEDS REVIEW: {f_review}"
            )
            for article in folder_articles:
                key = (folder_name, article.get("title", ""))
                rows = results_by_article[key]
                a_valid, a_review = self._counts_for(rows)
                self.write(
                    f"  - {article.get('title', '')}: "
                    f"{len(rows)} links | VALID: {a_valid} | "
                    f"NEEDS REVIEW: {a_review}"
                )

        self.write("")
        self.write("Overall Health")
        self.write("-" * 15)
        if scan_interrupted:
            self.write("🟠 SCAN INCOMPLETE — Scan interrupted by user.")
        elif not articles or not results:
            self.write("⚪ PENDING — No articles or links were validated. Check the scan output.")
        elif review:
            self.write("🟡 ATTENTION REQUIRED")
        else:
            self.write("🟢 HEALTHY")
