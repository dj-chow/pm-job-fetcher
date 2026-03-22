#!/usr/bin/env python3
"""PM Job Fetcher — Find product management jobs across 50+ companies."""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import date

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(SCRIPT_DIR, "companies.json")
SETTINGS_FILE = os.path.join(SCRIPT_DIR, "settings.json")
SEEN_JOBS_FILE = os.path.join(SCRIPT_DIR, "seen_jobs.json")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
REQUEST_TIMEOUT = 15
DELAY_BETWEEN_REQUESTS = 0.5
USER_AGENT = "Mozilla/5.0 (compatible; PMJobFetcher/1.0)"


# --- Config ---

def load_config(path):
    if not os.path.exists(path):
        print(f"Error: Config file not found: {path}")
        sys.exit(1)
    with open(path, "r") as f:
        config = json.load(f)
    errors = []
    if "filters" not in config:
        errors.append("Missing 'filters' key")
    else:
        if "title_keywords" not in config["filters"] or not config["filters"]["title_keywords"]:
            errors.append("'filters.title_keywords' must be a non-empty list")
        if "exclude_keywords" not in config["filters"]:
            errors.append("Missing 'filters.exclude_keywords'")
    if "companies" not in config or not config["companies"]:
        errors.append("'companies' must be a non-empty list")
    else:
        VALID_ATS = ("greenhouse", "lever", "ashby", "workday", "workable",
                     "smartrecruiters", "rippling", "shopify", "dayforce", "zoho_recruit")
        for i, c in enumerate(config["companies"]):
            for key in ("name", "ats", "slug"):
                if key not in c:
                    errors.append(f"Company #{i} missing '{key}'")
            if c.get("ats") not in VALID_ATS:
                errors.append(f"Company '{c.get('name', i)}': ats must be one of {VALID_ATS}")
            if c.get("ats") == "workday" and not c.get("workday_board"):
                errors.append(f"Company '{c.get('name', i)}': workday ats requires 'workday_board'")
    if errors:
        print("Config validation errors:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    return config


# --- ATS Fetchers ---

def fetch_greenhouse(slug):
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        data = json.loads(resp.read().decode())
    jobs = []
    for j in data.get("jobs", []):
        location = j.get("location", {})
        if isinstance(location, dict):
            location = location.get("name", "")
        jobs.append({
            "id": str(j["id"]),
            "title": j.get("title", ""),
            "location": location or "",
            "url": j.get("absolute_url", ""),
        })
    return jobs


def fetch_lever(slug):
    url = f"https://api.lever.co/v0/postings/{slug}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        data = json.loads(resp.read().decode())
    jobs = []
    for j in data:
        categories = j.get("categories", {})
        location = categories.get("location", "") if isinstance(categories, dict) else ""
        jobs.append({
            "id": str(j["id"]),
            "title": j.get("text", ""),
            "location": location or "",
            "url": j.get("hostedUrl", ""),
        })
    return jobs


def fetch_ashby(slug):
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        data = json.loads(resp.read().decode())
    jobs = []
    for j in data.get("jobs", []):
        location = j.get("location", "")
        if isinstance(location, dict):
            location = location.get("name", "")
        jobs.append({
            "id": str(j["id"]),
            "title": j.get("title", ""),
            "location": location or "",
            "url": j.get("jobUrl", ""),
        })
    return jobs


def _parse_workday_postings(data, slug, instance):
    jobs = []
    for j in data.get("jobPostings", []):
        external_path = j.get("externalPath", "")
        job_id = external_path.rsplit("_", 1)[-1] if "_" in external_path else external_path
        full_url = (f"https://{slug}.{instance}.myworkdayjobs.com{external_path}"
                    if external_path else "")
        location = j.get("locationsText", "")
        if not location:
            loc = j.get("primaryLocation", {})
            location = loc.get("descriptor", "") if isinstance(loc, dict) else ""
        jobs.append({
            "id": job_id or j.get("title", ""),
            "title": j.get("title", ""),
            "location": location,
            "url": full_url,
        })
    return jobs


WORKDAY_PAGE_SIZE = 20        # max limit Workday accepts
WORKDAY_MAX_PAGES = 15        # paginate up to 300 jobs per company


def fetch_workday(slug, company_config):
    """Workday CXS API — paginates up to WORKDAY_MAX_PAGES pages, falls back to playwright on CSRF."""
    board    = company_config.get("workday_board", "External")
    instance = company_config.get("workday_instance", "wd3")
    url = (f"https://{slug}.{instance}.myworkdayjobs.com"
           f"/wday/cxs/{slug}/{board}/jobs")

    all_jobs = []
    offset = 0
    total = None

    while True:
        payload = json.dumps({
            "limit": WORKDAY_PAGE_SIZE,
            "offset": offset,
            "searchText": "",
            "appliedFacets": {}
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 422:
                return _fetch_workday_playwright(slug, board, instance)
            raise

        page_jobs = _parse_workday_postings(data, slug, instance)
        all_jobs.extend(page_jobs)

        if total is None:
            total = data.get("total", 0)

        offset += WORKDAY_PAGE_SIZE
        if offset >= total or offset >= WORKDAY_MAX_PAGES * WORKDAY_PAGE_SIZE or not page_jobs:
            break
        time.sleep(DELAY_BETWEEN_REQUESTS)

    return all_jobs


def _fetch_workday_playwright(slug, board, instance):
    """Headless Chromium via playwright — handles Workday CSRF protection automatically."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError(
            "Workday CSRF protection: run 'pip install playwright && playwright install chromium' to enable"
        )
    search_url = (f"https://{slug}.{instance}.myworkdayjobs.com"
                  f"/en-US/{board}?q=product+manager")
    captured = []

    def on_response(response):
        if "/wday/cxs/" in response.url and response.status == 200:
            try:
                data = response.json()
                if "jobPostings" in data:
                    captured.extend(_parse_workday_postings(data, slug, instance))
            except Exception:
                pass

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.on("response", on_response)
        page.goto(search_url, timeout=30000, wait_until="networkidle")
        browser.close()

    return captured


def fetch_workable(slug, _company_config=None):
    """Workable ATS — used by Borrowell and others."""
    import urllib.parse
    url = f"https://apply.workable.com/api/v3/accounts/{slug}/jobs"
    payload = json.dumps({
        "query": "product manager",
        "location": [],
        "department": [],
        "worktype": [],
        "remote": []
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    })
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        data = json.loads(resp.read().decode())
    jobs = []
    for j in data.get("results", []):
        jobs.append({
            "id": j.get("shortcode", j.get("id", "")),
            "title": j.get("title", ""),
            "location": j.get("location", {}).get("city", "") if isinstance(j.get("location"), dict) else "",
            "url": f"https://apply.workable.com/{slug}/j/{j.get('shortcode', '')}",
        })
    return jobs


def fetch_smartrecruiters(slug, _company_config=None):
    """SmartRecruiters public API — used by Visa and others."""
    all_jobs = []
    offset = 0
    limit = 100
    while True:
        url = (f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
               f"?offset={offset}&limit={limit}")
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
        for j in data.get("content", []):
            loc_parts = []
            if j.get("location", {}).get("city"):
                loc_parts.append(j["location"]["city"])
            if j.get("location", {}).get("region"):
                loc_parts.append(j["location"]["region"])
            if j.get("location", {}).get("country"):
                loc_parts.append(j["location"]["country"])
            location = ", ".join(loc_parts)
            job_id = str(j.get("id", j.get("uuid", "")))
            all_jobs.append({
                "id": job_id,
                "title": j.get("name", ""),
                "location": location,
                "url": f"https://jobs.smartrecruiters.com/{slug}/{job_id}",
            })
        total = data.get("totalFound", 0)
        offset += limit
        if offset >= total or not data.get("content"):
            break
        time.sleep(DELAY_BETWEEN_REQUESTS)
    return all_jobs


def fetch_rippling(slug, _company_config=None):
    """Rippling ATS public API — used by Flybits and others."""
    url = f"https://api.rippling.com/platform/api/ats/v1/board/{slug}/jobs"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        data = json.loads(resp.read().decode())
    jobs = []
    for j in data:
        loc = j.get("workLocation", "")
        if isinstance(loc, dict):
            loc = loc.get("label", loc.get("name", ""))
        jobs.append({
            "id": str(j.get("uuid", "")),
            "title": j.get("name", ""),
            "location": loc,
            "url": j.get("url", ""),
        })
    return jobs


def fetch_shopify(_slug=None, _company_config=None):
    """Scrape Shopify's custom careers page for job listings."""
    import re as _re
    url = "https://www.shopify.com/careers/search"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    jobs = []
    seen_uuids = set()
    # Pattern: /careers/{title-slug}_{uuid} possibly followed by ? or "
    for match in _re.finditer(
        r'/careers/([\w-]+?_([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}))',
        html
    ):
        slug_title, uuid = match.groups()
        if uuid in seen_uuids:
            continue
        seen_uuids.add(uuid)
        title_slug = slug_title.rsplit("_", 1)[0]
        title = title_slug.replace("-", " ").replace("s ", "'s ").title()
        jobs.append({
            "id": uuid,
            "title": title,
            "location": "Remote",
            "url": f"https://www.shopify.com/careers/{slug_title}",
        })
    return jobs


def fetch_dayforce(slug, company_config):
    """Dayforce candidate portal — Playwright scraper for JS-rendered pages."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError("Dayforce requires playwright: pip install playwright && playwright install chromium")
    portal = company_config.get("dayforce_portal", slug)
    search_url = f"https://jobs.dayforcehcm.com/en-US/{portal}/CANDIDATEPORTAL"
    captured_jobs = []
    seen_ids = set()

    def on_response(response):
        if "/jobposting/search" in response.url and response.status == 200:
            try:
                data = response.json()
                for j in data.get("jobPostings", []):
                    job_id = str(j.get("jobPostingId", ""))
                    if not job_id or job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)
                    title = j.get("jobTitle", "")
                    location = j.get("formattedAddress", "")
                    req_id = j.get("jobReqId", "")
                    captured_jobs.append({
                        "id": job_id,
                        "title": title,
                        "location": location,
                        "url": f"{search_url}/jobs/{job_id}",
                    })
            except Exception:
                pass

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.on("response", on_response)
        page.goto(search_url, timeout=45000, wait_until="domcontentloaded")
        page.wait_for_timeout(8000)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(3000)
        browser.close()
    return captured_jobs


def fetch_zoho_recruit(slug, company_config):
    """Zoho Recruit careers page — Playwright scraper for JS-rendered pages."""
    import re as _re
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError("Zoho Recruit requires playwright: pip install playwright && playwright install chromium")
    careers_url = company_config.get("careers_url", "")
    if not careers_url:
        return []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(careers_url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        html = page.content()
        browser.close()
    jobs = []
    seen = set()
    for match in _re.finditer(
        r'<a[^>]+href="([^"]*(?:jobs/Careers|showjob|job|apply)[^"]*)"[^>]*>\s*([^<]+?)\s*</a>',
        html, _re.IGNORECASE
    ):
        url, title = match.groups()
        title = title.strip()
        if not title or len(title) < 5 or title in seen:
            continue
        seen.add(title)
        if not url.startswith("http"):
            base = careers_url.rsplit("/", 1)[0]
            url = base + "/" + url.lstrip("/")
        id_match = _re.search(r'/(\d+)', url)
        job_id = id_match.group(1) if id_match else title
        jobs.append({
            "id": str(job_id),
            "title": title,
            "location": "",
            "url": url,
        })
    return jobs


FETCHERS = {
    "greenhouse":      lambda slug, c: fetch_greenhouse(slug),
    "lever":           lambda slug, c: fetch_lever(slug),
    "ashby":           lambda slug, c: fetch_ashby(slug),
    "workday":         lambda slug, c: fetch_workday(slug, c),
    "workable":        lambda slug, c: fetch_workable(slug),
    "smartrecruiters": lambda slug, c: fetch_smartrecruiters(slug),
    "rippling":        lambda slug, c: fetch_rippling(slug),
    "shopify":         lambda slug, c: fetch_shopify(slug),
    "dayforce":        lambda slug, c: fetch_dayforce(slug, c),
    "zoho_recruit":    lambda slug, c: fetch_zoho_recruit(slug, c),
}


# --- Filtering ---

def is_pm_job(title, filters):
    title_lower = title.lower()
    for kw in filters.get("exclude_keywords", []):
        if kw.lower() in title_lower:
            return False
    matched = False
    for kw in filters["title_keywords"]:
        if kw.lower() in title_lower:
            matched = True
            break
    if not matched:
        return False
    levels = filters.get("experience_levels", [])
    if levels:
        for level in levels:
            if level.lower() in title_lower:
                return True
        return False
    return True


# --- Dedup ---

def load_seen_jobs():
    if os.path.exists(SEEN_JOBS_FILE):
        with open(SEEN_JOBS_FILE, "r") as f:
            return json.load(f)
    return {}


def save_seen_jobs(seen):
    tmp = SEEN_JOBS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(seen, f, indent=2)
    os.replace(tmp, SEEN_JOBS_FILE)


def make_dedup_key(ats, slug, job_id):
    return f"{ats}:{slug}:{job_id}"


# --- Settings ---

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    return {}


# --- Slack ---

def send_slack(webhook_url, results, today_str):
    total_new = sum(len(jobs) for jobs in results.values())
    if total_new == 0:
        return
    lines = [f"*PM Job Listings — {today_str}*\n{total_new} new jobs found:\n"]
    for company_key, jobs in sorted(results.items()):
        if not jobs:
            continue
        name, ats = company_key
        lines.append(f"*{name}* ({len(jobs)} jobs)")
        for j in jobs[:5]:
            loc = f" — {j['location']}" if j["location"] else ""
            if j["url"]:
                lines.append(f"  <{j['url']}|{j['title']}>{loc}")
            else:
                lines.append(f"  {j['title']}{loc}")
        if len(jobs) > 5:
            lines.append(f"  ...and {len(jobs) - 5} more")
        lines.append("")
    payload = json.dumps({"text": "\n".join(lines)}).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
    )
    try:
        urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT)
        print("Slack notification sent!")
    except Exception as e:
        print(f"Slack notification failed: {e}")


# --- Markdown Output ---

def generate_markdown(results, errors, no_jobs_companies, total_companies, today_str):
    total_new = sum(len(jobs) for jobs in results.values())
    lines = [
        f"# PM Job Listings — {today_str}",
        f"> {total_new} new jobs across {total_companies} companies"
        + (f" ({len(errors)} errors)" if errors else ""),
        "",
    ]
    for company_key, jobs in sorted(results.items()):
        if not jobs:
            continue
        name, ats = company_key
        lines.append(f"## {name} ({ats.title()})")
        lines.append("")
        lines.append("| Title | Location | Link |")
        lines.append("|-------|----------|------|")
        for j in jobs:
            title = j["title"].replace("|", "\\|")
            location = j["location"].replace("|", "\\|") if j["location"] else "—"
            link = f"[Apply]({j['url']})" if j["url"] else "—"
            lines.append(f"| {title} | {location} | {link} |")
        lines.append("")

    if no_jobs_companies:
        lines.append("## Companies with no new PM jobs")
        lines.append(", ".join(sorted(no_jobs_companies)))
        lines.append("")

    if errors:
        lines.append("## Errors (skipped)")
        for name, msg in sorted(errors):
            lines.append(f"- {name}: {msg}")
        lines.append("")

    return "\n".join(lines)


# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="Fetch PM job listings from company career pages.")
    parser.add_argument("--reset", action="store_true", help="Clear seen jobs and show everything")
    parser.add_argument("--all", action="store_true", help="Show all matching jobs, not just new ones")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Path to companies.json")
    args = parser.parse_args()

    config = load_config(args.config)
    filters = config["filters"]
    companies = config["companies"]

    if args.reset and os.path.exists(SEEN_JOBS_FILE):
        os.remove(SEEN_JOBS_FILE)
        print("Cleared seen jobs history.")

    seen = load_seen_jobs()
    today_str = date.today().strftime("%B %d, %Y")
    today_iso = date.today().isoformat()

    results = {}       # (name, ats) -> [jobs]
    errors = []        # [(name, message)]
    no_jobs = []       # [name]
    new_count = 0

    print(f"Fetching PM jobs from {len(companies)} companies...\n")

    for i, company in enumerate(companies):
        name = company["name"]
        ats = company["ats"]
        slug = company["slug"]
        print(f"  [{i+1}/{len(companies)}] {name}...", end=" ", flush=True)

        try:
            fetcher = FETCHERS[ats]
            all_jobs = fetcher(slug, company)
            pm_jobs = [j for j in all_jobs if is_pm_job(j["title"], filters)]

            new_jobs = []
            for j in pm_jobs:
                key = make_dedup_key(ats, slug, j["id"])
                if args.all or key not in seen:
                    new_jobs.append(j)
                    seen[key] = today_iso

            if new_jobs:
                results[(name, ats)] = new_jobs
                new_count += len(new_jobs)
                print(f"{len(new_jobs)} new PM jobs")
            else:
                no_jobs.append(name)
                print("no new PM jobs")

        except urllib.error.HTTPError as e:
            msg = f"HTTP {e.code} — slug may have changed"
            errors.append((name, msg))
            print(f"ERROR ({msg})")
        except urllib.error.URLError as e:
            msg = f"Connection error — {e.reason}"
            errors.append((name, msg))
            print(f"ERROR ({msg})")
        except Exception as e:
            msg = str(e)
            errors.append((name, msg))
            print(f"ERROR ({msg})")

        if i < len(companies) - 1:
            time.sleep(DELAY_BETWEEN_REQUESTS)

    # Save seen jobs
    save_seen_jobs(seen)

    # Generate markdown
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_file = os.path.join(OUTPUT_DIR, f"jobs_{date.today().isoformat()}.md")
    md = generate_markdown(results, errors, no_jobs, len(companies), today_str)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(md)

    # Send Slack notification if configured
    settings = load_settings()
    slack_url = settings.get("slack_webhook_url", "")
    if slack_url and new_count > 0:
        send_slack(slack_url, results, today_str)

    print(f"\nDone! {new_count} new PM jobs found.")
    print(f"Output: {output_file}")


if __name__ == "__main__":
    main()
