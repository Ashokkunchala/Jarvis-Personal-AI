"""Terminal clients for JARVIS.

* :mod:`jarvis.terminal.robot` - an animated floating robot that also shows a
  laptop gauge and can dial a live voice call.
* :mod:`jarvis.terminal.voice` - the background voice-call controller used by
  the robot; its heavy audio dependencies are imported only when a call starts.

The old Textual command-centre UI has been removed.
"""

from __future__ import annotations

__all__ = ["robot", "voice"]
