from app.live_voice import _origin_is_allowed


def test_live_voice_allows_configured_origin():
    assert _origin_is_allowed("http://localhost:3000", "127.0.0.1:8000", {"http://localhost:3000"})


def test_live_voice_allows_same_origin_backend_ui():
    assert _origin_is_allowed("http://127.0.0.1:8000", "127.0.0.1:8000", set())


def test_live_voice_rejects_unconfigured_cross_origin():
    assert not _origin_is_allowed("https://attacker.example", "127.0.0.1:8000", set())


def test_live_voice_allows_token_authenticated_native_client_without_origin():
    assert _origin_is_allowed(None, "127.0.0.1:8000", set())
