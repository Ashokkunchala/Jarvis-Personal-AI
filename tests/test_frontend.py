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
