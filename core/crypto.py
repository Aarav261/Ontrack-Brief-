"""Application-level encryption for credentials at rest (Fernet).

The OnTrack Auth-Token is a bearer credential to a third-party system (Deakin
OnTrack): a plaintext DB leak would hand an attacker a live session for every
user. We encrypt it at the DB boundary so a database dump is useless without the
key — which lives only in the environment, never in the DB.

Key
---
Set ``TOKEN_ENCRYPTION_KEY`` to a urlsafe-base64 32-byte Fernet key. Generate one
with::

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

If the key is unset we log a loud warning and fall back to passthrough (values
stored as-is) so local dev and tests keep working without configuration. Never
run production without the key set.

Migration
---------
Encrypted values are tagged with ``enc:v1:`` so reads can distinguish them from
legacy plaintext rows written before this module existed. ``decrypt`` returns
untagged values unchanged, and the next write re-stores them encrypted — since
the rotating token is persisted frequently, existing rows migrate on their own.
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

# Tags values this module encrypted, so decrypt() can tell them apart from
# legacy plaintext (or passthrough-mode) values unambiguously.
_PREFIX = "enc:v1:"

_KEY = os.environ.get("TOKEN_ENCRYPTION_KEY", "").strip()
_fernet = None

if _KEY:
    from cryptography.fernet import Fernet

    try:
        _fernet = Fernet(_KEY.encode())
    except (ValueError, TypeError) as exc:
        raise RuntimeError(
            "TOKEN_ENCRYPTION_KEY is set but invalid — it must be a urlsafe-base64 "
            "32-byte Fernet key. Generate one with: "
            'python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        ) from exc
else:
    log.warning(
        "TOKEN_ENCRYPTION_KEY not set — auth tokens will be stored UNENCRYPTED. "
        "Set it in production. Generate a key with: "
        'python -c "from cryptography.fernet import Fernet; '
        'print(Fernet.generate_key().decode())"'
    )


def is_enabled() -> bool:
    """True when an encryption key is configured."""
    return _fernet is not None


def encrypt(value: str | None) -> str | None:
    """Encrypt a secret for storage. No-op when no key is set or already tagged."""
    if value is None or _fernet is None:
        return value
    if value.startswith(_PREFIX):  # already encrypted — don't double-wrap
        return value
    return _PREFIX + _fernet.encrypt(value.encode()).decode()


def decrypt(value: str | None) -> str | None:
    """Decrypt a stored secret. Untagged (legacy plaintext) values pass through."""
    if value is None or not value.startswith(_PREFIX):
        return value
    if _fernet is None:
        log.error(
            "Encrypted value found but TOKEN_ENCRYPTION_KEY is not set; cannot decrypt"
        )
        return value
    from cryptography.fernet import InvalidToken

    try:
        return _fernet.decrypt(value[len(_PREFIX) :].encode()).decode()
    except InvalidToken:
        log.error("Failed to decrypt token — wrong TOKEN_ENCRYPTION_KEY for this data?")
        return value
