# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

# Pinned locale so number and date formatting cannot vary between the host and the
# container, or between two developers' machines (spec FR-012a).
ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=UTC \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY packages/core/src packages/core/src
COPY apps/api/src apps/api/src
COPY apps/api/alembic apps/api/alembic
COPY apps/api/alembic.ini apps/api/alembic.ini

# The CPU-only PyTorch index, matching the root `uv.lock` (spec 004 FR-011c).
# `packages/core` declares the BGE-M3 runtime, so this image installs torch whether or
# not it ever embeds. Without this index pip resolves the default CUDA wheel — thirteen
# `nvidia-*` distributions plus `triton`, gigabytes of runtime this container has no GPU
# to use. `--extra-index-url` would still allow the CUDA build to win, so the CPU index
# is the *primary* one and PyPI is the extra.
RUN pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    --extra-index-url https://pypi.org/simple \
    ./packages/core ./apps/api

# Alembic resolves its script location relative to the working directory.
WORKDIR /app/apps/api

EXPOSE 8000

CMD ["uvicorn", "eaios_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
