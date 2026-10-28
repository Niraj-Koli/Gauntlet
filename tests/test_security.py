import pytest

from gauntlet.security import InvalidToken, TraderIdentity, issue_token, verify_token


def test_a_token_round_trips_its_identity():
    token = issue_token("secret", TraderIdentity(3, 41), ttl_seconds=60, now=1000)
    assert verify_token("secret", token, now=1030) == TraderIdentity(3, 41)


def test_tokens_expire():
    token = issue_token("secret", TraderIdentity(3), ttl_seconds=60, now=1000)
    with pytest.raises(InvalidToken, match="expired"):
        verify_token("secret", token, now=1061)


def test_tokens_from_another_key_are_rejected():
    token = issue_token("other", TraderIdentity(3), ttl_seconds=60)
    with pytest.raises(InvalidToken, match="signature"):
        verify_token("secret", token)


def test_a_tampered_payload_is_rejected():
    token = issue_token("secret", TraderIdentity(3), ttl_seconds=60)
    payload, signature = token.split(".")
    forged = issue_token("secret", TraderIdentity(4), ttl_seconds=60).split(".")[0]
    with pytest.raises(InvalidToken):
        verify_token("secret", f"{forged}.{signature}")
    with pytest.raises(InvalidToken, match="malformed"):
        verify_token("secret", payload)
