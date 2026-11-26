"""Terminal entry point. The web UI lives in server.py (same scan engine)."""

from scanner import run_scan, is_valid_url, SCOPE_FOLDER, SCOPE_ARTICLE


def get_kb_url():
    print("\n" + "=" * 70)
    print("             ZOHO KB LINK CHECKER")
    print("=" * 70)

    while True:
        kb_url = input("\nEnter the Zoho KB URL:\n> ").strip()
        if not kb_url:
            print("Please enter a KB URL to continue.")
            continue
        if not is_valid_url(kb_url):
            print(
                "Invalid URL. Enter a complete URL starting with "
                "https:// or http://."
            )
            continue
        return kb_url


def get_scope():
    while True:
        choice = input(
            "\nScope: [1] Folder / whole KB (with subfolders)  "
            "[2] Single article\n> "
        ).strip()
        if choice in ("", "1"):
            return SCOPE_FOLDER
        if choice == "2":
            return SCOPE_ARTICLE
        print("Enter 1 or 2.")


def main():
    run_scan(get_kb_url(), scope=get_scope())


if __name__ == "__main__":
    main()
