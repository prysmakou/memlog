from datetime import UTC, datetime, timedelta
from typing import Annotated

import pyotp
import qrcode
import qrcode.image.svg
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from .config import AppConfig, AuthType
from .errors import LOGIN_FAILED, UNAUTHORIZED

_ALGORITHM = "HS256"
_oauth2 = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

# Replay protection: tracks the last accepted TOTP code so the same code
# cannot be used twice within the same 30-second window.
_last_totp: str | None = None


def _issue_token(config: AppConfig, username: str) -> str:
    exp = datetime.now(UTC) + timedelta(days=config.session_expiry_days)
    return jwt.encode(
        {"sub": username, "exp": exp},
        config.secret_key,  # type: ignore[arg-type]
        algorithm=_ALGORITHM,
    )


def _constant_eq(a: str, b: str) -> bool:
    """Timing-safe string comparison."""
    import hmac

    return hmac.compare_digest(a.encode(), b.encode())


def login(config: AppConfig, username: str, password: str) -> str:
    """Validate credentials and return a JWT. Raises 401 on failure."""
    global _last_totp

    if not _constant_eq(username, config.username or ""):
        raise LOGIN_FAILED
    if not _constant_eq(password, config.password or ""):
        raise LOGIN_FAILED

    if config.auth_type == AuthType.TOTP:
        # TOTP code is appended to the password field, separated by a space or directly
        # following (upstream flatnotes appends it to the password field directly).
        # We accept it as a separate trailing 6-digit token after a space.
        parts = password.rsplit(" ", 1)
        base_password = parts[0] if len(parts) == 2 else password
        totp_code = parts[1] if len(parts) == 2 else ""

        if not _constant_eq(base_password, config.password or ""):
            raise LOGIN_FAILED

        totp = pyotp.TOTP(config.totp_key or "")
        if not totp.verify(totp_code) or totp_code == _last_totp:
            raise LOGIN_FAILED
        _last_totp = totp_code

    return _issue_token(config, username)


def validate_token(config: AppConfig, token: str) -> str:
    """Validate JWT and return the username. Raises 401 on failure."""
    try:
        payload = jwt.decode(token, config.secret_key, algorithms=[_ALGORITHM])  # type: ignore[arg-type]
        sub: str | None = payload.get("sub")
        if sub is None:
            raise UNAUTHORIZED
        return sub
    except JWTError:
        raise UNAUTHORIZED from None


def print_totp_qr(config: AppConfig) -> None:
    """Print TOTP QR code and setup URI to stdout on first start."""
    totp = pyotp.TOTP(config.totp_key or "")
    uri = totp.provisioning_uri(name=config.username or "memlog", issuer_name="Memlog")
    qr = qrcode.QRCode()
    qr.add_data(uri)
    qr.make(fit=True)
    print("\nScan this QR code with your authenticator app:")
    qr.print_ascii(invert=True)
    print(f"\nManual key: {config.totp_key}\n")


# ── FastAPI dependency ────────────────────────────────────────────────────────


def require_auth(config: AppConfig) -> "Authenticator":
    return Authenticator(config)


class Authenticator:
    def __init__(self, config: AppConfig) -> None:
        self._config = config

    async def __call__(
        self,
        request: Request,
        bearer: Annotated[str | None, Depends(_oauth2)],
    ) -> str | None:
        if not self._config.auth_type.requires_auth():
            return None

        token = bearer or request.cookies.get("token")
        if not token:
            raise UNAUTHORIZED
        return validate_token(self._config, token)
