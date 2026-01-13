import os
import time
from typing import Dict


async def cleanup_statistics_reports(days: int = 7) -> Dict[str, int]:
    base_dir = os.path.join("src", "html", "out")
    try:
        entries = os.listdir(base_dir)
    except FileNotFoundError:
        return {"deleted": 0, "kept": 0}
    except Exception:
        return {"deleted": 0, "kept": 0}

    now = time.time()
    cutoff = now - (days * 86400)
    deleted = 0
    kept = 0

    for name in entries:
        if not name.startswith("statistics_") or not name.endswith(".html"):
            continue
        path = os.path.join(base_dir, name)
        try:
            stat = os.stat(path)
        except Exception:
            continue
        if stat.st_mtime < cutoff:
            try:
                os.remove(path)
                deleted += 1
            except Exception:
                kept += 1
        else:
            kept += 1

    return {"deleted": deleted, "kept": kept}
