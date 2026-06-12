"""Clerk session-JWT verification for protected Flask routes.

Verifies Clerk-issued session JWTs against the instance JWKS endpoint
(networkless after the first key fetch, keys cached by PyJWKClient), then
exposes a ``require_clerk_auth`` decorator that stashes the caller's Clerk
user id on ``flask.g`` so routes derive identity from the verified token —
never from a request body.
"""

from __future__ import annotations

import functools
import logging
import os

import jwt
from flask import g, jsonify, request
from jwt import PyJWKClient

log = logging.getLogger(__name__)

_jwks_client: PyJWKClient | None = None


def _frontend_url() -> str:
    url = os.environ.get("CLERK_FRONTEND_URL") or os.environ.get("VITE_CLERK_FRONTEND_URL")
    if not url:
        raise RuntimeError(
            "CLERK_FRONTEND_URL (or VITE_CLERK_FRONTEND_URL) is not set"
        )
    return url.rstrip("/")


def _client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(f"{_frontend_url()}/.well-known/jwks.json")
    return _jwks_client


def verify_session_token(token: str) -> dict:
    """Validate a Clerk session JWT; return its claims or raise on failure."""
    signing_key = _client().get_signing_key_from_jwt(token).key
    return jwt.decode(
        token,
        signing_key,
        algorithms=["RS256"],
        issuer=_frontend_url(),
        options={"require": ["exp", "iat", "sub"]},
    )


def require_clerk_auth(fn):
    """Decorator: require a valid Clerk session JWT in the Authorization header."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "missing bearer token"}), 401
        token = auth[len("Bearer ") :].strip()
        try:
            claims = verify_session_token(token)
        except Exception as exc:
            log.info("Clerk JWT rejected: %s", exc)
            return jsonify({"error": "invalid token"}), 401
        g.clerk_user_id = claims["sub"]
        g.clerk_claims = claims
        return fn(*args, **kwargs)

    return wrapper
