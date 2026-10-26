import shutil
import subprocess
import tempfile
from html.parser import HTMLParser
from pathlib import Path


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


def test_voice_first_interface_has_explicit_privacy_and_cancel_controls():
    html = HTML_PATH.read_text(encoding="utf-8")
    for expected in (
        'id="voiceStart"',
        'id="voiceStop"',
        'id="stopSpeech"',
        'id="voiceOrb"',
        'id="voiceTitle"',
        "transcript ready",
        "Tap Start voice to capture a message",
        "Full-duplex real-time audio and background listening are not yet integrated",
    ):
        assert expected in html
