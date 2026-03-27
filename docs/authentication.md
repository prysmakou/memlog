# Authentication

Memlog supports four authentication modes, set via `MEMLOG_AUTH_TYPE`.

## none

No login required. Anyone who can reach the server can read and write notes.

```yaml
MEMLOG_AUTH_TYPE: none
```

Good for: local use, trusted private networks, quick testing.

## read_only

No login required, but the API only allows read operations. Create, edit, and delete are disabled. The web UI hides the editor.

```yaml
MEMLOG_AUTH_TYPE: read_only
```

Good for: publishing a public read-only view of your notes.

## password

Username and password login. After a successful login, a JWT session cookie is issued and remains valid for `MEMLOG_SESSION_EXPIRY_DAYS` days (default: 30).

```yaml
MEMLOG_AUTH_TYPE: password
MEMLOG_USERNAME: admin
MEMLOG_PASSWORD: your-password
MEMLOG_SECRET_KEY: your-long-random-secret
```

Generate a strong secret key:

```bash
openssl rand -hex 32
```

## totp

Username, password, **and** a time-based one-time code (TOTP). Compatible with any authenticator app (Google Authenticator, Aegis, 1Password, etc.).

```yaml
MEMLOG_AUTH_TYPE: totp
MEMLOG_USERNAME: admin
MEMLOG_PASSWORD: your-password
MEMLOG_SECRET_KEY: your-long-random-secret
MEMLOG_TOTP_KEY: YOUR_BASE32_TOTP_SEED
```

### Setting up TOTP

**Option 1 — let Memlog generate the key:**

Omit `MEMLOG_TOTP_KEY` on first start. Memlog will generate a key and print a QR code to the container logs:

```bash
docker compose logs memlog
```

Scan the QR code with your authenticator app, then add `MEMLOG_TOTP_KEY` to your compose file with the printed key so it persists across restarts.

**Option 2 — bring your own key:**

Generate a Base32-encoded TOTP seed yourself:

```bash
python3 -c "import base64, os; print(base64.b32encode(os.urandom(20)).decode())"
```

Set it as `MEMLOG_TOTP_KEY` and register it in your authenticator app manually.

## MCP server authentication

When `MEMLOG_AUTH_TYPE` is `password` or `totp`, the MCP server also requires a token. Log in to the web UI, open the menu (top right), and click **Copy MCP Token**. Pass this token to your MCP client. See [MCP Server](mcp-server.md) for details.
