#!/usr/bin/env python3
"""
Take a manually-collected list of submission URLs (one per line, in
manual_links.txt) and visit each one to extract its GitHub repo link,
using the same real-Chrome + anti-detection setup that works reliably
against Cloudflare on individual submission pages.

Usage:
    python3 scrape_from_manual_links.py --input manual_links.txt --out submissions_all.json
"""
import argparse
import json
import re
import sys
import time

from playwright.sync_api import sync_playwright

GITHUB_RE = re.compile(
    r"https?://(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:[/?#\"'\s)]|$)"
)
GITHUB_IGNORE_OWNERS = {"lablab-ai", "lablabai"}


def extract_github_url(html: str):
    for owner, repo in GITHUB_RE.findall(html):
        if owner.lower() in GITHUB_IGNORE_OWNERS:
            continue
        repo = re.sub(r"\.git$", "", repo)
        return f"https://github.com/{owner}/{repo}"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="manual_links.txt")
    ap.add_argument("--out", default="submissions_all.json")
    args = ap.parse_args()

    with open(args.input) as f:
        urls = [line.strip() for line in f if line.strip()]

    # Skip a team's own "/submission" edit-page link -- not a real project.
    urls = [u for u in urls if not u.rstrip("/").endswith("/submission")]
    urls = sorted(set(urls))
    print(f"{len(urls)} submission URLs to process", file=sys.stderr)

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 900},
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = context.new_page()

        for i, url in enumerate(urls, 1):
            print(f"[{i}/{len(urls)}] {url}", file=sys.stderr)
            html = None
            for attempt in range(2):
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    try:
                        page.wait_for_selector("a[href*='github.com']", timeout=8000)
                    except Exception:
                        page.wait_for_timeout(2000)
                    if "Just a moment" in page.title():
                        page.wait_for_timeout(6000)
                    title = page.title()
                    html = page.content()
                    gh_link_count = page.locator("a[href*='github.com']").count()
                    print(f"  github.com anchors found on page: {gh_link_count}", file=sys.stderr)
                    break
                except Exception as e:
                    print(f"  ! attempt {attempt + 1} failed: {e}", file=sys.stderr)
                    time.sleep(2)
            if html is None:
                results.append({
                    "title": None, "team": None, "submission_url": url,
                    "github_url": None, "error": "timed out after retries",
                })
                continue
            gh = extract_github_url(html)
            parts = url.rstrip("/").split("/")
            team = parts[-2] if len(parts) >= 2 else None
            results.append({
                "title": title, "team": team,
                "submission_url": url, "github_url": gh,
            })
            time.sleep(0.5)

        browser.close()

    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)

    with_gh = sum(1 for r in results if r.get("github_url"))
    print(f"\nDone. {with_gh}/{len(results)} submissions had a discoverable GitHub link.",
          file=sys.stderr)
    print(f"Wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
