#!/usr/bin/env python3
"""Run this ONCE. Opens a real Chrome window to lablab.ai's login page.
Log in manually (however you normally do -- email, Google, etc.). Once
you're logged in and can see your account, come back to this terminal
and press Enter. This saves your session (cookies) to auth_state.json,
which scrape_submissions.py can then reuse so it's logged in too.
"""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, channel="chrome")
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://lablab.ai/api/auth/signin", wait_until="domcontentloaded")

    print("\nA browser window has opened.")
    print("Log into lablab.ai in that window (however you normally sign in).")
    print("Once you're fully logged in and can see your account/dashboard,")
    input("come back here and press Enter to continue...")

    context.storage_state(path="auth_state.json")
    print("\nSaved logged-in session to auth_state.json")
    print("You can now run scrape_submissions.py and it will use this login.")

    browser.close()
