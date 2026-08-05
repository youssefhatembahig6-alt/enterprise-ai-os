"""Seeded randomness with per-generator sub-seeds (research R3).

Each generator gets its own RNG derived from the root seed plus its own name and
tenant. A single shared RNG would make every generator's output depend on the
execution order of every other one — adding an employee upstream would shift every
downstream value, and any future reordering would look like a determinism bug.

Faker is pinned to an exact version in `pyproject.toml`. Its name and word lists
change between releases, so that pin is load-bearing rather than hygiene.
"""

from __future__ import annotations

import hashlib
import random

from faker import Faker

__all__ = ["Rng", "sub_seed"]

#: Locales are explicit and ordered. Faker's default locale list varies by install,
#: which would make generated names environment-dependent.
_LOCALES = ["en_US"]

# Arabic-script names are avoided deliberately: the dataset must stay greppable in
# a terminal on every teammate's machine, and mixed-direction text in psql output
# is a poor debugging experience. Names below are transliterated, which is also
# how they would appear in a real corporate directory.
_EG_GIVEN = (
    "Nadia Omar Youssef Mariam Karim Hana Tarek Salma Amir Dina Hassan Laila "
    "Khaled Rania Sherif Yasmin Mostafa Nour Ahmed Farida Ziad Heba Sami Injy"
).split()
_EG_FAMILY = (
    "Farouk Zaki Mansour Ibrahim ElSayed Hafez Nasr Shafik Rashad Gaber Halim "
    "Sabry Fahmy Lotfy Adel Bakr Darwish ElGendy Kamel Riad"
).split()
_AE_GIVEN = "Fatima Rashid Aisha Saeed Maryam Hamdan Noora Sultan Latifa Majid".split()
_AE_FAMILY = "AlMansoori AlKaabi AlSuwaidi AlNuaimi AlZaabi AlHammadi AlShamsi".split()


def sub_seed(root_seed: str, generator: str, scope: str = "") -> int:
    """Derive a stable 64-bit sub-seed for one generator in one scope."""
    material = f"{root_seed}:{generator}:{scope}".encode()
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


def _new_faker(seed_value: int) -> Faker:
    """A freshly seeded Faker.

    Deliberately NOT cached. Faker instances are stateful — every call advances an
    internal PRNG — so sharing one across two generation runs makes the second run
    continue where the first left off and produce different text. That defeats the
    whole determinism guarantee, and it is invisible within a single run: only
    generating twice in one process reveals it (see
    tests/unit/test_document_bytes.py::test_regenerating_produces_identical_bytes).
    """
    faker = Faker(_LOCALES)
    faker.seed_instance(seed_value)
    return faker


class Rng:
    """A generator's private source of randomness."""

    __slots__ = ("_faker", "_random", "_seed", "generator", "scope")

    def __init__(self, root_seed: str, generator: str, scope: str = "") -> None:
        self.generator = generator
        self.scope = scope
        self._seed = sub_seed(root_seed, generator, scope)
        self._random = random.Random(self._seed)
        self._faker = _new_faker(self._seed)

    @property
    def faker(self) -> Faker:
        return self._faker

    # -- primitives -------------------------------------------------------
    def choice(self, items: list[str] | tuple[str, ...]) -> str:
        return self._random.choice(list(items))

    def sample(self, items: list[str], count: int) -> list[str]:
        return self._random.sample(items, min(count, len(items)))

    def randint(self, low: int, high: int) -> int:
        return self._random.randint(low, high)

    def uniform(self, low: float, high: float) -> float:
        return self._random.uniform(low, high)

    def weighted(self, options: dict[str, float]) -> str:
        keys = sorted(options)  # sorted so dict ordering cannot affect the draw
        return self._random.choices(keys, weights=[options[k] for k in keys], k=1)[0]

    def shuffled(self, items: list[str]) -> list[str]:
        copy = list(items)
        self._random.shuffle(copy)
        return copy

    # -- domain helpers ---------------------------------------------------
    def person_name(self, country: str) -> str:
        given, family = (_AE_GIVEN, _AE_FAMILY) if country == "AE" else (_EG_GIVEN, _EG_FAMILY)
        return f"{self._random.choice(given)} {self._random.choice(family)}"

    def company_name(self) -> str:
        return str(self.faker.company())

    def sentence(self, words: int = 12) -> str:
        return str(self.faker.sentence(nb_words=words))

    def paragraph(self, sentences: int = 4) -> str:
        return str(self.faker.paragraph(nb_sentences=sentences))
