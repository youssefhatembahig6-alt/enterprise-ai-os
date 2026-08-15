# Fixture: prohibitions and quoted instructions that must NOT trip the detector

**This file is a test fixture.** Every sentence below mentions a latency threshold, and not
one of them claims it was met. If the detector fires on any of these it is unusable: the
documents that most need to discuss the thresholds are the ones that forbid claiming them,
and a check that punishes accurate hedging teaches people to delete the hedge.

The two latency figures are acceptance thresholds, not demonstrated results.

Neither the 2-second preview p95 nor the 5-second first-token p95 has been measured.

No document may describe the 2-second target as achieved until the benchmark has produced a
passing figure.

The requirement states that retrieval preview latency must meet the 2-second p95 target —
that is the requirement, not a report of the outcome.

A run that would otherwise report "the first-token p95 achieved the 5-second threshold" must
instead record `NOT RUN` when any prerequisite is absent.

The gate row reads `NOT RUN`, so the 2-second threshold is not claimed anywhere.
