# lablab.ai hackathon repo archiver

Grabs every submission from a lablab.ai hackathon page and creates a
standalone copy of each team's public GitHub repo under your own account.
Two steps, run wherever has internet access (your Oracle VM is fine —
lablab.ai isn't reachable from Claude's own sandbox, which is why this
is handed to you as a script rather than run automatically).

## 1. Scrape the submission list + GitHub links

```bash
pip install playwright
playwright install chromium
python3 scrape_submissions.py \
    --hackathon-url https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon \
    --out submissions.json
```

This clicks through every "Load more" on the /live results page (all
tracks), visits each submission's page, and pulls out the GitHub link if
one is listed. Check `submissions.json` afterwards — a handful of teams
may not have listed a GitHub link yet, or may have used a private repo
lablab can't see; those show up with `"github_url": null` and get
skipped in step 2.

## 2. Copy each repo into your own GitHub

```bash
export GITHUB_TOKEN=ghp_xxxxxxxx   # personal access token, 'repo' scope
python3 copy_to_github.py \
    --input submissions.json \
    --dest-owner irishkiwi007 \
    --dry-run          # remove this once the list looks right
```

Then drop `--dry-run` to actually run it. Add `--private` if you'd
rather these land as private repos than public ones. Each new repo is a
full standalone copy (bare clone + mirror push) — not a GitHub "fork" —
named `hackathon-<owner>-<repo>`, with a description pointing back at
the original repo and lablab submission page for attribution.

Since the hackathon runs through Sep 4, 2026 and new submissions keep
coming in, you can just re-run both scripts later — step 2 skips repos
it's already created and re-pushes to pick up any new commits from
teams still iterating.

## Note

These are all public repos on public GitHub — cloning and re-hosting
public code is fine mechanically, but if you ever publish or share
these copies beyond personal reference, keep the attribution in the
repo description (it's there by default) and check each repo's license
before reusing any of the code itself.
