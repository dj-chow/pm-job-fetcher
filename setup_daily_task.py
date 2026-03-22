#!/usr/bin/env python3
"""
Set up a Windows Task Scheduler task to run the daily PM job digest at 6pm ET.

Usage:
    python setup_daily_task.py          # create/update the task
    python setup_daily_task.py --remove # remove the task
"""

import os
import sys
import subprocess

TASK_NAME = "PMJobDigest"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DIGEST_SCRIPT = os.path.join(SCRIPT_DIR, "daily_digest.py")
PYTHON_EXE = sys.executable

# 6pm Eastern = 18:00 ET
# Windows Task Scheduler uses local time, so this assumes your PC clock is set to ET.
# If your PC is on ET, this is correct. If on another timezone, adjust accordingly.
TRIGGER_TIME = "18:00"


def create_task():
    """Create the Windows scheduled task."""
    # Build the action command
    action = f'"{PYTHON_EXE}" "{DIGEST_SCRIPT}"'

    cmd = [
        "schtasks", "/create",
        "/tn", TASK_NAME,
        "/tr", action,
        "/sc", "DAILY",
        "/st", TRIGGER_TIME,
        "/f",  # force overwrite if exists
        "/rl", "HIGHEST",  # run with highest privileges available
    ]

    print(f"Creating task '{TASK_NAME}' to run daily at {TRIGGER_TIME}...")
    print(f"Script: {DIGEST_SCRIPT}")
    print(f"Python: {PYTHON_EXE}")
    print()

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        print("✓ Task created successfully!")
        print()
        print("The task will run daily at 6:00 PM.")
        print("Your PC must be on at that time for it to trigger.")
        print()
        print("To verify: Task Scheduler > Task Scheduler Library > PMJobDigest")
        print("To run now: schtasks /run /tn PMJobDigest")
    else:
        print("ERROR creating task:")
        print(result.stdout)
        print(result.stderr)
        print()
        print("Try running this script as Administrator.")


def remove_task():
    """Remove the scheduled task."""
    cmd = ["schtasks", "/delete", "/tn", TASK_NAME, "/f"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"✓ Task '{TASK_NAME}' removed.")
    else:
        print(f"Could not remove task: {result.stderr}")


def query_task():
    """Show current task status."""
    cmd = ["schtasks", "/query", "/tn", TASK_NAME, "/fo", "LIST"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(result.stdout)
    else:
        print(f"Task '{TASK_NAME}' not found.")


if __name__ == "__main__":
    if "--remove" in sys.argv:
        remove_task()
    elif "--status" in sys.argv:
        query_task()
    else:
        create_task()
        print()
        print("NEXT STEP: Fill in settings.json with:")
        print("  email_from        — your Gmail address")
        print("  email_app_password — Gmail App Password (not your regular password)")
        print("                       Get it: myaccount.google.com > Security > App Passwords")
        print("  anthropic_api_key  — from console.anthropic.com")
        print()
        print("Then test it: python daily_digest.py --test")
