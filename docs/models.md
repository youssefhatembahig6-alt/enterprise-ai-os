# Pinned models

Two models, both pinned by revision, both verified against their authoritative model card
on the date recorded below. Nothing in this repository downloads either one automatically,
and neither is redistributed here (FR-011g).

Feature 004 depends on the exact identity of both. A different revision is a different
vector space or a different generator, and a quality figure attributed to the wrong one is
not a measurement — it is a coincidence. That is why the revision SHA and the weight
checksum are recorded here rather than left to whatever `main` happens to be.

---

## BGE-M3 — embedding

| Field | Value |
|-------|-------|
| Repository | `BAAI/bge-m3` |
| Revision SHA | `5617a9f61b028005a4858fdac845db406aefb181` |
| Revision date | 2024-07-03 |
| Weight file | `pytorch_model.bin` |
| Weight checksum (SHA-256) | `b5e0ce3470abf5ef3831aa1bd5553b486803e83251590ab7ff35a117cf6aad38` |
| Weight size | 2,271,145,830 bytes |
| Vector dimension | **1024** |
| Runtime | local CPU, PyTorch — no quantization |
| Licence | **MIT** |
| Licence restrictions | none beyond notice retention; commercial use and redistribution permitted |
| Verified | 2026-08-12, HuggingFace repository metadata |

The 1024 dimension is not a preference — it is what the existing Qdrant collection is already
configured for. A model producing any other width would require re-provisioning the store
(FR-011).

## Qwen2.5-3B-Instruct — generation

| Field | Value |
|-------|-------|
| Repository | `Qwen/Qwen2.5-3B-Instruct-GGUF` |
| Revision SHA | `7dabda4d13d513e3e842b20f0d435c732f172cbe` |
| Weight file | `qwen2.5-3b-instruct-q4_k_m.gguf` |
| Weight checksum (SHA-256) | `626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d` |
| Weight size | 2,104,932,768 bytes |
| Quantization | **Q4_K_M** (GGUF) |
| Runtime | `llama.cpp` server on a remote **T4** GPU session |
| Licence | **Qwen RESEARCH LICENSE AGREEMENT** (`license_name: qwen-research`) |
| Licence restrictions | **NON-COMMERCIAL ONLY** — see below |
| Verified | 2026-08-12, HuggingFace repository metadata and licence link |

### What the Qwen licence actually restricts

Recorded because "research licence" is vague enough to be ignored, and the restriction has
real consequences for this project:

- **§2(a)** limits use to *"NON-COMMERCIAL PURPOSES ONLY"*, which **§1(i)** defines as
  *"research or evaluation purposes only"*.
- **§2(b)** requires a separate licence from the licensor for any commercial use.
- **§3** permits redistribution only with the agreement attached, an attribution notice, and
  any modified files marked as modified.

**Consequence for this repository.** This feature is a graduation project — research and
evaluation — so §2(a) is satisfied. It is *not* satisfied by any commercial deployment of
this system, and swapping in a commercially licensed generator is the required change
before that could happen. The weights are never committed here and never baked into a
public image (§3, FR-011g).

---

## How weights reach a clean installation

No hosted inference runtime is introduced by either step. Both are plain file downloads
followed by a checksum comparison; nothing calls a third-party inference API at any point,
at provisioning time or at request time (FR-011c, FR-011e, FR-011f).

### BGE-M3, on the machine that embeds

Embedding runs **locally**, so these weights land on the developer machine or the CI
controlled lane — never inside an ordinary CI job, which is model-free (FR-035b).

One command downloads, verifies and records:

```bash
uv run python benchmarks/provision_bge.py
```

It fetches only the files this feature loads, checks the size and the SHA-256 against the
pins above, and — **only after the checksum matches** — writes an ignored `.revision`
marker beside them.

If the weights are already on disk, verify and record without touching the network:

```bash
uv run python benchmarks/provision_bge.py --verify-only
```

**Why a helper rather than two shell commands.** The old process was
`huggingface-cli download` followed by `sha256sum`, and it recorded the revision nowhere.
`benchmarks/phase0/preflight.py` reads a `.revision` marker to confirm which revision is
installed, and nothing created it — so correct weights with a matching checksum still
failed preflight with `weights revision is '<absent>'`. The helper is what closes that
loop, and it writes the marker atomically so an interrupted run leaves no half-written
revision asserting a verification that did not finish.

A checksum mismatch is a hard stop, not a warning, in both places:
`eaios_core.embedding.bge_m3` also refuses to construct when the file disagrees with the
pin.

### Qwen2.5-3B-Instruct, on the Colab session

Generation runs **remotely**, so these weights land only inside the ephemeral Colab session
that `infrastructure/colab/generation_server.ipynb` provisions. They are never present in
this repository, in any image built from it, or on the developer machine.

```bash
huggingface-cli download Qwen/Qwen2.5-3B-Instruct-GGUF \
  qwen2.5-3b-instruct-q4_k_m.gguf \
  --revision 7dabda4d13d513e3e842b20f0d435c732f172cbe \
  --local-dir /content/models
```

```bash
sha256sum /content/models/qwen2.5-3b-instruct-q4_k_m.gguf
```

Expect `626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d`.

### What is deliberately absent

- **No hosted inference API.** Not OpenAI, not Anthropic, not HuggingFace Inference
  Endpoints, not Together, not Replicate. The only outbound call this feature makes at
  request time is to the project's own generation server over its own tunnel (FR-011c).
- **No automatic download at request time.** Weight acquisition is a provisioning
  activity. An inference request that would trigger a download is a defect, and
  `tests/security/test_no_download_at_request_time.py` fails the build on it (FR-011f).
- **No committed weights.** `.gitignore` excludes `models/`, `*.gguf`, `*.safetensors` and
  `*.bin`; `tests/unit/test_no_weights_committed.py` fails the build if one is ever tracked
  (FR-011g).

---

## Measurement status

**No benchmark has been run.** Neither latency threshold has been measured, and this
document does not claim otherwise. Both figures in `benchmarks/phase0/GATE.md` read
`NOT RUN`, and `tests/unit/test_phase0_gate_not_claimed.py` fails the build if any
user-facing document — including this one — describes either threshold as met while its
gate row still says `NOT RUN` (FR-035e).
