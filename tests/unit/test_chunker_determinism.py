"""The chunker produces the same result everywhere, every time (FR-007, SC-007, CHK053).

**Why this is the first chunking test.** Every later guarantee rests on it. A citation
attests that an answer came from a specific span of a specific document; an evaluation
figure compares two runs. Both are meaningless if the same document can chunk differently
on two machines — the citation points at a span that no longer exists, and the comparison
measures the chunker rather than the change under test.

Three ways non-determinism gets in, and one test for each:

* **Run to run** — a mutable default, a cached counter, an accumulating buffer.
* **Process to process** — iteration over a set or dict, whose order follows
  `PYTHONHASHSEED`. This is the one that hides best: it is stable within a process, so a
  test that chunks twice in one interpreter passes while CI fails intermittently.
* **Machine to machine** — locale-dependent case folding, sorting, or number formatting.

The last two are checked in **subprocesses** with the environment varied, because neither
can be reproduced inside the interpreter that is already running.
"""

from __future__ import annotations

import itertools
import json
import os
import pathlib
import subprocess
import sys
from typing import Final

import pytest

from eaios_core.chunking import DEFAULT_CONFIG, chunk_document
from eaios_core.chunking.tokenizer import FixedVocabularyTokenizer

pytestmark = pytest.mark.unit

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]

DOCUMENT_ID: Final[str] = "11111111-2222-3333-4444-555555555555"

#: Structure, several sentences per block, one block long enough to force a split, and
#: mixed punctuation. A single flat paragraph would exercise one code path and pass.
SAMPLE: Final[str] = """# Travel and Expense Policy

All travel must be approved in advance by the employee's direct manager. Approval is
recorded in the travel system, not by email. Requests submitted less than five working
days before departure require director approval as well.

## Reimbursable expenses

Economy airfare, standard rail fare, and mid-tier hotel accommodation are reimbursable.
Meals are reimbursed against receipts up to the daily limit for the destination country;
alcohol is not reimbursable under any circumstances. Ground transport between the airport
and the accommodation is reimbursable, as is transport between the accommodation and the
client site. Personal detours are not.

## Currency and receipts

Expenses incurred in a currency other than the filing entity's functional currency are
converted at the rate published on the date the expense was incurred, and the source of
that rate must be recorded on the claim. Receipts are mandatory for every line above the
minimum threshold, and a claim missing a required receipt is returned rather than partially
approved. Claims must be filed within thirty days of the final day of travel; a claim filed
later requires a written exception from the finance director, who may decline it.
"""


#: Budgets the whole suite runs at.
#:
#: 400 is the settled production bound. It is **not sufficient on its own**: this sample is
#: 313 tokens, so at 400 every section fits in one chunk and the overlap path is never
#: reached. A determinism fault living in overlap selection would pass unnoticed — which is
#: exactly what happened, and what the T014 falsification exposed. The smaller budgets force
#: multi-chunk sections so that boundary *and* overlap selection are both under test.
BUDGETS: Final[tuple[int, ...]] = (400, 120, 60)


def _fingerprint(chunks: list) -> list[dict[str, object]]:  # type: ignore[type-arg]
    """The properties that must not move: order, bounds, text, identity."""
    return [
        {
            "ordinal": c.ordinal,
            "chunk_id": str(c.chunk_id),
            "text": c.text,
            "token_count": c.token_count,
            "start_offset": c.start_offset,
            "end_offset": c.end_offset,
        }
        for c in chunks
    ]


def _chunk_here(budget: int = 400) -> list[dict[str, object]]:
    import dataclasses

    config = dataclasses.replace(DEFAULT_CONFIG, max_tokens=budget)
    return _fingerprint(
        chunk_document(DOCUMENT_ID, SAMPLE, config=config, tokenizer=FixedVocabularyTokenizer())
    )


def _chunk_here_all() -> dict[int, list[dict[str, object]]]:
    return {budget: _chunk_here(budget) for budget in BUDGETS}


#: Chunk the same document in a fresh interpreter, at every budget, as JSON.
_CHILD = """
import dataclasses, json
from eaios_core.chunking import DEFAULT_CONFIG, chunk_document
from eaios_core.chunking.tokenizer import FixedVocabularyTokenizer

SAMPLE = json.loads({sample!r})
out = {{}}
for budget in {budgets!r}:
    config = dataclasses.replace(DEFAULT_CONFIG, max_tokens=budget)
    chunks = chunk_document({doc!r}, SAMPLE, config=config,
                            tokenizer=FixedVocabularyTokenizer())
    out[str(budget)] = [
        {{"ordinal": c.ordinal, "chunk_id": str(c.chunk_id), "text": c.text,
          "token_count": c.token_count, "start_offset": c.start_offset,
          "end_offset": c.end_offset}}
        for c in chunks
    ]
print(json.dumps(out))
"""


def _chunk_in_subprocess(**environment: str) -> dict[int, list[dict[str, object]]]:
    env = {**os.environ, **environment}
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = os.pathsep.join(
        str((REPO / part).resolve())
        for part in ("packages/core/src", "apps/api/src", "services/worker/src", "scripts/seed/src")
    )
    code = _CHILD.format(sample=json.dumps(SAMPLE), doc=DOCUMENT_ID, budgets=list(BUDGETS))
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert result.returncode == 0, f"child failed:\nstdout {result.stdout}\nstderr {result.stderr}"
    return {int(k): v for k, v in json.loads(result.stdout).items()}


class TestTheFixtureHasSubstance:
    """A determinism test over one trivial chunk passes without meaning anything."""

    @pytest.mark.parametrize("budget", BUDGETS)
    def test_the_sample_produces_several_chunks(self, budget: int) -> None:
        chunks = _chunk_here(budget)
        assert len(chunks) >= 3, (
            f"at budget {budget} the sample produced {len(chunks)} chunk(s); with fewer"
            " than three there is no boundary placement to be deterministic about"
        )

    def test_at_least_one_budget_exercises_overlap(self) -> None:
        """The guard the T014 falsification added.

        Determinism over boundary *selection* says nothing about determinism over overlap
        *selection* if no pair of chunks ever overlaps. At 400 tokens this 313-token
        sample fits each section in one chunk and produces none.
        """
        overlapping = {
            budget: sum(
                1
                for a, b in itertools.pairwise(chunks)
                if int(b["start_offset"]) < int(a["end_offset"])  # type: ignore[call-overload]
            )
            for budget, chunks in _chunk_here_all().items()
        }
        assert sum(overlapping.values()) > 0, (
            "no budget produced a single overlapping pair, so every assertion in this"
            f" file is blind to the overlap path: {overlapping}"
        )

    @pytest.mark.parametrize("budget", BUDGETS)
    def test_the_chunks_carry_distinct_identifiers(self, budget: int) -> None:
        ids = [c["chunk_id"] for c in _chunk_here(budget)]
        assert len(set(ids)) == len(ids), f"duplicate chunk identifiers: {ids}"


class TestSameProcess:
    def test_two_calls_agree(self) -> None:
        assert _chunk_here_all() == _chunk_here_all(), (
            "two calls in one process disagreed, so the chunker carries state between invocations"
        )

    def test_a_third_call_after_other_work_agrees(self) -> None:
        """Guards against a lazily built cache that is populated by the first call."""
        first = _chunk_here_all()
        for _ in range(3):
            chunk_document(
                "99999999-9999-9999-9999-999999999999",
                "Unrelated content. Entirely different sentences here.",
                config=DEFAULT_CONFIG,
                tokenizer=FixedVocabularyTokenizer(),
            )
        assert _chunk_here_all() == first, "chunking an unrelated document changed the result"


class TestAcrossProcesses:
    """`PYTHONHASHSEED` changes set and dict iteration order between interpreters."""

    def test_two_hash_seeds_agree(self) -> None:
        first = _chunk_in_subprocess(PYTHONHASHSEED="0")
        second = _chunk_in_subprocess(PYTHONHASHSEED="12345")
        assert first == second, (
            "the chunker depends on hash iteration order, so its output changes between"
            " interpreters. This passes locally and fails intermittently in CI"
        )

    def test_many_hash_seeds_agree(self) -> None:
        """One alternative seed can coincide with the baseline; several rarely do."""
        baseline = _chunk_here_all()
        for seed in ("1", "3", "9", "1000"):
            assert _chunk_in_subprocess(PYTHONHASHSEED=seed) == baseline, (
                f"chunking under PYTHONHASHSEED={seed} differed from this process"
            )

    def test_the_subprocess_agrees_with_this_process(self) -> None:
        assert _chunk_in_subprocess(PYTHONHASHSEED="7") == _chunk_here_all()


#: Locale names to try, most-different first. Two must actually apply or the class fails.
_LOCALE_CANDIDATES: Final[tuple[str, ...]] = (
    "tr_TR.UTF-8",
    "Turkish_Turkey.1254",
    "de_DE.UTF-8",
    "German_Germany.1252",
    "en_US.UTF-8",
    "English_United States.1252",
    "C",
)

#: Text chosen for locale sensitivity, not for prose. Dotted/dotless I is the classic
#: case-folding divergence; the German sharp s and the accented forms exercise collation
#: and normalization paths that a naive implementation routes through the C library.
_UNICODE_SAMPLE: Final[str] = (
    "# İstanbul Ilıca ISSUE\n\n"
    "Işık ışıldar ve İdare işleri İZLER. Straße Grüße ÄÖÜ äöü ß SS.\n"
    "Ünal Çelik reviewed the ΣΊΣΥΦΟΣ file. Ångström ångström AA aa.\n\n"
    "## İkinci Bölüm\n\n"
    "Diğer işlemler ILGILI birimlere iletilir. Café CAFÉ café naïve NAÏVE.\n"
)

#: Chunk in a child that *actually applies* the locale. Setting `LC_ALL` alone does not:
#: Python starts in the C locale and only honours the environment when something calls
#: `setlocale`. The previous version of this class set the variable and nothing else, so
#: all four cases passed without exercising a single locale-dependent code path.
_LOCALE_CHILD = """
import dataclasses, json, locale, sys

requested = {locale!r}
try:
    applied = locale.setlocale(locale.LC_ALL, requested)
except locale.Error:
    print(json.dumps({{"applied": None}}))
    sys.exit(0)

from eaios_core.chunking import DEFAULT_CONFIG, chunk_document
from eaios_core.chunking.tokenizer import FixedVocabularyTokenizer

SAMPLE = json.loads({sample!r})
out = {{}}
for budget in {budgets!r}:
    config = dataclasses.replace(DEFAULT_CONFIG, max_tokens=budget)
    chunks = chunk_document({doc!r}, SAMPLE, config=config,
                            tokenizer=FixedVocabularyTokenizer())
    out[str(budget)] = [
        {{"ordinal": c.ordinal, "chunk_id": str(c.chunk_id), "text": c.text,
          "token_count": c.token_count, "start_offset": c.start_offset,
          "end_offset": c.end_offset}}
        for c in chunks
    ]
print(json.dumps({{"applied": applied, "chunks": out}}))
"""


def _chunk_under_locale(name: str, sample: str) -> dict[str, object] | None:
    """Chunk `sample` in a child that applies `name`; None if the locale is unavailable."""
    env = {**os.environ}
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = os.pathsep.join(
        str((REPO / part).resolve())
        for part in ("packages/core/src", "apps/api/src", "services/worker/src", "scripts/seed/src")
    )
    code = _LOCALE_CHILD.format(
        locale=name, sample=json.dumps(sample), doc=DOCUMENT_ID, budgets=list(BUDGETS)
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert result.returncode == 0, f"child failed:\n{result.stdout}\n{result.stderr}"
    payload = json.loads(result.stdout)
    return payload if payload.get("applied") else None


class TestAcrossLocales:
    """Locale changes case folding, collation and number formatting — where it applies.

    Every case here **calls `setlocale`** in the child. Setting `LC_ALL` and nothing else
    leaves Python in the C locale, which is how the earlier version of this class passed
    four cases while exercising none.
    """

    @pytest.fixture(scope="class")
    def applied(self) -> dict[str, dict[str, object]]:
        results: dict[str, dict[str, object]] = {}
        for name in _LOCALE_CANDIDATES:
            payload = _chunk_under_locale(name, _UNICODE_SAMPLE)
            if payload is not None:
                results[str(payload["applied"])] = payload["chunks"]  # type: ignore[index]
        return results

    def test_at_least_two_distinct_locales_were_exercised(
        self, applied: dict[str, dict[str, object]]
    ) -> None:
        """The guard. One locale proves nothing; zero proves less."""
        assert len(applied) >= 2, (
            "fewer than two locales actually applied, so this class compared a result"
            f" with itself: applied {sorted(applied)}"
        )

    def test_every_applied_locale_produces_the_same_chunks(
        self, applied: dict[str, dict[str, object]]
    ) -> None:
        names = sorted(applied)
        baseline_name = names[0]
        baseline = applied[baseline_name]
        for name in names[1:]:
            assert applied[name] == baseline, (
                f"chunking under locale {name!r} differed from {baseline_name!r}. The"
                " chunker is reaching a locale-sensitive operation — case folding,"
                " collation, or number formatting"
            )

    def test_the_unicode_sample_is_actually_locale_sensitive(self) -> None:
        """Falsification of the fixture: a sample with no such characters proves nothing."""
        assert "İ" in _UNICODE_SAMPLE and "ı" in _UNICODE_SAMPLE, (
            "the sample no longer contains dotted/dotless I, the classic case-folding"
            " divergence this class exists to catch"
        )
        assert "ß" in _UNICODE_SAMPLE

    def test_the_unicode_sample_chunks_to_something(self) -> None:
        import dataclasses

        chunks = chunk_document(
            DOCUMENT_ID,
            _UNICODE_SAMPLE,
            config=dataclasses.replace(DEFAULT_CONFIG, max_tokens=60),
            tokenizer=FixedVocabularyTokenizer(),
        )
        assert len(chunks) >= 2, f"the Unicode sample produced {len(chunks)} chunk(s)"
