"""Feedback Loop and Accuracy Logging Module with Undo support."""

from __future__ import annotations
import csv
from datetime import datetime
from pathlib import Path
import shutil
from typing import Dict, Any, List, Optional
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import DEFAULT_LOG_FILE, CATEGORIES


class FeedbackTracker:
    """Manages the decision history, accuracy tracking, corrections, and undo operations."""

    FIELDNAMES = [
        "id",
        "timestamp",
        "filename",
        "original_path",
        "current_path",
        "decision",
        "confidence",
        "correction",
        "is_correct",
        "status",
        "model_mode",
        "snippet_preview"
    ]

    def __init__(self, log_path: Path | str = DEFAULT_LOG_FILE):
        self.log_path = Path(log_path).resolve()
        self._ensure_log_file()

    def _ensure_log_file(self) -> None:
        """Ensures the CSV file exists with proper headers."""
        if not self.log_path.exists():
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)
                writer.writeheader()

    def _read_all_records(self) -> List[Dict[str, str]]:
        """Reads all rows from the CSV log."""
        if not self.log_path.exists():
            return []
        with open(self.log_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader)

    def _write_all_records(self, records: List[Dict[str, str]]) -> None:
        """Overwrites the CSV log with updated records."""
        with open(self.log_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)
            writer.writeheader()
            writer.writerows(records)

    def log_decision(
        self,
        filename: str,
        original_path: Path,
        current_path: Path,
        decision: str,
        confidence: float,
        model_mode: str,
        snippet: str
    ) -> str:
        """Logs a new file sorting decision to the CSV.

        Returns:
            The unique entry ID.
        """
        records = self._read_all_records()
        next_id = str(len(records) + 1)
        now_iso = datetime.now().isoformat(timespec="seconds")
        clean_snippet = " ".join(snippet.split())[:120]

        row = {
            "id": next_id,
            "timestamp": now_iso,
            "filename": filename,
            "original_path": str(original_path),
            "current_path": str(current_path),
            "decision": decision,
            "confidence": f"{confidence:.4f}",
            "correction": decision,  # Defaults to decision until corrected
            "is_correct": "True",
            "status": "MOVED",
            "model_mode": model_mode,
            "snippet_preview": clean_snippet
        }

        with open(self.log_path, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)
            writer.writerow(row)

        return next_id

    def undo_last_move(self, correction_category: Optional[str] = None) -> Optional[Dict[str, str]]:
        """Reverts the most recent move and marks it in the feedback loop.

        Args:
            correction_category: Optional folder category that was the intended target.

        Returns:
            Dictionary with details of the undone record, or None if no moves found.
        """
        records = self._read_all_records()
        if not records:
            return None

        # Find the last record that is currently MOVED or CORRECTED
        target_idx = None
        for i in reversed(range(len(records))):
            if records[i]["status"] in ("MOVED", "CORRECTED"):
                target_idx = i
                break

        if target_idx is None:
            return None

        record = records[target_idx]
        current_path = Path(record["current_path"])
        original_path = Path(record["original_path"])

        # Revert file back to original location
        if current_path.exists():
            original_path.parent.mkdir(parents=True, exist_ok=True)
            # Avoid overwriting if a file already exists at original path
            dest = original_path
            if dest.exists() and dest != current_path:
                stem = original_path.stem
                ext = original_path.suffix
                dest = original_path.parent / f"{stem}_reverted{ext}"
            shutil.move(str(current_path), str(dest))
            record["current_path"] = str(dest)
        else:
            print(f"[Notice] File no longer at {current_path}. Log updated anyway.")

        record["status"] = "UNDONE"
        if correction_category:
            record["correction"] = correction_category
            record["is_correct"] = "True" if correction_category == record["decision"] else "False"

        records[target_idx] = record
        self._write_all_records(records)
        return record

    def record_correction(self, identifier: str, correct_category: str) -> Optional[Dict[str, str]]:
        """Applies a human correction to a prior decision and relocates the file.

        Args:
            identifier: Either row ID or filename.
            correct_category: The true intended category.

        Returns:
            Updated record or None.
        """
        if correct_category not in CATEGORIES:
            raise ValueError(f"Invalid category '{correct_category}'. Must be one of {list(CATEGORIES.keys())}")

        records = self._read_all_records()
        target_idx = None

        # Match by ID or filename (last occurrence)
        for i in reversed(range(len(records))):
            if records[i]["id"] == identifier or records[i]["filename"].lower() == identifier.lower():
                target_idx = i
                break

        if target_idx is None:
            return None

        record = records[target_idx]
        current_path = Path(record["current_path"])

        # If file exists at current location, move it to the corrected category folder
        if current_path.exists():
            target_folder = current_path.parent.parent / correct_category
            target_folder.mkdir(parents=True, exist_ok=True)
            new_path = target_folder / current_path.name
            if new_path.exists() and new_path != current_path:
                stem = current_path.stem
                ext = current_path.suffix
                new_path = target_folder / f"{stem}_corr{ext}"
            shutil.move(str(current_path), str(new_path))
            record["current_path"] = str(new_path)

        record["correction"] = correct_category
        record["is_correct"] = "True" if record["decision"] == correct_category else "False"
        record["status"] = "CORRECTED"

        records[target_idx] = record
        self._write_all_records(records)
        return record

    def compute_stats(self) -> Dict[str, Any]:
        """Calculates running accuracy and feedback loop metrics."""
        records = self._read_all_records()
        total = len(records)
        if total == 0:
            return {
                "total_decisions": 0,
                "accuracy": 0.0,
                "correct_count": 0,
                "corrected_count": 0,
                "undone_count": 0,
                "avg_confidence": 0.0,
                "category_breakdown": {},
                "misclassifications": []
            }

        correct_count = sum(1 for r in records if r["is_correct"] == "True")
        corrected_count = sum(1 for r in records if r["is_correct"] == "False" or r["status"] == "CORRECTED")
        undone_count = sum(1 for r in records if r["status"] == "UNDONE")

        confidences = [float(r["confidence"]) for r in records if r.get("confidence")]
        avg_confidence = (sum(confidences) / len(confidences)) if confidences else 0.0

        # Accuracy: percentage where initial decision matches correction
        accuracy = (correct_count / total) * 100 if total > 0 else 0.0

        # Breakdown per category
        category_breakdown: Dict[str, Dict[str, int]] = {k: {"predicted": 0, "actual": 0} for k in CATEGORIES}
        misclassifications: List[Dict[str, str]] = []

        for r in records:
            dec = r.get("decision", "Misc")
            corr = r.get("correction", dec)
            if dec in category_breakdown:
                category_breakdown[dec]["predicted"] += 1
            if corr in category_breakdown:
                category_breakdown[corr]["actual"] += 1

            if dec != corr:
                misclassifications.append({
                    "id": r["id"],
                    "filename": r["filename"],
                    "predicted": dec,
                    "corrected_to": corr,
                    "confidence": r["confidence"]
                })

        return {
            "total_decisions": total,
            "accuracy": round(accuracy, 2),
            "correct_count": correct_count,
            "corrected_count": corrected_count,
            "undone_count": undone_count,
            "avg_confidence": round(avg_confidence, 4),
            "category_breakdown": category_breakdown,
            "misclassifications": misclassifications
        }

    def print_stats(self) -> None:
        """Renders an ASCII summary of the feedback loop and accuracy metrics."""
        stats = self.compute_stats()
        print("=" * 60)
        print("📊 JEV DOWNLOADS SORTER — ACCURACY & FEEDBACK LOOP")
        print("=" * 60)
        print(f"Total Decisions Logged: {stats['total_decisions']}")
        print(f"Current Running Accuracy: {stats['accuracy']:.1f}%")
        print(f"Average Confidence:     {stats['avg_confidence'] * 100:.1f}%")
        print(f"Undone Operations:      {stats['undone_count']}")
        print(f"Human Corrections:      {stats['corrected_count']}")
        print("-" * 60)
        print("Category Distribution:")
        for cat, counts in stats["category_breakdown"].items():
            print(f"  • {cat:<12} Predicted: {counts['predicted']:<3} | Actual (Feedback): {counts['actual']:<3}")

        if stats["misclassifications"]:
            print("-" * 60)
            print("Feedback Loop (Misclassifications Corrected):")
            for m in stats["misclassifications"][-5:]:
                print(f"  [#{m['id']}] {m['filename']}: Predicted {m['predicted']} -> Corrected to {m['corrected_to']} (Conf: {float(m['confidence']) * 100:.1f}%)")
        print("=" * 60)
