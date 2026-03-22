#!/usr/bin/env python3
"""Auto-detect ATS and add companies to your config.

Usage:
    python3 add_companies.py Figma Ramp Notion
    python3 add_companies.py "https://boards.greenhouse.io/stripe"
    python3 add_companies.py --list       # show current companies
    python3 add_companies.py --clear      # start fresh
"""

import json
import os
import re
import sys
import urllib.request
import urllib.error

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "companies.json")
REQUEST_TIMEOUT = 10
USER_AGENT = "Mozilla/5.0 (compatible; PMJobFetcher/1.0)"

# Patterns for careers page URLs
URL_PATTERNS = [
    (r"boards\.greenhouse\.io/([a-zA-Z0-9_-]+)", "greenhouse"),
    (r"greenhouse\.io/([a-zA-Z0-9_-]+)", "greenhouse"),
    (r"jobs\.lever\.co/([a-zA-Z0-9_-]+)", "lever"),
    (r"jobs\.ashbyhq\.com/([a-zA-Z0-9_-]+)", "ashby"),
]


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {
        "filters": {
            "title_keywords": [
                "Product Manager", "TPM", "Technical Program Manager",
                "Program Manager", "APM", "Associate Product Manager",
                "Group Product Manager", "Director of Product",
                "VP Product", "Head of Product", "Product Lead",
                "Product Director", "Chief Product Officer"
            ],
            "exclude_keywords": [
                "Production Manager", "Manufacturing",
                "Production Engineering", "Property Manager"
            ],
            "experience_levels": []
        },
        "companies": []
    }


def save_config(config):
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(config, f, indent=2)
    os.replace(tmp, CONFIG_FILE)


def parse_url(text):
    """Try to extract ATS + slug from a URL."""
    for pattern, ats in URL_PATTERNS:
        m = re.search(pattern, text)
        if m:
            return ats, m.group(1)
    return None, None


def probe_ats(slug):
    """Try all 3 ATS APIs to find which one works for this slug."""
    endpoints = [
        ("greenhouse", f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"),
        ("lever", f"https://api.lever.co/v0/postings/{slug}"),
        ("ashby", f"https://api.ashbyhq.com/posting-api/job-board/{slug}"),
    ]
    for ats, url in endpoints:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                data = json.loads(resp.read().decode())
                # Verify it actually has job data (not just a 200 with empty/error)
                if ats == "greenhouse" and isinstance(data, dict) and "jobs" in data:
                    return ats
                elif ats == "lever" and isinstance(data, list):
                    return ats
                elif ats == "ashby" and isinstance(data, dict) and "jobs" in data:
                    return ats
        except Exception:
            pass
    return None


def slug_from_name(name):
    """Convert a company name to a likely slug."""
    return re.sub(r"[^a-z0-9]+", "", name.lower().strip())


def already_exists(config, ats, slug):
    for c in config["companies"]:
        if c["ats"] == ats and c["slug"] == slug:
            return True
    return False


def add_company(config, name_or_url):
    """Add a single company. Returns (success, message)."""
    name_or_url = name_or_url.strip()
    if not name_or_url:
        return False, "Empty input"

    # Try URL first
    ats, slug = parse_url(name_or_url)
    if ats and slug:
        display_name = slug.replace("-", " ").title()
        if already_exists(config, ats, slug):
            return False, f"{display_name} already in your list"
        config["companies"].append({"name": display_name, "ats": ats, "slug": slug})
        return True, f"Added {display_name} ({ats})"

    # It's a company name — try to auto-detect
    name = name_or_url.strip()
    slug = slug_from_name(name)

    # Check if already there
    for c in config["companies"]:
        if c["slug"] == slug:
            return False, f"{name} already in your list"

    print(f"    Detecting ATS for {name}...", end=" ", flush=True)
    ats = probe_ats(slug)

    if ats:
        print(f"found on {ats}!")
        config["companies"].append({"name": name, "ats": ats, "slug": slug})
        return True, f"Added {name} ({ats})"

    # Try common slug variations
    variations = [
        slug,
        slug + "hq",
        slug + "-inc",
        slug.replace("ai", "-ai"),
        name.lower().replace(" ", "-"),
        name.lower().replace(" ", ""),
    ]
    seen_slugs = {slug}
    for var in variations:
        if var in seen_slugs:
            continue
        seen_slugs.add(var)
        ats = probe_ats(var)
        if ats:
            print(f"found on {ats} (as '{var}')!")
            config["companies"].append({"name": name, "ats": ats, "slug": var})
            return True, f"Added {name} ({ats}, slug: {var})"

    print("not found")
    return False, f"Could not find {name} on Greenhouse, Lever, or Ashby. Try pasting their careers page URL instead."


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 add_companies.py Figma Ramp Notion")
        print('  python3 add_companies.py "https://boards.greenhouse.io/stripe"')
        print("  python3 add_companies.py --list")
        print("  python3 add_companies.py --clear")
        sys.exit(0)

    config = load_config()

    if sys.argv[1] == "--list":
        if not config["companies"]:
            print("No companies configured yet. Run: python3 add_companies.py Stripe Figma Notion")
        else:
            print(f"Your companies ({len(config['companies'])}):\n")
            for c in config["companies"]:
                print(f"  {c['name']} ({c['ats']}, slug: {c['slug']})")
        return

    if sys.argv[1] == "--clear":
        config["companies"] = []
        save_config(config)
        print("Cleared all companies. Add new ones with: python3 add_companies.py Stripe Figma")
        return

    inputs = sys.argv[1:]
    added = 0
    failed = 0

    print(f"Adding {len(inputs)} companies...\n")
    for item in inputs:
        ok, msg = add_company(config, item)
        if ok:
            print(f"  OK: {msg}")
            added += 1
        else:
            print(f"  SKIP: {msg}")
            failed += 1

    save_config(config)
    print(f"\nDone! {added} added, {failed} skipped. Total: {len(config['companies'])} companies.")
    if added > 0:
        print("Run: python3 fetch_jobs.py")


if __name__ == "__main__":
    main()
