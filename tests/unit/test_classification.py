"""Data classification levels (spec FR-010a, FR-010b).

Exactly four levels. The set is closed because storage keys, vector payloads, and
every future authorization rule are written against it — a fifth level appearing by
accident would be a silent widening of what "restricted" means.
"""

from __future__ import annotations

import pytest

from eaios_core.classification import Classification

pytestmark = pytest.mark.unit


class TestClosedSet:
    def test_exactly_four_levels(self) -> None:
        assert len(Classification) == 4

    def test_the_four_levels_are_the_specified_ones(self) -> None:
        assert {c.value for c in Classification} == {
            "PUBLIC",
            "INTERNAL",
            "CONFIDENTIAL",
            "RESTRICTED",
        }

    @pytest.mark.parametrize("bad", ["SECRET", "public", "Internal", "", "TOP_SECRET"])
    def test_unrecognized_values_are_rejected(self, bad: str) -> None:
        with pytest.raises(ValueError):
            Classification(bad)


class TestOrdering:
    def test_levels_are_ordered_by_sensitivity(self) -> None:
        assert (
            Classification.PUBLIC
            < Classification.INTERNAL
            < Classification.CONFIDENTIAL
            < Classification.RESTRICTED
        )

    def test_public_is_the_least_sensitive(self) -> None:
        assert min(Classification) is Classification.PUBLIC

    def test_restricted_is_the_most_sensitive(self) -> None:
        assert max(Classification) is Classification.RESTRICTED

    def test_at_least_as_sensitive_as(self) -> None:
        assert Classification.RESTRICTED.at_least(Classification.CONFIDENTIAL)
        assert not Classification.INTERNAL.at_least(Classification.CONFIDENTIAL)


class TestPublicSemantics:
    def test_only_public_is_anonymously_visible(self) -> None:
        """The public site may render exactly one level and no other."""
        visible = [c for c in Classification if c.is_public]
        assert visible == [Classification.PUBLIC]

    def test_restricted_requires_more_than_a_role(self) -> None:
        """FR-010a — RESTRICTED needs an explicit grant beyond role alone."""
        assert Classification.RESTRICTED.requires_explicit_grant
        assert not Classification.CONFIDENTIAL.requires_explicit_grant
