default:
    @just --list

# --- Dev ---

# Install all dependencies
install:
    npm ci
    pre-commit install

# Build both Rust binaries (backend + MCP server)
build-rs:
    cargo build --release

# Run the Rust backend locally (port 8000, requires MEMLOG_PATH)
backend:
    MEMLOG_PATH=./tmp-notes MEMLOG_AUTH_TYPE=none MEMLOG_PORT=8000 \
    cargo run -p memlog-server

# Build the Rust MCP server binary
mcp-rs-build:
    cargo build --release -p memlog-mcp

# Run the Rust MCP server locally (HTTP+SSE on :8090, proxies to backend on :8000)
mcp-rs:
    MEMLOG_URL=http://localhost:8000 MCP_BIND=0.0.0.0:8090 \
    cargo run --release -p memlog-mcp

# Run frontend dev server (port 8080, proxies API to :8000)
frontend:
    npm run dev

# --- Test & Lint ---

# Run all tests
test:
    cargo test

# Format frontend
fmt-frontend:
    npx prettier --write .

# --- Release ---

# Publish a release candidate: just release-rc 0.0.3 1  →  v0.0.3-rc.1
release-rc version rc:
    sed -i '' 's/^version = ".*"/version = "{{version}}-rc.{{rc}}"/' server-rs/Cargo.toml mcp-server-rs/Cargo.toml
    git add server-rs/Cargo.toml mcp-server-rs/Cargo.toml Cargo.lock
    git commit -m "chore: bump version to {{version}}-rc.{{rc}}"
    git tag v{{version}}-rc.{{rc}}
    git push origin main
    git push origin v{{version}}-rc.{{rc}}

# Publish a full release: just release 0.0.3  →  v0.0.3
release version:
    sed -i '' 's/^version = ".*"/version = "{{version}}"/' server-rs/Cargo.toml mcp-server-rs/Cargo.toml
    git add server-rs/Cargo.toml mcp-server-rs/Cargo.toml Cargo.lock
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
