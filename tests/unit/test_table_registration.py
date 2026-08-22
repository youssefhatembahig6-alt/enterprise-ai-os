"""A Feature 004 table is registered the moment it exists, not later (Principle IX).

Two registries have to learn about every new table, and both are easy to forget because
forgetting them is silent:

* `POST_BASELINE_TABLES` (`eaios_core.models`) says "migration 0001 does not create this".
  A table absent from it makes `baseline_tables()` claim the baseline owns something it
  does not, and `tests/integration/test_migrations.py` then expects a fresh
  `alembic upgrade head` to create it twice.
* `RUNTIME_TABLES` (`eaios_seed.loaders.stores`) says "`reset_all` must truncate this".
  A table absent from it survives a reset, so a row written before seeding leaves the
  environment non-empty in a way the pre-flight cannot see — the exact state FR-014
  exists to refuse.

**Why this is a test and not eight entries added now.** The original plan added all eight
names to both registries during Phase 1, before any of the tables existed. That inverts the
failure: `reset_all` would `TRUNCATE` tables that are not there, and the emptiness
pre-flight would count a table it cannot query. The registration has to happen *with* the
model — T057, T078, T138, T193 — and this file is what makes forgetting it fail
immediately rather than three phases later.

So the invariant runs in both directions, and the direction that catches a **stale**
registry matters as much as the one that catches a missing entry: a name registered for a
table that was renamed or never built is a truncation of nothing and a claim about a
migration that does not exist.

**It is vacuous today, and says so.** None of the eight exist yet, so every assertion below
passes over an empty set. `TestTheDetectorFires` plants a real table in the metadata and
requires each gap to be reported — without it, this file would keep passing if the checks
were replaced with `pass`.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Final

import pytest
import sqlalchemy as sa

from eaios_core.models import POST_BASELINE_TABLES, Base
from eaios_seed.loaders.stores import RUNTIME_TABLES

pytestmark = pytest.mark.unit

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
VERSIONS: Final[Path] = REPO_ROOT / "apps" / "api" / "alembic" / "versions"

#: The eight, derived from `data-model.md` rather than invented. `conversations` and
#: `conversation_turns` sit under one heading there, which is how the count was once
#: read as seven.
FEATURE_004_TABLES: Final[frozenset[str]] = frozenset(
    {
        "ingestion_runs",
        "ingestion_document_states",
        "corpus_versions",
        "conversations",
        "conversation_turns",
        "turn_citations",
        "evaluation_runs",
        "evaluation_question_results",
    }
)

#: Which task creates each one, so a failure says where the missing registration belongs.
OWNING_TASK: Final[dict[str, str]] = {
    "ingestion_runs": "T057",
    "ingestion_document_states": "T057",
    "corpus_versions": "T078",
    "conversations": "T138",
    "conversation_turns": "T138",
    "turn_citations": "T138",
    "evaluation_runs": "T193",
    "evaluation_question_results": "T193",
}


def _in_metadata() -> set[str]:
    return FEATURE_004_TABLES & set(Base.metadata.tables)


def _migration_sources() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(VERSIONS.glob("*.py"))
    )


class TestTheCanonicalSetIsStable:
    def test_there_are_eight(self) -> None:
        assert len(FEATURE_004_TABLES) == 8, sorted(FEATURE_004_TABLES)

    def test_every_name_has_an_owning_task(self) -> None:
        """A name with no task is a name nobody is going to create."""
        assert set(OWNING_TASK) == FEATURE_004_TABLES


class TestAModelInMetadataIsRegistered:
    """Direction one: the table exists, so the registry must already know.

    Each case is an **implication**, not a skip. A table that does not exist yet makes
    the premise false and the test pass, which is the honest reading — nothing is being
    left unchecked, there is simply nothing yet to check. A `pytest.skip` would report
    the same situation as a missing dependency, and CI runs with `EAIOS_NO_SKIPS=1`,
    where that becomes a failure for a file whose subject has not been written.

    What makes the vacuous pass safe is `TestTheDetectorFires`, which plants a real table
    and requires each gap to be reported.
    """

    @pytest.mark.parametrize("table", sorted(FEATURE_004_TABLES))
    def test_it_is_in_post_baseline_tables(self, table: str) -> None:
        if table not in Base.metadata.tables:
            return  # not built yet — an implication, not a skip. See the class docstring.
        assert table in POST_BASELINE_TABLES, (
            f"`{table}` is in the model metadata and not in POST_BASELINE_TABLES."
            f" Add it in {OWNING_TASK[table]}, with the model — `baseline_tables()`"
            " currently claims migration 0001 creates it"
        )

    @pytest.mark.parametrize("table", sorted(FEATURE_004_TABLES))
    def test_it_is_in_runtime_tables(self, table: str) -> None:
        if table not in Base.metadata.tables:
            return
        assert table in RUNTIME_TABLES, (
            f"`{table}` is in the model metadata and not in RUNTIME_TABLES."
            f" Add it in {OWNING_TASK[table]} — `reset_all` does not truncate it, so rows"
            " survive a reset and the emptiness pre-flight cannot see them"
        )

    @pytest.mark.parametrize("table", sorted(FEATURE_004_TABLES))
    def test_it_is_created_by_a_migration(self, table: str) -> None:
        if table not in Base.metadata.tables:
            return
        assert f'"{table}"' in _migration_sources(), (
            f"`{table}` exists in the models and in no migration, so it exists in no"
            " database"
        )


class TestNoRegistryIsAheadOfReality:
    """Direction two: a registered name whose table does not exist.

    This is the failure the corrected T055 avoids. A name in `RUNTIME_TABLES` before its
    table exists makes `reset_all` truncate nothing at an address that does not resolve,
    and the emptiness pre-flight count a table it cannot query.
    """

    @pytest.mark.parametrize("table", sorted(FEATURE_004_TABLES))
    def test_post_baseline_does_not_name_an_absent_table(self, table: str) -> None:
        if table in POST_BASELINE_TABLES:
            assert table in Base.metadata.tables, (
                f"POST_BASELINE_TABLES names `{table}` and no model defines it."
                " Registration must land with the model, not before it"
            )

    @pytest.mark.parametrize("table", sorted(FEATURE_004_TABLES))
    def test_runtime_tables_does_not_name_an_absent_table(self, table: str) -> None:
        if table in RUNTIME_TABLES:
            assert table in Base.metadata.tables, (
                f"RUNTIME_TABLES names `{table}` and no model defines it. `reset_all`"
                " would TRUNCATE a table that is not there"
            )

    @pytest.mark.parametrize("table", sorted(FEATURE_004_TABLES))
    def test_a_registered_table_has_its_migration(self, table: str) -> None:
        if table in POST_BASELINE_TABLES or table in RUNTIME_TABLES:
            assert f'"{table}"' in _migration_sources(), (
                f"`{table}` is registered and created by no migration"
            )


class TestTheTwoRegistriesAgree:
    def test_neither_is_ahead_of_the_other(self) -> None:
        """Both entries land in the same task, so a name in one and not the other means
        half a registration shipped."""
        in_post = FEATURE_004_TABLES & POST_BASELINE_TABLES
        in_runtime = FEATURE_004_TABLES & set(RUNTIME_TABLES)
        assert in_post == in_runtime, (
            f"registries disagree — POST_BASELINE only: {sorted(in_post - in_runtime)},"
            f" RUNTIME only: {sorted(in_runtime - in_post)}"
        )

    def test_registration_matches_the_metadata_exactly(self) -> None:
        present = _in_metadata()
        assert present == FEATURE_004_TABLES & POST_BASELINE_TABLES
        assert FEATURE_004_TABLES & set(RUNTIME_TABLES) == present


@pytest.fixture
def planted_table() -> Iterator[str]:
    """A real Feature 004 table in the metadata, removed again afterwards.

    Nothing on disk is touched: the table is added to `Base.metadata` in memory and
    removed in `finally`, so the repository files are byte-identical either way.
    """
    name = "corpus_versions"
    assert name not in Base.metadata.tables, "the fixture would mask a real table"
    sa.Table(name, Base.metadata, sa.Column("id", sa.Integer, primary_key=True))
    try:
        yield name
    finally:
        Base.metadata.remove(Base.metadata.tables[name])
        assert name not in Base.metadata.tables


class TestTheDetectorFires:
    """Falsification. Every assertion above passes over an empty set today, so each gap
    is planted deliberately and required to be reported."""

    def test_the_plant_is_real(self, planted_table: str) -> None:
        assert planted_table in Base.metadata.tables
        assert planted_table in FEATURE_004_TABLES

    def test_a_missing_post_baseline_entry_is_caught(self, planted_table: str) -> None:
        assert planted_table not in POST_BASELINE_TABLES
        assert planted_table in _in_metadata(), (
            "the planted table is not seen as present, so the POST_BASELINE check would"
            " skip rather than fail"
        )
        assert _in_metadata() != FEATURE_004_TABLES & POST_BASELINE_TABLES, (
            "a table in the metadata and absent from POST_BASELINE_TABLES did not break"
            " the equality this file rests on"
        )

    def test_a_missing_runtime_entry_is_caught(self, planted_table: str) -> None:
        assert planted_table not in RUNTIME_TABLES
        assert FEATURE_004_TABLES & set(RUNTIME_TABLES) != _in_metadata()

    def test_a_missing_migration_is_caught(self, planted_table: str) -> None:
        assert f'"{planted_table}"' not in _migration_sources(), (
            "the planted table is already named in a migration, so this falsification"
            " proves nothing"
        )

    def test_the_registries_would_disagree(self, planted_table: str) -> None:
        """The cross-check specifically, since it is the one that catches half a
        registration."""
        in_post = FEATURE_004_TABLES & POST_BASELINE_TABLES
        in_runtime = FEATURE_004_TABLES & set(RUNTIME_TABLES)
        assert in_post == in_runtime, "both are empty, so the plant is the only gap"
        assert planted_table not in in_post

    def test_the_metadata_is_restored_afterwards(self) -> None:
        """Runs after the fixture has torn down for the tests above."""
        assert "corpus_versions" not in Base.metadata.tables


class TestPhaseOneRegisteredNothingEarly:
    """The corrected T055's own claim, asserted rather than described."""

    def test_no_feature_004_name_is_registered_yet(self) -> None:
        assert set() == FEATURE_004_TABLES & POST_BASELINE_TABLES
        assert FEATURE_004_TABLES & set(RUNTIME_TABLES) == set()

    def test_the_existing_registries_are_unchanged(self) -> None:
        """Feature 003's entries must survive this correction untouched."""
        assert frozenset(
            {"contact_submissions", "user_credentials", "sessions"}
        ) == POST_BASELINE_TABLES
        assert set(RUNTIME_TABLES) == {
            "contact_submissions",
            "sessions",
            "user_credentials",
        }
