"""No document claims a latency threshold that has not been measured (FR-035e).

**The failure this prevents.** Both figures are acceptance thresholds. Neither has been
measured. The way that quietly stops being true is not a lie — it is a README written in
good faith six weeks later, by someone who read "≤ 2 s p95" in the spec and reported it as
a property of the system. From then on the project claims a measurement it never took, and
the claim is load-bearing: someone plans against it.

So the rule is mechanical. A user-facing document may not describe either threshold as met
while its row in `benchmarks/phase0/GATE.md` reads `NOT RUN`.

**Two ways this check can be useless, and the guard for each:**

* **Vacuous** — it never fires, because its patterns match nothing. Guarded by
  `genuine_claim.md`, a fixture the detector must catch.
* **Self-triggering** — it fires on the documents that *forbid* the claim, since those
  necessarily quote it. That would be worse than useless: it would punish accurate hedging
  and teach people to delete it. Guarded by `quoted_instruction.md`, whose every sentence
  mentions a threshold and none of which claims one.

**Specification and planning artefacts are out of scope.** `spec.md`, `plan.md` and
`tasks.md` state the requirement — "retrieval preview latency MUST meet the 2-second p95" —
which is an instruction, not a status. Scanning them would flag the requirement for being
written down.
"""

from __future__ import annotations

import pathlib
import re
from typing import Final

import pytest

pytestmark = pytest.mark.unit

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]
GATE: Final[pathlib.Path] = REPO / "benchmarks/phase0/GATE.md"
FIXTURES: Final[pathlib.Path] = REPO / "tests/fixtures/gate_claims"

#: User-facing surfaces. Requirements documents are deliberately absent — see the docstring.
SCANNED_FILES: Final[tuple[pathlib.Path, ...]] = (
    REPO / "README.md",
    REPO / "specs/004-permission-aware-rag/verification.md",
)
SCANNED_TREES: Final[tuple[pathlib.Path, ...]] = (REPO / "docs",)

#: Rows in GATE.md, and how a document might name each one.
ROW_SUBJECTS: Final[dict[str, tuple[str, ...]]] = {
    "preview": ("preview", "retrieval", "2-second", "2 second", "2s", "2.0 s", "2 s"),
    "first_token": ("first-token", "first token", "5-second", "5 second", "5s", "5.0 s", "5 s"),
}

#: Verbs that turn a mention into a claim.
_ACHIEVEMENT: Final[re.Pattern[str]] = re.compile(
    r"\b(?:meets?|met|achiev(?:es|ed|ing)|satisf(?:ies|ied)|passes|passed|"
    r"was measured at|is (?:under|below|within)|comes in (?:under|below))\b",
    re.IGNORECASE,
)

#: Anything that makes the sentence a denial, a requirement, or a quotation.
_HEDGE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:not|never|no|none|nor|neither|must|may not|cannot|until|unless|would|"
    r"acceptance threshold|has not been|have not been|NOT RUN|instead|forbid\w*|"
    r"prohibit\w*|requirement|target\b(?=[^.]*\bmust\b))\b",
    re.IGNORECASE,
)


def _sentences(text: str) -> list[str]:
    # Code fences hold example output and command transcripts, not claims about status.
    without_code = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n\s*\n", without_code) if s.strip()]


def claims_in(text: str) -> list[str]:
    """Sentences asserting a threshold was met, with hedged ones excluded."""
    found: list[str] = []
    for sentence in _sentences(text):
        if not _ACHIEVEMENT.search(sentence):
            continue
        if _HEDGE.search(sentence):
            continue
        if any(
            subject.lower() in sentence.lower()
            for subjects in ROW_SUBJECTS.values()
            for subject in subjects
        ):
            found.append(" ".join(sentence.split())[:200])
    return found


def unmeasured_rows() -> set[str]:
    """Rows whose GATE.md status is `NOT RUN`."""
    text = GATE.read_text(encoding="utf-8")
    unmeasured: set[str] = set()
    for row in ROW_SUBJECTS:
        pattern = rf"^\|\s*`?{re.escape(row)}`?\s*\|\s*`?([A-Z_ ]+)`?\s*\|"
        match = re.search(pattern, text, re.MULTILINE)
        assert match, f"GATE.md has no `{row}` row; the gate cannot be read"
        if match.group(1).strip() == "NOT RUN":
            unmeasured.add(row)
    return unmeasured


def _scanned_documents() -> list[pathlib.Path]:
    documents = [path for path in SCANNED_FILES if path.is_file()]
    for tree in SCANNED_TREES:
        if tree.is_dir():
            documents.extend(sorted(tree.rglob("*.md")))
    return documents


class TestTheGateIsReadable:
    def test_the_gate_file_exists(self) -> None:
        assert GATE.is_file(), f"missing {GATE.relative_to(REPO)}"

    def test_both_rows_are_present(self) -> None:
        text = GATE.read_text(encoding="utf-8")
        for row in ROW_SUBJECTS:
            assert re.search(rf"^\|\s*`?{re.escape(row)}`?\s*\|", text, re.MULTILINE), (
                f"GATE.md has no `{row}` row"
            )

    def test_nothing_has_been_measured_yet(self) -> None:
        """States the current, deliberate baseline. When a row genuinely passes, this
        assertion is the one that has to be updated — consciously."""
        assert unmeasured_rows() == {"preview", "first_token"}


class TestTheDetectorIsNotVacuous:
    """Falsification: the detector must catch the claim fixture."""

    def test_the_genuine_claim_fixture_exists(self) -> None:
        assert (FIXTURES / "genuine_claim.md").is_file()

    def test_the_genuine_claim_is_detected(self) -> None:
        found = claims_in((FIXTURES / "genuine_claim.md").read_text(encoding="utf-8"))
        assert found, (
            "the detector found nothing in a fixture written to be caught, so a passing"
            " scan of the real documents proves nothing"
        )

    def test_both_thresholds_are_detectable(self) -> None:
        """One pattern matching would let the other threshold be claimed freely."""
        text = (FIXTURES / "genuine_claim.md").read_text(encoding="utf-8")
        found = " ".join(claims_in(text)).lower()
        assert "2-second" in found or "2 second" in found, f"preview claim missed: {found}"
        assert "first-token" in found or "5-second" in found, f"first-token claim missed: {found}"


class TestTheDetectorIsNotSelfTriggering:
    """The opposite failure: firing on documents that forbid the claim."""

    def test_the_quoted_instruction_fixture_exists(self) -> None:
        assert (FIXTURES / "quoted_instruction.md").is_file()

    def test_prohibitions_and_quotations_are_not_flagged(self) -> None:
        found = claims_in((FIXTURES / "quoted_instruction.md").read_text(encoding="utf-8"))
        assert found == [], (
            "the detector flagged sentences that deny or forbid the claim. A check that"
            " punishes accurate hedging teaches people to delete the hedge:\n  "
            + "\n  ".join(found)
        )


class TestNoDocumentClaimsAnUnmeasuredThreshold:
    def test_the_scan_has_subjects(self) -> None:
        documents = _scanned_documents()
        assert len(documents) >= 3, (
            f"only {len(documents)} document(s) scanned; the assertion below would run"
            " over an almost-empty set"
        )

    def test_no_scanned_document_claims_an_unmeasured_threshold(self) -> None:
        if not unmeasured_rows():
            pytest.skip("both rows are measured; there is nothing left to falsely claim")

        offenders = [
            f"{path.relative_to(REPO)}: {claim}"
            for path in _scanned_documents()
            for claim in claims_in(path.read_text(encoding="utf-8"))
        ]
        assert offenders == [], (
            "a user-facing document describes a latency threshold as met while its"
            f" GATE.md row reads NOT RUN ({sorted(unmeasured_rows())}). Neither figure"
            " has been measured (FR-035e):\n  " + "\n  ".join(offenders)
        )
