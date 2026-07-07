from app.core.security import constant_time_equal, redact_secrets


def test_secret_redaction():
    text = "api_key=supersecret token:abc authorization=BearerXYZ"
    redacted = redact_secrets(text)
    assert "supersecret" not in redacted
    assert "abc" not in redacted
    assert "BearerXYZ" not in redacted


def test_constant_time_compare_semantics():
    assert constant_time_equal("a", "a")
    assert not constant_time_equal("a", "b")
