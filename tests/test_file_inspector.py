"""Tests for file inspector module."""

import tempfile
from pathlib import Path
from file_inspector import inspect_file, FileState


def test_inspect_text_file():
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_file = Path(tmp_dir) / "notes.txt"
        test_content = "This is a simple text note with some text." * 10
        test_file.write_text(test_content, encoding="utf-8")

        state = inspect_file(test_file, max_chars=500)
        assert isinstance(state, FileState)
        assert state.filename == "notes.txt"
        assert state.extension == ".txt"
        assert state.size_bytes == len(test_content.encode("utf-8"))
        assert "simple text note" in state.snippet
        assert len(state.snippet) <= 500

        payload = state.to_state_payload()
        assert "Filename: notes.txt" in payload
        assert "Extension: .txt" in payload
        assert "Content Snippet (first 500 chars):" in payload


def test_inspect_code_file():
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_file = Path(tmp_dir) / "server.py"
        code_content = "import os\n\ndef main():\n    print('Hello World')\n"
        test_file.write_text(code_content, encoding="utf-8")

        state = inspect_file(test_file)
        assert state.filename == "server.py"
        assert state.extension == ".py"
        assert "import os" in state.snippet


def test_inspect_large_file_truncation():
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_file = Path(tmp_dir) / "large.txt"
        large_content = "A" * 2000
        test_file.write_text(large_content, encoding="utf-8")

        state = inspect_file(test_file, max_chars=500)
        assert len(state.snippet) == 500
        assert state.size_bytes == 2000
