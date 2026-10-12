# Nexova backend development image.
# Serves both FastAPI apps: Supply Directory API and Inventory API.
FROM python:3.13-slim

# Install uv (used to install the pinned Python dependencies).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app/backrooms/services

# Install the locked dependency set exported to requirements.txt.
COPY requirements.txt ./requirements.txt
RUN uv pip install --system --no-cache -r requirements.txt

# Application source. Overlaid by a bind mount at runtime for hot reload.
COPY . .

EXPOSE 8000 8001

# Default command runs the Supply Directory API. The `inventory-api` Compose
# service overrides `command` to run the Inventory API on port 8001 instead.
CMD ["uvicorn", "services.Supply_directory_API.main:app", "--app-dir", "/app/backrooms", "--host", "0.0.0.0", "--port", "8000", "--reload"]
