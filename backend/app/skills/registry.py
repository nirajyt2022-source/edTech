"""Read-only skill registry — maps skill_tag to contract instance."""

from .column_addition import ColumnAdditionContract
from .column_subtraction import ColumnSubtractionWithBorrowContract
from .multiplication_table import MultiplicationTableRecallContract

SKILL_REGISTRY = {
    "column_add_with_carry": ColumnAdditionContract(),
    "column_sub_with_borrow": ColumnSubtractionWithBorrowContract(),
    "multiplication_table_recall": MultiplicationTableRecallContract(),
}
