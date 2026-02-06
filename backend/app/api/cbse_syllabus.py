from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from supabase import create_client
from app.core.config import get_settings

router = APIRouter(prefix="/api/cbse-syllabus", tags=["cbse-syllabus"])

settings = get_settings()

def get_supabase():
    """Create a fresh Supabase client to ensure schema is up to date."""
    return create_client(settings.supabase_url, settings.supabase_service_key)

supabase = get_supabase()


class SyllabusTopic(BaseModel):
    name: str
    subtopics: list[str] | None = None


class SyllabusChapter(BaseModel):
    name: str
    topics: list[SyllabusTopic]


class CBSESyllabus(BaseModel):
    id: str
    grade: str
    subject: str
    chapters: list[SyllabusChapter]


@router.get("/{grade}/{subject}")
async def get_cbse_syllabus(grade: str, subject: str):
    """Get CBSE syllabus for a specific grade and subject."""
    try:
        result = supabase.table("cbse_syllabus") \
            .select("*") \
            .eq("grade", grade) \
            .eq("subject", subject) \
            .single() \
            .execute()

        if not result.data:
            raise HTTPException(status_code=404, detail=f"Syllabus not found for {grade} {subject}")

        return result.data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get syllabus: {str(e)}")


@router.get("/grades")
async def list_available_grades():
    """List all grades with available syllabi."""
    try:
        result = supabase.table("cbse_syllabus") \
            .select("grade") \
            .execute()

        grades = sorted(list(set(row["grade"] for row in result.data)))
        return {"grades": grades}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list grades: {str(e)}")


@router.get("/subjects/{grade}")
async def list_subjects_for_grade(grade: str):
    """List all subjects available for a specific grade."""
    try:
        result = supabase.table("cbse_syllabus") \
            .select("subject") \
            .eq("grade", grade) \
            .execute()

        subjects = sorted([row["subject"] for row in result.data])
        return {"grade": grade, "subjects": subjects}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list subjects: {str(e)}")


# Seed data endpoint (admin only - for initial setup)
@router.post("/seed")
async def seed_cbse_syllabus():
    """Seed the CBSE syllabus data. Run once during setup."""

    syllabus_data = [
        # Class 1
        {
            "grade": "Class 1",
            "subject": "Maths",
            "chapters": [
                {"name": "Numbers (1-100)", "topics": [
                    {"name": "Counting 1-50", "subtopics": ["Forward counting", "Backward counting"]},
                    {"name": "Counting 51-100", "subtopics": ["Reading numbers", "Writing numbers"]},
                    {"name": "Number names", "subtopics": ["1-20 in words", "21-50 in words"]}
                ]},
                {"name": "Addition", "topics": [
                    {"name": "Addition up to 9", "subtopics": ["Using objects", "Using fingers"]},
                    {"name": "Addition up to 18", "subtopics": ["Single digit addition", "Word problems"]}
                ]},
                {"name": "Subtraction", "topics": [
                    {"name": "Subtraction up to 9", "subtopics": ["Taking away", "Finding difference"]},
                    {"name": "Subtraction up to 18", "subtopics": ["Without borrowing"]}
                ]},
                {"name": "Shapes", "topics": [
                    {"name": "Basic shapes", "subtopics": ["Circle", "Square", "Triangle", "Rectangle"]}
                ]},
                {"name": "Measurement", "topics": [
                    {"name": "Comparing lengths", "subtopics": ["Long and short", "Tall and short"]},
                    {"name": "Comparing weights", "subtopics": ["Heavy and light"]}
                ]}
            ]
        },
        {
            "grade": "Class 1",
            "subject": "English",
            "chapters": [
                {"name": "Alphabet", "topics": [
                    {"name": "Capital letters", "subtopics": ["A-M", "N-Z"]},
                    {"name": "Small letters", "subtopics": ["a-m", "n-z"]},
                    {"name": "Letter sounds", "subtopics": ["Phonics basics"]}
                ]},
                {"name": "Words", "topics": [
                    {"name": "Three letter words", "subtopics": ["CVC words", "Word families"]},
                    {"name": "Sight words", "subtopics": ["Common words", "Action words"]}
                ]},
                {"name": "Sentences", "topics": [
                    {"name": "Simple sentences", "subtopics": ["Reading sentences", "Forming sentences"]}
                ]}
            ]
        },
        {
            "grade": "Class 1",
            "subject": "EVS",
            "chapters": [
                {"name": "My Family", "topics": [
                    {"name": "Family members", "subtopics": ["Parents", "Siblings", "Grandparents"]},
                    {"name": "My home", "subtopics": ["Rooms in a house", "Things at home"]}
                ]},
                {"name": "My Body", "topics": [
                    {"name": "Body parts", "subtopics": ["Head", "Hands", "Legs"]},
                    {"name": "Sense organs", "subtopics": ["Eyes", "Ears", "Nose"]}
                ]},
                {"name": "Plants Around Us", "topics": [
                    {"name": "Parts of a plant", "subtopics": ["Roots", "Stem", "Leaves", "Flower"]}
                ]},
                {"name": "Animals Around Us", "topics": [
                    {"name": "Pet animals", "subtopics": ["Dog", "Cat", "Fish"]},
                    {"name": "Farm animals", "subtopics": ["Cow", "Hen", "Goat"]}
                ]}
            ]
        },
        # Class 2
        {
            "grade": "Class 2",
            "subject": "Maths",
            "chapters": [
                {"name": "Numbers (1-200)", "topics": [
                    {"name": "Counting to 200", "subtopics": ["Skip counting by 2s", "Skip counting by 5s", "Skip counting by 10s"]},
                    {"name": "Place value", "subtopics": ["Ones and Tens", "Expanded form"]}
                ]},
                {"name": "Addition", "topics": [
                    {"name": "2-digit addition", "subtopics": ["Without carrying", "With carrying"]},
                    {"name": "Word problems", "subtopics": ["Addition stories"]}
                ]},
                {"name": "Subtraction", "topics": [
                    {"name": "2-digit subtraction", "subtopics": ["Without borrowing", "With borrowing"]},
                    {"name": "Word problems", "subtopics": ["Subtraction stories"]}
                ]},
                {"name": "Multiplication", "topics": [
                    {"name": "Introduction to multiplication", "subtopics": ["Repeated addition", "Groups of"]},
                    {"name": "Tables 2-5", "subtopics": ["Table of 2", "Table of 3", "Table of 4", "Table of 5"]}
                ]},
                {"name": "Measurement", "topics": [
                    {"name": "Length", "subtopics": ["Centimeters", "Meters"]},
                    {"name": "Time", "subtopics": ["Reading clock", "Days of week"]}
                ]},
                {"name": "Money", "topics": [
                    {"name": "Indian currency", "subtopics": ["Coins", "Notes", "Simple addition"]}
                ]}
            ]
        },
        {
            "grade": "Class 2",
            "subject": "English",
            "chapters": [
                {"name": "Reading", "topics": [
                    {"name": "Short stories", "subtopics": ["Reading aloud", "Comprehension"]},
                    {"name": "Poems", "subtopics": ["Rhyming words", "Recitation"]}
                ]},
                {"name": "Grammar", "topics": [
                    {"name": "Nouns", "subtopics": ["Naming words", "Common nouns", "Proper nouns"]},
                    {"name": "Verbs", "subtopics": ["Action words", "Is/Am/Are"]},
                    {"name": "Pronouns", "subtopics": ["He/She/It/They"]}
                ]},
                {"name": "Writing", "topics": [
                    {"name": "Sentence writing", "subtopics": ["Capital letters", "Full stops"]},
                    {"name": "Picture description", "subtopics": ["Simple sentences about pictures"]}
                ]}
            ]
        },
        {
            "grade": "Class 2",
            "subject": "EVS",
            "chapters": [
                {"name": "Food", "topics": [
                    {"name": "Types of food", "subtopics": ["Fruits", "Vegetables", "Grains"]},
                    {"name": "Healthy eating", "subtopics": ["Good food habits"]}
                ]},
                {"name": "Water", "topics": [
                    {"name": "Sources of water", "subtopics": ["Rain", "Rivers", "Wells"]},
                    {"name": "Uses of water", "subtopics": ["Drinking", "Cleaning", "Cooking"]}
                ]},
                {"name": "Shelter", "topics": [
                    {"name": "Types of houses", "subtopics": ["Kutcha house", "Pucca house"]},
                    {"name": "Animal homes", "subtopics": ["Nest", "Burrow", "Den"]}
                ]},
                {"name": "Plants", "topics": [
                    {"name": "Types of plants", "subtopics": ["Trees", "Shrubs", "Herbs"]},
                    {"name": "Uses of plants", "subtopics": ["Food", "Medicine", "Shelter"]}
                ]}
            ]
        },
        # Class 3
        {
            "grade": "Class 3",
            "subject": "Maths",
            "chapters": [
                {"name": "Numbers (1-1000)", "topics": [
                    {"name": "3-digit numbers", "subtopics": ["Place value", "Expanded form", "Comparing numbers"]},
                    {"name": "Number patterns", "subtopics": ["Skip counting", "Ascending order", "Descending order"]}
                ]},
                {"name": "Addition", "topics": [
                    {"name": "3-digit addition", "subtopics": ["Without carrying", "With carrying"]},
                    {"name": "Word problems", "subtopics": ["Multi-step problems"]}
                ]},
                {"name": "Subtraction", "topics": [
                    {"name": "3-digit subtraction", "subtopics": ["Without borrowing", "With borrowing"]},
                    {"name": "Word problems", "subtopics": ["Multi-step problems"]}
                ]},
                {"name": "Multiplication", "topics": [
                    {"name": "Tables 2-10", "subtopics": ["Table of 6", "Table of 7", "Table of 8", "Table of 9", "Table of 10"]},
                    {"name": "2-digit multiplication", "subtopics": ["By 1-digit number"]}
                ]},
                {"name": "Division", "topics": [
                    {"name": "Introduction to division", "subtopics": ["Equal sharing", "Grouping"]},
                    {"name": "Division facts", "subtopics": ["Division by 2-5"]}
                ]},
                {"name": "Fractions", "topics": [
                    {"name": "Introduction to fractions", "subtopics": ["Half", "Quarter", "Three-fourths"]},
                    {"name": "Fraction of a whole", "subtopics": ["Shading fractions"]}
                ]},
                {"name": "Measurement", "topics": [
                    {"name": "Length", "subtopics": ["Meters and centimeters", "Conversion"]},
                    {"name": "Weight", "subtopics": ["Kilograms and grams"]},
                    {"name": "Capacity", "subtopics": ["Liters and milliliters"]}
                ]},
                {"name": "Time", "topics": [
                    {"name": "Reading time", "subtopics": ["Hours and minutes", "AM and PM"]},
                    {"name": "Calendar", "subtopics": ["Months", "Dates"]}
                ]},
                {"name": "Geometry", "topics": [
                    {"name": "2D shapes", "subtopics": ["Properties of shapes", "Perimeter"]},
                    {"name": "3D shapes", "subtopics": ["Cube", "Cuboid", "Sphere", "Cylinder"]}
                ]}
            ]
        },
        {
            "grade": "Class 3",
            "subject": "English",
            "chapters": [
                {"name": "Reading Comprehension", "topics": [
                    {"name": "Stories", "subtopics": ["Fiction", "Moral stories"]},
                    {"name": "Poems", "subtopics": ["Understanding poems", "Rhyme scheme"]}
                ]},
                {"name": "Grammar", "topics": [
                    {"name": "Nouns", "subtopics": ["Singular and plural", "Gender"]},
                    {"name": "Pronouns", "subtopics": ["Personal pronouns", "Possessive pronouns"]},
                    {"name": "Verbs", "subtopics": ["Present tense", "Past tense"]},
                    {"name": "Adjectives", "subtopics": ["Describing words", "Degrees of comparison"]},
                    {"name": "Articles", "subtopics": ["A, An, The"]}
                ]},
                {"name": "Writing", "topics": [
                    {"name": "Paragraph writing", "subtopics": ["My family", "My school", "My pet"]},
                    {"name": "Letter writing", "subtopics": ["Informal letters"]}
                ]},
                {"name": "Vocabulary", "topics": [
                    {"name": "Synonyms", "subtopics": ["Similar meaning words"]},
                    {"name": "Antonyms", "subtopics": ["Opposite words"]},
                    {"name": "Homophones", "subtopics": ["Same sound, different meaning"]}
                ]}
            ]
        },
        {
            "grade": "Class 3",
            "subject": "EVS",
            "chapters": [
                {"name": "Family and Friends", "topics": [
                    {"name": "Relationships", "subtopics": ["Extended family", "Neighbors"]},
                    {"name": "Festivals", "subtopics": ["National festivals", "Religious festivals"]}
                ]},
                {"name": "Food and Nutrition", "topics": [
                    {"name": "Food groups", "subtopics": ["Energy giving", "Body building", "Protective"]},
                    {"name": "Cooking", "subtopics": ["Raw and cooked food", "Kitchen utensils"]}
                ]},
                {"name": "Our Environment", "topics": [
                    {"name": "Air", "subtopics": ["Properties of air", "Air pollution"]},
                    {"name": "Water", "subtopics": ["Water cycle", "Conservation"]}
                ]},
                {"name": "Living Things", "topics": [
                    {"name": "Animals", "subtopics": ["Wild animals", "Domestic animals", "Animal habitats"]},
                    {"name": "Plants", "subtopics": ["Photosynthesis basics", "Seed germination"]}
                ]},
                {"name": "Transport", "topics": [
                    {"name": "Means of transport", "subtopics": ["Land", "Water", "Air"]},
                    {"name": "Traffic rules", "subtopics": ["Road safety"]}
                ]}
            ]
        },
        # Class 4
        {
            "grade": "Class 4",
            "subject": "Maths",
            "chapters": [
                {"name": "Large Numbers", "topics": [
                    {"name": "Numbers up to 10,000", "subtopics": ["Place value", "Comparison", "Rounding off"]},
                    {"name": "Indian number system", "subtopics": ["Lakhs", "Reading large numbers"]}
                ]},
                {"name": "Operations", "topics": [
                    {"name": "Addition and Subtraction", "subtopics": ["4-digit numbers", "Word problems"]},
                    {"name": "Multiplication", "subtopics": ["2-digit by 2-digit", "Word problems"]},
                    {"name": "Division", "subtopics": ["Long division", "Division with remainder"]}
                ]},
                {"name": "Factors and Multiples", "topics": [
                    {"name": "Factors", "subtopics": ["Finding factors", "Common factors"]},
                    {"name": "Multiples", "subtopics": ["Finding multiples", "LCM basics"]}
                ]},
                {"name": "Fractions", "topics": [
                    {"name": "Types of fractions", "subtopics": ["Proper", "Improper", "Mixed"]},
                    {"name": "Equivalent fractions", "subtopics": ["Finding equivalent fractions"]},
                    {"name": "Addition of fractions", "subtopics": ["Like fractions"]}
                ]},
                {"name": "Decimals", "topics": [
                    {"name": "Introduction to decimals", "subtopics": ["Tenths", "Hundredths"]},
                    {"name": "Decimal operations", "subtopics": ["Addition", "Subtraction"]}
                ]},
                {"name": "Geometry", "topics": [
                    {"name": "Lines and angles", "subtopics": ["Types of lines", "Types of angles"]},
                    {"name": "Perimeter and Area", "subtopics": ["Rectangle", "Square"]}
                ]},
                {"name": "Data Handling", "topics": [
                    {"name": "Pictographs", "subtopics": ["Reading pictographs", "Creating pictographs"]},
                    {"name": "Bar graphs", "subtopics": ["Reading bar graphs"]}
                ]}
            ]
        },
        {
            "grade": "Class 4",
            "subject": "English",
            "chapters": [
                {"name": "Reading", "topics": [
                    {"name": "Prose", "subtopics": ["Stories", "Essays", "Comprehension"]},
                    {"name": "Poetry", "subtopics": ["Poems", "Figures of speech"]}
                ]},
                {"name": "Grammar", "topics": [
                    {"name": "Tenses", "subtopics": ["Present tense", "Past tense", "Future tense"]},
                    {"name": "Sentence types", "subtopics": ["Declarative", "Interrogative", "Imperative", "Exclamatory"]},
                    {"name": "Conjunctions", "subtopics": ["And, But, Or, Because"]},
                    {"name": "Prepositions", "subtopics": ["Place prepositions", "Time prepositions"]},
                    {"name": "Adverbs", "subtopics": ["Adverbs of manner", "Adverbs of time"]}
                ]},
                {"name": "Writing", "topics": [
                    {"name": "Essay writing", "subtopics": ["Descriptive essays", "Narrative essays"]},
                    {"name": "Letter writing", "subtopics": ["Formal letters", "Informal letters"]},
                    {"name": "Story writing", "subtopics": ["Picture-based stories"]}
                ]},
                {"name": "Vocabulary", "topics": [
                    {"name": "Prefixes and Suffixes", "subtopics": ["Common prefixes", "Common suffixes"]},
                    {"name": "Idioms", "subtopics": ["Common idioms"]}
                ]}
            ]
        },
        {
            "grade": "Class 4",
            "subject": "EVS",
            "chapters": [
                {"name": "Our Body", "topics": [
                    {"name": "Digestive system", "subtopics": ["Organs involved", "Process of digestion"]},
                    {"name": "Respiratory system", "subtopics": ["Breathing", "Lungs"]}
                ]},
                {"name": "Food and Health", "topics": [
                    {"name": "Balanced diet", "subtopics": ["Nutrients", "Food pyramid"]},
                    {"name": "Hygiene", "subtopics": ["Personal hygiene", "Food hygiene"]}
                ]},
                {"name": "Natural Resources", "topics": [
                    {"name": "Soil", "subtopics": ["Types of soil", "Soil erosion"]},
                    {"name": "Rocks and minerals", "subtopics": ["Types of rocks", "Uses"]}
                ]},
                {"name": "Our Environment", "topics": [
                    {"name": "Ecosystems", "subtopics": ["Food chain", "Food web"]},
                    {"name": "Conservation", "subtopics": ["Save water", "Save trees"]}
                ]},
                {"name": "India", "topics": [
                    {"name": "States of India", "subtopics": ["Northern states", "Southern states"]},
                    {"name": "National symbols", "subtopics": ["Flag", "Emblem", "Anthem"]}
                ]}
            ]
        },
        # Class 5
        {
            "grade": "Class 5",
            "subject": "Maths",
            "chapters": [
                {"name": "Large Numbers", "topics": [
                    {"name": "Numbers up to 10 lakhs", "subtopics": ["Indian system", "International system"]},
                    {"name": "Roman numerals", "subtopics": ["Reading", "Writing"]}
                ]},
                {"name": "Operations", "topics": [
                    {"name": "Multiplication", "subtopics": ["3-digit by 2-digit", "Word problems"]},
                    {"name": "Division", "subtopics": ["4-digit by 2-digit", "Word problems"]},
                    {"name": "BODMAS", "subtopics": ["Order of operations"]}
                ]},
                {"name": "HCF and LCM", "topics": [
                    {"name": "HCF", "subtopics": ["Factor method", "Division method"]},
                    {"name": "LCM", "subtopics": ["Multiple method", "Division method"]}
                ]},
                {"name": "Fractions", "topics": [
                    {"name": "Operations", "subtopics": ["Addition", "Subtraction", "Multiplication"]},
                    {"name": "Word problems", "subtopics": ["Fraction problems"]}
                ]},
                {"name": "Decimals", "topics": [
                    {"name": "Operations", "subtopics": ["All four operations"]},
                    {"name": "Conversion", "subtopics": ["Fractions to decimals", "Decimals to fractions"]}
                ]},
                {"name": "Percentage", "topics": [
                    {"name": "Introduction", "subtopics": ["Meaning of percent", "Converting to fraction"]},
                    {"name": "Simple problems", "subtopics": ["Finding percentage"]}
                ]},
                {"name": "Geometry", "topics": [
                    {"name": "Angles", "subtopics": ["Measuring angles", "Types of angles"]},
                    {"name": "Triangles", "subtopics": ["Types of triangles", "Properties"]},
                    {"name": "Area", "subtopics": ["Triangle", "Parallelogram"]}
                ]},
                {"name": "Data Handling", "topics": [
                    {"name": "Average", "subtopics": ["Finding average"]},
                    {"name": "Graphs", "subtopics": ["Line graphs", "Pie charts basics"]}
                ]}
            ]
        },
        {
            "grade": "Class 5",
            "subject": "English",
            "chapters": [
                {"name": "Reading", "topics": [
                    {"name": "Comprehension", "subtopics": ["Unseen passages", "Inference questions"]},
                    {"name": "Literature", "subtopics": ["Stories", "Poems", "Drama"]}
                ]},
                {"name": "Grammar", "topics": [
                    {"name": "Tenses", "subtopics": ["Simple", "Continuous", "Perfect"]},
                    {"name": "Voice", "subtopics": ["Active voice", "Passive voice"]},
                    {"name": "Direct and Indirect speech", "subtopics": ["Reporting statements", "Reporting questions"]},
                    {"name": "Clauses", "subtopics": ["Main clause", "Subordinate clause"]},
                    {"name": "Punctuation", "subtopics": ["All punctuation marks"]}
                ]},
                {"name": "Writing", "topics": [
                    {"name": "Essays", "subtopics": ["Argumentative", "Descriptive", "Narrative"]},
                    {"name": "Letters", "subtopics": ["Formal", "Informal", "Application"]},
                    {"name": "Diary entry", "subtopics": ["Personal diary"]},
                    {"name": "Notice writing", "subtopics": ["School notices"]}
                ]},
                {"name": "Vocabulary", "topics": [
                    {"name": "Word formation", "subtopics": ["Prefixes", "Suffixes", "Compound words"]},
                    {"name": "Proverbs", "subtopics": ["Common proverbs and meanings"]}
                ]}
            ]
        },
        {
            "grade": "Class 5",
            "subject": "EVS",
            "chapters": [
                {"name": "Human Body", "topics": [
                    {"name": "Circulatory system", "subtopics": ["Heart", "Blood vessels", "Blood"]},
                    {"name": "Nervous system", "subtopics": ["Brain", "Nerves"]}
                ]},
                {"name": "Living World", "topics": [
                    {"name": "Adaptation", "subtopics": ["Desert animals", "Aquatic animals"]},
                    {"name": "Reproduction", "subtopics": ["Plants", "Animals basics"]}
                ]},
                {"name": "Matter", "topics": [
                    {"name": "States of matter", "subtopics": ["Solid", "Liquid", "Gas"]},
                    {"name": "Changes", "subtopics": ["Physical changes", "Chemical changes"]}
                ]},
                {"name": "Natural Disasters", "topics": [
                    {"name": "Types", "subtopics": ["Earthquake", "Flood", "Cyclone"]},
                    {"name": "Safety measures", "subtopics": ["Dos and Don'ts"]}
                ]},
                {"name": "Our Country", "topics": [
                    {"name": "Government", "subtopics": ["Democracy", "Constitution basics"]},
                    {"name": "History", "subtopics": ["Freedom struggle", "Important leaders"]}
                ]}
            ]
        },
        # Hindi - Class 1-5
        {
            "grade": "Class 1",
            "subject": "Hindi",
            "chapters": [
                {"name": "Varnamala", "topics": [
                    {"name": "Swar", "subtopics": ["अ से अः तक"]},
                    {"name": "Vyanjan", "subtopics": ["क से ज्ञ तक"]}
                ]},
                {"name": "Matras", "topics": [
                    {"name": "Aa ki matra", "subtopics": ["आ की मात्रा वाले शब्द"]},
                    {"name": "I ki matra", "subtopics": ["इ की मात्रा वाले शब्द"]}
                ]}
            ]
        },
        {
            "grade": "Class 2",
            "subject": "Hindi",
            "chapters": [
                {"name": "Matras", "topics": [
                    {"name": "All matras", "subtopics": ["ई, उ, ऊ, ए, ऐ, ओ, औ"]},
                    {"name": "Matra practice", "subtopics": ["शब्द बनाना", "वाक्य बनाना"]}
                ]},
                {"name": "Shabd Rachna", "topics": [
                    {"name": "Two letter words", "subtopics": ["दो अक्षर के शब्द"]},
                    {"name": "Three letter words", "subtopics": ["तीन अक्षर के शब्द"]}
                ]}
            ]
        },
        {
            "grade": "Class 3",
            "subject": "Hindi",
            "chapters": [
                {"name": "Vyakaran", "topics": [
                    {"name": "Sangya", "subtopics": ["व्यक्तिवाचक", "जातिवाचक", "भाववाचक"]},
                    {"name": "Sarvanam", "subtopics": ["पुरुषवाचक", "निश्चयवाचक"]},
                    {"name": "Visheshan", "subtopics": ["गुणवाचक", "संख्यावाचक"]}
                ]},
                {"name": "Lekhan", "topics": [
                    {"name": "Anuched Lekhan", "subtopics": ["छोटे अनुच्छेद"]},
                    {"name": "Patra Lekhan", "subtopics": ["अनौपचारिक पत्र"]}
                ]}
            ]
        },
        {
            "grade": "Class 4",
            "subject": "Hindi",
            "chapters": [
                {"name": "Vyakaran", "topics": [
                    {"name": "Kriya", "subtopics": ["सकर्मक", "अकर्मक"]},
                    {"name": "Kaal", "subtopics": ["वर्तमान", "भूत", "भविष्य"]},
                    {"name": "Vachan", "subtopics": ["एकवचन", "बहुवचन"]}
                ]},
                {"name": "Rachnatmak Lekhan", "topics": [
                    {"name": "Nibandh", "subtopics": ["वर्णनात्मक निबंध"]},
                    {"name": "Kahani Lekhan", "subtopics": ["चित्र देखकर कहानी"]}
                ]}
            ]
        },
        {
            "grade": "Class 5",
            "subject": "Hindi",
            "chapters": [
                {"name": "Vyakaran", "topics": [
                    {"name": "Samas", "subtopics": ["द्वंद्व", "तत्पुरुष", "कर्मधारय"]},
                    {"name": "Upsarg Pratyay", "subtopics": ["उपसर्ग", "प्रत्यय"]},
                    {"name": "Muhavare", "subtopics": ["मुहावरे और अर्थ"]}
                ]},
                {"name": "Rachnatmak Lekhan", "topics": [
                    {"name": "Anuched", "subtopics": ["विभिन्न विषयों पर"]},
                    {"name": "Patra Lekhan", "subtopics": ["औपचारिक पत्र"]},
                    {"name": "Samvad Lekhan", "subtopics": ["संवाद लेखन"]}
                ]}
            ]
        },
        # Science - Class 4-5 only
        {
            "grade": "Class 4",
            "subject": "Science",
            "chapters": [
                {"name": "Living Things", "topics": [
                    {"name": "Plants", "subtopics": ["Parts of plant", "Photosynthesis", "Types of plants"]},
                    {"name": "Animals", "subtopics": ["Classification", "Habitats", "Food habits"]}
                ]},
                {"name": "Human Body", "topics": [
                    {"name": "Digestive System", "subtopics": ["Organs", "Digestion process"]},
                    {"name": "Skeletal System", "subtopics": ["Bones", "Joints"]}
                ]},
                {"name": "Matter and Materials", "topics": [
                    {"name": "States of Matter", "subtopics": ["Solid", "Liquid", "Gas"]},
                    {"name": "Properties", "subtopics": ["Solubility", "Magnetism"]}
                ]},
                {"name": "Force and Motion", "topics": [
                    {"name": "Types of Force", "subtopics": ["Push", "Pull", "Friction"]},
                    {"name": "Simple Machines", "subtopics": ["Lever", "Pulley", "Wheel"]}
                ]}
            ]
        },
        {
            "grade": "Class 5",
            "subject": "Science",
            "chapters": [
                {"name": "Living Things", "topics": [
                    {"name": "Reproduction", "subtopics": ["Plants", "Animals"]},
                    {"name": "Adaptation", "subtopics": ["Desert", "Aquatic", "Polar"]}
                ]},
                {"name": "Human Body", "topics": [
                    {"name": "Circulatory System", "subtopics": ["Heart", "Blood", "Blood vessels"]},
                    {"name": "Respiratory System", "subtopics": ["Lungs", "Breathing"]},
                    {"name": "Nervous System", "subtopics": ["Brain", "Nerves", "Senses"]}
                ]},
                {"name": "Matter", "topics": [
                    {"name": "Physical Changes", "subtopics": ["Melting", "Freezing", "Evaporation"]},
                    {"name": "Chemical Changes", "subtopics": ["Burning", "Rusting", "Cooking"]}
                ]},
                {"name": "Energy", "topics": [
                    {"name": "Forms of Energy", "subtopics": ["Heat", "Light", "Sound"]},
                    {"name": "Sources", "subtopics": ["Renewable", "Non-renewable"]}
                ]},
                {"name": "Earth and Space", "topics": [
                    {"name": "Solar System", "subtopics": ["Sun", "Planets", "Moon"]},
                    {"name": "Earth", "subtopics": ["Rotation", "Revolution", "Seasons"]}
                ]}
            ]
        },
        # Computer - Class 1-5
        {
            "grade": "Class 1",
            "subject": "Computer",
            "chapters": [
                {"name": "Introduction to Computers", "topics": [
                    {"name": "What is a Computer", "subtopics": ["Uses of computer"]},
                    {"name": "Parts of Computer", "subtopics": ["Monitor", "Keyboard", "Mouse", "CPU"]}
                ]}
            ]
        },
        {
            "grade": "Class 2",
            "subject": "Computer",
            "chapters": [
                {"name": "Computer Basics", "topics": [
                    {"name": "Starting Computer", "subtopics": ["Switch on", "Switch off"]},
                    {"name": "Using Mouse", "subtopics": ["Click", "Double click", "Drag"]}
                ]},
                {"name": "Keyboard", "topics": [
                    {"name": "Typing", "subtopics": ["Alphabets", "Numbers"]},
                    {"name": "Special Keys", "subtopics": ["Enter", "Space", "Backspace"]}
                ]}
            ]
        },
        {
            "grade": "Class 3",
            "subject": "Computer",
            "chapters": [
                {"name": "MS Paint", "topics": [
                    {"name": "Drawing Tools", "subtopics": ["Pencil", "Brush", "Shapes"]},
                    {"name": "Colors", "subtopics": ["Fill color", "Color picker"]},
                    {"name": "Saving Work", "subtopics": ["Save", "Save As"]}
                ]},
                {"name": "Computer Care", "topics": [
                    {"name": "Do's and Don'ts", "subtopics": ["Handling", "Cleaning"]}
                ]}
            ]
        },
        {
            "grade": "Class 4",
            "subject": "Computer",
            "chapters": [
                {"name": "MS Word Basics", "topics": [
                    {"name": "Typing Documents", "subtopics": ["Creating new", "Opening files"]},
                    {"name": "Formatting", "subtopics": ["Font", "Size", "Color", "Bold", "Italic"]},
                    {"name": "Saving Documents", "subtopics": ["Save", "Print"]}
                ]},
                {"name": "Internet Basics", "topics": [
                    {"name": "What is Internet", "subtopics": ["Uses of internet"]},
                    {"name": "Web Browser", "subtopics": ["Opening browser", "Typing URL"]}
                ]}
            ]
        },
        {
            "grade": "Class 5",
            "subject": "Computer",
            "chapters": [
                {"name": "MS Word Advanced", "topics": [
                    {"name": "Tables", "subtopics": ["Insert table", "Add rows", "Add columns"]},
                    {"name": "Images", "subtopics": ["Insert picture", "Resize"]}
                ]},
                {"name": "MS PowerPoint", "topics": [
                    {"name": "Creating Slides", "subtopics": ["New slide", "Layouts"]},
                    {"name": "Adding Content", "subtopics": ["Text", "Images", "Shapes"]},
                    {"name": "Slideshow", "subtopics": ["Running presentation"]}
                ]},
                {"name": "Internet Safety", "topics": [
                    {"name": "Safe Browsing", "subtopics": ["Personal information", "Passwords"]},
                    {"name": "Cyber Safety", "subtopics": ["Online strangers", "Cyberbullying"]}
                ]}
            ]
        }
    ]

    try:
        # Create fresh client to ensure schema is up to date
        fresh_client = get_supabase()

        for syllabus in syllabus_data:
            # Upsert - insert or update if exists
            fresh_client.table("cbse_syllabus").upsert({
                "grade": syllabus["grade"],
                "subject": syllabus["subject"],
                "chapters": syllabus["chapters"]
            }, on_conflict="grade,subject").execute()

        return {"success": True, "message": f"Seeded {len(syllabus_data)} syllabus entries"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to seed syllabus: {str(e)}")
