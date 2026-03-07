"""
HTML Renderer — takes assembled worksheet dict and generates beautiful HTML
using one Gemini API call.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


def _grade_to_age(grade: str) -> str:
    """Convert grade string to age range."""
    grade_ages = {
        "Class 1": "6-7",
        "Class 2": "7-8",
        "Class 3": "8-9",
        "Class 4": "9-10",
        "Class 5": "10-11",
    }
    for k, v in grade_ages.items():
        if k.lower() in grade.lower():
            return v
    return "6-11"


def build_render_prompt(worksheet: dict) -> str:
    """Build the Gemini prompt that generates beautiful HTML from worksheet data."""

    title = worksheet.get("title", "Worksheet")
    grade = worksheet.get("grade", "")
    subject = worksheet.get("subject", "")
    topic = worksheet.get("topic", "")
    skill_focus = worksheet.get("skill_focus", "")
    common_mistake = worksheet.get("common_mistake", "")
    parent_tip = worksheet.get("parent_tip", "")
    objectives = worksheet.get("learning_objectives", [])
    questions = worksheet.get("questions", [])

    # Build question descriptions for the prompt
    q_descriptions = []
    for i, q in enumerate(questions):
        q_text = q.get("text", "")
        q_type = q.get("type", "short_answer")
        q_diff = q.get("difficulty", "medium")
        q_role = q.get("role", "")
        q_hint = q.get("hint", "")
        q_options = q.get("options", [])
        q_answer = q.get("correct_answer", "")
        q_visual_type = q.get("visual_type", "")
        q_visual_data = q.get("visual_data", {})

        desc = f"Q{i + 1} [{q_role}/{q_diff}]:\n"
        desc += f"  Type: {q_type}\n"
        desc += f"  Text: {q_text}\n"
        desc += f"  Answer: {q_answer}\n"

        if q_options:
            desc += f"  Options: {json.dumps(q_options)}\n"
        if q_hint:
            desc += f"  Hint: {q_hint}\n"

        # Visual data — this is the key part
        if q_visual_type and q_visual_data:
            desc += f"  Visual Type: {q_visual_type}\n"

            if q_visual_type == "object_group":
                groups = q_visual_data.get("groups", [])
                emoji = q_visual_data.get("object_emoji", "●")
                obj_name = q_visual_data.get("object_name", "objects")
                op = q_visual_data.get("operation", "+")
                group_strs = []
                for g in groups:
                    count = g.get("count", 0)
                    e = g.get("emoji", emoji)
                    group_strs.append(f"{count} × {e}")
                desc += f"  Visual: Show {f' {op} '.join(group_strs)} = ? (use actual emoji repeated, e.g., {emoji}{emoji}{emoji} for count 3)\n"
                desc += f"  Object: {obj_name} ({emoji})\n"

            elif q_visual_type == "pie_fraction":
                n = q_visual_data.get("numerator", 1)
                d = q_visual_data.get("denominator", 4)
                desc += f"  Visual: Draw a pie chart with {d} equal slices, {n} colored. Show fraction {n}/{d}.\n"

            elif q_visual_type == "clock":
                h = q_visual_data.get("hour", 12)
                m = q_visual_data.get("minute", 0)
                desc += f"  Visual: Draw an analog clock showing {h}:{m:02d}. Include all 12 numbers.\n"

            elif q_visual_type == "shapes":
                shapes = q_visual_data.get("shapes", [])
                target = q_visual_data.get("target", "")
                shape_names = [s.get("name", "") for s in shapes]
                desc += f"  Visual: Draw 4 shapes labeled A, B, C, D: {', '.join(shape_names)}. Target: {target}.\n"
                desc += "  Use different colors for each shape. Draw with SVG.\n"

            elif q_visual_type == "number_line":
                start = q_visual_data.get("hops_from", q_visual_data.get("start", 0))
                hops = q_visual_data.get("hops_count", 0)
                end_val = q_visual_data.get("end", 20)
                desc += f"  Visual: Draw a number line 0-{end_val}. Show {hops} hop arcs starting from {start}. Landing = ?\n"

            elif q_visual_type == "percentage_bar":
                pct = q_visual_data.get("percent", 50)
                desc += (
                    f"  Visual: Draw a horizontal percentage bar showing {pct}%. Include gridlines at 25%, 50%, 75%.\n"
                )

            elif q_visual_type == "picture_word_match":
                emoji_val = q_visual_data.get("emoji", "")
                word = q_visual_data.get("word", "")
                desc += f"  Visual: Show large emoji {emoji_val} with label '{word}' below.\n"

            elif q_visual_type == "ten_frame":
                filled = q_visual_data.get("filled", 0)
                desc += f"  Visual: Draw a 2x5 ten frame grid with {filled} filled dots.\n"

            elif q_visual_type == "money_coins":
                desc += f"  Visual: Draw Indian coins/notes as labeled circles. Data: {json.dumps(q_visual_data)}\n"

            else:
                desc += f"  Visual Data: {json.dumps(q_visual_data)}\n"

        q_descriptions.append(desc)

    objectives_str = "\n".join(f"  ✓ {obj}" for obj in objectives) if objectives else "  ✓ Practice and learn"

    prompt = f"""You are an expert children's worksheet designer. Generate a SINGLE complete HTML page for a beautiful, colorful, print-ready worksheet.

WORKSHEET DATA (verified by our curriculum engine — use EXACT numbers and answers):

Title: {title}
Grade: {grade} (Age {_grade_to_age(grade)})
Subject: {subject}
Topic: {topic}
Skill Focus: {skill_focus}
Learning Objectives:
{objectives_str}
Common Mistake: {common_mistake}
Parent Tip: {parent_tip}

QUESTIONS:
{chr(10).join(q_descriptions)}

DESIGN RULES:

1. OUTPUT: Single complete HTML with ALL CSS inline in a <style> tag. No external resources. No JavaScript.

2. PAGE: A4 portrait (210mm x 297mm), 15mm margins, white background, @media print CSS.

3. HEADER:
   - Large playful title (use a fun CSS font style — rounded, bold)
   - Colored pills for Grade, Subject, Topic
   - Learning objectives with checkmarks in a green box
   - "For Parents" tip in amber/warm box
   - Name: _______ Date: _______ Score: ___/{len(questions)} line

4. SECTIONS: Group questions into:
   - Foundation (recognition questions, easy) — green header
   - Application (application/representation, medium) — amber header
   - Stretch (thinking/error_detection, hard) — red header

5. PICTORIAL QUESTIONS (MOST IMPORTANT):
   For questions with visual data, the VISUAL IS THE QUESTION.

   For object_group: Show ACTUAL EMOJI characters in large size (1.5-2.5em), arranged in two groups.
   Left group -> colored "+" circle -> Right group -> colored "=" circle -> dashed answer box with "?"
   Each question card gets a DIFFERENT pastel background (amber, sky, rose, mint, lavender, peach, etc.)

   Example layout for 5 apples + 3 apples:
   🍎🍎🍎🍎🍎  [+]  🍎🍎🍎  [=]  [?]

   For pie_fraction: Draw SVG pie chart with colored/uncolored sectors.
   For clock: Draw SVG analog clock with hour numbers, hour hand, minute hand.
   For shapes: Draw SVG shapes (circle, triangle, square, rectangle, pentagon, hexagon) with colors.
   For number_line: Draw SVG number line with hop arcs.
   For percentage_bar: Draw colored horizontal bar with gridlines.
   For picture_word_match: Show large emoji (3em) centered with word below.
   For ten_frame: Draw 2x5 grid with filled/empty dots.

6. QUESTION TYPES:
   - MCQ: Question text + 4 options in 2x2 grid with A/B/C/D colored circles
   - Fill blank: Equation with blank line for answer
   - True/False: Statement + True/False options
   - Word problem: Story text with emoji illustration + answer line
   - Short answer: Question + lined writing space
   - Error detection: "Is this correct?" with True/False

7. Each question card must have:
   - Question number in colored circle
   - Difficulty stars (1-3)
   - The visual (if any) — LARGE and COLORFUL
   - Question text
   - Answer area (options/blank/lines)
   - Hint in light yellow italic (small text)
   - "Show your working:" space for medium/hard questions

8. FOOTER: "Generated by Skolar" small text, page numbers

9. ANSWER KEY: After all questions, a light gray section with answers in small font.
   Can be cut off by parent.

10. VISUAL STYLE:
    - Pastel color palette (no harsh colors)
    - Rounded corners (8-12px) on all cards
    - Subtle box shadows
    - Each question card: different pastel background
    - Large emoji (1.5-2.5em) for visibility
    - Kid-friendly but professional
    - Adequate spacing between questions
    - Indian context (use rupee symbol for money, Indian names in word problems)

CRITICAL:
- Use EXACTLY the numbers and answers provided. DO NOT change any.
- Every MCQ must include the correct answer among the options.
- Emoji must be actual Unicode emoji characters, not images.
- All SVG must be inline (no external references).
- Output ONLY the HTML. No markdown fences, no explanation, no preamble."""

    return prompt


def render_worksheet_html(client: object, worksheet: dict) -> str:
    """Call Gemini to render the worksheet as beautiful HTML.

    Args:
        client: The OpenAI-compatible client (same one used for fill_slots)
        worksheet: The assembled worksheet dict from assembler.py

    Returns:
        HTML string of the rendered worksheet
    """
    prompt = build_render_prompt(worksheet)

    logger.info("[html_renderer] Generating HTML for: %s", worksheet.get("title", ""))

    try:
        response = client.chat.completions.create(
            model="gemini-2.5-flash",
            messages=[
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=12000,
        )

        html = response.choices[0].message.content.strip()

        # Clean up any markdown fences
        if html.startswith("```html"):
            html = html[7:]
        if html.startswith("```"):
            html = html[3:]
        if html.endswith("```"):
            html = html[:-3]
        html = html.strip()

        # Basic validation
        if "<html" not in html.lower() and "<body" not in html.lower() and "<div" not in html.lower():
            logger.warning("[html_renderer] Response doesn't look like HTML, returning empty")
            return ""

        logger.info("[html_renderer] Generated %d bytes of HTML", len(html))
        return html

    except Exception as e:
        logger.error("[html_renderer] Gemini render failed: %s", e)
        return ""
