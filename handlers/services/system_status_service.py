import os
import sys
import time
from typing import Dict

from db_handler.db_funk import db_ping

_START_TS = time.monotonic()


def _format_uptime(seconds: float) -> str:
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


async def get_system_status() -> Dict[str, str]:
    uptime = _format_uptime(time.monotonic() - _START_TS)
    python_version = sys.version.split()[0]
    pid = str(os.getpid())
    db_ok = await db_ping()
    return {
        "uptime": uptime,
        "python": python_version,
        "pid": pid,
        "db": "OK" if db_ok else "FAIL",
    }
