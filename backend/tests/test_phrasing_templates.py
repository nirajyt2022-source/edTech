"""Tests for phrasing template lookup and sampling."""

from app.data.phrasing_templates import (
    PHRASING_TEMPLATES,
    PHRASING_TEMPLATES_BY_SUFFIX,
    get_phrasing_samples,
)


class TestPhrasingTemplatesData:
    def test_exact_keys_have_lists(self):
        for tag, templates in PHRASING_TEMPLATES.items():
            assert isinstance(templates, list), f"{tag} should map to a list"
            assert len(templates) >= 3, f"{tag} needs at least 3 templates, got {len(templates)}"

    def test_suffix_keys_have_lists(self):
        for suffix, templates in PHRASING_TEMPLATES_BY_SUFFIX.items():
            assert suffix.startswith("_"), f"suffix key '{suffix}' must start with '_'"
            assert isinstance(templates, list)
            assert len(templates) >= 3, f"{suffix} needs at least 3 templates"


class TestGetPhrasingSamples:
    def test_exact_match(self):
        samples = get_phrasing_samples("column_add_with_carry", count=2)
        assert len(samples) == 2
        for s in samples:
            assert s in PHRASING_TEMPLATES["column_add_with_carry"]

    def test_suffix_fallback(self):
        samples = get_phrasing_samples("subtraction_word_problem", count=2)
        assert len(samples) == 2
        for s in samples:
            assert s in PHRASING_TEMPLATES_BY_SUFFIX["_word_problem"]

    def test_no_match_returns_empty(self):
        samples = get_phrasing_samples("totally_unknown_xyz", count=2)
        assert samples == []

    def test_count_capped_at_available(self):
        samples = get_phrasing_samples("estimation", count=100)
        assert len(samples) == len(PHRASING_TEMPLATES["estimation"])

    def test_count_zero_returns_empty(self):
        samples = get_phrasing_samples("clock_reading", count=0)
        assert samples == []

    def test_all_exact_tags_return_samples(self):
        for tag in PHRASING_TEMPLATES:
            samples = get_phrasing_samples(tag, count=1)
            assert len(samples) == 1, f"Expected 1 sample for '{tag}', got {len(samples)}"

    def test_suffix_error_spot(self):
        samples = get_phrasing_samples("addition_error_spot", count=2)
        assert len(samples) == 2
        for s in samples:
            assert s in PHRASING_TEMPLATES_BY_SUFFIX["_error_spot"]
