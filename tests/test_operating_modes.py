import asyncio
from pathlib import Path

import pytest

from app.personality import mode_instruction
from jarvis.personality_modes import MODES, ModeStore, overlay_for
from jarvis.tools.registry import Risk, Tool, ToolRegistry

REQUIRED = {'personal', 'friend', 'mentor', 'devops', 'developer', 'research', 'system_admin', 'security', 'fitness', 'emergency'}


def test_requested_modes_preserve_existing_styles():
    assert REQUIRED <= MODES.keys()
    assert {'assistant', 'friend', 'teacher', 'storyteller', 'doctor'} <= MODES.keys()
    for key in REQUIRED:
        assert mode_instruction(key) == overlay_for(key)
        assert MODES[key].voice_style


@pytest.mark.parametrize('mode', sorted(REQUIRED))
def test_operating_modes_persist_but_never_bypass_execution_confirmation(mode, tmp_path):
    store = ModeStore(tmp_path / 'mode.json')
    assert store.set(mode).name == mode and store.get() == mode
    registry = ToolRegistry()
    called = []
    registry.register(Tool(name='critical', description='test', parameters={}, handler=lambda: called.append(True), risk=Risk.HIGH))
    assert not asyncio.run(registry.execute('critical', auto_approve=True)).ok
    assert not called


def test_web_selector_exposes_every_requested_mode_without_removing_legacy_options():
    from html.parser import HTMLParser
    class Options(HTMLParser):
        in_modes = False
        options = []
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'select' and attrs.get('id') == 'personalityMode':
                self.in_modes = True
            if tag == 'option' and self.in_modes:
                self.options.append(attrs['value'])
        def handle_endtag(self, tag):
            if tag == 'select':
                self.in_modes = False
    parser = Options()
    parser.feed((Path(__file__).parents[1] / 'app/static/index.html').read_text())
    assert REQUIRED <= set(parser.options)
    assert set(parser.options) == set(MODES)


def test_emergency_mode_makes_no_dispatch_or_tool_access_claim():
    overlay = overlay_for('emergency').lower()
    assert 'contacting local emergency services' in overlay
    assert 'never bypass approvals' in overlay
    assert 'do not imply monitoring' in overlay
