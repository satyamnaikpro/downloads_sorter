"""Jev Classifier Module integrating the TypeSafe Jev SDK for System One decision-making."""

from __future__ import annotations
import os
import re
from dataclasses import dataclass
from typing import Dict, Any, Optional
from dotenv import load_dotenv

try:
    from typesafe_sdk import Choice, TypeSafeClient, SystemOneResponse, ChoiceAnswer, Usage
    TYPESAFE_SDK_AVAILABLE = True
except ImportError:
    TYPESAFE_SDK_AVAILABLE = False

    @dataclass
    class Choice:
        instructions: str
        criteria: Dict[str, str]
        type: str = "choice"

    @dataclass
    class ChoiceAnswer:
        choice: str
        confidence: float
        probabilities: Dict[str, float]

    @dataclass
    class Usage:
        input_tokens: int = 0
        output_tokens: int = 0

    @dataclass
    class SystemOneResponse:
        model: str
        usage: Usage
        choices: Dict[str, ChoiceAnswer] = None
        answers: Dict[str, ChoiceAnswer] = None

        def __post_init__(self):
            if self.choices is None and self.answers is not None:
                self.choices = self.answers
            elif self.answers is None and self.choices is not None:
                self.answers = self.choices
            elif self.choices is None and self.answers is None:
                self.choices = {}
                self.answers = {}

    class TypeSafeClient:
        def __init__(self, **kwargs):
            pass

        def system_one(self, *args, **kwargs):
            raise NotImplementedError("typesafe-sdk is not installed. Install via: pip install typesafe-sdk")

from config import CATEGORIES, DEFAULT_JEV_MODEL
from file_inspector import FileState

# Load environment variables (.env file if present)
load_dotenv()


@dataclass
class ClassificationResult:
    """Encapsulates the typed decision returned by Jev."""
    category: str
    confidence: float
    probabilities: Dict[str, float]
    raw_response: SystemOneResponse
    is_simulated: bool

    def summary(self) -> str:
        pct = self.confidence * 100
        sim_tag = " (Simulated/Fallback Mode)" if self.is_simulated else " (Live Jev Model)"
        return f"[{self.category}] with {pct:.1f}% confidence{sim_tag}"


class JevClassifier:
    """Manages interactions with the Jev System One model via the typesafe-sdk."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, force_mock: bool = False):
        """Initializes the Jev classifier client.

        Args:
            api_key: Optional API key. If not provided, checks TYPESAFE_API_KEY or JEV_API_KEY.
            base_url: Optional API endpoint (e.g., https://api.typesafe.ai or OpenRouter).
            force_mock: If True, forces local simulation without calling the remote API.
        """
        self.force_mock = force_mock
        self.api_key = api_key or os.getenv("TYPESAFE_API_KEY") or os.getenv("JEV_API_KEY")
        self.base_url = base_url or os.getenv("TYPESAFE_BASE_URL")
        self.model = os.getenv("TYPESAFE_DEFAULT_MODEL", DEFAULT_JEV_MODEL)
        self.client: Optional[TypeSafeClient] = None

        if not self.force_mock and self.api_key:
            client_kwargs: Dict[str, Any] = {"api_key": self.api_key}
            if self.base_url:
                client_kwargs["base_url"] = self.base_url
            try:
                self.client = TypeSafeClient(**client_kwargs)
            except Exception as e:
                print(f"[Warning] Could not initialize TypeSafeClient ({e}). Falling back to simulation.")
                self.client = None

    def build_question(self) -> Choice:
        """Constructs the Jev Choice question primitive with criteria."""
        return Choice(
            instructions=(
                "Examine the file metadata (filename, extension, size) and content snippet. "
                "Classify this file into exactly one target folder category: "
                "Invoices, Screenshots, Code, Resumes, or Misc."
            ),
            criteria=CATEGORIES
        )

    def classify_file_state(self, file_state: FileState) -> ClassificationResult:
        """Evaluates file state using Jev's System One model.

        Args:
            file_state: Extracted FileState object.

        Returns:
            ClassificationResult containing the typed category choice and confidence.
        """
        state_payload = file_state.to_state_payload()
        question = self.build_question()

        if self.client is not None:
            try:
                # Call Jev System One model via SDK
                response: SystemOneResponse = self.client.system_one(
                    state=state_payload,
                    questions={"folder": question},
                    model=self.model
                )
                if hasattr(response, "choices") and response.choices and "folder" in response.choices:
                    choice_answer: ChoiceAnswer = response.choices["folder"]
                elif hasattr(response, "answers") and response.answers and "folder" in response.answers:
                    choice_answer: ChoiceAnswer = response.answers["folder"]
                else:
                    choice_answer: ChoiceAnswer = response.choices["folder"]
                return ClassificationResult(
                    category=choice_answer.choice,
                    confidence=choice_answer.confidence,
                    probabilities=choice_answer.probabilities,
                    raw_response=response,
                    is_simulated=False
                )
            except Exception as e:
                print(f"[Warning] Remote Jev API call failed ({e}). Using local decision fallback.")

        # Fallback / Mock simulation mode
        return self._simulate_system_one_decision(file_state)

    def _simulate_system_one_decision(self, file_state: FileState) -> ClassificationResult:
        """Heuristic decision generator producing a valid typed SystemOneResponse."""
        fn = file_state.filename.lower()
        ext = file_state.extension.lower()
        snippet = file_state.snippet.lower()
        combined = f"{fn} {snippet}"

        code_exts = {
            ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".scss", ".json",
            ".yml", ".yaml", ".sh", ".bash", ".sql", ".rs", ".go", ".c", ".cpp",
            ".h", ".hpp", ".java", ".kt", ".rb", ".php", ".xml", ".toml"
        }
        image_exts = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

        scores: Dict[str, float] = {k: 0.05 for k in CATEGORIES}

        # 1. Code detection
        if ext in code_exts:
            scores["Code"] += 0.85
        elif any(kw in snippet for kw in ["def ", "function ", "import ", "const ", "var ", "class ", "select *", "<html>"]):
            scores["Code"] += 0.65

        # 2. Screenshots detection
        if (ext in image_exts and any(kw in fn for kw in ["screenshot", "screen shot", "snip", "cleanshot", "capture", "screencap"])) or (
            ext in image_exts and re.search(r"\d{4}[-_]\d{2}[-_]\d{2}", fn)
        ):
            scores["Screenshots"] += 0.88
        elif ext in image_exts:
            scores["Screenshots"] += 0.40

        # 3. Invoices detection
        invoice_keywords = [
            "invoice", "receipt", "billing", "billed to", "tax invoice", "amount due",
            "subtotal", "payment receipt", "statement of account", "po number", "order confirmation"
        ]
        invoice_matches = sum(1 for kw in invoice_keywords if kw in combined)
        if invoice_matches > 0:
            scores["Invoices"] += min(0.92, 0.45 + (invoice_matches * 0.15))

        # 4. Resumes detection
        resume_keywords = [
            "resume", "curriculum vitae", "education", "experience", "work experience",
            "skills", "employment history", "professional summary", "bachelor of", "master of", "github.com/"
        ]
        resume_matches = sum(1 for kw in resume_keywords if kw in combined)
        if ext in {".pdf", ".docx", ".doc", ".txt"} and resume_matches > 0:
            scores["Resumes"] += min(0.93, 0.40 + (resume_matches * 0.15))

        # Normalize probabilities
        total = sum(scores.values())
        probabilities = {k: round(v / total, 4) for k, v in scores.items()}

        # Pick top choice
        best_choice = max(probabilities.items(), key=lambda item: item[1])
        choice_name = best_choice[0]
        confidence = best_choice[1]

        # Construct genuine typed SystemOneResponse and ChoiceAnswer
        answer = ChoiceAnswer(
            choice=choice_name,
            confidence=confidence,
            probabilities=probabilities
        )
        try:
            simulated_response = SystemOneResponse(
                model=f"{self.model}-simulated",
                usage=Usage(input_tokens=len(file_state.to_state_payload()) // 4, output_tokens=1),
                choices={"folder": answer},
                answers={"folder": answer}
            )
        except TypeError:
            try:
                simulated_response = SystemOneResponse(
                    model=f"{self.model}-simulated",
                    usage=Usage(input_tokens=len(file_state.to_state_payload()) // 4, output_tokens=1),
                    choices={"folder": answer}
                )
            except TypeError:
                simulated_response = SystemOneResponse(
                    model=f"{self.model}-simulated",
                    usage=Usage(input_tokens=len(file_state.to_state_payload()) // 4, output_tokens=1),
                    answers={"folder": answer}
                )

        return ClassificationResult(
            category=choice_name,
            confidence=confidence,
            probabilities=probabilities,
            raw_response=simulated_response,
            is_simulated=True
        )
