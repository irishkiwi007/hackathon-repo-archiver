#!/usr/bin/env python3
"""
Scrape all submissions (all tracks) from a lablab.ai hackathon page and
extract each team's public GitHub repo URL.

Why Playwright and not requests: lablab.ai's submission list is a
client-rendered Next.js grid with a "Load more" button, so a plain HTTP
GET only returns the first page. Playwright drives a real headless
browser so we can click "Load more" until everything is loaded.

Usage:
    pip install playwright
    playwright install chromium
    python3 scrape_submissions.py \
        --hackathon-url https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon \
        --out submissions.json

Output: submissions.json, a list of:
    {
        "title": "...",
        "team": "...",
        "submission_url": "https://lablab.ai/ai-hackathons/.../<team>/<slug>",
        "github_url": "https://github.com/owner/repo" | null
    }
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

# Links that show up on lablab submission pages but aren't the project repo.
GITHUB_IGNORE_OWNERS = {"lablab-ai", "lablabai"}


def load_all_submissions(page, hackathon_url: str, max_rounds: int = 100):
    """Navigate to the /live results page and load every submission card.

    Handles both patterns: a "Load more" button, and plain infinite-scroll
    where scrolling to the bottom triggers more cards to load.
    """
    live_url = hackathon_url.rstrip("/") + "/live"
    page.goto(live_url, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(2000)

    print(f"  page title: {page.title()!r}", file=sys.stderr)

    load_more_selectors = [
        "text=Load more",
        "button:has-text('Load more')",
        "text=Load More",
    ]
    slug = hackathon_url.rstrip("/").split("/")[-1]
    pattern = re.compile(rf"/ai-hackathons/{re.escape(slug)}/[^/]+/[^/?#]+/?$")

    def count_matches():
        hrefs = page.eval_on_selector_all(
            "a[href*='/ai-hackathons/']",
            "els => els.map(e => e.getAttribute('href'))",
        )
        return {h for h in hrefs if h and pattern.search(h)}

    clicks = 0
    stale_rounds = 0
    prev_count = len(count_matches())
    for round_num in range(max_rounds):
        # A modal (headlessui portal) sometimes pops up -- e.g. after the
        # first Load more click -- and blocks all further clicks by
        # intercepting pointer events. Dismiss it before trying anything.
        try:
            if page.locator("#headlessui-portal-root").count() > 0:
                page.keyboard.press("Escape")
                page.wait_for_timeout(300)
                # Some modals need an explicit close click rather than Escape
                close_btn = page.locator(
                    "#headlessui-portal-root button[aria-label='Close'], "
                    "#headlessui-portal-root button:has-text('Close'), "
                    "#headlessui-portal-root [aria-label='close']"
                ).first
                if close_btn.count() > 0:
                    close_btn.click(timeout=1000)
                page.wait_for_timeout(300)
        except Exception:
            pass

        clicked = False
        for sel in load_more_selectors:
            btn = page.locator(sel).first
            try:
                cnt = btn.count()
                vis = btn.is_visible(timeout=1500) if cnt else False
                if round_num < 5:
                    print(f"    [{sel!r}] count={cnt} visible={vis}", file=sys.stderr)
                if vis:
                    btn.scroll_into_view_if_needed()
                    btn.click(timeout=5000, force=True)
                    clicks += 1
                    clicked = True
                    page.wait_for_timeout(1800)
                    break
            except Exception as e:
                print(f"    [{sel!r}] click attempt raised: {e}", file=sys.stderr)
                continue

        if not clicked:
            # No button found/clickable -- scroll all the way to the
            # actual current bottom of the page (not a fixed pixel
            # offset, since page height grows as more cards load).
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2000)

        new_count = len(count_matches())
        print(f"  round {round_num + 1}: {new_count} links "
              f"(clicked={clicked})", file=sys.stderr)
        if new_count > prev_count:
            prev_count = new_count
            stale_rounds = 0
        else:
            stale_rounds += 1
            if stale_rounds >= 8:
                break

    print(f"  clicked Load more {clicks} time(s); "
          f"{prev_count} unique submission links found", file=sys.stderr)
    if prev_count == 0:
        with open("debug_live_page.html", "w") as f:
            f.write(page.content())
        print("  saved debug_live_page.html for inspection", file=sys.stderr)

    return sorted(count_matches())


def extract_github_url(html: str):
    for owner, repo in GITHUB_RE.findall(html):
        if owner.lower() in GITHUB_IGNORE_OWNERS:
            continue
        repo = re.sub(r"\.git$", "", repo)
        return f"https://github.com/{owner}/{repo}"
    return None


def scrape(hackathon_url: str, out_path: str, args_limit: int = 0):
    results = []
    with sync_playwright() as p:
        # Phase 1: load the full submission list. Plain headless Chromium
        # works cleanly here -- no Cloudflare issue on this page, and
        # critically, a phantom popup that blocks "Load more" clicks only
        # shows up in a headed/real-Chrome browser, not headless.
        list_browser = p.chromium.launch(headless=True)
        list_page = list_browser.new_page(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        ))
        print("Loading submission list (clicking Load more)...", file=sys.stderr)
        rel_links = load_all_submissions(list_page, hackathon_url)
        print(f"Found {len(rel_links)} submissions.", file=sys.stderr)
        list_browser.close()

        # Phase 2: visit each submission page. This is where Cloudflare's
        # bot check bites, so use a real Chrome channel, headed, with
        # navigator.webdriver hidden.
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

        base = "https://lablab.ai"
        if args_limit:
            rel_links = rel_links[:args_limit]
            print(f"(limited to first {args_limit} for testing)", file=sys.stderr)
        for i, rel in enumerate(rel_links, 1):
            url = rel if rel.startswith("http") else base + rel
            print(f"[{i}/{len(rel_links)}] {url}", file=sys.stderr)
            html = None
            for attempt in range(2):
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    # Wait specifically for a github.com link to render, since
                    # it's injected client-side after initial page load. If
                    # none shows up within 8s, the submission likely just
                    # doesn't have one -- proceed and grab whatever loaded.
                    try:
                        page.wait_for_selector("a[href*='github.com']", timeout=8000)
                    except Exception:
                        page.wait_for_timeout(2000)
                    # If we landed on Cloudflare's interstitial, give it a
                    # few more seconds to auto-resolve, then re-check.
                    if "Just a moment" in page.title():
                        page.wait_for_timeout(6000)
                    title = page.title()
                    html = page.content()
                    gh_link_count = page.locator("a[href*='github.com']").count()
                    print(f"  github.com anchors found on page: {gh_link_count}", file=sys.stderr)
                    if gh_link_count == 0 and i == 1:
                        with open("debug_submission_page.html", "w") as dbg:
                            dbg.write(html)
                        print("  saved debug_submission_page.html", file=sys.stderr)
                    break
                except Exception as e:
                    print(f"  ! attempt {attempt + 1} failed: {e}", file=sys.stderr)
                    time.sleep(2)
            if html is None:
                results.append({
                    "title": None,
                    "team": None,
                    "submission_url": url,
                    "github_url": None,
                    "error": "timed out after retries",
                })
                continue
            gh = extract_github_url(html)
            team = rel.strip("/").split("/")[-2]
            results.append({
                "title": title,
                "team": team,
                "submission_url": url,
                "github_url": gh,
            })
            time.sleep(0.5)  # be polite

        browser.close()

    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

    with_gh = sum(1 for r in results if r.get("github_url"))
    print(f"\nDone. {with_gh}/{len(results)} submissions had a discoverable GitHub link.",
          file=sys.stderr)
    print(f"Wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--hackathon-url", required=True,
                     help="e.g. https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon")
    ap.add_argument("--out", default="submissions.json")
    ap.add_argument("--limit", type=int, default=0,
                     help="Only process the first N submissions (for testing)")
    args = ap.parse_args()
    scrape(args.hackathon_url, args.out, args.limit)
