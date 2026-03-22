default:
    @just --list

# --- Dev ---

# Install all dependencies
install:
    npm ci
    pre-commit install

# Run the Python backend locally (port 8000, requires MEMLOG_PATH)
backend:
    cd server && MEMLOG_PATH=../tmp-notes MEMLOG_AUTH_TYPE=none \
    uv run uvicorn memlog.main:app --reload --port 8000

# Run the Python MCP server locally (port 8090, proxies to backend on :8000)
mcp:
    cd mcp-server && MEMLOG_URL=http://localhost:8000 \
    uv run uvicorn memlog_mcp.main:app --reload --port 8090

# Run frontend dev server (port 8080, proxies API to :8000)
frontend:
    npm run dev

# --- Test & Lint ---

# Run Python backend tests
test:
    cd server && uv run pytest

# Run MCP server tests
test-mcp:
    cd mcp-server && uv run pytest

# Format Python (ruff)
fmt:
    cd server && uv run ruff format .
    cd mcp-server && uv run ruff format .

# Format frontend
fmt-frontend:
    npx prettier --write .

# --- Release ---

# Publish a release candidate: just release-rc 0.0.3 1  →  v0.0.3-rc.1
release-rc version rc:
    sed -i '' 's/^version = ".*"/version = "{{version}}-rc.{{rc}}"/' server/pyproject.toml mcp-server/pyproject.toml
    git add server/pyproject.toml mcp-server/pyproject.toml
    git commit -m "chore: bump version to {{version}}-rc.{{rc}}"
    git tag v{{version}}-rc.{{rc}}
    git push origin main
    git push origin v{{version}}-rc.{{rc}}

# Publish a full release: just release 0.0.3  →  v0.0.3
release version:
    sed -i '' 's/^version = ".*"/version = "{{version}}"/' server/pyproject.toml mcp-server/pyproject.toml
    git add server/pyproject.toml mcp-server/pyproject.toml
    git commit -m "chore: bump version to {{version}}"
    git tag v{{version}}
    git push origin main
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
