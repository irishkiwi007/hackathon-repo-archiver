#!/usr/bin/env python3
"""Check whether the /live page's raw HTML source (including the embedded
Next.js RSC data payload in <script> tags, not just rendered <a> links)
contains more submission team-slugs than what's actually rendered as
clickable cards. If Next.js ships the full dataset to the client and only
renders a subset, the extra data would still be sitting in the raw HTML
text even though it's not in a clickable link.
"""
import re
import sys
from playwright.sync_api import sync_playwright

SLUG = "alpaca-ai-trading-agents-hackathon"
LIVE_URL = f"https://lablab.ai/ai-hackathons/{SLUG}/live"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(user_agent=(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ))
    page.goto(LIVE_URL, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(3000)

    html = page.content()
    with open("live_full_source.html", "w") as f:
        f.write(html)

    # Search the RAW TEXT (not just rendered <a> tags) for any occurrence
    # of a team/submission slug pattern anywhere in the page source,
    # including inside embedded JSON script blobs.
    pattern = re.compile(rf"/ai-hackathons/{re.escape(SLUG)}/([a-z0-9\-]+)/([a-z0-9\-]+)")
    matches = pattern.findall(html)
    unique_pairs = sorted(set(matches))

    # Also count rendered clickable <a> links specifically, for comparison
    rendered_hrefs = page.eval_on_selector_all(
        "a[href*='/ai-hackathons/']",
        "els => els.map(e => e.getAttribute('href'))",
    )
    rendered_pattern = re.compile(rf"/ai-hackathons/{re.escape(SLUG)}/[^/]+/[^/?#]+/?$")
    rendered_unique = sorted({h for h in rendered_hrefs if h and rendered_pattern.search(h)})

    print(f"Team/submission-slug pairs found ANYWHERE in raw page text: {len(unique_pairs)}", file=sys.stderr)
    print(f"Team/submission links actually rendered as clickable <a>: {len(rendered_unique)}", file=sys.stderr)
    print(f"Saved full source to live_full_source.html ({len(html)} chars)", file=sys.stderr)

    if len(unique_pairs) > len(rendered_unique):
        print("\n>>> Found MORE in raw text than rendered! Extra ones:", file=sys.stderr)
        rendered_set = {tuple(r.strip("/").split("/")[-2:]) for r in rendered_unique}
        for team, sub in unique_pairs:
            if (team, sub) not in rendered_set:
                print(f"    {team}/{sub}", file=sys.stderr)
    else:
        print("\nNo extra ones found -- raw text matches rendered count exactly.", file=sys.stderr)

    browser.close()
