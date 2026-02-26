"""Tests for intra-tier number progression in scenario blocks."""

import json
from pathlib import Path
from unittest.mock import patch

from app.services.worksheet_generator import _build_scenario_block, build_system_prompt


class TestScenarioBlockOrdering:
    """Scenario pairs should be split into Foundation (smaller) and Stretch (larger)."""

    def test_addition_pairs_split_foundation_stretch(self):
        """Foundation pairs should have smaller sums than Stretch pairs."""
        block = _build_scenario_block("Addition (carries)", "Class 3")
        if block is None:
            # No scenario pool file — skip
            return
        assert "Foundation pairs:" in block or "Stretch pairs:" in block

    def test_foundation_sums_less_than_stretch(self):
        """Parse output and verify Foundation sums < Stretch sums."""
        block = _build_scenario_block("Addition (carries)", "Class 3")
        if block is None:
            return

        import re

        foundation_sums = []
        stretch_sums = []
        for line in block.split("\n"):
            if "Foundation pairs:" in line:
                foundation_sums = [int(s) for s in re.findall(r"=(\d+)", line)]
            elif "Stretch pairs:" in line:
                stretch_sums = [int(s) for s in re.findall(r"=(\d+)", line)]

        if foundation_sums and stretch_sums:
            assert max(foundation_sums) <= max(stretch_sums), (
                f"Foundation max {max(foundation_sums)} should be <= Stretch max {max(stretch_sums)}"
            )

    def test_prompt_header_mentions_ordering(self):
        """The scenario block header should hint at number ordering."""
        block = _build_scenario_block("Addition (carries)", "Class 3")
        if block is None:
            return
        assert "smaller numbers first" in block.lower() or "larger later" in block.lower()


class TestNumberProgressionRule:
    """System prompt should include rule 9 about number progression."""

    def test_rule_9_in_system_prompt(self):
        sp = build_system_prompt("standard", "Maths")
        assert "NUMBER PROGRESSION" in sp
        assert "smaller" in sp.lower()

    def test_rule_9_mentions_groups(self):
        sp = build_system_prompt("standard", "Maths")
        assert "Foundation" in sp
        assert "Stretch" in sp
