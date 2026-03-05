from app.services.trust_dual_run import should_run_dual_shadow
from app.services.trust_monitor import get_trust_metrics


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *_args, **_kwargs):
        return self

    def gte(self, *_args, **_kwargs):
        return self

    def execute(self):
        class _Res:
            data = self._rows

        return _Res()


class _FakeDb:
    def __init__(self, failures, dual):
        self._failures = failures
        self._dual = dual

    def table(self, name):
        if name == "trust_failures":
            return _FakeQuery(self._failures)
        if name == "trust_dual_run_results":
            return _FakeQuery(self._dual)
        return _FakeQuery([])


def test_dual_shadow_sampling_bounds_and_determinism():
    key = "req|grade|subject|topic"
    assert should_run_dual_shadow(key, 0) is False
    assert should_run_dual_shadow(key, 100) is True
    assert should_run_dual_shadow(key, 5) == should_run_dual_shadow(key, 5)


def test_trust_metrics_aggregation():
    db = _FakeDb(
        failures=[
            {
                "request_id": "r1",
                "rule_id": "R15_ANSWER_AUTHORITY",
                "severity": "P0",
                "grade": "Class 5",
                "subject": "Maths",
                "topic": "Fractions",
                "fingerprint": "fp1",
                "was_served": True,
            },
            {
                "request_id": "r2",
                "rule_id": "R21_PARENT_CONFIDENCE",
                "severity": "P1",
                "grade": "Class 1",
                "subject": "Maths",
                "topic": "Addition",
                "fingerprint": "fp2",
                "was_served": False,
            },
        ],
        dual=[
            {"verdict_match": True},
            {"verdict_match": False},
        ],
    )
    out = get_trust_metrics(db, hours=24)
    assert out["failure_rows"] == 2
    assert out["served_p0_rows"] == 1
    assert out["served_p1_rows"] == 0
    assert out["dual_run"]["sample_count"] == 2
    assert out["dual_run"]["verdict_match_count"] == 1
