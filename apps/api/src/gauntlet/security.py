"""Signed tokens that bind an MCP connection to one trader (and optionally one run).

The trading floor issues a token per run; the accounts server derives the account from
it, so an agent can only ever act on its own account. Format: base64url(JSON payload) +
"." + base64url(HMAC-SHA256 of the payload).
"""

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass


class InvalidToken(Exception):
    pass


@dataclass(frozen=True)
class TraderIdentity:
    trader_id: int
    run_id: int | None = None


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(secret: str, payload: bytes) -> bytes:
    return hmac.new(secret.encode(), payload, hashlib.sha256).digest()


def issue_token(secret: str, identity: TraderIdentity, ttl_seconds: int, now: float | None = None) -> str:
    expires = int((now if now is not None else time.time()) + ttl_seconds)
    payload = json.dumps(
        {"t": identity.trader_id, "r": identity.run_id, "exp": expires}, separators=(",", ":")
    ).encode()
    return f"{_b64(payload)}.{_b64(_sign(secret, payload))}"


def verify_token(secret: str, token: str, now: float | None = None) -> TraderIdentity:
    try:
        encoded_payload, encoded_signature = token.split(".")
        payload = _unb64(encoded_payload)
        signature = _unb64(encoded_signature)
    except ValueError as e:
        raise InvalidToken("malformed token") from e
    if not hmac.compare_digest(signature, _sign(secret, payload)):
        raise InvalidToken("bad signature")
    claims = json.loads(payload)
    if claims["exp"] < (now if now is not None else time.time()):
        raise InvalidToken("token expired")
    return TraderIdentity(trader_id=int(claims["t"]), run_id=claims["r"])
