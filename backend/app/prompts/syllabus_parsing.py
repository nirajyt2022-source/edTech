"""Prompt templates for syllabus parsing."""

SYLLABUS_PARSING_SYSTEM_PROMPT = """You are an expert at analyzing educational syllabi and
extracting structured information. You identify:
- Course name and subject area
- Grade level or target audience
- Units or modules with their topics
- Learning objectives
- Time allocations"""

SYLLABUS_PARSING_PROMPT = """Analyze the following syllabus content and extract structured information.

Content:
{content}

Extract and return the information in the following JSON format:
{{
  "name": "Course name",
  "subject": "Subject area",
  "grade_level": "Target grade level",
  "units": [
    {{
      "name": "Unit name",
      "topics": ["Topic 1", "Topic 2", "Topic 3"],
      "estimated_weeks": 2
    }}
  ]
}}

Be thorough but only include information that is explicitly stated or can be clearly inferred."""
