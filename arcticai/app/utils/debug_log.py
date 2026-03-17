from __future__ import annotations

import json
import time
import uuid
from typing import Any


LOG_PATH = "debug-0679f1.log"
SESSION_ID = "0679f1"


def dlog(*, location: str, message: str, data: dict[str, Any] | None = None, run_id: str, hypothesis_id: str) -> None:
    payload = {
        "sessionId": SESSION_ID,
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data or {},
        "timestamp": int(time.time() * 1000),
        "id": f"log_{int(time.time()*1000)}_{uuid.uuid4().hex[:8]}",
    }
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        # Debug logging must never break runtime behavior.
        pass

