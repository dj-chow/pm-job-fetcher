# Tech Debt

## Active
| ID | Description | Impact | Added |
|----|-------------|--------|-------|
| (none) | | | |

## Resolved
| ID | Description | Resolved | How |
|----|-------------|----------|-----|
| TD-R001 | Hardcoded path in `run_digest.bat` | 2026-03-21 | Replaced with `%~dp0` (self-referencing) |
| TD-R002 | Hardcoded paths in `daily_digest.py`, `linkedin_networking.py`, `update_task.ps1`, `settings.json` pointed to old `Land PM Job` folder | 2026-03-22 | Updated all references to `Land_PM_Job` after folder rename. Scheduled task recreated with correct path. |
| TD-002 | Hardcoded absolute paths for EXCEL_TRACKER in `daily_digest.py`, `linkedin_networking.py`, `update_task.ps1`, `run_digest.bat` | 2026-03-22 | Moved Excel path to `settings.json` (`excel_tracker_path`). Removed hardcoded constants. `run_digest.bat` uses `%APPDATA%` and `python` on PATH. `update_task.ps1` uses `$PSScriptRoot`. `IMPLEMENTATION_PLAN.md` reference updated. |
