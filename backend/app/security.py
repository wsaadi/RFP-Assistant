"""Security utilities: password hashing, JWT tokens, and API key encryption."""
import base64
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt

from .config import settings

logger = logging.getLogger("security")


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
        return payload
    except JWTError:
        return None


# ── API key encryption (Fernet symmetric encryption) ──
# Derives a Fernet key from SECRET_KEY so we don't need a separate key.

def _get_fernet() -> Fernet:
    """Derive a Fernet key from the application SECRET_KEY."""
    # Fernet requires a 32-byte url-safe base64-encoded key.
    # Derive it deterministically from SECRET_KEY using SHA-256.
    key_bytes = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)


def encrypt_api_key(plaintext: str) -> str:
    """Encrypt an API key for database storage.

    Returns the encrypted value as a base64 string prefixed with 'enc:'.
    """
    if not plaintext:
        return ""
    f = _get_fernet()
    encrypted = f.encrypt(plaintext.encode("utf-8"))
    return "enc:" + encrypted.decode("utf-8")


def decrypt_api_key(stored_value: str) -> str:
    """Decrypt an API key from database storage.

    Handles both encrypted (prefixed with 'enc:') and legacy plaintext values.
    """
    if not stored_value:
        return ""
    if stored_value.startswith("enc:"):
        try:
            f = _get_fernet()
            decrypted = f.decrypt(stored_value[4:].encode("utf-8"))
            return decrypted.decode("utf-8")
        except InvalidToken:
            logger.error("Failed to decrypt API key — SECRET_KEY may have changed")
            return ""
    # Legacy: return plaintext value as-is (will be re-encrypted on next save)
    return stored_value
