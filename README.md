# PM Job Fetcher

A Python tool that scans company career pages across 10 ATS platforms for Product Manager jobs, customizes resumes per role, and delivers a daily digest via email and WhatsApp.

Built to automate my own job search. Runs daily via Windows Task Scheduler.

## What it does

- **Fetches PM jobs** from Greenhouse, Lever, Ashby, Workable, Workday, SmartRecruiters, Rippling, Shopify, Dayforce, and Zoho Recruit
- **Filters by location** (configurable allowlist/blocklist)
- **Scores and ranks** jobs by keyword relevance
- **Customizes resumes** per job using a Claude-powered skill
- **Sends email digest** with top matches
- **Sends WhatsApp alerts** per job via Meta Cloud API (template message + resume attachment)
- **Tracks seen jobs** so you only get new listings
- **Updates Excel tracker** with new matches

## Architecture

```
fetch_jobs.py          Scrapes career pages across 10 ATS types
    |                  Workday: direct CXS API + Playwright CSRF fallback
    |                  Dayforce/Zoho: Playwright-based HTML scraping
    v
daily_digest.py        Orchestration layer
    |-- Location filter (allowlist/blocklist)
    |-- Scoring engine (keyword weights)
    |-- Resume customizer (Claude skill)
    |-- Email sender (Gmail SMTP)
    |-- WhatsApp sender (Meta Cloud API)
    |-- Excel tracker update (openpyxl)
    v
output/                Daily markdown job listings
customized_resumes/    Per-job tailored resumes
```

## Setup

**Requirements:** Python 3.10+, Playwright (for Workday CSRF, Dayforce, Zoho)

```bash
pip install playwright python-docx openpyxl
playwright install chromium
```

**Configuration:**

1. Copy `settings.json.example` to `settings.json` and fill in your credentials
2. Copy `companies.example.json` to `companies.json` and add your target companies
3. (Optional) Copy `networking_companies.example.json` to `networking_companies.json` for LinkedIn discovery

```json
{
  "email_from": "your-email@gmail.com",
  "email_app_password": "your-app-password",
  "email_to": "destination@email.com",
  "base_resume_path": "/path/to/your/resume.docx",
  "excel_tracker_path": "/path/to/your/tracker.xlsx",
  "whatsapp_phone_id": "your-phone-id",
  "whatsapp_token": "your-token",
  "whatsapp_to": "+1234567890"
}
```

## Usage

```bash
# Fetch new jobs
python fetch_jobs.py

# Show all jobs (ignore history)
python fetch_jobs.py --all

# Reset seen history
python fetch_jobs.py --reset

# Full digest (fetch + score + email + WhatsApp)
python daily_digest.py

# Test mode (no email/WhatsApp sent)
python daily_digest.py --test

# Add companies (auto-detects ATS for Greenhouse/Lever/Ashby)
python add_companies.py Stripe Figma Notion

# List tracked companies
python add_companies.py --list
```

## Supported ATS platforms

| ATS | Method |
|-----|--------|
| Greenhouse | Public JSON API |
| Workday | CXS API + Playwright CSRF fallback |
| Ashby | Public JSON API |
| Lever | Public JSON API |
| Workable | Public JSON API |
| SmartRecruiters | Public REST API |
| Rippling | Public REST API |
| Shopify | HTML scraper |
| Dayforce | Playwright (captures API responses) |
| Zoho Recruit | Playwright HTML scraper |

## LinkedIn contact discovery

`linkedin_networking.py` helps research PM-adjacent contacts at target companies on LinkedIn. It searches for relevant roles, scores contacts by relevance, generates personalized outreach drafts via Claude, and writes results to an Excel tracker for manual review before sending.

## Built with

Python, Playwright, Claude Code, Meta WhatsApp Cloud API, Gmail SMTP
