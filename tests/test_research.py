from app.research import search_web


def test_search_web_parses_attributed_result(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, limit):
            return b'<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage">Example result</a><div class="result__snippet">Useful summary</div>'

    monkeypatch.setattr("app.research.urlopen", lambda *args, **kwargs: FakeResponse())
    results = search_web("test query", 1)
    assert results
    assert results[0]["url"] == "https://example.com/page"
    assert "Example result" in results[0]["title"]
    assert results[0]["snippet"] == "Useful summary"
