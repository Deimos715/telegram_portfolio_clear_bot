import os
import signal
import asyncio


async def request_restart() -> None:
    await asyncio.sleep(0.7)
    try:
        os.kill(os.getpid(), signal.SIGTERM)
    except Exception:
        raise SystemExit(0)
