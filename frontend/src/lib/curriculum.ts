import { api } from './api'

// ─── Topic display names ─────────────────────────────────────────────────────
// Maps canonical TOPIC_PROFILES keys (slot_engine.py) → short display names.
// getTopicName() falls back gracefully for unknown slugs.

export const TOPIC_NAMES: Record<string, string> = {
  // ── Class 1 Maths
  'Numbers 1 to 50 (Class 1)': 'Numbers 1 to 50',
  'Numbers 51 to 100 (Class 1)': 'Numbers 51 to 100',
  'Addition up to 20 (Class 1)': 'Addition up to 20',
  'Subtraction within 20 (Class 1)': 'Subtraction within 20',
  'Basic Shapes (Class 1)': 'Basic Shapes',
  'Measurement (Class 1)': 'Measurement',
  'Time (Class 1)': 'Time',
  'Money (Class 1)': 'Money',
  // ── Class 2 Maths
  'Numbers up to 1000 (Class 2)': 'Numbers up to 1000',
  'Addition (2-digit with carry)': 'Addition with Carry',
  'Subtraction (2-digit with borrow)': 'Subtraction with Borrow',
  'Multiplication (tables 2-5)': 'Multiplication (Tables 2–5)',
  'Division (sharing equally)': 'Division – Sharing Equally',
  'Shapes and space (2D)': 'Shapes and Space',
  'Measurement (length, weight)': 'Measurement (Length & Weight)',
  'Time (hour, half-hour)': 'Time (Hour & Half-Hour)',
  'Money (coins and notes)': 'Money (Coins & Notes)',
  'Data handling (pictographs)': 'Data Handling – Pictographs',
  // ── Class 3 Maths
  'Addition (carries)': 'Addition with Carry',
  'Subtraction (borrowing)': 'Subtraction with Borrow',
  'Addition and subtraction (3-digit)': 'Addition & Subtraction',
  'Multiplication (tables 2-10)': 'Multiplication (Tables 2–10)',
  'Division basics': 'Division Basics',
  'Numbers up to 10000': 'Numbers up to 10,000',
  'Fractions (halves, quarters)': 'Fractions (Halves & Quarters)',
  'Fractions': 'Fractions',
  'Time (reading clock, calendar)': 'Time – Clock & Calendar',
  'Money (bills and change)': 'Money (Bills & Change)',
  'Symmetry': 'Symmetry',
  'Patterns and sequences': 'Patterns & Sequences',
  // ── Class 4 Maths
  'Large numbers (up to 1,00,000)': 'Large Numbers (up to 1 Lakh)',
  'Addition and subtraction (5-digit)': 'Addition & Subtraction (5-digit)',
  'Multiplication (3-digit × 2-digit)': 'Multiplication',
  'Division (long division)': 'Division (Long Division)',
  'Fractions (equivalent, comparison)': 'Fractions – Equivalent & Compare',
  'Decimals (tenths, hundredths)': 'Decimals',
  'Geometry (angles, lines)': 'Geometry – Angles & Lines',
  'Perimeter and area': 'Perimeter & Area',
  'Time (minutes, 24-hour clock)': 'Time – Minutes & 24-hour',
  'Money (bills, profit/loss)': 'Money – Profit & Loss',
  // ── Class 5 Maths
  'Numbers up to 10 lakh (Class 5)': 'Numbers up to 10 Lakh',
  'Factors and multiples (Class 5)': 'Factors & Multiples',
  'HCF and LCM (Class 5)': 'HCF and LCM',
  'Fractions (add and subtract) (Class 5)': 'Fractions – Add & Subtract',
  'Decimals (all operations) (Class 5)': 'Decimals (All Operations)',
  'Percentage (Class 5)': 'Percentage',
  'Area and volume (Class 5)': 'Area & Volume',
  'Geometry (circles, symmetry) (Class 5)': 'Geometry – Circles & Symmetry',
  'Data handling (pie charts) (Class 5)': 'Data Handling – Pie Charts',
  'Speed distance time (Class 5)': 'Speed, Distance & Time',
  // ── Class 1 English
  'Alphabet (Class 1)': 'Alphabet',
  'Phonics (Class 1)': 'Phonics',
  'Self and Family Vocabulary (Class 1)': 'Self & Family Vocabulary',
  'Animals and Food Vocabulary (Class 1)': 'Animals & Food Vocabulary',
  'Greetings and Polite Words (Class 1)': 'Greetings & Polite Words',
  'Seasons (Class 1)': 'Seasons',
  'Simple Sentences (Class 1)': 'Simple Sentences',
  // ── Class 2 English
  'Nouns (Class 2)': 'Nouns',
  'Verbs (Class 2)': 'Verbs',
  'Pronouns (Class 2)': 'Pronouns',
  'Sentences (Class 2)': 'Sentences',
  'Rhyming Words (Class 2)': 'Rhyming Words',
  'Punctuation (Class 2)': 'Punctuation',
  // ── Class 3 English
  'Nouns (Class 3)': 'Nouns',
  'Verbs (Class 3)': 'Verbs',
  'Adjectives (Class 3)': 'Adjectives',
  'Pronouns (Class 3)': 'Pronouns',
  'Tenses (Class 3)': 'Tenses',
  'Punctuation (Class 3)': 'Punctuation',
  'Vocabulary (Class 3)': 'Vocabulary',
  'Reading Comprehension (Class 3)': 'Reading Comprehension',
  // ── Class 4 English
  'Tenses (Class 4)': 'Tenses',
  'Sentence Types (Class 4)': 'Sentence Types',
  'Conjunctions (Class 4)': 'Conjunctions',
  'Prepositions (Class 4)': 'Prepositions',
  'Adverbs (Class 4)': 'Adverbs',
  'Prefixes and Suffixes (Class 4)': 'Prefixes & Suffixes',
  'Vocabulary (Class 4)': 'Vocabulary',
  'Reading Comprehension (Class 4)': 'Reading Comprehension',
  // ── Class 5 English
  'Active and Passive Voice (Class 5)': 'Active & Passive Voice',
  'Direct and Indirect Speech (Class 5)': 'Direct & Indirect Speech',
  'Complex Sentences (Class 5)': 'Complex Sentences',
  'Summary Writing (Class 5)': 'Summary Writing',
  'Comprehension (Class 5)': 'Comprehension',
  'Synonyms and Antonyms (Class 5)': 'Synonyms & Antonyms',
  'Formal Letter Writing (Class 5)': 'Formal Letter Writing',
  'Creative Writing (Class 5)': 'Creative Writing',
  'Clauses (Class 5)': 'Clauses',
  // ── Class 1 EVS
  'My Family (Class 1)': 'My Family',
  'My Body (Class 1)': 'My Body',
  'Plants Around Us (Class 1)': 'Plants Around Us',
  'Animals Around Us (Class 1)': 'Animals Around Us',
  'Food We Eat (Class 1)': 'Food We Eat',
  'Seasons and Weather (Class 1)': 'Seasons & Weather',
  // ── Class 2 EVS
  'Plants (Class 2-EVS)': 'Plants',
  'Animals and Habitats (Class 2)': 'Animals & Habitats',
  'Food and Nutrition (Class 2)': 'Food & Nutrition',
  'Water (Class 2)': 'Water',
  'Shelter (Class 2)': 'Shelter',
  'Our Senses (Class 2)': 'Our Senses',
  // ── Class 3 Science
  'Plants (Class 3)': 'Plants',
  'Animals (Class 3)': 'Animals',
  'Food and Nutrition (Class 3)': 'Food & Nutrition',
  'Shelter (Class 3)': 'Shelter',
  'Water (Class 3)': 'Water',
  'Air (Class 3)': 'Air',
  'Our Body (Class 3)': 'Our Body',
  // ── Class 4 Science
  'Living Things (Class 4)': 'Living Things',
  'Human Body (Class 4)': 'Human Body',
  'States of Matter (Class 4)': 'States of Matter',
  'Force and Motion (Class 4)': 'Force & Motion',
  'Simple Machines (Class 4)': 'Simple Machines',
  'Photosynthesis (Class 4)': 'Photosynthesis',
  'Animal Adaptation (Class 4)': 'Animal Adaptation',
  // ── Class 5 Science
  'Circulatory System (Class 5)': 'Circulatory System',
  'Respiratory and Nervous System (Class 5)': 'Respiratory & Nervous System',
  'Reproduction in Plants and Animals (Class 5)': 'Reproduction',
  'Physical and Chemical Changes (Class 5)': 'Physical & Chemical Changes',
  'Forms of Energy (Class 5)': 'Forms of Energy',
  'Solar System and Earth (Class 5)': 'Solar System & Earth',
  'Ecosystem and Food Chains (Class 5)': 'Ecosystem & Food Chains',
  // ── Computer Class 1
  'Parts of Computer (Class 1)': 'Parts of a Computer',
  'Using Mouse and Keyboard (Class 1)': 'Mouse & Keyboard',
  // ── Computer Class 2
  'Desktop and Icons (Class 2)': 'Desktop & Icons',
  'Basic Typing (Class 2)': 'Basic Typing',
  'Special Keys (Class 2)': 'Special Keys',
  // ── Computer Class 3
  'MS Paint Basics (Class 3)': 'MS Paint Basics',
  'Keyboard Shortcuts (Class 3)': 'Keyboard Shortcuts',
  'Files and Folders (Class 3)': 'Files & Folders',
  // ── Computer Class 4
  'MS Word Basics (Class 4)': 'MS Word Basics',
  'Introduction to Scratch (Class 4)': 'Intro to Scratch',
  'Internet Safety (Class 4)': 'Internet Safety',
  // ── Computer Class 5
  'Scratch Programming (Class 5)': 'Scratch Programming',
  'Internet Basics (Class 5)': 'Internet Basics',
  'MS PowerPoint Basics (Class 5)': 'MS PowerPoint Basics',
  'Digital Citizenship (Class 5)': 'Digital Citizenship',
  // ── Hindi Class 1
  'Varnamala Swar (Class 1)': 'Varnamala – Swar',
  'Varnamala Vyanjan (Class 1)': 'Varnamala – Vyanjan',
  'Family Words (Class 1)': 'Family Words',
  // ── Hindi Class 2
  'Matras Introduction (Class 2)': 'Matras – Introduction',
  'Two Letter Words (Class 2)': 'Two-Letter Words',
  'Three Letter Words (Class 2)': 'Three-Letter Words',
  'Rhymes and Poems (Class 2)': 'Rhymes & Poems',
  'Nature Vocabulary (Class 2)': 'Nature Vocabulary',
  // ── Hindi Class 3
  'Varnamala (Class 3)': 'Varnamala',
  'Matras (Class 3)': 'Matras',
  'Shabd Rachna (Class 3)': 'Shabd Rachna',
  'Vakya Rachna (Class 3)': 'Vakya Rachna',
  'Kahani Lekhan (Class 3)': 'Kahani Lekhan',
  // ── Hindi Class 4
  'Anusvaar and Visarg (Class 4)': 'Anusvaar & Visarg',
  'Vachan and Ling (Class 4)': 'Vachan & Ling',
  'Kaal (Class 4)': 'Kaal',
  'Patra Lekhan (Class 4)': 'Patra Lekhan',
  'Comprehension Hindi (Class 4)': 'Comprehension',
  // ── Hindi Class 5
  'Muhavare (Class 5)': 'Muhavare',
  'Paryayvachi Shabd (Class 5)': 'Paryayvachi Shabd',
  'Vilom Shabd (Class 5)': 'Vilom Shabd',
  'Samas (Class 5)': 'Samas',
  'Samvad Lekhan (Class 5)': 'Samvad Lekhan',
  // ── GK
  'Famous Landmarks (Class 3)': 'Famous Landmarks',
  'National Symbols (Class 3)': 'National Symbols',
  'Solar System Basics (Class 3)': 'Solar System Basics',
  'Current Awareness (Class 3)': 'Current Awareness',
  'Continents and Oceans (Class 4)': 'Continents & Oceans',
  'Famous Scientists (Class 4)': 'Famous Scientists',
  'Festivals of India (Class 4)': 'Festivals of India',
  'Sports and Games (Class 4)': 'Sports & Games',
  'Indian Constitution (Class 5)': 'Indian Constitution',
  'World Heritage Sites (Class 5)': 'World Heritage Sites',
  'Space Missions (Class 5)': 'Space Missions',
  'Environmental Awareness (Class 5)': 'Environmental Awareness',
  // ── Moral Science
  'Sharing (Class 1)': 'Sharing',
  'Honesty (Class 1)': 'Honesty',
  'Kindness (Class 2)': 'Kindness',
  'Respecting Elders (Class 2)': 'Respecting Elders',
  'Teamwork (Class 3)': 'Teamwork',
  'Empathy (Class 3)': 'Empathy',
  'Environmental Care (Class 3)': 'Environmental Care',
  'Leadership (Class 4)': 'Leadership',
  'Global Citizenship (Class 5)': 'Global Citizenship',
  'Digital Ethics (Class 5)': 'Digital Ethics',
  // ── Health & PE
  'Personal Hygiene (Class 1)': 'Personal Hygiene',
  'Good Posture (Class 1)': 'Good Posture',
  'Basic Physical Activities (Class 1)': 'Basic Physical Activities',
  'Healthy Eating Habits (Class 2)': 'Healthy Eating Habits',
  'Outdoor Play (Class 2)': 'Outdoor Play',
  'Basic Stretching (Class 2)': 'Basic Stretching',
  'Balanced Diet (Class 3)': 'Balanced Diet',
  'Team Sports Rules (Class 3)': 'Team Sports Rules',
  'Safety at Play (Class 3)': 'Safety at Play',
  'First Aid Basics (Class 4)': 'First Aid Basics',
  'Yoga Introduction (Class 4)': 'Yoga Introduction',
  'Importance of Sleep (Class 4)': 'Importance of Sleep',
  'Fitness and Stamina (Class 5)': 'Fitness & Stamina',
  'Nutrition Labels Reading (Class 5)': 'Reading Nutrition Labels',
  'Mental Health Awareness (Class 5)': 'Mental Health Awareness',
}

/** Return a short display name for a topic slug. Falls back to slug with underscores replaced. */
export function getTopicName(slug: string): string {
  return TOPIC_NAMES[slug] ?? slug.replace(/_/g, ' ')
}
// ─────────────────────────────────────────────────────────────────────────────

export interface CurriculumSubject {
  name: string
  region: string
  source?: string
  skills: string[]
  logic_tags: string[]
  depth: 'core' | 'reinforcement'
}

interface SubjectsResponse {
  grade: number
  region: string
  subjects: CurriculumSubject[]
}

interface SubjectDetailResponse {
  grade: number
  subject: string
  region: string
  source?: string
  skills: string[]
  logic_tags: string[]
  depth: string
  stage: string
}

export async function fetchSubjects(
  grade: number,
  region: string,
  includeReinforcement = false
): Promise<CurriculumSubject[]> {
  const params = new URLSearchParams({
    region,
    include_reinforcement: String(includeReinforcement),
  })
  const response = await api.get<SubjectsResponse>(
    `/api/curriculum/subjects/${grade}?${params}`
  )
  return response.data.subjects
}

export async function fetchSkills(
  grade: number,
  subject: string,
  region: string
): Promise<SubjectDetailResponse> {
  const encodedSubject = encodeURIComponent(subject)
  const response = await api.get<SubjectDetailResponse>(
    `/api/curriculum/${grade}/${encodedSubject}?region=${region}`
  )
  return response.data
}
