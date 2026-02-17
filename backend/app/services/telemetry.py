import time
import json
import logging
import asyncio
from typing import Optional
from functools import wraps

logger = logging.getLogger("practicecraft.telemetry")


def emit_event(event: str, *, route: str, version: str, student_id: Optional[str] = None,
               skill_tag: Optional[str] = None, topic: Optional[str] = None,
               error_type: Optional[str] = None, latency_ms: Optional[int] = None,
               ok: Optional[bool] = None):
    payload = {
        "event": event,
        "route": route,
        "version": version,
        "student_id": student_id,
        "skill_tag": skill_tag,
        "topic": topic,
        "error_type": error_type,
        "latency_ms": latency_ms,
        "ok": ok,
        "ts": time.time(),
    }
    # log as single-line JSON for easy parsing in prod
    logger.info("telemetry=%s", json.dumps(payload, separators=(",", ":")))

    # persist to Supabase (best-effort, never block the request)
    import os
    if os.getenv("ENABLE_TELEMETRY_DB", "0") != "1":
        return

    try:
        from app.services.supabase_client import get_supabase_client
        sb = get_supabase_client()
        sb.table("telemetry_events").insert({
            "event": event,
            "route": route,
            "version": version,
            "student_id": student_id,
            "skill_tag": skill_tag,
            "topic": topic,
            "error_type": error_type,
            "latency_ms": latency_ms,
            "ok": ok,
        }).execute()
    except Exception as e:
        logger.error(f"[telemetry.emit_event] {e}", exc_info=True)


def instrument(route: str, version: str):
    def deco(fn):
        if asyncio.iscoroutinefunction(fn):
            @wraps(fn)
            async def wrapped_async(*args, **kwargs):
                t0 = time.time()
                ok = True
                err = None
                try:
                    out = await fn(*args, **kwargs)
                    return out
                except Exception as e:
                    ok = False
                    err = str(e.__class__.__name__)
                    raise
                finally:
                    dt = int((time.time() - t0) * 1000)
                    emit_event("api_call", route=route, version=version, latency_ms=dt, ok=ok,
                               error_type=err)
            return wrapped_async
        else:
            @wraps(fn)
            def wrapped(*args, **kwargs):
                t0 = time.time()
                ok = True
                err = None
                try:
                    out = fn(*args, **kwargs)
                    return out
                except Exception as e:
                    ok = False
                    err = str(e.__class__.__name__)
                    raise
                finally:
                    dt = int((time.time() - t0) * 1000)
                    emit_event("api_call", route=route, version=version, latency_ms=dt, ok=ok,
                               error_type=err)
            return wrapped
    return deco
