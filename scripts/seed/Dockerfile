# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

# The locale pin matters most here: this is the image that writes generated
# documents, and a differing locale would change formatted numbers and dates,
# which would change file bytes, which would change the fingerprint (FR-012a).
ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=UTC \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONHASHSEED=0 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY scripts/seed/pyproject.toml scripts/seed/pyproject.toml
COPY packages/core/src packages/core/src
COPY scripts/seed/src scripts/seed/src

# The CPU-only PyTorch index, matching the root `uv.lock` (spec 004 FR-011c).
# `packages/core` declares the BGE-M3 runtime, so this image installs torch whether or
# not it ever embeds. Without this index pip resolves the default CUDA wheel — thirteen
# `nvidia-*` distributions plus `triton`, gigabytes of runtime this container has no GPU
# to use. `--extra-index-url` would still allow the CUDA build to win, so the CPU index
# is the *primary* one and PyPI is the extra.
RUN pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    --extra-index-url https://pypi.org/simple \
    ./packages/core ./scripts/seed

ENTRYPOINT ["eaios-seed"]
CMD ["--help"]
