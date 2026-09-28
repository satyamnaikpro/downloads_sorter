"""Tests for Jev Classifier module."""

from pathlib import Path
from jev_classifier import JevClassifier, ClassificationResult, SystemOneResponse, ChoiceAnswer
from file_inspector import FileState
from config import CATEGORIES


def test_question_criteria():
    classifier = JevClassifier(force_mock=True)
    question = classifier.build_question()
    assert question.type == "choice"
    assert set(question.criteria.keys()) == set(CATEGORIES.keys())


def test_classify_invoice_file():
    classifier = JevClassifier(force_mock=True)
    state = FileState(
        path=Path("dummy_invoice.pdf"),
        filename="Invoice_INV-2026-904.pdf",
        extension=".pdf",
        size_bytes=10240,
        size_human="10.00 KB",
        snippet="INVOICE #904. Billed to Acme Corporation. Subtotal: $5,000. Amount Due: $5,000. Payment due upon receipt."
    )
    result = classifier.classify_file_state(state)
    assert isinstance(result, ClassificationResult)
    assert result.category == "Invoices"
    assert result.confidence > 0.5
    assert isinstance(result.raw_response, SystemOneResponse)
    assert isinstance(result.raw_response.choices["folder"], ChoiceAnswer)


def test_classify_code_file():
    classifier = JevClassifier(force_mock=True)
    state = FileState(
        path=Path("app.py"),
        filename="app.py",
        extension=".py",
        size_bytes=450,
        size_human="450 B",
        snippet="from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get('/')\ndef root():\n    return {'status': 'ok'}"
    )
    result = classifier.classify_file_state(state)
    assert result.category == "Code"
    assert result.confidence > 0.5


def test_classify_screenshot():
    classifier = JevClassifier(force_mock=True)
    state = FileState(
        path=Path("Screenshot 2026-09-28 at 12.00.00.png"),
        filename="Screenshot 2026-09-28 at 12.00.00.png",
        extension=".png",
        size_bytes=204800,
        size_human="200.00 KB",
        snippet="[Image (Format: PNG, Dimensions: 1920x1080, Color Mode: RGBA)]"
    )
    result = classifier.classify_file_state(state)
    assert result.category == "Screenshots"


def test_classify_resume():
    classifier = JevClassifier(force_mock=True)
    state = FileState(
        path=Path("Alex_Doe_Resume.pdf"),
        filename="Alex_Doe_Resume.pdf",
        extension=".pdf",
        size_bytes=51200,
        size_human="50.00 KB",
        snippet="Alex Doe - Senior Software Engineer. Professional Experience: 2021-Present. Education: Bachelor of Science in Computer Science."
    )
    result = classifier.classify_file_state(state)
    assert result.category == "Resumes"
