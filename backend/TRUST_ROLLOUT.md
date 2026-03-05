# Trust Rollout Runbook (P0/P1 Zero-Tolerance)

This runbook operationalizes the trust-first plan on the live V2 path.

## 1) Required Env Flags

Set in deployment config:

- `TRUST_STRICT_P1=true` (production), `false` (staging during debug)
- `TRUST_CANARY_PERCENT=5`
- `TRUST_AUTOPOLICY_REPEAT_THRESHOLD=3`
- `TRUST_AUTOPOLICY_P1_IMPROVEMENT_MIN=0.2`
- `TRUST_DUAL_RUN_ENABLED=true` (Week 4)
- `TRUST_DUAL_RUN_PERCENT=5` (start at 5, then 10/25)
- `TRUST_DUAL_RUN_TIMEOUT_MS=45000`

## 2) Migration Order

Run SQL migrations in order:

1. `backend/migrations/010_trust_policy_engine.sql`
2. `backend/migrations/011_trust_dual_run.sql`

## 3) Week-by-Week Rollout

### Week 1 (Phase 0+1)

- Enable truthful verdicts + trust summary.
- Keep `TRUST_STRICT_P1=false` in staging.
- Enable `TRUST_STRICT_P1=true` in production after staging validation.
- Monitor `GET /health/trust-metrics?hours=24`.

Exit gate:
- served P0 rows = 0
- served P1 rows = 0

### Week 2 (Phase 2 manual approval)

- Enable nightly:
  - `python scripts/propose_trust_policies.py`
  - `python scripts/promote_trust_policies.py` (manual review before running)
- Snapshot baseline:
  - `python scripts/trust_baseline_report.py`

Exit gate:
- no new served P0
- net P1 reduction on recurring scopes

### Week 3 (Phase 3 canary + rollback)

- Keep new auto-policies in `canary`.
- Auto rollback trigger:
  - any served P0/P1
  - blocked spike above agreed threshold
  - latency regression >20%

Recommended command:
- `python scripts/trust_rollout_check.py --hours 24`

### Week 4 (Phase 4 dual-run parity)

- Enable shadow parity on live V2 requests:
  - `TRUST_DUAL_RUN_ENABLED=true`
  - `TRUST_DUAL_RUN_PERCENT=5` (increase gradually)
- Compare parity from `trust_dual_run_results` and `/health/trust-metrics`.
- Cut over default engine only after 7 consecutive days:
  - no served P0
  - no served P1
  - stable blocked rate
  - high verdict match rate in dual run

## 4) Operational Endpoints

- `GET /health/trust-metrics?hours=24`
- `GET /health/deep`
- `GET /health/ai-metrics`

All are protected by `X-Health-Token` when `HEALTH_CHECK_TOKEN` is configured.

## 5) No-Server Option (GitHub Actions)

If you do not run a VM/server, use:

- `.github/workflows/trust-nightly.yml`

Set repository secrets:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`
- `GEMINI_API_KEY` (optional for future trust jobs; safe to set)

Then trigger manually with **Actions → Trust Nightly Ops → Run workflow**,
or wait for the daily schedule.
