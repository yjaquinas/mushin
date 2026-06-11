"""Password hashing for the email/password fallback provider.

Argon2id via ``argon2-cffi``. The *full encoded hash* (algorithm, parameters,
salt, and digest, all in the PHC string) is stored in ``user.password_hash`` —
there is no separate salt column because the salt lives inside the encoded
string. Plaintext is never logged, echoed, or persisted.

The encoded string looks like::

    $argon2id$v=19$m=65536,t=3,p=4$<b64-salt>$<b64-hash>

``verify()`` is constant-time (argon2-cffi handles that internally) and returns
a plain bool rather than raising, so callers never branch on exception type for
the common wrong-password case.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Defaults are argon2-cffi's recommended Argon2id parameters. They are encoded
# into every hash, so tuning them later does not invalidate existing hashes.
_hasher = PasswordHasher()


def hash_password(plaintext: str) -> str:
    """Return the full Argon2id PHC-encoded hash for *plaintext*.

    Never log the input or the return value alongside the input — the encoded
    hash is safe at rest, but the plaintext must never touch a log line.
    """
    if not plaintext:
        raise ValueError("password must not be empty")
    return _hasher.hash(plaintext)


def verify_password(encoded_hash: str | None, plaintext: str) -> bool:
    """Return whether *plaintext* matches the stored *encoded_hash*.

    Returns ``False`` (never raises) for a wrong password, a malformed stored
    hash, or a ``None`` hash (e.g. an OAuth-only or guest account that has no
    password set). This keeps the login path from leaking *why* it failed.
    """
    if not encoded_hash:
        return False
    try:
        return _hasher.verify(encoded_hash, plaintext)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
