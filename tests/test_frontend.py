from html.parser import HTMLParser
from pathlib import Path

import shutil
import subprocess
import tempfile


HTML_PATH = Path(__file__).parents[1] / "app" / "static" / "index.html"


class ScriptCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []
        self.in_script = False
        self.current = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.in_script = True
            self.current = []

    def handle_data(self, data):
        if self.in_script:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.in_script:
            self.scripts.append("".join(self.current))
            self.in_script = False


def test_inline_javascript_syntax_when_node_is_available():
    node = shutil.which("node")
    if not node:
        return
    parser = ScriptCollector()
    parser.feed(HTML_PATH.read_text(encoding="utf-8"))
    assert parser.scripts, "Expected the browser UI to contain its application script"
    for script in parser.scripts:
        with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as handle:
            handle.write(script)
            path = handle.name
        try:
            result = subprocess.run([node, "--check", path], text=True, capture_output=True, check=False)
            assert result.returncode == 0, result.stderr
        finally:
            Path(path).unlink(missing_ok=True)


def test_voice_first_interface_has_live_audio_and_fallback_controls():
    html = HTML_PATH.read_text(encoding="utf-8")
    for expected in (
        'id="liveVoiceConnect"',
        'id="liveVoiceStop"',
        'id="liveVoiceInterrupt"',
        'id="liveVoiceStatus"',
        'id="liveVoiceTranscript"',
        'src="/static/live_voice.js"',
        'id="voiceOrb"',
        "Keep this backend private",
    ):
        assert expected in html
    live_client = (HTML_PATH.parent / "live_voice.js").read_text(encoding="utf-8")
    for expected in (
        '"/api/live-voice?ticket="',
        '"/api/live-voice-ticket"',
        'Authorization:"Bearer "+token',
        'type:"audio"',
        'type:"audio_end"',
        "getUserMedia",
        "stopPlayback",
    ):
        assert expected in live_client


def test_external_live_voice_javascript_syntax_when_node_is_available():
    node = shutil.which("node")
    if not node:
        return
    script = HTML_PATH.parent / "live_voice.js"
    result = subprocess.run([node, "--check", str(script)], text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr


def test_every_element_id_the_scripts_look_up_exists_in_the_page():
    """A missing id makes $("id").addEventListener throw and silently kills the page script."""
    import re

    html = HTML_PATH.read_text(encoding="utf-8")
    ids = set(re.findall(r'id="([^"]+)"', html))
    js = html + (HTML_PATH.parent / "live_voice.js").read_text(encoding="utf-8")
    used = set(re.findall(r'\$\("([A-Za-z0-9_-]+)"\)', js))
    # elements created at runtime are not expected in the static HTML
    missing = sorted(used - ids - {"welcome"})
    assert not missing, f"script looks up ids that are not in index.html: {missing}"


def test_live_voice_client_script_is_served_by_both_entry_points():
    from fastapi.testclient import TestClient

    from app.main import app as main_app
    from app.main_enhanced import app as enhanced_app

    for app in (main_app, enhanced_app):
        res = TestClient(app).get("/static/live_voice.js")
        assert res.status_code == 200 and "javascript" in res.headers["content-type"]
        assert "/api/live-voice" in res.text
        # the ticket endpoint exists (401/503 without a token, not 404)
        assert TestClient(app).post("/api/live-voice-ticket").status_code in (401, 503)
