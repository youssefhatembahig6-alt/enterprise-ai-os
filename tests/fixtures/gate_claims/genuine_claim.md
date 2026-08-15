# Fixture: a genuine false achievement claim

**This file is a test fixture. It is not a status report and nothing in it is true.**

It exists so `tests/unit/test_phase0_gate_not_claimed.py` can be falsified: T037 copies this
content into a scanned document and requires the detector to fail the build. A detector that
never fires is indistinguishable from one that has nothing to find.

The sentence below is the kind of claim the detector must catch — an unhedged assertion, in
the voice a status document uses, that a threshold was met:

Retrieval preview latency meets the 2-second p95 target on the reference machine.

And the generation half, phrased differently so the detector is not matching one string:

The first-token p95 was measured at 4.1 seconds, achieving the 5-second threshold.
