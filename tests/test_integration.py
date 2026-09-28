"""Integration tests for the downloads sorter pipeline."""

import tempfile
from pathlib import Path
from jev_classifier import JevClassifier
from feedback import FeedbackTracker
from monitor import DownloadSorterHandler


def test_full_pipeline_sorting():
    with tempfile.TemporaryDirectory() as tmp_dir:
        watch_dir = Path(tmp_dir)
        csv_path = watch_dir / "accuracy_log.csv"

        feedback = FeedbackTracker(log_path=csv_path)
        classifier = JevClassifier(force_mock=True)
        handler = DownloadSorterHandler(
            watch_dir=watch_dir,
            classifier=classifier,
            feedback=feedback,
            debounce_seconds=0.1
        )

        # 1. Test Invoices file
        inv_file = watch_dir / "Invoice_October_2026.txt"
        inv_file.write_text("INVOICE #4412\nBilled To: Globex Corp\nAmount Due: $1,400\nPayment terms: Net 30", encoding="utf-8")
        dest_inv = handler.process_file(inv_file)
        assert dest_inv is not None
        assert dest_inv.parent.name == "Invoices"
        assert dest_inv.exists()
        assert not inv_file.exists()

        # 2. Test Code file
        code_file = watch_dir / "script.py"
        code_file.write_text("import sys\ndef run():\n    print('Hello')\n", encoding="utf-8")
        dest_code = handler.process_file(code_file)
        assert dest_code is not None
        assert dest_code.parent.name == "Code"
        assert dest_code.exists()

        # 3. Test Resume file
        resume_file = watch_dir / "John_Doe_Resume.txt"
        resume_file.write_text("John Doe\nSummary: Software Engineer\nEducation: Bachelor of Science\nExperience: 5 years", encoding="utf-8")
        dest_resume = handler.process_file(resume_file)
        assert dest_resume is not None
        assert dest_resume.parent.name == "Resumes"

        # Check feedback stats
        stats = feedback.compute_stats()
        assert stats["total_decisions"] == 3
        assert stats["accuracy"] == 100.0

        # 4. Test Undo on the last file (Resume)
        undone = feedback.undo_last_move()
        assert undone is not None
        assert resume_file.exists()
        assert not dest_resume.exists()
