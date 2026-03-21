default:
    @just --list

# --- Dev ---

# Install all dependencies (including dev)
install:
    uv sync --dev
    npm ci
    uv run pre-commit install

# Install MCP server dependencies
install-mcp:
    uv sync --group mcp

# Run the MCP server (used by Claude Code)
mcp:
    uv run --group mcp python mcp_server.py

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

# --- Release ---

# Publish a release candidate: just release-rc 0.0.3 1  →  v0.0.3-rc.1
release-rc version rc:
    sed -i '' 's/^version = .*/version = "{{version}}-rc.{{rc}}"/' pyproject.toml
    git add pyproject.toml
    git commit -m "chore: bump version to {{version}}-rc.{{rc}}"
    git tag v{{version}}-rc.{{rc}}
    git push origin develop
    git push origin v{{version}}-rc.{{rc}}

# Publish a full release: just release 0.0.3  →  v0.0.3
release version:
    sed -i '' 's/^version = .*/version = "{{version}}"/' pyproject.toml
    git add pyproject.toml
    git commit -m "chore: bump version to {{version}}"
    git tag v{{version}}
    git push origin develop
    git push origin v{{version}}

# Create a GitHub release from an existing tag
gh-release version:
    gh release create v{{version}} --generate-notes

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
