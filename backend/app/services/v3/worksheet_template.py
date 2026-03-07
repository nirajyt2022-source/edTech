"""Render worksheet dict to beautiful HTML using Jinja2 template."""

from __future__ import annotations

import math
import os

from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "templates")

_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=True,
)

# Register custom filters/globals for SVG math
_env.globals["math"] = math
_env.globals["range"] = range
_env.globals["int"] = int
_env.globals["str"] = str
_env.globals["len"] = len
_env.globals["min"] = min
_env.globals["max"] = max
_env.globals["enumerate"] = enumerate


def render_worksheet_html(worksheet: dict) -> str:
    """Render enriched worksheet to HTML string.

    Args:
        worksheet: Worksheet dict with visual_strategy enrichments applied.

    Returns:
        Complete HTML string ready for iframe display or WeasyPrint PDF.
    """
    template = _env.get_template("worksheet.html.j2")
    return template.render(worksheet=worksheet)
