# Live web research (initial adapter)

The authenticated `POST /api/research` endpoint performs a user-triggered DuckDuckGo HTML search and returns titles, URLs, and snippets for up to eight results. Example body:

```json
{"query":"FastAPI official security guidance","limit":5}
```

Include the bearer token as described in [Personal Data API](PERSONAL-DATA-API.md). Search depends on the external provider's HTML and may fail or change; a timeout/provider failure returns HTTP 502. The returned snippets are untrusted data, not instructions. Follow source links and verify claims before acting.

This is search, not full browser automation: it does not sign in, click forms, submit transactions, download files, or execute webpage-provided instructions. Browser automation remains a separate future milestone with an allow-listed, isolated worker and confirmation gates.
