"""Read-only skill registry — maps skill_tag to contract instance."""

from .column_addition import ColumnAdditionContract

SKILL_REGISTRY = {
    "column_add_with_carry": ColumnAdditionContract(),
}
