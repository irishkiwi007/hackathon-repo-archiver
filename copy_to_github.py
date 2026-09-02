#!/usr/bin/env python3
"""
Read submissions.json (from scrape_submissions.py) and create a standalone
copy -- a brand new repo, not a GitHub "fork" -- of every listed GitHub repo
under your own GitHub account.

Method: bare clone the source repo, create an empty new repo via the GitHub
API, then `git push --mirror` into it. This preserves full history but has
no "forked from" relationship on GitHub -- it's an independent repo.

Setup:
    export GITHUB_TOKEN=ghp_xxx   # needs 'repo' scope
    pip install requests

Usage:
    python3 copy_to_github.py --input submissions.json --dest-owner irishkiwi007
    # add --dry-run first to see what it would do without creating anything
    # add --private to make the copies private (default: public)
    # add --prefix hackathon-2026- to prefix new repo names
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import requests

API = "https://api.github.com"


def slugify(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-")
    return re.sub(r"-{2,}", "-", s)[:90] or "repo"


def github_repo_exists(token, owner, repo):
    r = requests.get(f"{API}/repos/{owner}/{repo}",
                      headers={"Authorization": f"token {token}"})
    return r.status_code == 200


def create_repo(token, name, private, description):
    r = requests.post(
        f"{API}/user/repos",
        headers={"Authorization": f"token {token}",
                 "Accept": "application/vnd.github+json"},
        json={
            "name": name,
            "private": private,
            "description": description[:350],
            "auto_init": False,
        },
    )
    if r.status_code >= 300:
        raise RuntimeError(f"create_repo failed ({r.status_code}): {r.text}")
    return r.json()


def mirror_copy(source_url, dest_clone_url, token):
    tmp = tempfile.mkdtemp(prefix="hackcopy_")
    bare_dir = os.path.join(tmp, "repo.git")
    try:
        subprocess.run(["git", "clone", "--bare", source_url, bare_dir],
                        check=True, capture_output=True, text=True)
        # inject token into the destination URL for auth
        auth_url = dest_clone_url.replace("https://", f"https://{token}@")
        subprocess.run(["git", "push", "--mirror", auth_url],
                        cwd=bare_dir, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"git failed: {e.cmd}\nstdout: {e.stdout}\nstderr: {e.stderr}"
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="submissions.json")
    ap.add_argument("--dest-owner", required=True,
                     help="Your GitHub username or org to create copies under")
    ap.add_argument("--prefix", default="hackathon-")
    ap.add_argument("--private", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token and not args.dry_run:
        sys.exit("Set GITHUB_TOKEN in your environment (a PAT with 'repo' scope).")

    with open(args.input) as f:
        submissions = json.load(f)

    ok, skipped, failed = [], [], []

    for sub in submissions:
        gh = sub.get("github_url")
        title = sub.get("title") or sub.get("team") or "unknown"
        if not gh:
            print(f"SKIP (no github link): {title}")
            skipped.append(sub)
            continue

        owner_repo = gh.rstrip("/").split("github.com/")[-1]
        try:
            src_owner, src_repo = owner_repo.split("/")[:2]
        except ValueError:
            print(f"SKIP (bad github url {gh}): {title}")
            skipped.append(sub)
            continue

        if src_owner.lower() == args.dest_owner.lower():
            print(f"SKIP (it's your own repo already): {title}")
            skipped.append(sub)
            continue

        new_name = slugify(f"{args.prefix}{src_owner}-{src_repo}")
        desc = (f"Standalone archived copy of {gh} — {sub.get('team','')} — "
                f"submission: {sub.get('submission_url','')}")

        print(f"\n{title}\n  source: {gh}\n  new repo: {args.dest_owner}/{new_name}")

        if args.dry_run:
            continue

        if github_repo_exists(token, args.dest_owner, new_name):
            print("  already exists, skipping create (will still push/update)")
        else:
            try:
                create_repo(token, new_name, args.private, desc)
            except RuntimeError as e:
                print(f"  ! {e}")
                failed.append({**sub, "error": str(e)})
                continue

        dest_clone_url = f"https://github.com/{args.dest_owner}/{new_name}.git"
        try:
            mirror_copy(gh, dest_clone_url, token)
            print("  done.")
            ok.append({**sub, "new_repo": dest_clone_url})
        except RuntimeError as e:
            print(f"  ! {e}")
            failed.append({**sub, "error": str(e)})

    print(f"\n\nSummary: {len(ok)} copied, {len(skipped)} skipped (no repo link), "
          f"{len(failed)} failed.")
    if failed:
        print("Failed:")
        for f in failed:
            print(f"  - {f.get('title')}: {f.get('error')}")

    with open("copy_results.json", "w") as f:
        json.dump({"ok": ok, "skipped": skipped, "failed": failed}, f, indent=2)


if __name__ == "__main__":
    main()
