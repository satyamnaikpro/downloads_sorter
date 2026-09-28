"""Watchdog folder monitor and file sorting dispatcher for Jev Downloads Sorter."""

from __future__ import annotations
import os
import shutil
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path
from typing import Optional, Set
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileMovedEvent
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False

    class FileSystemEventHandler:
        pass

    class FileCreatedEvent:
        is_directory = False
        src_path = ""

    class FileMovedEvent:
        is_directory = False
        dest_path = ""

    Observer = None

from config import CATEGORIES, IGNORED_EXTENSIONS
from file_inspector import inspect_file, FileState
from jev_classifier import JevClassifier, ClassificationResult
from feedback import FeedbackTracker


class DownloadSorterHandler(FileSystemEventHandler):
    """Event handler that detects newly created/completed downloads and routes them with Jev."""

    def __init__(
        self,
        watch_dir: Path,
        classifier: JevClassifier,
        feedback: FeedbackTracker,
        debounce_seconds: float = 1.0,
        dry_run: bool = False
    ):
        super().__init__()
        self.watch_dir = Path(watch_dir).resolve()
        self.classifier = classifier
        self.feedback = feedback
        self.debounce_seconds = debounce_seconds
        self.dry_run = dry_run

        # Exclude category folders from triggering events
        self.category_names: Set[str] = set(CATEGORIES.keys())
        self._processing: Set[Path] = set()

    def _is_in_category_folder(self, path: Path) -> bool:
        """Checks if a file is already inside one of the category target folders."""
        try:
            relative_parts = path.resolve().relative_to(self.watch_dir).parts
            if relative_parts and relative_parts[0] in self.category_names:
                return True
        except ValueError:
            pass
        return False

    def _wait_for_file_settled(self, path: Path, max_wait: float = 10.0) -> bool:
        """Waits for file writes to finish by checking file size stability."""
        start_time = time.time()
        last_size = -1

        while (time.time() - start_time) < max_wait:
            if not path.exists():
                return False
            try:
                current_size = path.stat().st_size
                if current_size == last_size and current_size > 0:
                    # File size is stable, verify read access
                    with open(path, "rb") as f:
                        f.read(10)
                    return True
                last_size = current_size
            except (OSError, PermissionError):
                pass
            time.sleep(self.debounce_seconds)

        return path.exists()

    def process_file(self, path: Path) -> Optional[Path]:
        """Inspects, classifies with Jev, and moves the downloaded file."""
        path = path.resolve()

        # Pre-checks: existence, directory, ignored extensions, already inside category folder
        if not path.exists() or path.is_dir():
            return None
        if path.name.startswith(".") or path.suffix.lower() in IGNORED_EXTENSIONS:
            return None
        if self._is_in_category_folder(path):
            return None
        if path in self._processing:
            return None

        self._processing.add(path)
        try:
            # Wait for any active browser write / download to settle
            if not self._wait_for_file_settled(path):
                return None

            print(f"\n📥 Detected new file: {path.name}")

            # 1. Build State string from metadata and first 500 chars
            file_state: FileState = inspect_file(path, max_chars=500)
            print(f"📄 State extracted ({file_state.size_human}, {file_state.extension or 'no ext'}):")
            preview = file_state.snippet.replace("\n", " ")[:90]
            print(f"   Snippet: \"{preview}...\"")

            # 2. Query Jev System One Decision Model
            print("🤖 Consulting Jev System One model...")
            result: ClassificationResult = self.classifier.classify_file_state(file_state)
            category = result.category
            confidence = result.confidence
            mode = "SIMULATED" if result.is_simulated else "LIVE"

            print(f"✨ Jev Decision: {category} (Confidence: {confidence * 100:.1f}%) [{mode}]")

            if self.dry_run:
                print(f"🔍 [DRY-RUN] Would move '{path.name}' -> '{self.watch_dir / category}'")
                return path

            # 3. Move file to target category directory
            target_dir = self.watch_dir / category
            target_dir.mkdir(parents=True, exist_ok=True)

            dest_path = target_dir / path.name
            if dest_path.exists() and dest_path != path:
                # Collision resolution
                counter = 1
                stem = path.stem
                ext = path.suffix
                while dest_path.exists():
                    dest_path = target_dir / f"{stem} ({counter}){ext}"
                    counter += 1

            shutil.move(str(path), str(dest_path))
            print(f"🚀 Moved to: {dest_path.relative_to(self.watch_dir)}")

            # 4. Log decision into CSV feedback loop
            log_id = self.feedback.log_decision(
                filename=path.name,
                original_path=path,
                current_path=dest_path,
                decision=category,
                confidence=confidence,
                model_mode=mode,
                snippet=file_state.snippet
            )
            print(f"📝 Decision logged (Log ID #{log_id}). [Undo anytime with: python sorter.py --undo]")
            return dest_path

        except Exception as e:
            print(f"❌ Error sorting file {path.name}: {e}")
            return None
        finally:
            self._processing.discard(path)

    def on_created(self, event: FileCreatedEvent) -> None:
        if not event.is_directory:
            self.process_file(Path(event.src_path))

    def on_moved(self, event: FileMovedEvent) -> None:
        """Triggered when downloads finish (e.g., .crdownload -> .pdf)."""
        if not event.is_directory:
            self.process_file(Path(event.dest_path))


def start_monitoring(
    watch_dir: Path,
    classifier: JevClassifier,
    feedback: FeedbackTracker,
    dry_run: bool = False
) -> None:
    """Starts the Watchdog observer on the target folder."""
    watch_dir = Path(watch_dir).resolve()
    watch_dir.mkdir(parents=True, exist_ok=True)

    if not WATCHDOG_AVAILABLE or Observer is None:
        print("❌ The 'watchdog' library is required for real-time folder monitoring.")
        print("   Install it using: pip install watchdog")
        return

    event_handler = DownloadSorterHandler(
        watch_dir=watch_dir,
        classifier=classifier,
        feedback=feedback,
        dry_run=dry_run
    )

    observer = Observer()
    observer.schedule(event_handler, str(watch_dir), recursive=True)
    observer.start()

    print("=" * 60)
    print("👁️  JEV DOWNLOADS SORTER — ACTIVE FOLDER MONITOR")
    print("=" * 60)
    print(f"Watching directory : {watch_dir}")
    print(f"Target categories  : {list(CATEGORIES.keys())}")
    print(f"Mode               : {'DRY RUN' if dry_run else 'LIVE SORTING'}")
    print("Press Ctrl+C to stop.")
    print("=" * 60)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping folder monitor...")
        observer.stop()
    observer.join()
