from __future__ import annotations

import hashlib
import hmac
import re
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()  # Argon2id with library defaults (memory-hard)

# Precomputed hash used to equalise timing when the account doesn't exist.
_DUMMY_HASH = _hasher.hash("timing-equaliser-not-a-real-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def constant_time_equals(a: str | None, b: str | None) -> bool:
    return bool(a) and bool(b) and hmac.compare_digest(a, b)  # type: ignore[arg-type]


COMMON_PASSWORDS = {"password", "password1", "12345678", "123456789", "qwerty123", "letmein1", "iloveyou", "admin123"}


def password_problems(password: str, email: str = "") -> list[str]:
    """Length-first policy (NIST 800-63B style): min 10 chars, not common, not the email."""
    problems = []
    if len(password) < 10:
        problems.append("must be at least 10 characters")
    if len(password) > 128:
        problems.append("must be at most 128 characters")
    if password.lower() in COMMON_PASSWORDS:
        problems.append("is too common")
    if email and password.lower() == email.lower().split("@")[0]:
        problems.append("must not match your email")
    if re.fullmatch(r"(.)\1+", password):
        problems.append("must not be a single repeated character")
    return problems
