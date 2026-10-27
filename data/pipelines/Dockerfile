# Prefect worker image for the Nexova data pipelines.
# Build from the repository root:
#   docker build -f data/pipelines/Dockerfile -t nexova-prefect-worker .
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY data/pipelines/pyproject.toml data/pipelines/uv.lock ./data/pipelines/
RUN cd data/pipelines && uv sync --frozen --no-dev

COPY data ./data

ENV PATH="/app/data/pipelines/.venv/bin:$PATH"
ENV PYTHONPATH="/app"

# Default command runs the CLI. Compose overrides this for the Prefect server
# and worker services.
CMD ["python", "data/pipelines/pipeline.py"]
