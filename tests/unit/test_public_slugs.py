"""Detail-page addresses are stable and unique (spec 002 FR-004).

FR-004 requires human-readable addresses that do not move between seed runs. The
dataset has no slug column, so slugs are derived — which makes the derivation
itself the thing that has to be deterministic.

The suffix is the part worth testing hardest. Feature 001 generates repeated
vacancy titles across offices, so collisions are known to occur here rather than
being hypothetical, and a positional counter would depend on iteration order —
the class of non-determinism that feature spent five convergence passes removing.
"""

from __future__ import annotations

import pytest

from eaios_api.public.slugs import MAX_KEBAB, SUFFIX_LENGTH, derive_slug, kebab, slug_suffix

pytestmark = pytest.mark.unit


class TestKebab:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Operations Analyst", "operations-analyst"),
            ("Chief of Staff", "chief-of-staff"),
            ("  Padded  Title  ", "padded-title"),
            ("Multi--Hyphen___Mess", "multi-hyphen-mess"),
            ("Q4 2026 Results!", "q4-2026-results"),
        ],
    )
    def test_produces_readable_addresses(self, text: str, expected: str) -> None:
        assert kebab(text) == expected

    def test_diacritics_are_normalised(self) -> None:
        """Generated names include Arabic-derived Latin spellings. Two spellings of
        the same name that differ only by composition must not produce different
        addresses."""
        assert kebab("Farida Mansoúr") == kebab("Farida Mansour")

    def test_long_text_is_cut_on_a_word_boundary(self) -> None:
        long = "Senior Principal Distinguished Engineering Manager For Platform Reliability"
        result = kebab(long)
        assert len(result) <= MAX_KEBAB
        assert not result.endswith("-")
        # Cut between words, not mid-word.
        assert long.lower().replace(" ", "-").startswith(result)

    def test_punctuation_only_text_yields_nothing(self) -> None:
        assert kebab("!!! ???") == ""


class TestSuffix:
    def test_is_stable_for_the_same_record(self) -> None:
        first = slug_suffix("vacancy", "niletech", "Analyst:Cairo:2026-01-01")
        second = slug_suffix("vacancy", "niletech", "Analyst:Cairo:2026-01-01")
        assert first == second

    def test_has_the_declared_length(self) -> None:
        assert len(slug_suffix("news", "niletech", "anything")) == SUFFIX_LENGTH

    def test_differs_for_different_records(self) -> None:
        a = slug_suffix("vacancy", "niletech", "Analyst:Cairo:2026-01-01")
        b = slug_suffix("vacancy", "niletech", "Analyst:Dubai:2026-01-01")
        assert a != b

    def test_differs_across_tenants(self) -> None:
        """The same title in the other tenant must not produce the same address —
        otherwise a NileTech slug could resolve against Delta content."""
        assert slug_suffix("news", "niletech", "Launch") != slug_suffix(
            "news", "delta-retail", "Launch"
        )

    def test_differs_across_entity_types(self) -> None:
        assert slug_suffix("news", "niletech", "X") != slug_suffix("vacancy", "niletech", "X")


class TestDeriveSlug:
    def test_combines_text_and_suffix(self) -> None:
        slug = derive_slug("vacancy", "niletech", "Analyst:Cairo:2026-01-01", "Analyst Cairo")
        assert slug.startswith("analyst-cairo-")
        assert len(slug.rsplit("-", 1)[1]) == SUFFIX_LENGTH

    def test_identical_titles_get_different_addresses(self) -> None:
        """The reason the suffix exists. Feature 001 really does generate the same
        vacancy title in more than one office."""
        cairo = derive_slug("vacancy", "niletech", "Analyst:Cairo:2026-01-01", "Analyst")
        dubai = derive_slug("vacancy", "niletech", "Analyst:Dubai:2026-01-01", "Analyst")
        assert cairo != dubai
        assert cairo.startswith("analyst-") and dubai.startswith("analyst-")

    def test_untitled_records_still_get_an_address(self) -> None:
        """A headline of only punctuation would otherwise produce an empty path
        segment, which is not a URL."""
        slug = derive_slug("news", "niletech", "key", "!!!")
        assert slug and "/" not in slug
        assert len(slug) == SUFFIX_LENGTH

    def test_addresses_are_url_safe(self) -> None:
        slug = derive_slug("news", "niletech", "k", "Ahmed's “Big” Announcement — 50% Growth!")
        assert all(c.isalnum() or c == "-" for c in slug)


class TestDeterminismAcrossProcesses:
    def test_the_suffix_is_a_pure_function_of_its_inputs(self) -> None:
        """No clock, no randomness, no environment. This is what makes a shared
        link still work after a reseed."""
        expected = slug_suffix("news", "niletech", "2026-06-01:Launch")
        for _ in range(5):
            assert slug_suffix("news", "niletech", "2026-06-01:Launch") == expected
