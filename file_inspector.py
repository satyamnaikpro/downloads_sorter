"""File Inspector module for extracting metadata and text snippets from files."""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re
import string

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    from PIL import Image
except ImportError:
    Image = None


@dataclass
class FileState:
    """Represents the extracted state of a downloaded file."""
    path: Path
    filename: str
    extension: str
    size_bytes: int
    size_human: str
    snippet: str

    def to_state_payload(self) -> str:
        """Formats the file metadata and snippet into a Jev State string."""
        return (
            f"Filename: {self.filename}\n"
            f"Extension: {self.extension}\n"
            f"Size: {self.size_human} ({self.size_bytes} bytes)\n"
            f"Content Snippet (first 500 chars):\n"
            f'"""\n{self.snippet.strip()}\n"""'
        )


def _format_size(size_bytes: int) -> str:
    """Formats bytes into a readable string (e.g., '14.2 KB')."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def _extract_pdf_snippet(path: Path, max_chars: int = 500) -> str:
    """Extracts text from a PDF file using pypdf."""
    if not PdfReader:
        return "[PDF document: pypdf not installed for text extraction]"
    try:
        reader = PdfReader(str(path))
        extracted_text = []
        for page in reader.pages[:2]:  # Check first two pages
            text = page.extract_text() or ""
            extracted_text.append(text)
            if sum(len(t) for t in extracted_text) >= max_chars:
                break
        combined = " ".join(extracted_text).strip()
        cleaned = re.sub(r"\s+", " ", combined)
        return cleaned[:max_chars] if cleaned else "[PDF document: image-based or no extractable text]"
    except Exception as e:
        return f"[PDF document parsing error: {e}]"


def _extract_image_snippet(path: Path) -> str:
    """Extracts metadata and image details using Pillow."""
    if not Image:
        return f"[Image file: {path.suffix.upper()}]"
    try:
        with Image.open(path) as img:
            details = [f"Format: {img.format}", f"Dimensions: {img.width}x{img.height}", f"Color Mode: {img.mode}"]
            info = img.info
            if "description" in info:
                details.append(f"Description: {info['description'][:100]}")
            return f"[Image ({', '.join(details)})]"
    except Exception as e:
        return f"[Image file ({path.suffix.upper()}): {e}]"


def _extract_text_snippet(path: Path, max_chars: int = 500) -> str:
    """Extracts the first max_chars characters from a text or binary file."""
    # Try reading as text with UTF-8
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            chunk = f.read(max_chars)
            # Check ratio of printable characters
            printable_count = sum(1 for c in chunk if c in string.printable)
            if len(chunk) > 0 and (printable_count / len(chunk)) > 0.7:
                return chunk
    except Exception:
        pass

    # Fallback to reading raw bytes and filtering printable characters
    try:
        with open(path, "rb") as f:
            raw_bytes = f.read(max_chars * 2)
            printable_bytes = bytes([b for b in raw_bytes if 32 <= b <= 126 or b in (9, 10, 13)])
            decoded = printable_bytes.decode("ascii", errors="ignore").strip()
            if decoded:
                return decoded[:max_chars]
            return "[Binary content: no printable text detected]"
    except Exception as e:
        return f"[Unable to read file content: {e}]"


def inspect_file(file_path: Path, max_chars: int = 500) -> FileState:
    """Inspects a file on disk and extracts its metadata and text snippet.

    Args:
        file_path: Path to the target file.
        max_chars: Maximum characters of content snippet to extract (default: 500).

    Returns:
        FileState instance containing filename, extension, sizes, and content snippet.
    """
    path = Path(file_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    filename = path.name
    extension = path.suffix.lower()
    size_bytes = path.stat().st_size
    size_human = _format_size(size_bytes)

    # Extract snippet depending on extension type
    if extension == ".pdf":
        snippet = _extract_pdf_snippet(path, max_chars=max_chars)
    elif extension in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff"}:
        snippet = _extract_image_snippet(path)
    else:
        snippet = _extract_text_snippet(path, max_chars=max_chars)

    return FileState(
        path=path,
        filename=filename,
        extension=extension,
        size_bytes=size_bytes,
        size_human=size_human,
        snippet=snippet
    )
