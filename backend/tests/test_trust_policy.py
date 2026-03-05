from app.services.trust_policy import TrustSeverity, is_trust_blocking_failure, severity_for_rule


def test_severity_mapping_known_rules():
    assert severity_for_rule("R15_ANSWER_AUTHORITY") == TrustSeverity.P0
    assert severity_for_rule("R21_PARENT_CONFIDENCE") == TrustSeverity.P1
    assert severity_for_rule("R19_CURRICULUM_DEPTH") == TrustSeverity.P2


def test_blocking_logic():
    assert is_trust_blocking_failure("R15_ANSWER_AUTHORITY", strict_p1=False) is True
    assert is_trust_blocking_failure("R21_PARENT_CONFIDENCE", strict_p1=False) is False
    assert is_trust_blocking_failure("R21_PARENT_CONFIDENCE", strict_p1=True) is True


def test_v3_quality_gate_rules_mapped():
    assert severity_for_rule("V3_QUALITY_GATE_BLOCK") == TrustSeverity.P0
    assert severity_for_rule("V3_QUALITY_GATE_WARNING") == TrustSeverity.P1
