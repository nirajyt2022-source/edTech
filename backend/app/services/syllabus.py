"""Syllabus parsing service for extracting structured data from syllabus documents."""

from app.services.ai import get_ai_service
from app.prompts.syllabus_parsing import SYLLABUS_PARSING_PROMPT


class SyllabusService:
    """Service for parsing syllabus documents into structured data."""

    def __init__(self):
        self.ai_service = get_ai_service()

    async def parse_syllabus(self, content: str, file_type: str) -> dict:
        """Parse a syllabus document and extract structured data.

        Args:
            content: The syllabus content (text or base64 encoded)
            file_type: The file type (pdf, docx, txt)

        Returns:
            Structured syllabus data
        """
        # TODO: Implement document parsing and AI extraction
        prompt = SYLLABUS_PARSING_PROMPT.format(content=content)
        response = await self.ai_service.generate_completion(prompt)
        # TODO: Parse response into Syllabus model
        return {"raw_response": response}


def get_syllabus_service() -> SyllabusService:
    return SyllabusService()
