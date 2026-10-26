import asyncio
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jarvis.core.brain import JarvisBrain

logging.basicConfig(level=logging.WARNING)


async def main() -> None:
    brain = JarvisBrain()
    started = time.time()

    async def confirm(tool, args):
        print(f"\n  [CONFIRM] {tool.name}({args}) -> APPROVED", flush=True)
        return True

    prompt = (
        "Read my battery percent and current volume, then set system volume to 32 "
        "and tell me the final value."
    )
    async for ev in brain.ask(prompt, confirm=confirm):
        stamp = f"[{time.time() - started:.1f}s]"
        if ev["type"] == "text_delta":
            sys.stdout.write(ev["text"])
            sys.stdout.flush()
        else:
            print(f"\n<{ev['type']}> {ev} {stamp}", flush=True)
    print()


if __name__ == "__main__":
    asyncio.run(main())
