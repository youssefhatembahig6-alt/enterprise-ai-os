"""The sentence-aware chunker (FR-007, FR-007a, FR-008, FR-009).

Boundary placement, in the order FR-007a states it:

1. **Structure first.** A heading opens a section; the section's text is packed into
   chunks, and a chunk never crosses into the next section. Section boundaries are
   semantic boundaries — the paragraph after a heading answers a different question from
   the paragraph before it.
2. **Sentence boundaries within the budget.** Sentences are packed until the next one
   would not fit.
3. **Never split a sentence**, unless one sentence alone exceeds the budget. This is the
   rule that protects grounding: a fragment cut mid-clause can invert its source's
   meaning, and a citation would then attest to something the document does not say — a
   failure that reads as a success.
4. **The oversized-sentence exception** cuts at the nearest preceding clause boundary, or
   at whitespace when no clause boundary is available. Never mid-word, never by character
   count, and always at the same place on every machine.
5. **No empty or whitespace-only chunk.** Such a chunk embeds to a vector that matches
   everything weakly and nothing meaningfully.

**A chunk is a span, not a rebuilt string.** Every chunk is `normalized[start:end]` —
a verbatim, contiguous slice of the normalized document. Overlap is expressed by
neighbouring spans overlapping, not by copying text between them. This is what lets a
citation quote an exact excerpt span and have that span resolve back into the source
document (FR-028b3); a chunk reassembled by joining sentences with single spaces cannot be
located in the document it came from, and its offsets would be fiction.

**Determinism** (FR-007) is a structural property of this module, not a test result. There
is no iteration over a set or dict, no locale-sensitive operation, no wall-clock read, and
no randomness. Every function here maps its inputs to exactly one output.
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
import unicodedata
import uuid
from typing import Final

from .config import ChunkerConfig
from .tokenizer import Tokenizer

__all__ = ["Chunk", "chunk_document", "normalize"]

#: A markdown-style heading line. Headings open sections rather than joining paragraphs.
_HEADING: Final[re.Pattern[str]] = re.compile(r"^\s{0,3}#{1,6}\s+\S")

#: A blank line separates paragraphs within a section.
_PARAGRAPH_BREAK: Final[re.Pattern[str]] = re.compile(r"\n[ \t]*\n")

#: Sentence end: terminal punctuation followed by whitespace. Abbreviations are not
#: special-cased on purpose — a wrong split at "Dr. Smith" costs one boundary, while an
#: abbreviation list is a locale-shaped guess that changes behaviour by machine.
_SENTENCE_SPLIT: Final[re.Pattern[str]] = re.compile(r"(?<=[.!?])\s+")

#: Clause boundaries, preferred over whitespace when an oversized sentence must be cut.
_CLAUSE: Final[tuple[str, ...]] = (", ", "; ", ": ", " — ", " – ")

#: A half-open character span into the normalized document.
_Span = tuple[int, int]


@dataclasses.dataclass(frozen=True, slots=True)
class Chunk:
    """One indexed unit of a document.

    `text` is exactly `normalized_document[start_offset:end_offset]`, which is what makes
    a citation's excerpt span resolvable back into the source.
    """

    chunk_id: uuid.UUID
    ordinal: int
    text: str
    token_count: int
    start_offset: int
    end_offset: int
    normalized_content_hash: str


def normalize(content: str) -> str:
    """Normalize a document to the form chunking, hashing and offsets all operate on.

    NFC, then line endings, then trailing whitespace per line. Applied before anything
    else so that the same document saved on Windows and on Linux — or typed with a
    combining accent instead of a precomposed one — produces identical chunks, identical
    offsets and identical identifiers (FR-007).
    """
    text = unicodedata.normalize("NFC", content)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n"))


def _content_hash(normalized: str) -> str:
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _chunk_id(
    document_id: str, content_hash: str, ordinal: int, config: ChunkerConfig
) -> uuid.UUID:
    """Derive a chunk identifier from the document, the text, and the procedure (FR-007b).

    The last four inputs are what make "identical identifiers" mean *produced the same
    way* rather than *the text matched*. Without them two chunk generations computed under
    different tokenizers or bounds would be indistinguishable in the index.
    """
    payload = "‖".join(
        (
            document_id,
            content_hash,
            str(ordinal),
            config.tokenizer_identity,
            str(config.max_tokens),
            str(config.overlap_tokens),
            config.chunker_version,
        )
    )
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return uuid.UUID(bytes=digest[:16], version=5)


def _trim(text: str, span: _Span) -> _Span | None:
    """Shrink a span past leading and trailing whitespace; None if nothing is left."""
    start, end = span
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return (start, end) if end > start else None


def _section_spans(text: str) -> list[_Span]:
    """Spans covering each section. A heading line opens a new one."""
    paragraphs: list[_Span] = []
    cursor = 0
    for match in _PARAGRAPH_BREAK.finditer(text):
        paragraphs.append((cursor, match.start()))
        cursor = match.end()
    paragraphs.append((cursor, len(text)))

    sections: list[_Span] = []
    current: _Span | None = None
    for raw in paragraphs:
        span = _trim(text, raw)
        if span is None:
            continue
        if _HEADING.match(text[span[0] : span[1]].split("\n", 1)[0]):
            if current is not None:
                sections.append(current)
            # The heading leads its section. Keeping it attached rather than emitting it
            # alone means the first chunk of a section carries the context that names it,
            # instead of a one-line chunk that retrieves for every query and answers none.
            current = span
        elif current is None:
            current = span
        else:
            current = (current[0], span[1])
    if current is not None:
        sections.append(current)
    return sections


def _sentence_spans(text: str, section: _Span) -> list[_Span]:
    """Sentence spans inside one section, paragraph by paragraph."""
    lo, hi = section
    blocks: list[_Span] = []
    cursor = lo
    for match in _PARAGRAPH_BREAK.finditer(text, lo, hi):
        blocks.append((cursor, match.start()))
        cursor = match.end()
    blocks.append((cursor, hi))

    spans: list[_Span] = []
    for raw_block in blocks:
        block = _trim(text, raw_block)
        if block is None:
            continue
        start = block[0]
        for match in _SENTENCE_SPLIT.finditer(text, block[0], block[1]):
            candidate = _trim(text, (start, match.start()))
            if candidate:
                spans.append(candidate)
            start = match.end()
        tail = _trim(text, (start, block[1]))
        if tail:
            spans.append(tail)
    return spans


def _split_oversized(text: str, span: _Span, budget: int, tokenizer: Tokenizer) -> list[_Span]:
    """Cut one over-budget sentence at clause boundaries, falling back to whitespace.

    Deterministic by construction: it always takes the *last* admissible boundary at or
    before the budget, so the same sentence cuts in the same place everywhere.
    """
    pieces: list[_Span] = []
    start, end = span

    while start < end and tokenizer.count(text[start:end]) > budget:
        cut = _last_boundary_within_budget(text, (start, end), budget, tokenizer)
        if cut is None or cut <= start:  # pragma: no cover - one word over budget
            break
        piece = _trim(text, (start, cut))
        if piece:
            pieces.append(piece)
        start = cut

    tail = _trim(text, (start, end))
    if tail:
        pieces.append(tail)
    return pieces


def _last_boundary_within_budget(
    text: str, span: _Span, budget: int, tokenizer: Tokenizer
) -> int | None:
    """Offset of the best cut: the latest clause boundary within budget, else whitespace."""
    lo, hi = span
    best_clause: int | None = None

    for marker in _CLAUSE:
        cursor = lo
        while True:
            found = text.find(marker, cursor, hi)
            if found == -1:
                break
            boundary = found + len(marker)
            if tokenizer.count(text[lo:boundary]) <= budget:
                best_clause = boundary if best_clause is None else max(best_clause, boundary)
            cursor = boundary

    if best_clause is not None:
        return best_clause

    best_space: int | None = None
    for match in re.finditer(r"\s+", text[lo:hi]):
        boundary = lo + match.start()
        if tokenizer.count(text[lo:boundary]) <= budget:
            best_space = boundary
        else:
            break
    return best_space


def _overlap_start(
    text: str, sentences: list[_Span], last: int, budget: int, tokenizer: Tokenizer
) -> int:
    """Index of the first sentence the next chunk repeats.

    Complete sentences only. A partial-sentence overlap would reintroduce, through the
    back door, exactly the mid-sentence fragment rule 3 exists to prevent.
    """
    if budget <= 0:
        return last + 1
    first = last + 1
    for index in range(last, -1, -1):
        span = (sentences[index][0], sentences[last][1])
        if tokenizer.count(text[span[0] : span[1]]) > budget:
            break
        first = index
    return first


def chunk_document(
    document_id: str,
    content: str,
    *,
    config: ChunkerConfig,
    tokenizer: Tokenizer,
) -> list[Chunk]:
    """Chunk one document deterministically.

    Args:
        document_id: Owning document's identity; part of every chunk identifier.
        content: Raw document text.
        config: Settled bounds and versions.
        tokenizer: Counts tokens; its identity enters every chunk identifier.

    Returns:
        Chunks in document order, each a verbatim span of the normalized document.
        Empty for empty or whitespace-only input.
    """
    normalized = normalize(content)
    if not normalized.strip():
        return []

    content_hash = _content_hash(normalized)
    spans: list[_Span] = []

    for section in _section_spans(normalized):
        sentences = _sentence_spans(normalized, section)
        index = 0
        while index < len(sentences):
            if tokenizer.count(normalized[sentences[index][0] : sentences[index][1]]) > (
                config.max_tokens
            ):
                # Rule 3's single exception. Its pieces stand alone: a fragment must never
                # become a neighbour's overlap, or the mid-sentence text this rule exists
                # to contain would leak into an intact chunk.
                spans.extend(
                    _split_oversized(normalized, sentences[index], config.max_tokens, tokenizer)
                )
                index += 1
                continue

            last = index
            while last + 1 < len(sentences):
                candidate = (sentences[index][0], sentences[last + 1][1])
                if tokenizer.count(normalized[candidate[0] : candidate[1]]) > config.max_tokens:
                    break
                if (
                    tokenizer.count(normalized[sentences[last + 1][0] : sentences[last + 1][1]])
                    > config.max_tokens
                ):
                    break
                last += 1

            spans.append((sentences[index][0], sentences[last][1]))

            # Overlap exists to give the *next* chunk its lead-in. With nothing left to
            # lead into, applying it would emit a chunk wholly contained in the one just
            # appended — a duplicate that doubles the index and retrieves against itself.
            if last + 1 >= len(sentences):
                break

            following = _overlap_start(
                normalized, sentences, last, config.overlap_tokens, tokenizer
            )
            # Never rewind to where we started, or the loop cannot terminate.
            index = following if following > index else last + 1

    return [
        Chunk(
            chunk_id=_chunk_id(document_id, content_hash, ordinal, config),
            ordinal=ordinal,
            text=normalized[start:end],
            token_count=tokenizer.count(normalized[start:end]),
            start_offset=start,
            end_offset=end,
            normalized_content_hash=content_hash,
        )
        for ordinal, (start, end) in enumerate(spans)
        if normalized[start:end].strip()
    ]
