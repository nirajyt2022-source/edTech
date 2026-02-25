# Debugging Protocol

Aligned with CLAUDE.md Rule 2 (no silent failures) and Rule 6 (grep after replace_all).

## Pre-Flight Checklist

Before investigating any bug, confirm:

```bash
cd backend && python -m ruff check app/ --fix && python -m ruff format app/
cd backend && python -m pytest tests/ -x -v
cd frontend && npm run build
```

If any of these fail, fix them first — you may already have found the bug.

## Rule 2: No Silent Failures

Every `except` block MUST log. Never use bare `except: pass`.

### Pattern: Correct Error Handling

```python
# CORRECT — log + re-raise or return meaningful error
except HTTPException:
    raise
except Exception as e:
    logger.error("operation_failed", error=str(e), context_var=context_var)
    raise HTTPException(status_code=500, detail="Operation failed")
```

### Anti-Pattern: Silent Swallow

```python
# WRONG — silent failure, impossible to debug
except Exception:
    pass

# WRONG — returns empty data, hides real errors
except Exception:
    return []
```

### Audit Command

Find all silent failures in the codebase:

```bash
# Find bare except:pass
grep -rn "except.*:$" backend/app/ | grep -v "raise\|logger\|log\."

# Find except blocks that return empty without logging
grep -rn -A2 "except Exception" backend/app/ | grep "return \[\]\|return {}\|return None\|pass$"
```

## Rule 6: Grep After replace_all

After any Edit with `replace_all=true`, ALWAYS grep for stale references.

### Protocol

1. **Before**: Note the old name/pattern being replaced
2. **Edit**: Run the replace_all
3. **After**: Grep for the old name in ALL files that might reference it

```bash
# Example: renamed get_user_id_from_token → get_user_id
grep -rn "get_user_id_from_token" backend/app/
# Must return ZERO results. If any found, fix them.
```

### Common Stale Reference Sources

| Renamed | Check in |
|---------|----------|
| Function names | All `.py` files that import it |
| Module-level variables | All files that reference `module.variable` |
| Class names | All files + tests |
| API route paths | Frontend `api.ts`, tests, docs |
| Environment variables | `.env`, `config.py`, deploy configs |

### Verification Command

```bash
# After any rename, run:
cd backend && python -m py_compile app/path/to/changed_file.py
cd backend && python -m pytest tests/ -x -q  # catch import errors
```

## Debugging Flowchart

```
Bug reported
    │
    ├─► 1. Reproduce locally (backend logs, browser console)
    │
    ├─► 2. Check structlog output for error context
    │       logger.error() includes structured fields
    │
    ├─► 3. Check Sentry for stack trace + AI call spans
    │       All AIClient methods have Sentry instrumentation
    │
    ├─► 4. Isolate: backend or frontend?
    │       curl the API endpoint directly
    │
    ├─► 5. Read the code path (don't guess)
    │       Read the file before suggesting changes
    │
    ├─► 6. Fix + verify
    │       py_compile → ruff → pytest → frontend build
    │
    └─► 7. Grep for collateral damage
            Did the fix break any imports/references?
```

## Common Debugging Scenarios

### LLM Returns Bad JSON

```bash
# Check ai_client.py logs
grep "generate_json parse failed" backend/logs/

# The _parse_json() method strips markdown fences automatically.
# If still failing, check if Gemini returned HTML or error text.
```

### Auth Failures (401/422)

```bash
# All auth goes through deps.py get_user_id()
# Check: is Authorization header present?
curl -v https://api/endpoint -H "Authorization: Bearer TOKEN"

# Check: is the JWT valid and not expired?
# Supabase client.auth.get_user(token) will throw if invalid
```

### Rate Limit Hit (429)

```bash
# All rate limits are in @limiter.limit() decorators
# Check which endpoint and what the limit is:
grep -rn "@limiter.limit" backend/app/api/
```

### Database Query Fails (500)

```bash
# Check Supabase dashboard for:
# 1. RLS policies blocking the query
# 2. Column name mismatches
# 3. Foreign key constraint violations

# All DB access goes through DbClient (Depends injection)
# Check the .eq() / .select() chain in the endpoint
```

## Pre-Commit Quality Gate

The `.git/hooks/pre-commit` runs automatically:

| Check | Blocking? | Command |
|-------|-----------|---------|
| ruff check (lint + security) | Yes | `ruff check backend/app/ --fix` |
| ruff format | Yes (auto-fixes) | `ruff format backend/app/` |
| mypy type check | No (gradual) | `mypy backend/app/ --ignore-missing-imports` |
| pytest | Yes | `pytest tests/ -x -q` |
| eslint | Yes | `npm run lint` |
| tsc --noEmit | Yes | `npx tsc --noEmit` |
| vite build | Yes | `npm run build` |

Skip with `--no-verify` only when you understand why a check fails and it's a false positive.
