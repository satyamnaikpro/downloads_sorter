"""Configuration and Category Definitions for Downloads Sorter with Jev."""

from pathlib import Path
import os

# Default watched directory: ~/Downloads (or overridden via CLI/env)
DEFAULT_WATCH_DIR = Path.home() / "Downloads"

# Category choices with descriptions for Jev's System One decision criteria
CATEGORIES = {
    "Invoices": "Billing documents, receipts, invoices, statements, fee schedules, payment confirmations, purchase orders, subscriptions.",
    "Screenshots": "Screen captures, screenshot images (PNG, JPG), display recordings, UI mockups, desktop snips.",
    "Code": "Source code files, scripts, programming files, configs, stylesheets, database queries (e.g., .py, .js, .ts, .html, .css, .json, .sql, .sh, .rs, .go).",
    "Resumes": "Curriculum vitae (CV), resume documents, job application materials, candidate profiles, employment/education history.",
    "Misc": "Miscellaneous files, general documents, media files, archives (zip, tar), installers (exe, msi), or files that do not match other categories."
}

# Temporary download extensions to ignore until writing completes
IGNORED_EXTENSIONS = {
    ".crdownload",
    ".part",
    ".tmp",
    ".download",
    ".aria2",
    ".ds_store"
}

# Accuracy & feedback log CSV filename
DEFAULT_LOG_FILE = "accuracy_log.csv"

# Model name for Jev
DEFAULT_JEV_MODEL = os.getenv("TYPESAFE_DEFAULT_MODEL", "jev-1")
