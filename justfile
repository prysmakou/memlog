default:
    @just --list

# --- Dev ---

# Install all dependencies (including dev)
install:
    uv sync --dev
    npm ci

# Run backend dev server (port 8000)
backend:
    uv run uvicorn main:app --app-dir server --reload --port 8000

# Run frontend dev server (port 8080, proxies API to :8000)
frontend:
    npm run dev

# --- Test & Lint ---

# Run backend tests
test:
    uv run pytest -v

# Lint & format backend
lint:
    uv run ruff check server/
    uv run ruff format --check server/

# Format backend (write)
fmt:
    uv run ruff format server/
    uv run ruff check --fix server/

# Format frontend
fmt-frontend:
    npx prettier --write .

# --- Docker ---

# Build Docker image
build tag="local":
    docker build -t memlog:{{tag}} .

# Run the Docker image locally
run tag="local":
    docker run --rm -p 8080:8080 \
        -v "$(pwd)/tmp-notes:/data" \
        -e MEMLOG_AUTH_TYPE=none \
        memlog:{{tag}}
