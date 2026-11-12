"""Tests for the read-only web tools (search and page reading).

No network access: parsing and validation are exercised with fixtures and
monkeypatched fetch/DNS layers.
"""

from __future__ import annotations

import urllib.parse

import pytest

from jarvis.tools.net import web_tools
from jarvis.tools.net.web_tools import _SearchParser, _TextExtractor, _unwrap_duck_link

DDG_HTML = """
<html><body>
<a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Faws&amp;rut=abc">
  ECS blue green deployments</a>
<a class="result__snippet">How to do blue/green deployment on Amazon ECS with CodeDeploy.</a>
<a rel="nofollow" class="result__a" href="https://direct.example.net/page">A direct link result</a>
<a class="result__snippet">Second snippet text.</a>
</body></html>
"""

PAGE_HTML = """
<html><head><title>Example Page</title><style>body{color:red}</style></head>
<body>
<script>alert("ignore me")</script>
<h1>Main heading</h1>
<p>First paragraph of useful text.</p>
<p>Second paragraph with more detail.</p>
<template>hidden template</template>
</body></html>
"""


class TestSearchParser:
    def test_parses_results_with_unwrapped_links(self):
        parser = _SearchParser()
        parser.feed(DDG_HTML)
        assert len(parser.results) == 2
        first = parser.results[0]
        assert "ECS blue green" in first["title"]
        assert first["url"] == "https://example.com/aws"
        assert "blue/green deployment" in first["snippet"]
        assert parser.results[1]["url"] == "https://direct.example.net/page"

    def test_unwrap_plain_and_duck_links(self):
        assert _unwrap_duck_link("https://a.example/x") == "https://a.example/x"
        wrapped = "//duckduckgo.com/l/?uddg=" + urllib.parse.quote("https://b.example/y?z=1")
        assert _unwrap_duck_link(wrapped) == "https://b.example/y?z=1"
        assert _unwrap_duck_link("") == ""


class TestTextExtractor:
    def test_extracts_visible_text_and_title(self):
        ex = _TextExtractor()
        ex.feed(PAGE_HTML)
        text, truncated = ex.text(4000)
        assert ex.title.strip() == "Example Page"
        assert "Main heading" in text
        assert "First paragraph" in text
        assert "alert" not in text
        assert "color:red" not in text
        assert "hidden template" not in text
        assert truncated is False

    def test_truncation_flag(self):
        ex = _TextExtractor()
        ex.feed(PAGE_HTML)
        text, truncated = ex.text(20)
        assert len(text) == 20
        assert truncated is True


class TestUrlValidation:
    @pytest.mark.parametrize("url", ["http://127.0.0.1/", "http://localhost/admin",
                                     "https://192.168.1.1/", "http://[::1]/",
                                     "ftp://example.com/x", "file:///etc/passwd",
                                     "http://10.0.0.5/", "http://169.254.169.254/"])
    def test_refuses_local_and_non_web(self, url):
        assert web_tools.read_web_page(url)["success"] is False

    def test_bare_domain_gets_https(self, monkeypatch):
        seen = {}

        def fake_fetch(url, max_bytes=web_tools.MAX_PAGE_BYTES):
            seen["url"] = url
            return PAGE_HTML.encode(), url

        monkeypatch.setattr(web_tools, "_fetch", fake_fetch)
        # Skip real DNS for the validation step.
        monkeypatch.setattr(web_tools.socket, "getaddrinfo",
                            lambda host, port, proto=None: [(2, 1, 6, "", ("93.184.216.34", port))])
        result = web_tools.read_web_page("example.com")
        assert result["success"] is True
        assert seen["url"] == "https://example.com"


class TestReadWebPage:
    def test_success_shape(self, monkeypatch):
        monkeypatch.setattr(web_tools, "_fetch", lambda url, max_bytes=web_tools.MAX_PAGE_BYTES: (PAGE_HTML.encode(), url))
        result = web_tools.read_web_page("https://example.com/page")
        assert result["success"] is True
        assert result["title"] == "Example Page"
        assert "Second paragraph" in result["text"]
        assert "untrusted" in result["note"]

    def test_fetch_failure_is_soft_error(self, monkeypatch):
        def boom(url, max_bytes=web_tools.MAX_PAGE_BYTES):
            raise OSError("connection refused")

        monkeypatch.setattr(web_tools, "_fetch", boom)
        result = web_tools.read_web_page("https://example.com/")
        assert result["success"] is False
        assert "Could not read" in result["error"]


class TestSearchWeb:
    def test_success_shape(self, monkeypatch):
        monkeypatch.setattr(web_tools, "_fetch", lambda url, max_bytes=web_tools.MAX_PAGE_BYTES: (DDG_HTML.encode(), url))
        result = web_tools.search_web("ecs deployment", max_results=5)
        assert result["success"] is True
        assert len(result["results"]) == 2
        assert result["results"][0]["url"] == "https://example.com/aws"

    def test_empty_query_rejected(self):
        assert web_tools.search_web("   ")["success"] is False

    def test_no_results_is_soft_error(self, monkeypatch):
        monkeypatch.setattr(web_tools, "_fetch", lambda url, max_bytes=web_tools.MAX_PAGE_BYTES: (b"<html></html>", url))
        assert web_tools.search_web("nothing here")["success"] is False


class TestRegistryIntegration:
    def test_web_tools_registered(self):
        from jarvis.tools.builtin_tools import build_registry

        registry = build_registry()
        for name in ("web_search", "web_read_page"):
            tool = registry.get(name)
            assert tool is not None
            assert tool.category == "web"
            assert tool.confirm_required is False
