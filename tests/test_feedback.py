"""Tests for feedback loop, accuracy metrics, and undo operations."""

import tempfile
from pathlib import Path
from feedback import FeedbackTracker


def test_feedback_logging_and_stats():
    with tempfile.TemporaryDirectory() as tmp_dir:
        csv_path = Path(tmp_dir) / "test_accuracy.csv"
        tracker = FeedbackTracker(log_path=csv_path)

        # Log an initial decision
        entry_id = tracker.log_decision(
            filename="invoice_1.pdf",
            original_path=Path("/downloads/invoice_1.pdf"),
            current_path=Path("/downloads/Invoices/invoice_1.pdf"),
            decision="Invoices",
            confidence=0.95,
            model_mode="SIMULATED",
            snippet="Invoice #1 Billed to ACME"
        )
        assert entry_id == "1"

        stats = tracker.compute_stats()
        assert stats["total_decisions"] == 1
        assert stats["accuracy"] == 100.0
        assert stats["correct_count"] == 1
        assert stats["undone_count"] == 0


def test_undo_operation():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        csv_path = tmp_path / "test_accuracy.csv"
        tracker = FeedbackTracker(log_path=csv_path)

        orig_file = tmp_path / "receipt.pdf"
        dest_dir = tmp_path / "Invoices"
        dest_dir.mkdir()
        dest_file = dest_dir / "receipt.pdf"

        # Create file at destination
        dest_file.write_text("dummy receipt", encoding="utf-8")

        tracker.log_decision(
            filename="receipt.pdf",
            original_path=orig_file,
            current_path=dest_file,
            decision="Invoices",
            confidence=0.91,
            model_mode="SIMULATED",
            snippet="Dummy receipt text"
        )

        assert dest_file.exists()
        assert not orig_file.exists()

        # Perform Undo
        undone = tracker.undo_last_move(correction_category="Misc")
        assert undone is not None
        assert undone["status"] == "UNDONE"
        assert undone["correction"] == "Misc"
        assert undone["is_correct"] == "False"

        # File should now be back at original path
        assert orig_file.exists()
        assert not dest_file.exists()

        stats = tracker.compute_stats()
        assert stats["undone_count"] == 1
        assert stats["accuracy"] == 0.0  # marked incorrect via correction


def test_record_correction():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        csv_path = tmp_path / "test_accuracy.csv"
        tracker = FeedbackTracker(log_path=csv_path)

        invoices_dir = tmp_path / "Invoices"
        invoices_dir.mkdir()
        file_path = invoices_dir / "code_sample.py"
        file_path.write_text("print('hello')", encoding="utf-8")

        tracker.log_decision(
            filename="code_sample.py",
            original_path=tmp_path / "code_sample.py",
            current_path=file_path,
            decision="Invoices",  # Initial mistake
            confidence=0.55,
            model_mode="SIMULATED",
            snippet="print('hello')"
        )

        # Apply human correction
        updated = tracker.record_correction("code_sample.py", "Code")
        assert updated is not None
        assert updated["correction"] == "Code"
        assert updated["is_correct"] == "False"
        assert updated["status"] == "CORRECTED"

        # Verify file moved to Code folder
        assert not file_path.exists()
        expected_new_path = tmp_path / "Code" / "code_sample.py"
        assert expected_new_path.exists()
