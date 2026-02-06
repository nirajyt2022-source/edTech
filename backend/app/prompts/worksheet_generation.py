"""Prompt templates for worksheet generation."""

WORKSHEET_GENERATION_SYSTEM_PROMPT = """You are an expert educator who creates high-quality,
pedagogically sound worksheets for students. You generate questions that:
- Are age and grade-level appropriate
- Test understanding, not just memorization
- Have clear, unambiguous wording
- Include a mix of difficulty levels when requested
- Cover the requested topic thoroughly"""

WORKSHEET_GENERATION_PROMPT = """Create a worksheet with the following specifications:

Subject: {subject}
Grade Level: {grade_level}
Topic: {topic}
Number of Questions: {num_questions}
Question Types: {question_types}
Difficulty: {difficulty}

{custom_instructions}

Generate the worksheet in the following JSON format:
{{
  "title": "Worksheet title",
  "questions": [
    {{
      "id": "q1",
      "type": "multiple_choice|fill_blank|short_answer|true_false|matching",
      "text": "Question text",
      "options": ["A", "B", "C", "D"],  // for multiple_choice only
      "correct_answer": "correct answer",
      "explanation": "Why this is correct",
      "difficulty": "easy|medium|hard"
    }}
  ]
}}

Ensure all questions are accurate and appropriate for the specified grade level."""
