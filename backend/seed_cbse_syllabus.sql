-- CBSE Syllabus Seed Data
-- Run this in Supabase SQL Editor after running supabase_schema.sql

-- First refresh the PostgREST schema cache
NOTIFY pgrst, 'reload schema';

-- Clear existing data (optional)
DELETE FROM cbse_syllabus;

-- Class 1 - Maths
INSERT INTO cbse_syllabus (grade, subject, chapters) VALUES
('Class 1', 'Maths', '[
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
]'::jsonb);

-- Class 1 - English
INSERT INTO cbse_syllabus (grade, subject, chapters) VALUES
('Class 1', 'English', '[
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
]'::jsonb);

-- Class 1 - EVS
INSERT INTO cbse_syllabus (grade, subject, chapters) VALUES
('Class 1', 'EVS', '[
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
]'::jsonb);

-- Class 1 - Hindi
INSERT INTO cbse_syllabus (grade, subject, chapters) VALUES
('Class 1', 'Hindi', '[
  {"name": "Varnamala", "topics": [
    {"name": "Swar", "subtopics": ["अ से अः तक"]},
    {"name": "Vyanjan", "subtopics": ["क से ज्ञ तक"]}
  ]},
  {"name": "Matras", "topics": [
    {"name": "Aa ki matra", "subtopics": ["आ की मात्रा वाले शब्द"]},
    {"name": "I ki matra", "subtopics": ["इ की मात्रा वाले शब्द"]}
  ]}
]'::jsonb);

-- Class 1 - Computer
INSERT INTO cbse_syllabus (grade, subject, chapters) VALUES
('Class 1', 'Computer', '[
  {"name": "Introduction to Computers", "topics": [
    {"name": "What is a Computer", "subtopics": ["Uses of computer"]},
    {"name": "Parts of Computer", "subtopics": ["Monitor", "Keyboard", "Mouse", "CPU"]}
  ]}
]'::jsonb);

-- Class 2 - Maths
INSERT INTO cbse_syllabus (grade, subject, chapters) VALUES
('Class 2', 'Maths', '[
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
]'::jsonb);

-- Class 2 - English
INSERT INTO cbse_syllabus (grade, subject, chapters) VALUES
('Class 2', 'English', '[
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
]'::jsonb);

-- Class 2 - EVS
INSERT INTO cbse_syllabus (grade, subject, chapters) VALUES
('Class 2', 'EVS', '[
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
]'::jsonb);

-- Class 2 - Hindi
INSERT INTO cbse_syllabus (grade, subject, chapters) VALUES
('Class 2', 'Hindi', '[
  {"name": "Matras", "topics": [
    {"name": "All matras", "subtopics": ["ई, उ, ऊ, ए, ऐ, ओ, औ"]},
    {"name": "Matra practice", "subtopics": ["शब्द बनाना", "वाक्य बनाना"]}
  ]},
  {"name": "Shabd Rachna", "topics": [
    {"name": "Two letter words", "subtopics": ["दो अक्षर के शब्द"]},
    {"name": "Three letter words", "subtopics": ["तीन अक्षर के शब्द"]}
  ]}
]'::jsonb);

-- Class 2 - Computer
INSERT INTO cbse_syllabus (grade, subject, chapters) VALUES
('Class 2', 'Computer', '[
  {"name": "Computer Basics", "topics": [
    {"name": "Starting Computer", "subtopics": ["Switch on", "Switch off"]},
    {"name": "Using Mouse", "subtopics": ["Click", "Double click", "Drag"]}
  ]},
  {"name": "Keyboard", "topics": [
    {"name": "Typing", "subtopics": ["Alphabets", "Numbers"]},
    {"name": "Special Keys", "subtopics": ["Enter", "Space", "Backspace"]}
  ]}
]'::jsonb);

-- Class 3 - Maths
INSERT INTO cbse_syllabus (grade, subject, chapters) VALUES
('Class 3', 'Maths', '[
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
]'::jsonb);

-- Class 3 - English
INSERT INTO cbse_syllabus (grade, subject, chapters) VALUES
('Class 3', 'English', '[
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
]'::jsonb);

-- Class 3 - EVS
INSERT INTO cbse_syllabus (grade, subject, chapters) VALUES
('Class 3', 'EVS', '[
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
]'::jsonb);

-- Class 3 - Hindi
INSERT INTO cbse_syllabus (grade, subject, chapters) VALUES
('Class 3', 'Hindi', '[
  {"name": "Vyakaran", "topics": [
    {"name": "Sangya", "subtopics": ["व्यक्तिवाचक", "जातिवाचक", "भाववाचक"]},
    {"name": "Sarvanam", "subtopics": ["पुरुषवाचक", "निश्चयवाचक"]},
    {"name": "Visheshan", "subtopics": ["गुणवाचक", "संख्यावाचक"]}
  ]},
  {"name": "Lekhan", "topics": [
    {"name": "Anuched Lekhan", "subtopics": ["छोटे अनुच्छेद"]},
    {"name": "Patra Lekhan", "subtopics": ["अनौपचारिक पत्र"]}
  ]}
]'::jsonb);

-- Class 3 - Computer
INSERT INTO cbse_syllabus (grade, subject, chapters) VALUES
('Class 3', 'Computer', '[
  {"name": "MS Paint", "topics": [
    {"name": "Drawing Tools", "subtopics": ["Pencil", "Brush", "Shapes"]},
    {"name": "Colors", "subtopics": ["Fill color", "Color picker"]},
    {"name": "Saving Work", "subtopics": ["Save", "Save As"]}
  ]},
  {"name": "Computer Care", "topics": [
    {"name": "Dos and Donts", "subtopics": ["Handling", "Cleaning"]}
  ]}
]'::jsonb);

-- Class 4 - Maths
INSERT INTO cbse_syllabus (grade, subject, chapters) VALUES
('Class 4', 'Maths', '[
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
]'::jsonb);

-- Class 4 - English
INSERT INTO cbse_syllabus (grade, subject, chapters) VALUES
('Class 4', 'English', '[
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
]'::jsonb);

-- Class 4 - EVS
INSERT INTO cbse_syllabus (grade, subject, chapters) VALUES
('Class 4', 'EVS', '[
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
]'::jsonb);

-- Class 4 - Hindi
INSERT INTO cbse_syllabus (grade, subject, chapters) VALUES
('Class 4', 'Hindi', '[
  {"name": "Vyakaran", "topics": [
    {"name": "Kriya", "subtopics": ["सकर्मक", "अकर्मक"]},
    {"name": "Kaal", "subtopics": ["वर्तमान", "भूत", "भविष्य"]},
    {"name": "Vachan", "subtopics": ["एकवचन", "बहुवचन"]}
  ]},
  {"name": "Rachnatmak Lekhan", "topics": [
    {"name": "Nibandh", "subtopics": ["वर्णनात्मक निबंध"]},
    {"name": "Kahani Lekhan", "subtopics": ["चित्र देखकर कहानी"]}
  ]}
]'::jsonb);

-- Class 4 - Science
INSERT INTO cbse_syllabus (grade, subject, chapters) VALUES
('Class 4', 'Science', '[
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
]'::jsonb);

-- Class 4 - Computer
INSERT INTO cbse_syllabus (grade, subject, chapters) VALUES
('Class 4', 'Computer', '[
  {"name": "MS Word Basics", "topics": [
    {"name": "Typing Documents", "subtopics": ["Creating new", "Opening files"]},
    {"name": "Formatting", "subtopics": ["Font", "Size", "Color", "Bold", "Italic"]},
    {"name": "Saving Documents", "subtopics": ["Save", "Print"]}
  ]},
  {"name": "Internet Basics", "topics": [
    {"name": "What is Internet", "subtopics": ["Uses of internet"]},
    {"name": "Web Browser", "subtopics": ["Opening browser", "Typing URL"]}
  ]}
]'::jsonb);

-- Class 5 - Maths
INSERT INTO cbse_syllabus (grade, subject, chapters) VALUES
('Class 5', 'Maths', '[
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
]'::jsonb);

-- Class 5 - English
INSERT INTO cbse_syllabus (grade, subject, chapters) VALUES
('Class 5', 'English', '[
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
]'::jsonb);

-- Class 5 - EVS
INSERT INTO cbse_syllabus (grade, subject, chapters) VALUES
('Class 5', 'EVS', '[
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
    {"name": "Safety measures", "subtopics": ["Dos and Donts"]}
  ]},
  {"name": "Our Country", "topics": [
    {"name": "Government", "subtopics": ["Democracy", "Constitution basics"]},
    {"name": "History", "subtopics": ["Freedom struggle", "Important leaders"]}
  ]}
]'::jsonb);

-- Class 5 - Hindi
INSERT INTO cbse_syllabus (grade, subject, chapters) VALUES
('Class 5', 'Hindi', '[
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
]'::jsonb);

-- Class 5 - Science
INSERT INTO cbse_syllabus (grade, subject, chapters) VALUES
('Class 5', 'Science', '[
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
]'::jsonb);

-- Class 5 - Computer
INSERT INTO cbse_syllabus (grade, subject, chapters) VALUES
('Class 5', 'Computer', '[
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
]'::jsonb);

-- Refresh schema cache again after inserts
NOTIFY pgrst, 'reload schema';

-- Verify the data was inserted
SELECT grade, subject, jsonb_array_length(chapters) as chapter_count FROM cbse_syllabus ORDER BY grade, subject;
