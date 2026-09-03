#!/usr/bin/env python3
"""One-off diagnostic: does the track-filtered submissions gallery on the
main hackathon page (as opposed to /live) expose more than 50 items?

Usage: python3 test_track_gallery.py
"""
import re
import sys
from playwright.sync_api import sync_playwright

URL = "https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon?track=options-alpha-agents#submissions"
SLUG = "alpaca-ai-trading-agents-hackathon"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(user_agent=(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ))
    page.goto(URL, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(3000)

    pattern = re.compile(rf"/ai-hackathons/{re.escape(SLUG)}/[^/]+/[^/?#]+/?$")

    def count():
        hrefs = page.eval_on_selector_all(
            "a[href*='/ai-hackathons/']",
            "els => els.map(e => e.getAttribute('href'))",
        )
        return len({h for h in hrefs if h and pattern.search(h)})

    print(f"Initial count on track gallery: {count()}", file=sys.stderr)

    # Try clicking any Load more found here too, same as the /live page.
    clicks = 0
    for _ in range(30):
        clicked = False
        for sel in ["text=Load more", "button:has-text('Load more')"]:
            btn = page.locator(sel).first
            try:
                if btn.is_visible(timeout=1000):
                    btn.scroll_into_view_if_needed()
                    btn.click(timeout=5000, force=True)
                    clicks += 1
                    clicked = True
                    page.wait_for_timeout(1200)
                    break
            except Exception:
                continue
        if not clicked:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1000)

    print(f"Clicks: {clicks}", file=sys.stderr)
    print(f"Final count on track gallery: {count()}", file=sys.stderr)

    browser.close()
