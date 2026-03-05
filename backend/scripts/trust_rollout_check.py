"""Rollout readiness check for trust-first production guardrails.

Usage:
  cd backend && python scripts/trust_rollout_check.py --hours 24
"""

from __future__ import annotations

import argparse
import json

from app.core.config import get_settings
from app.services.supabase_client import get_supabase_client
from app.services.trust_monitor import get_trust_metrics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=24)
    args = parser.parse_args()

    settings = get_settings()
    db = get_supabase_client()
    metrics = get_trust_metrics(db, hours=args.hours)

    served_p0 = int(metrics.get("served_p0_rows", 0))
    served_p1 = int(metrics.get("served_p1_rows", 0))
    dual = metrics.get("dual_run", {}) or {}
    dual_match_rate = float(dual.get("verdict_match_rate", 1.0))

    checks = {
        "strict_p1_enabled": bool(settings.trust_strict_p1),
        "no_served_p0": served_p0 == 0,
        "no_served_p1": served_p1 == 0 if settings.trust_strict_p1 else True,
        "dual_run_match_rate_gte_0_90": dual_match_rate >= 0.90,
    }
    ready = all(checks.values())

    print(
        json.dumps(
            {
                "ready": ready,
                "checks": checks,
                "metrics": metrics,
                "config": {
                    "trust_strict_p1": settings.trust_strict_p1,
                    "trust_dual_run_enabled": settings.trust_dual_run_enabled,
                    "trust_dual_run_percent": settings.trust_dual_run_percent,
                },
            },
            indent=2,
        )
    )
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
