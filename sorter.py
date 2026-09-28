#!/usr/bin/env python3
"""Downloads Sorter with Jev — CLI Entrypoint.

Uses TypeSafe's Jev System One decision model to automatically classify
and sort downloaded files into categorized destination folders, with real-time
watchdog monitoring, instant undo capability, and a continuous feedback loop.
"""

from __future__ import annotations
import argparse
import sys
from pathlib import Path

# Ensure Windows terminals support UTF-8 output without UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from config import DEFAULT_WATCH_DIR, CATEGORIES, DEFAULT_LOG_FILE
from jev_classifier import JevClassifier
from feedback import FeedbackTracker
from monitor import DownloadSorterHandler, start_monitoring
from file_inspector import inspect_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Downloads Sorter with Jev — Fast, structured System One decision sorting."
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Run continuous watchdog folder monitor (default behavior if no action specified)."
    )
    parser.add_argument(
        "--dir", "-d",
        type=Path,
        default=DEFAULT_WATCH_DIR,
        help=f"Target directory to monitor and sort (default: {DEFAULT_WATCH_DIR})."
    )
    parser.add_argument(
        "--undo",
        action="store_true",
        help="Revert the most recent move and record feedback."
    )
    parser.add_argument(
        "--correct",
        nargs=2,
        metavar=("IDENTIFIER", "CORRECT_CATEGORY"),
        help="Correct a past classification by Log ID or Filename (e.g., --correct 3 Invoices)."
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Display running accuracy metrics and feedback loop statistics."
    )
    parser.add_argument(
        "--sort-file",
        type=Path,
        metavar="FILE_PATH",
        help="Sort a single file immediately with Jev."
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="Scan and sort all existing loose files in the target directory once."
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Force simulated Jev responses without calling the live API."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the sorting without actually moving any files."
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=Path(DEFAULT_LOG_FILE),
        help=f"Path to the accuracy and feedback CSV log (default: {DEFAULT_LOG_FILE})."
    )

    return parser.parse_args()


def handle_undo(feedback: FeedbackTracker) -> None:
    """Handles the --undo command."""
    print("↩ Checking last move operation in feedback log...")
    # Preview latest record before undoing
    records = feedback._read_all_records()
    active_records = [r for r in records if r["status"] in ("MOVED", "CORRECTED")]

    if not active_records:
        print("⚠️ No reversible moves found in the feedback log.")
        return

    last = active_records[-1]
    print(f"   Target: \"{last['filename']}\"")
    print(f"   From:   {last['original_path']}")
    print(f"   To:     {last['current_path']} (Decision: {last['decision']})")

    # Optional correction prompt if run interactively
    correction = None
    if sys.stdin.isatty():
        prompt = (
            f"What was the correct folder? "
            f"[{'/'.join(CATEGORIES.keys())}] (press Enter to leave unchanged): "
        )
        try:
            val = input(prompt).strip()
            if val in CATEGORIES:
                correction = val
        except (KeyboardInterrupt, EOFError):
            pass

    undone = feedback.undo_last_move(correction_category=correction)
    if undone:
        print(f"✅ Successfully reverted '{undone['filename']}' back to its original location.")
        if correction:
            print(f"📝 Recorded correction: {correction} (was {undone['decision']}). Running accuracy updated!")
    else:
        print("❌ Could not revert the move.")


def handle_correct(feedback: FeedbackTracker, identifier: str, correct_cat: str) -> None:
    """Handles the --correct command."""
    if correct_cat not in CATEGORIES:
        print(f"❌ Error: '{correct_cat}' is not a valid category. Valid options: {list(CATEGORIES.keys())}")
        return

    try:
        updated = feedback.record_correction(identifier, correct_cat)
        if updated:
            print(f"✅ Corrected record #{updated['id']} ({updated['filename']}):")
            print(f"   Initial Decision: {updated['decision']}")
            print(f"   Corrected To:     {updated['correction']}")
            print(f"   Current Path:     {updated['current_path']}")
            print("📊 Accuracy metrics updated:")
            feedback.print_stats()
        else:
            print(f"⚠️ No record found matching identifier '{identifier}'.")
    except Exception as e:
        print(f"❌ Error applying correction: {e}")


def handle_scan(
    watch_dir: Path,
    classifier: JevClassifier,
    feedback: FeedbackTracker,
    dry_run: bool = False
) -> None:
    """Scans and sorts loose files currently in the watch directory."""
    watch_dir = watch_dir.resolve()
    if not watch_dir.exists():
        print(f"Directory not found: {watch_dir}")
        return

    print(f"🔍 Scanning directory for loose files: {watch_dir}")
    handler = DownloadSorterHandler(
        watch_dir=watch_dir,
        classifier=classifier,
        feedback=feedback,
        dry_run=dry_run
    )

    count = 0
    for item in sorted(watch_dir.iterdir()):
        if item.is_file() and not item.name.startswith("."):
            dest = handler.process_file(item)
            if dest:
                count += 1

    print(f"\n🎉 Scan complete! Processed and sorted {count} file(s).")


def main() -> None:
    args = parse_args()

    feedback = FeedbackTracker(log_path=args.log_file)
    classifier = JevClassifier(force_mock=args.mock)

    # 1. Handle --stats
    if args.stats:
        feedback.print_stats()
        return

    # 2. Handle --undo
    if args.undo:
        handle_undo(feedback)
        return

    # 3. Handle --correct
    if args.correct:
        ident, cat = args.correct
        handle_correct(feedback, ident, cat)
        return

    # 4. Handle --sort-file
    if args.sort_file:
        target_file = args.sort_file.resolve()
        if not target_file.exists():
            print(f"❌ File does not exist: {target_file}")
            sys.exit(1)
        handler = DownloadSorterHandler(
            watch_dir=target_file.parent,
            classifier=classifier,
            feedback=feedback,
            dry_run=args.dry_run
        )
        handler.process_file(target_file)
        return

    # 5. Handle --scan
    if args.scan:
        handle_scan(args.dir, classifier, feedback, dry_run=args.dry_run)
        return

    # 6. Default: Watchdog monitoring
    start_monitoring(
        watch_dir=args.dir,
        classifier=classifier,
        feedback=feedback,
        dry_run=args.dry_run
    )


if __name__ == "__main__":
    main()
