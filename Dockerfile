# Stage 1: Builder — install dependencies with uv
FROM python:3.12-slim AS builder

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml ./
RUN uv pip install --system --no-cache -r pyproject.toml 2>/dev/null || \
    uv pip install --system --no-cache . 2>/dev/null || true

COPY . .
RUN uv pip install --system --no-cache . 2>/dev/null || true


# Stage 2: Runtime — lean image, non-root user
FROM python:3.12-slim AS runtime

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1000 rupiv && \
    useradd --uid 1000 --gid rupiv --create-home rupiv

WORKDIR /app

# Copy installed Python packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source
COPY --chown=rupiv:rupiv src/ /app/src/

USER rupiv

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["uvicorn", "rupiv.main:app", "--host", "0.0.0.0", "--port", "8000"]
