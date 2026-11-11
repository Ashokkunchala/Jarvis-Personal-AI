import shutil
import subprocess
import tempfile
from html.parser import HTMLParser
from pathlib import Path

HTML_PATH = Path(__file__).parents[1] / "app" / "static" / "index.html"
DASHBOARD_PATH = HTML_PATH.with_name("dashboard.html")


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
    for html_path in (HTML_PATH, DASHBOARD_PATH):
        parser = ScriptCollector()
        parser.feed(html_path.read_text(encoding="utf-8"))
        assert parser.scripts, f"Expected {html_path.name} to contain its application script"
        for script in parser.scripts:
            with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as handle:
                handle.write(script)
                path = handle.name
            try:
                result = subprocess.run([node, "--check", path], text=True, capture_output=True, check=False)
                assert result.returncode == 0, result.stderr
            finally:
                Path(path).unlink(missing_ok=True)


def test_dashboard_displays_measured_network_traffic():
    dashboard = DASHBOARD_PATH.read_text(encoding="utf-8")
    assert 'id="networkTraffic"' in dashboard
    assert "network_bytes_sent" in dashboard
    assert "network_bytes_recv" in dashboard
    assert "previousNetwork" in dashboard
    assert 'id="runtimeFeed"' in dashboard
    assert '"/api/runtime/events?"' in dashboard
    assert "addRuntimeEvent" in dashboard
    assert "setupWarningPanel" in dashboard
    assert "checkThresholdWarnings" in dashboard
    assert "Notification.requestPermission()" in dashboard
    assert "localStorage.setItem(\"jarvisThresholdWarnings\"" in dashboard


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
        "case \"transcript\"",
        "[1006,1011,1012].includes(event.code)",
        "reconnectAttempts<2",
        "event.code===4429",
        'clearTimeout(reconnectTimer)',
    ):
        assert expected in live_client


def test_saved_plans_are_visible_and_explicitly_non_executable():
    html = HTML_PATH.read_text(encoding="utf-8")
    assert 'id="planForm"' in html
    assert 'id="planSteps"' in html
    assert 'id="plans"' in html
    assert '"/api/plans"' in html
    assert '"/api/plans/"+plan.id+"/history"' in html
    assert 'status:"cancelled"' in html
    assert "never run tools" in html
    assert "A target date creates a one-time reminder" in html


def test_scheduled_checks_are_opt_in_and_have_disable_controls():
    html = HTML_PATH.read_text(encoding="utf-8")
    assert 'id="scheduleForm"' in html
    assert 'id="scheduleTool"' in html
    assert '"/api/schedules"' in html
    assert 'method:"PATCH",body:JSON.stringify({enabled:false})' in html
    assert '"/api/schedules/"+schedule.id+"/history"' in html
    assert "New schedules start disabled" in html
    assert 'value="read_file"' not in html


def test_external_live_voice_javascript_syntax_when_node_is_available():
    node = shutil.which("node")
    if not node:
        return
    script = HTML_PATH.parent / "live_voice.js"
    result = subprocess.run([node, "--check", str(script)], text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    worklet = HTML_PATH.parent / "audio_capture_worklet.js"
    result = subprocess.run([node, "--check", str(worklet)], text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
