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

RUN pip install --no-cache-dir ./packages/core ./scripts/seed

ENTRYPOINT ["eaios-seed"]
CMD ["--help"]
