from app.research import search_web


def test_search_web_parses_attributed_result(monkeypatch):
    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, limit):
            return b'<a class="result__a" href="https://example.com/page">Example result</a><a class="result__snippet">Useful summary</a>'

    monkeypatch.setattr("app.research.urlopen", lambda *args, **kwargs: FakeResponse())
    results = search_web("test query", 1)
    assert results
    assert results[0]["url"] == "https://example.com/page"
    assert "Example result" in results[0]["title"]
