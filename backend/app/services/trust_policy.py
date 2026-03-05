"""Trust taxonomy and rule severity mapping.

Single source of truth for release-gate rule severities used by runtime
gating, audits, and CI checks.
"""

from __future__ import annotations

from enum import Enum


class TrustSeverity(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


# Release gate rule name -> trust severity.
RULE_SEVERITY: dict[str, TrustSeverity] = {
    # Hard correctness / integrity failures
    "R01_ARITHMETIC_VERIFIED": TrustSeverity.P0,
    "R02_KNOWN_TYPES_ONLY": TrustSeverity.P0,
    "R05_QUESTION_COUNT_EXACT": TrustSeverity.P0,
    "R08_MINIMUM_QUALITY_BAR": TrustSeverity.P0,
    "R14_SENTENCE_DIVERSITY_GUARD": TrustSeverity.P0,
    "R15_ANSWER_AUTHORITY": TrustSeverity.P0,
    "R22_MCQ_UNIQUE_ANSWER": TrustSeverity.P0,
    "R23_ANSWER_KEY_COMPLETE": TrustSeverity.P0,
    # Curriculum and trust-facing quality failures
    "R04_CURRICULUM_GROUNDED": TrustSeverity.P1,
    "R07_WORD_PROBLEM_VERIFIED": TrustSeverity.P1,
    "R09_SKILL_TAGS_VALID": TrustSeverity.P1,
    "R11_TOPIC_DRIFT_GUARD": TrustSeverity.P1,
    "R16_MCQ_QUALITY_GUARD": TrustSeverity.P1,
    "R17_HINDI_SCRIPT_PURITY": TrustSeverity.P1,
    "R18_FILL_BLANK_AMBIGUITY": TrustSeverity.P1,
    "R20_RENDER_INTEGRITY": TrustSeverity.P1,
    "R21_PARENT_CONFIDENCE": TrustSeverity.P1,
    "R24_MINIMUM_QUALITY_SCORE": TrustSeverity.P1,
    # V3 quality gate compatibility rules
    "V3_QUALITY_GATE_BLOCK": TrustSeverity.P0,
    "V3_QUALITY_GATE_WARNING": TrustSeverity.P1,
    # Informational / stamp-style checks
    "R03_FORMAT_MIX_TOLERANCE": TrustSeverity.P2,
    "R06_ADAPTIVE_EXPLICIT": TrustSeverity.P2,
    "R10_WARNINGS_TRANSPARENT": TrustSeverity.P2,
    "R12_ROUND_NUMBER_GUARD": TrustSeverity.P2,
    "R13_SENTENCE_STRUCTURE_GUARD": TrustSeverity.P2,
    "R19_CURRICULUM_DEPTH": TrustSeverity.P2,
}


# Rules where runtime exceptions should fail closed in strict mode.
FAIL_CLOSED_RULES: frozenset[str] = frozenset(
    {name for name, sev in RULE_SEVERITY.items() if sev in (TrustSeverity.P0, TrustSeverity.P1)}
)


def severity_for_rule(rule_name: str) -> TrustSeverity:
    """Return mapped trust severity for a rule, defaulting to P2."""
    return RULE_SEVERITY.get(rule_name, TrustSeverity.P2)


def is_trust_blocking_failure(rule_name: str, *, strict_p1: bool) -> bool:
    """Whether a failed rule must block under current strictness mode."""
    severity = severity_for_rule(rule_name)
    if severity == TrustSeverity.P0:
        return True
    if severity == TrustSeverity.P1 and strict_p1:
        return True
    return False
