import { useState, useEffect, useRef, useCallback } from 'react'

interface Props {
  onGetStarted: () => void
  onSignIn: () => void
}

/* ─── Topic data from CLAUDE.md ─── */
const MATHS_TOPICS: Record<string, string[]> = {
  'Class 1': [
    'Numbers 1-50', 'Numbers 51-100', 'Addition (up to 20)', 'Subtraction (within 20)',
    'Basic Shapes', 'Measurement', 'Time', 'Money',
  ],
  'Class 2': [
    'Numbers up to 1000', 'Addition', 'Subtraction', 'Multiplication', 'Division',
    'Shapes & Space', 'Measurement', 'Time', 'Money', 'Data Handling',
  ],
  'Class 3': [
    'Addition (carries)', 'Subtraction (borrowing)', 'Add & Subtract (3-digit)',
    'Multiplication (tables 2-10)', 'Division basics', 'Numbers up to 10000',
    'Fractions (halves, quarters)', 'Fractions', 'Time (clock, calendar)',
    'Money (bills & change)', 'Symmetry', 'Patterns & sequences',
  ],
  'Class 4': [
    'Large numbers (1,00,000)', 'Addition & Subtraction (5-digit)',
    'Multiplication (3-digit)', 'Division (long division)', 'Fractions (equivalent)',
    'Decimals (tenths)', 'Geometry (angles)', 'Perimeter & Area',
    'Time (24-hour clock)', 'Money (profit/loss)',
  ],
  'Class 5': [
    'Numbers up to 10 lakh', 'Factors & Multiples', 'HCF & LCM',
    'Fractions (add & subtract)', 'Decimals (all operations)', 'Percentage',
    'Area & Volume', 'Geometry (circles)', 'Data handling (pie charts)',
    'Speed, Distance & Time',
  ],
}

const ENGLISH_TOPICS: Record<string, string[]> = {
  'Class 1': [
    'Alphabet', 'Phonics', 'Family Vocabulary', 'Animals & Food',
    'Greetings', 'Seasons', 'Simple Sentences',
  ],
  'Class 2': ['Nouns', 'Verbs', 'Pronouns', 'Sentences', 'Rhyming Words', 'Punctuation'],
  'Class 3': [
    'Nouns', 'Verbs', 'Adjectives', 'Pronouns', 'Tenses',
    'Punctuation', 'Vocabulary', 'Reading Comprehension',
  ],
  'Class 4': [
    'Tenses', 'Sentence Types', 'Conjunctions', 'Prepositions',
    'Adverbs', 'Prefixes & Suffixes', 'Vocabulary', 'Reading Comprehension',
  ],
  'Class 5': [
    'Active & Passive Voice', 'Direct & Indirect Speech', 'Complex Sentences',
    'Summary Writing', 'Comprehension', 'Synonyms & Antonyms',
    'Formal Letter Writing', 'Creative Writing', 'Clauses',
  ],
}

const SCIENCE_TOPICS: Record<string, string[]> = {
  'Class 1 (EVS)': ['My Family', 'My Body', 'Plants Around Us', 'Animals Around Us', 'Food We Eat', 'Seasons & Weather'],
  'Class 2 (EVS)': ['Plants', 'Animals & Habitats', 'Food & Nutrition', 'Water', 'Shelter', 'Our Senses'],
  'Class 3': ['Plants', 'Animals', 'Food & Nutrition', 'Shelter', 'Water', 'Air', 'Our Body'],
  'Class 4': ['Living Things', 'Human Body', 'States of Matter', 'Force & Motion', 'Simple Machines', 'Photosynthesis', 'Animal Adaptation'],
  'Class 5': ['Circulatory System', 'Respiratory & Nervous System', 'Reproduction', 'Physical & Chemical Changes', 'Forms of Energy', 'Solar System & Earth', 'Ecosystem & Food Chains'],
}

const COMPUTER_TOPICS: Record<string, string[]> = {
  'Class 1': ['Parts of Computer', 'Mouse & Keyboard'],
  'Class 2': ['Desktop & Icons', 'Basic Typing', 'Special Keys'],
  'Class 3': ['MS Paint', 'Keyboard Shortcuts', 'Files & Folders'],
  'Class 4': ['MS Word', 'Scratch', 'Internet Safety'],
  'Class 5': ['Scratch Programming', 'Internet Basics', 'MS PowerPoint', 'Digital Citizenship'],
}

const GK_TOPICS: Record<string, string[]> = {
  'Class 3': ['Famous Landmarks', 'National Symbols', 'Solar System Basics', 'Current Awareness'],
  'Class 4': ['Continents & Oceans', 'Famous Scientists', 'Festivals of India', 'Sports & Games'],
  'Class 5': ['Indian Constitution', 'World Heritage Sites', 'Space Missions', 'Environmental Awareness'],
}

const MORAL_TOPICS: Record<string, string[]> = {
  'Class 1': ['Sharing', 'Honesty'],
  'Class 2': ['Kindness', 'Respecting Elders'],
  'Class 3': ['Teamwork', 'Empathy', 'Environmental Care'],
  'Class 4': ['Leadership'],
  'Class 5': ['Global Citizenship', 'Digital Ethics'],
}

const HEALTH_TOPICS: Record<string, string[]> = {
  'Class 1': ['Personal Hygiene', 'Good Posture', 'Physical Activities'],
  'Class 2': ['Healthy Eating', 'Outdoor Play', 'Stretching'],
  'Class 3': ['Balanced Diet', 'Team Sports', 'Safety at Play'],
  'Class 4': ['First Aid', 'Yoga', 'Sleep Hygiene'],
  'Class 5': ['Fitness & Stamina', 'Nutrition Labels', 'Mental Health'],
}

/* ─── Gold Class feature steps ─── */
const GOLD_STEPS = [
  {
    num: '01',
    icon: '\u2B50\u2B50\u2B50',
    title: 'Tiered Difficulty',
    desc: 'Foundation \u2192 Application \u2192 Stretch on every single sheet. Every child can start with confidence, and every child is challenged to think deeper. Star badges show the tier visually.',
    example: '\u2B50 Foundation: Q1. 347 + 256 = ___\n\u2B50\u2B50 Application: Q5. Priya earned \u20B9478 at the mela\u2026\n\u2B50\u2B50\u2B50 Stretch: Q9. Find the error in this calculation\u2026',
  },
  {
    num: '02',
    icon: '\uD83C\uDFAF',
    title: 'Mastery-Personalised',
    desc: 'Tracks your child\'s mastery level \u2014 learning \u2192 improving \u2192 mastered. The next worksheet automatically adjusts: more practice on weak spots, harder questions where they\'re strong.',
    example: 'Child mastered basic addition \u2192 next sheet boosts Thinking questions and reduces Recognition. Struggling with carries \u2192 extra carry-focused practice injected.',
  },
  {
    num: '03',
    icon: '\uD83D\uDCA1',
    title: 'Hints on Stretch',
    desc: 'Thinking and error detection questions include a collapsible hint \u2014 a metacognitive nudge, not the answer. Teaches strategy, not shortcuts.',
    example: '\uD83D\uDCA1 Hint: "Think about what happens when the ones column adds up to more than 9. Where does the extra go?"',
  },
  {
    num: '04',
    icon: '\uD83D\uDCCA',
    title: 'Parent Insight',
    desc: 'After grading, you get actionable guidance: what your child may be confusing, what to practise next, and a mastery progress bar with streak tracking.',
    example: '"Your child may be confusing tens and ones when carrying. Next: try the Place Value worksheet. Mastery: Improving (streak: 3 \u2713)"',
  },
  {
    num: '05',
    icon: '\uD83D\uDCCB',
    title: 'Learning Objective',
    desc: 'Every worksheet states its goal clearly so parents and teachers know exactly what skill is being practised \u2014 not just "Class 3 Maths".',
    example: '\u2713 Add 3-digit numbers where carrying is needed\n\u2713 Spot common addition mistakes and fix them\n\u2713 Solve real-life addition word problems',
  },
  {
    num: '06',
    icon: '\uD83D\uDDA8\uFE0F',
    title: 'Premium PDF',
    desc: 'Name \u00B7 Date \u00B7 Score fields. Tier section headers. Answer key toggle. Looks like a Pearson workbook, prints beautifully on A4. No branding clutter.',
    example: 'Professional layout with Foundation / Application / Stretch sections, ruled answer lines, and a clean toggle for showing or hiding the answer key.',
  },
]

/* ─── Comparison table data ─── */
const COMPARISON_ROWS = [
  {
    feature: 'Skill consistency',
    free: 'Random question types. No guaranteed mix of recall, application, and reasoning.',
    pc: 'Every sheet has 5 cognitive slots: Recognition, Application, Representation, Error Detection, Thinking.',
  },
  {
    feature: 'Curriculum alignment',
    free: 'Loosely tagged to chapters. Questions often off-syllabus or wrong grade level.',
    pc: 'Every topic mapped to NCERT. 66 topic profiles with per-grade constraints.',
  },
  {
    feature: 'Difficulty tiering',
    free: 'All questions at one difficulty. Struggling kids give up at Q1.',
    pc: 'Foundation \u2192 Application \u2192 Stretch on every sheet. Star badges show the tier.',
  },
  {
    feature: 'Mastery personalisation',
    free: 'Same worksheet for every child, regardless of what they know.',
    pc: 'Tracks mastery level per skill. Next worksheet adapts automatically.',
  },
  {
    feature: 'Indian context problems',
    free: '"Ram has 5 apples" \u2014 generic, repeated, culturally flat.',
    pc: 'Auto-rickshaw fares, Diwali diyas, mela shopping, cricket overs \u2014 320+ Indian contexts.',
  },
  {
    feature: 'Hints on hard questions',
    free: 'No hints. Child is stuck. Parent guesses. Frustration.',
    pc: 'Collapsible hint on every Stretch question \u2014 a nudge, not the answer.',
  },
  {
    feature: 'Parent insight after grading',
    free: 'Worksheet ends. No feedback. No next step.',
    pc: '"Watch for carry errors. Next: Place Value worksheet." Mastery bar + streak.',
  },
  {
    feature: 'Print quality',
    free: 'Web-page printout with ads, headers, broken formatting.',
    pc: 'Premium A4 PDF. Name/Date/Score fields. Tier headers. Answer key toggle.',
  },
]

/* ─── Scroll-reveal component ─── */
function RevealSection({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const node = ref.current
    if (!node) return
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) setVisible(true) },
      { threshold: 0.12 }
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  return (
    <div ref={ref} className={`transition-all duration-700 ease-out ${visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-6'} ${className}`}>
      {children}
    </div>
  )
}

/* ─── Reusable UI atoms ─── */
function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-xs font-medium tracking-[0.2em] uppercase text-slate-400 mb-4">
      {children}
    </p>
  )
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="font-['Playfair_Display',Georgia,serif] text-3xl sm:text-4xl md:text-[2.75rem] font-semibold leading-[1.15] tracking-tight text-slate-900 mb-4">
      {children}
    </h2>
  )
}

/* ─── Main landing page ─── */
export default function Landing({ onGetStarted, onSignIn }: Props) {
  const [scrolled, setScrolled] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [activeSubject, setActiveSubject] = useState<'Maths' | 'English' | 'Science' | 'Computer' | 'GK' | 'Moral Science' | 'Health'>('Maths')
  const [activeStep, setActiveStep] = useState(0)

  // Sticky nav scroll detection
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const scrollTo = useCallback((id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
    setMobileMenuOpen(false)
  }, [])

  const navLinks = [
    { label: 'How It Works', id: 'how-it-works' },
    { label: 'Subjects', id: 'subjects' },
    { label: 'Why Us', id: 'why-us' },
    { label: 'Pricing', id: 'pricing' },
  ]

  const subjectData = activeSubject === 'Maths' ? MATHS_TOPICS
    : activeSubject === 'English' ? ENGLISH_TOPICS
    : activeSubject === 'Computer' ? COMPUTER_TOPICS
    : activeSubject === 'GK' ? GK_TOPICS
    : activeSubject === 'Moral Science' ? MORAL_TOPICS
    : activeSubject === 'Health' ? HEALTH_TOPICS
    : SCIENCE_TOPICS

  return (
    <div className="min-h-screen bg-white text-slate-900">
      {/* ───────── 1. STICKY NAV ───────── */}
      <nav className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        scrolled
          ? 'bg-white/95 backdrop-blur-md border-b border-slate-100 shadow-sm'
          : 'bg-transparent'
      }`}>
        <div className="max-w-6xl mx-auto px-5 h-16 flex items-center justify-between">
          {/* Logo */}
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-lg bg-indigo-600 flex items-center justify-center">
              <span className="font-['Playfair_Display',Georgia,serif] text-white font-bold text-lg leading-none">P</span>
            </div>
            <span className="font-['Playfair_Display',Georgia,serif] text-xl font-semibold tracking-tight">
              <span className="text-slate-900">Practice</span><span className="text-indigo-600">Craft</span>
            </span>
          </div>

          {/* Desktop nav links */}
          <div className="hidden md:flex items-center gap-8">
            {navLinks.map((l) => (
              <button key={l.id} onClick={() => scrollTo(l.id)} className="text-sm text-slate-500 hover:text-slate-900 transition-colors bg-transparent border-none cursor-pointer">
                {l.label}
              </button>
            ))}
          </div>

          {/* Right CTA */}
          <div className="hidden md:flex items-center gap-4">
            <button onClick={onSignIn} className="text-sm text-slate-600 hover:text-slate-900 bg-transparent border-none cursor-pointer">
              Log in
            </button>
            <button
              onClick={onGetStarted}
              className="px-5 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 transition-colors"
            >
              Try Free
            </button>
          </div>

          {/* Mobile hamburger */}
          <button
            className="md:hidden p-2 text-slate-600 bg-transparent border-none cursor-pointer"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            aria-label="Toggle menu"
          >
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              {mobileMenuOpen
                ? <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                : <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />}
            </svg>
          </button>
        </div>

        {/* Mobile menu */}
        {mobileMenuOpen && (
          <div className="md:hidden bg-white border-b border-slate-100 px-5 pb-4">
            {navLinks.map((l) => (
              <button key={l.id} onClick={() => scrollTo(l.id)} className="block w-full text-left py-2.5 text-sm text-slate-600 hover:text-slate-900 bg-transparent border-none cursor-pointer">
                {l.label}
              </button>
            ))}
            <div className="flex gap-3 pt-3 border-t border-slate-100 mt-2">
              <button onClick={onSignIn} className="flex-1 py-2.5 text-sm text-slate-600 border border-slate-200 rounded-lg bg-transparent cursor-pointer">
                Log in
              </button>
              <button onClick={onGetStarted} className="flex-1 py-2.5 text-sm text-white bg-indigo-600 rounded-lg border-none cursor-pointer font-medium">
                Try Free
              </button>
            </div>
          </div>
        )}
      </nav>

      {/* ───────── 2. HERO ───────── */}
      <section className="pt-28 sm:pt-36 pb-16 sm:pb-24 px-5">
        <div className="max-w-6xl mx-auto">
          <div className="max-w-3xl mx-auto text-center">
            <p className="text-xs font-medium tracking-[0.2em] uppercase text-slate-400 mb-6">
              CBSE Classes 2 &middot; 3 &middot; 4 &nbsp;&middot;&nbsp; Maths &middot; English &middot; Science
            </p>

            <h1 className="font-['Playfair_Display',Georgia,serif] text-[2.75rem] sm:text-6xl md:text-7xl font-semibold leading-[1.08] tracking-tight text-slate-900 mb-6">
              Worksheets that{' '}
              <span className="relative inline-block">
                <span className="relative z-10">know your child.</span>
                <span className="absolute bottom-1 sm:bottom-2 left-0 right-0 h-3 sm:h-4 bg-amber-300/40 -z-0 rounded-sm animate-[underline-grow_1s_ease-out_0.5s_forwards] origin-left scale-x-0" />
              </span>
            </h1>

            <p className="text-lg sm:text-xl text-slate-500 leading-relaxed max-w-2xl mx-auto mb-10">
              Not random. Not generic. Gold Class CBSE practice sheets personalised
              to your child's mastery level &mdash; concept by concept, skill by skill.
            </p>

            <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-14">
              <button
                onClick={onGetStarted}
                className="w-full sm:w-auto px-8 py-3.5 bg-indigo-600 text-white text-base font-semibold rounded-xl hover:bg-indigo-700 transition-colors shadow-lg shadow-indigo-600/20 border-none cursor-pointer"
              >
                Start Free &mdash; No card needed
              </button>
              <button
                onClick={() => scrollTo('how-it-works')}
                className="w-full sm:w-auto px-8 py-3.5 bg-transparent text-slate-600 text-base font-medium rounded-xl border border-slate-200 hover:border-slate-300 hover:bg-slate-50 transition-colors cursor-pointer"
              >
                See how it works &darr;
              </button>
            </div>
          </div>

          {/* Floating worksheet preview */}
          <div className="max-w-md mx-auto">
            <div className="bg-white rounded-2xl border border-slate-100 shadow-[0_4px_24px_rgba(0,0,0,0.08)] p-6 animate-[float_6s_ease-in-out_infinite]">
              <div className="flex items-center gap-2 mb-4">
                <span className="text-base">{'\uD83D\uDCCB'}</span>
                <div>
                  <p className="text-xs font-medium tracking-wide uppercase text-slate-400">Today's Goal</p>
                  <p className="text-sm font-semibold text-slate-800">Addition with Carrying &middot; Class 3</p>
                </div>
              </div>
              <div className="space-y-3">
                <div className="p-3 bg-slate-50 rounded-lg">
                  <p className="text-[11px] font-bold text-amber-600 mb-1">{'\u2B50'} Foundation</p>
                  <p className="text-sm text-slate-700">Q1. &nbsp;347 + 256 = ___</p>
                </div>
                <div className="p-3 bg-slate-50 rounded-lg">
                  <p className="text-[11px] font-bold text-amber-600 mb-1">{'\u2B50\u2B50'} Application</p>
                  <p className="text-sm text-slate-700">Q5. &nbsp;Priya had {'\u20B9'}478. She earned {'\u20B9'}256 more at the mela&hellip;</p>
                </div>
                <div className="p-3 bg-slate-50 rounded-lg">
                  <p className="text-[11px] font-bold text-amber-600 mb-1">{'\u2B50\u2B50\u2B50'} Stretch</p>
                  <p className="text-sm text-slate-700">Q9. &nbsp;[Error Detection]</p>
                  <button className="mt-1.5 text-xs text-indigo-500 font-medium flex items-center gap-1 bg-transparent border-none cursor-pointer p-0">
                    {'\uD83D\uDCA1'} Hint {'\u25B8'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ───────── 3. SOCIAL PROOF BAR ───────── */}
      <section className="py-8 bg-slate-50 border-y border-slate-100">
        <div className="max-w-4xl mx-auto px-5 text-center">
          <p className="text-sm text-slate-400 mb-3">Trusted by parents and teachers across India</p>
          <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-sm font-semibold text-slate-600">
            <span>66 Topics</span>
            <span className="text-slate-300">&middot;</span>
            <span>4 Subjects</span>
            <span className="text-slate-300">&middot;</span>
            <span>3 Grade Levels</span>
            <span className="text-slate-300">&middot;</span>
            <span>26/26 Tests Passing</span>
          </div>
        </div>
      </section>

      {/* ───────── 4. THE PROBLEM ───────── */}
      <section id="why-us" className="py-20 sm:py-28 px-5">
        <div className="max-w-6xl mx-auto">
          <RevealSection className="text-center mb-14">
            <Eyebrow>The Problem</Eyebrow>
            <SectionHeading>Every free worksheet tool has the same flaw.</SectionHeading>
          </RevealSection>

          <div className="grid md:grid-cols-3 gap-6">
            {[
              {
                title: 'Same sheet for every child',
                desc: 'A child who has mastered addition gets the same worksheet as one just starting. No personalisation, no adaptation.',
              },
              {
                title: 'All questions at one difficulty',
                desc: 'Struggling children hit Q1 and give up. Advanced children finish in 5 minutes and learn nothing new.',
              },
              {
                title: 'No guidance after it\'s done',
                desc: 'Parents don\'t know if their child did well, what they got wrong, or what to practise next.',
              },
            ].map((card, i) => (
              <RevealSection key={i}>
                <div className="bg-white rounded-2xl border border-slate-100 shadow-[0_2px_8px_rgba(0,0,0,0.06)] p-6 h-full border-l-4 border-l-red-400">
                  <h3 className="text-lg font-semibold text-slate-900 mb-2">{card.title}</h3>
                  <p className="text-sm text-slate-500 leading-relaxed">{card.desc}</p>
                </div>
              </RevealSection>
            ))}
          </div>
        </div>
      </section>

      {/* ───────── 5. GOLD CLASS FEATURES (dot-grid bg) ───────── */}
      <section id="how-it-works" className="py-20 sm:py-28 px-5 relative overflow-hidden">
        {/* Academic dot grid */}
        <div className="absolute inset-0" style={{
          backgroundColor: '#fafafa',
          backgroundImage: 'radial-gradient(circle, #d1d5db 1px, transparent 1px)',
          backgroundSize: '24px 24px',
        }} />
        <div className="absolute inset-0 bg-gradient-to-b from-white via-white/90 to-white" />

        <div className="relative max-w-6xl mx-auto">
          <RevealSection className="text-center mb-14">
            <Eyebrow>Gold Class</Eyebrow>
            <SectionHeading>The only CBSE worksheet that adapts to your child.</SectionHeading>
            <p className="text-slate-500 text-lg">Six deliberate dimensions. Zero randomness.</p>
          </RevealSection>

          {/* Tab navigation */}
          <div className="flex flex-wrap justify-center gap-2 mb-10">
            {GOLD_STEPS.map((step, i) => (
              <button
                key={i}
                onClick={() => setActiveStep(i)}
                className={`px-4 py-2 text-sm font-medium rounded-lg border transition-all cursor-pointer ${
                  activeStep === i
                    ? 'bg-indigo-600 text-white border-indigo-600 shadow-md shadow-indigo-600/20'
                    : 'bg-white text-slate-500 border-slate-200 hover:border-slate-300 hover:text-slate-700'
                }`}
              >
                <span className="hidden sm:inline">{step.num} </span>{step.title}
              </button>
            ))}
          </div>

          {/* Active step content */}
          <div className="max-w-3xl mx-auto">
            <div className="bg-white rounded-2xl border border-slate-100 shadow-[0_4px_24px_rgba(0,0,0,0.08)] p-8 sm:p-10 transition-all duration-500">
              <p className="text-4xl mb-4">{GOLD_STEPS[activeStep].icon}</p>
              <p className="text-xs font-bold tracking-[0.2em] uppercase text-amber-500 mb-2">
                {GOLD_STEPS[activeStep].num}
              </p>
              <h3 className="font-['Playfair_Display',Georgia,serif] text-2xl sm:text-3xl font-semibold text-slate-900 mb-4">
                {GOLD_STEPS[activeStep].title}
              </h3>
              <p className="text-slate-500 leading-relaxed mb-6">{GOLD_STEPS[activeStep].desc}</p>
              <div className="bg-slate-50 rounded-xl p-5 border border-slate-100">
                <p className="text-xs font-bold tracking-wide uppercase text-slate-400 mb-2">Example</p>
                <p className="text-sm text-slate-600 whitespace-pre-line leading-relaxed">{GOLD_STEPS[activeStep].example}</p>
              </div>
            </div>
          </div>

          {/* Dot indicators */}
          <div className="flex justify-center gap-2 mt-8">
            {GOLD_STEPS.map((_, i) => (
              <button
                key={i}
                onClick={() => setActiveStep(i)}
                className={`w-2 h-2 rounded-full transition-all border-none cursor-pointer ${
                  activeStep === i ? 'bg-indigo-600 w-6' : 'bg-slate-300'
                }`}
                aria-label={`Step ${i + 1}`}
              />
            ))}
          </div>
        </div>
      </section>

      {/* ───────── 6. SUBJECTS SECTION ───────── */}
      <section id="subjects" className="py-20 sm:py-28 px-5">
        <div className="max-w-6xl mx-auto">
          <RevealSection className="text-center mb-14">
            <Eyebrow>Built on NCERT</Eyebrow>
            <SectionHeading>Covers what your child actually studies.</SectionHeading>
          </RevealSection>

          {/* Subject toggles */}
          <div className="flex justify-center gap-3 mb-10">
            {(['Maths', 'English', 'Science', 'Computer', 'GK', 'Moral Science', 'Health'] as const).map((subj) => (
              <button
                key={subj}
                onClick={() => setActiveSubject(subj)}
                className={`px-6 py-2.5 text-sm font-semibold rounded-lg border transition-all cursor-pointer ${
                  activeSubject === subj
                    ? 'bg-indigo-600 text-white border-indigo-600'
                    : 'bg-white text-slate-500 border-slate-200 hover:border-slate-300'
                }`}
              >
                {subj}
              </button>
            ))}
          </div>

          {/* Topic pills */}
          <div className="max-w-4xl mx-auto transition-opacity duration-300">
            {Object.entries(subjectData).map(([grade, topics]) => (
              <div key={grade} className="mb-8">
                <p className="text-sm font-semibold text-slate-400 uppercase tracking-wide mb-3">{grade}</p>
                <div className="flex flex-wrap gap-2">
                  {topics.map((t) => (
                    <span key={t} className="px-3.5 py-1.5 bg-slate-100 text-slate-700 text-sm rounded-full">
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ───────── 7. COMPARISON TABLE (dot-grid bg) ───────── */}
      <section className="py-20 sm:py-28 px-5 relative overflow-hidden">
        <div className="absolute inset-0" style={{
          backgroundColor: '#fafafa',
          backgroundImage: 'radial-gradient(circle, #d1d5db 1px, transparent 1px)',
          backgroundSize: '24px 24px',
        }} />
        <div className="absolute inset-0 bg-gradient-to-b from-white via-white/90 to-white" />

        <div className="relative max-w-5xl mx-auto">
          <RevealSection className="text-center mb-14">
            <Eyebrow>The Difference</Eyebrow>
            <SectionHeading>Why not just use a free tool?</SectionHeading>
          </RevealSection>

          <RevealSection>
            <div className="bg-white rounded-2xl border border-slate-100 shadow-[0_2px_8px_rgba(0,0,0,0.06)] overflow-hidden">
              {/* Table header */}
              <div className="grid grid-cols-[1fr_1fr_1fr] text-sm font-semibold border-b border-slate-100">
                <div className="p-4 text-slate-400">Feature</div>
                <div className="p-4 text-slate-400 border-l border-slate-100">Free Tools</div>
                <div className="p-4 bg-indigo-50 text-indigo-700 border-l border-slate-100">PracticeCraft</div>
              </div>
              {/* Rows */}
              {COMPARISON_ROWS.map((row, i) => (
                <div key={i} className={`grid grid-cols-[1fr_1fr_1fr] text-sm ${i < COMPARISON_ROWS.length - 1 ? 'border-b border-slate-50' : ''}`}>
                  <div className="p-4 font-medium text-slate-700">{row.feature}</div>
                  <div className="p-4 text-red-400 border-l border-slate-100 leading-relaxed">{row.free}</div>
                  <div className="p-4 text-indigo-700 font-medium border-l border-slate-100 bg-indigo-50/30 leading-relaxed">{row.pc}</div>
                </div>
              ))}
            </div>
          </RevealSection>

          {/* Mobile-friendly stacked view */}
          <div className="md:hidden mt-6">
            <p className="text-xs text-slate-400 text-center">Scroll horizontally to compare &rarr;</p>
          </div>
        </div>
      </section>

      {/* ───────── 8. FOR PARENTS / FOR TEACHERS ───────── */}
      <section className="py-20 sm:py-28 px-5">
        <div className="max-w-6xl mx-auto grid md:grid-cols-2 gap-8">
          <RevealSection>
            <div className="bg-white rounded-2xl border border-slate-100 shadow-[0_2px_8px_rgba(0,0,0,0.06)] p-8 h-full">
              <p className="text-3xl mb-4">{'\uD83D\uDC68\u200D\uD83D\uDC69\u200D\uD83D\uDC67'}</p>
              <h3 className="font-['Playfair_Display',Georgia,serif] text-2xl font-semibold text-slate-900 mb-5">For Parents</h3>
              <ul className="space-y-3 text-sm text-slate-600 leading-relaxed">
                <li className="flex gap-3"><span className="text-indigo-500 font-bold mt-0.5">{'\u2713'}</span>Generate a worksheet in 30 seconds &mdash; pick grade, topic, go</li>
                <li className="flex gap-3"><span className="text-indigo-500 font-bold mt-0.5">{'\u2713'}</span>Every sheet adapts to your child's mastery level automatically</li>
                <li className="flex gap-3"><span className="text-indigo-500 font-bold mt-0.5">{'\u2713'}</span>Clear learning objectives so you know what's being practised</li>
                <li className="flex gap-3"><span className="text-indigo-500 font-bold mt-0.5">{'\u2713'}</span>Parent insight after grading: what to watch for and what to try next</li>
                <li className="flex gap-3"><span className="text-indigo-500 font-bold mt-0.5">{'\u2713'}</span>Share worksheets via WhatsApp with one tap</li>
              </ul>
            </div>
          </RevealSection>

          <RevealSection>
            <div className="bg-white rounded-2xl border border-slate-100 shadow-[0_2px_8px_rgba(0,0,0,0.06)] p-8 h-full">
              <p className="text-3xl mb-4">{'\uD83C\uDFEB'}</p>
              <h3 className="font-['Playfair_Display',Georgia,serif] text-2xl font-semibold text-slate-900 mb-5">For Teachers</h3>
              <ul className="space-y-3 text-sm text-slate-600 leading-relaxed">
                <li className="flex gap-3"><span className="text-indigo-500 font-bold mt-0.5">{'\u2713'}</span>Bulk generation &mdash; create 5 topic worksheets for a class in one click</li>
                <li className="flex gap-3"><span className="text-indigo-500 font-bold mt-0.5">{'\u2713'}</span>CBSE-aligned to NCERT &mdash; use as homework, classwork, or revision</li>
                <li className="flex gap-3"><span className="text-indigo-500 font-bold mt-0.5">{'\u2713'}</span>Premium PDF with Name/Date/Score &mdash; print and distribute directly</li>
                <li className="flex gap-3"><span className="text-indigo-500 font-bold mt-0.5">{'\u2713'}</span>Track class-level mastery across topics over time</li>
                <li className="flex gap-3"><span className="text-indigo-500 font-bold mt-0.5">{'\u2713'}</span>Separate class profiles with dedicated worksheet history</li>
              </ul>
            </div>
          </RevealSection>
        </div>
      </section>

      {/* ───────── 9. PRICING ───────── */}
      <section id="pricing" className="py-20 sm:py-28 px-5 bg-slate-50">
        <div className="max-w-6xl mx-auto">
          <RevealSection className="text-center mb-14">
            <Eyebrow>Simple Pricing</Eyebrow>
            <SectionHeading>Start free. Upgrade when ready.</SectionHeading>
          </RevealSection>

          <div className="grid md:grid-cols-2 gap-8 max-w-3xl mx-auto">
            {/* Free tier */}
            <RevealSection>
              <div className="bg-white rounded-2xl border border-slate-100 shadow-[0_2px_8px_rgba(0,0,0,0.06)] p-8 h-full flex flex-col">
                <h3 className="font-['Playfair_Display',Georgia,serif] text-3xl font-semibold text-slate-900 mb-1">Free</h3>
                <p className="text-sm text-slate-400 mb-6">10 worksheets / month</p>
                <ul className="space-y-3 text-sm text-slate-600 mb-8 flex-1">
                  <li className="flex gap-2.5"><span className="text-slate-400">{'\u2713'}</span>All 4 subjects &mdash; Maths, English, Science, Hindi</li>
                  <li className="flex gap-2.5"><span className="text-slate-400">{'\u2713'}</span>All grades (Class 2, 3, 4)</li>
                  <li className="flex gap-2.5"><span className="text-slate-400">{'\u2713'}</span>Basic PDF with answer key</li>
                  <li className="flex gap-2.5"><span className="text-slate-400">{'\u2713'}</span>Generate in 30 seconds</li>
                </ul>
                <button
                  onClick={onGetStarted}
                  className="w-full py-3 text-sm font-semibold text-indigo-600 border-2 border-indigo-600 rounded-xl hover:bg-indigo-50 transition-colors bg-transparent cursor-pointer"
                >
                  Get Started Free
                </button>
              </div>
            </RevealSection>

            {/* Paid tier */}
            <RevealSection>
              <div className="bg-white rounded-2xl border-2 border-indigo-600 shadow-[0_4px_24px_rgba(79,70,229,0.15)] p-8 h-full flex flex-col relative">
                <span className="absolute -top-3 left-6 px-3 py-1 bg-amber-400 text-amber-900 text-xs font-bold uppercase tracking-wider rounded-full">
                  Most Popular
                </span>
                <h3 className="font-['Playfair_Display',Georgia,serif] text-3xl font-semibold text-slate-900 mb-1">
                  {'\u20B9'}299<span className="text-lg font-normal text-slate-400"> / month</span>
                </h3>
                <p className="text-sm text-slate-400 mb-6">Unlimited worksheets</p>
                <ul className="space-y-3 text-sm text-slate-600 mb-8 flex-1">
                  <li className="flex gap-2.5"><span className="text-indigo-500 font-bold">{'\u2713'}</span>Everything in Free, plus:</li>
                  <li className="flex gap-2.5"><span className="text-indigo-500 font-bold">{'\u2713'}</span>Mastery tracking per child</li>
                  <li className="flex gap-2.5"><span className="text-indigo-500 font-bold">{'\u2713'}</span>Parent insights after grading</li>
                  <li className="flex gap-2.5"><span className="text-indigo-500 font-bold">{'\u2713'}</span>Bulk generation (5 topics at once)</li>
                  <li className="flex gap-2.5"><span className="text-indigo-500 font-bold">{'\u2713'}</span>School branding on PDF</li>
                  <li className="flex gap-2.5"><span className="text-indigo-500 font-bold">{'\u2713'}</span>Priority support</li>
                </ul>
                <button
                  onClick={onGetStarted}
                  className="w-full py-3 text-sm font-semibold text-white bg-indigo-600 rounded-xl hover:bg-indigo-700 transition-colors border-none cursor-pointer shadow-lg shadow-indigo-600/20"
                >
                  Start Free Trial
                </button>
              </div>
            </RevealSection>
          </div>
        </div>
      </section>

      {/* ───────── 10. PHILOSOPHY (dot-grid bg) ───────── */}
      <section className="py-20 sm:py-28 px-5 relative overflow-hidden">
        <div className="absolute inset-0" style={{
          backgroundColor: '#fafafa',
          backgroundImage: 'radial-gradient(circle, #d1d5db 1px, transparent 1px)',
          backgroundSize: '24px 24px',
        }} />
        <div className="absolute inset-0 bg-gradient-to-b from-white via-white/90 to-white" />

        <div className="relative max-w-6xl mx-auto">
          <RevealSection className="text-center mb-14">
            <Eyebrow>Our Philosophy</Eyebrow>
            <SectionHeading>Built for long-term mastery.</SectionHeading>
            <p className="text-slate-500 text-lg max-w-2xl mx-auto">
              PracticeCraft doesn't generate worksheets &mdash; it engineers learning paths.
            </p>
          </RevealSection>

          <div className="grid md:grid-cols-3 gap-6">
            {[
              {
                num: '01',
                title: 'Depth-First Curriculum',
                desc: 'Each skill is practised until foundational strength is established. No jumping between topics until the building blocks are solid.',
              },
              {
                num: '02',
                title: 'Structured Progression',
                desc: 'Foundation \u2192 Application \u2192 Stretch mirrors how effective classrooms build reasoning. Every worksheet follows this arc.',
              },
              {
                num: '03',
                title: 'Educational Integrity',
                desc: 'No AI hallucinations. Every question is pedagogically validated and deterministically sound. 66 topic profiles, each hand-crafted.',
              },
            ].map((card, i) => (
              <RevealSection key={i}>
                <div className="bg-white rounded-2xl border border-slate-100 shadow-[0_2px_8px_rgba(0,0,0,0.06)] p-7">
                  <p className="text-xs font-bold tracking-[0.2em] uppercase text-amber-500 mb-3">{card.num}</p>
                  <h3 className="font-['Playfair_Display',Georgia,serif] text-xl font-semibold text-slate-900 mb-3">{card.title}</h3>
                  <p className="text-sm text-slate-500 leading-relaxed">{card.desc}</p>
                </div>
              </RevealSection>
            ))}
          </div>
        </div>
      </section>

      {/* ───────── 11. FINAL CTA ───────── */}
      <section className="py-20 sm:py-28 px-5">
        <RevealSection className="text-center max-w-2xl mx-auto">
          <SectionHeading>Ready to build real mastery?</SectionHeading>
          <p className="text-lg text-slate-500 mb-10">
            Your child's first personalised worksheet is free.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <button
              onClick={onGetStarted}
              className="w-full sm:w-auto px-8 py-3.5 bg-indigo-600 text-white text-base font-semibold rounded-xl hover:bg-indigo-700 transition-colors shadow-lg shadow-indigo-600/20 border-none cursor-pointer"
            >
              Start Generating Worksheets
            </button>
            <button
              onClick={() => window.open('mailto:hello@practicecraft.in', '_blank')}
              className="w-full sm:w-auto px-8 py-3.5 bg-transparent text-slate-600 text-base font-medium rounded-xl border border-slate-200 hover:border-slate-300 hover:bg-slate-50 transition-colors cursor-pointer"
            >
              Talk to Our Team
            </button>
          </div>
        </RevealSection>
      </section>

      {/* ───────── 12. FOOTER ───────── */}
      <footer className="py-10 px-5 border-t border-slate-100">
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-md bg-indigo-600 flex items-center justify-center">
              <span className="font-['Playfair_Display',Georgia,serif] text-white font-bold text-sm leading-none">P</span>
            </div>
            <span className="font-['Playfair_Display',Georgia,serif] text-base font-semibold">
              Practice<span className="text-indigo-600">Craft</span>
            </span>
          </div>
          <div className="flex flex-wrap items-center justify-center gap-6 text-sm text-slate-400">
            {navLinks.map((l) => (
              <button key={l.id} onClick={() => scrollTo(l.id)} className="hover:text-slate-600 transition-colors bg-transparent border-none cursor-pointer text-sm text-slate-400">
                {l.label}
              </button>
            ))}
          </div>
          <p className="text-xs text-slate-400 text-center sm:text-right">
            &copy; 2026 PracticeCraft &middot; Built for Indian families, aligned to CBSE/NCERT
          </p>
        </div>
      </footer>

      {/* ───────── CSS keyframes ───────── */}
      <style>{`
        @keyframes float {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-10px); }
        }
        @keyframes underline-grow {
          from { transform: scaleX(0); }
          to { transform: scaleX(1); }
        }
      `}</style>
    </div>
  )
}
