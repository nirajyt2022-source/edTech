import { useState, useEffect, useRef } from 'react'

// ── SVG Icons (no external dependency) ───────────────────────────────────────
const IcShuffle = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="16 3 21 3 21 8"/><line x1="4" y1="20" x2="21" y2="3"/>
    <polyline points="21 16 21 21 16 21"/><line x1="15" y1="15" x2="21" y2="21"/>
  </svg>
)
const IcChart = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/>
    <line x1="6" y1="20" x2="6" y2="14"/><line x1="2" y1="20" x2="22" y2="20"/>
  </svg>
)
const IcPrinter = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="6 9 6 2 18 2 18 9"/>
    <path d="M6 18H4a2 2 0 01-2-2v-5a2 2 0 012-2h16a2 2 0 012 2v5a2 2 0 01-2 2h-2"/>
    <rect x="6" y="14" width="12" height="8"/>
  </svg>
)
const IcTarget = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>
  </svg>
)
const IcLightbulb = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M9 21h6M12 3a6 6 0 016 6c0 2-.9 3.8-2.3 5L15 16H9l-.7-2C6.9 12.8 6 11 6 9a6 6 0 016-6z"/>
  </svg>
)
const IcGradCap = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 10v6M2 10l10-5 10 5-10 5z"/>
    <path d="M6 12v5c3 3 9 3 12 0v-5"/>
  </svg>
)
const IcBook = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/>
  </svg>
)
const IcFlag = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/>
    <line x1="4" y1="22" x2="4" y2="15"/>
  </svg>
)

interface Props {
  onGetStarted: () => void
  onSignIn: () => void
}

// ── Subject / Topic Data ──────────────────────────────────────────────────────
const SUBJECTS = [
  {
    key: 'maths', label: 'Mathematics', symbol: '∑',
    description: 'Number sense to speed-distance-time across all five classes.',
    classes: {
      'Class 1': ['Numbers 1–50', 'Numbers 51–100', 'Addition ≤20', 'Subtraction ≤20', 'Basic Shapes', 'Measurement', 'Time', 'Money'],
      'Class 2': ['Numbers ≤1000', 'Addition (carry)', 'Subtraction (borrow)', 'Multiplication ×2–5', 'Division', 'Shapes & Space', 'Measurement', 'Time', 'Money', 'Data Handling'],
      'Class 3': ['Addition (carries)', 'Subtraction (borrow)', 'Add & Subtract (3-digit)', 'Multiplication ×2–10', 'Division', 'Numbers ≤10,000', 'Fractions', 'Time', 'Money', 'Symmetry', 'Patterns & Sequences'],
      'Class 4': ['Large Numbers ≤1,00,000', 'Add & Subtract (5-digit)', 'Multiplication 3d×2d', 'Long Division', 'Equivalent Fractions', 'Decimals', 'Angles & Lines', 'Perimeter & Area', 'Time (24-hr)', 'Money & Profit'],
      'Class 5': ['Numbers ≤10 lakh', 'Factors & Multiples', 'HCF & LCM', 'Fractions (add/sub)', 'Decimals (all ops)', 'Percentage', 'Area & Volume', 'Geometry', 'Data Handling (pie charts)', 'Speed Distance Time'],
    },
  },
  {
    key: 'english', label: 'English', symbol: 'A',
    description: 'Grammar, writing, comprehension — from phonics to clauses.',
    classes: {
      'Class 1': ['Alphabet', 'Phonics', 'Family Vocabulary', 'Animals & Food', 'Greetings', 'Seasons', 'Simple Sentences'],
      'Class 2': ['Nouns', 'Verbs', 'Pronouns', 'Sentences', 'Rhyming Words', 'Punctuation'],
      'Class 3': ['Nouns', 'Verbs', 'Adjectives', 'Pronouns', 'Tenses', 'Punctuation', 'Vocabulary', 'Comprehension'],
      'Class 4': ['Tenses', 'Sentence Types', 'Conjunctions', 'Prepositions', 'Adverbs', 'Prefixes & Suffixes', 'Vocabulary', 'Comprehension'],
      'Class 5': ['Active & Passive Voice', 'Direct & Indirect Speech', 'Complex Sentences', 'Summary Writing', 'Comprehension', 'Synonyms & Antonyms', 'Letter Writing', 'Creative Writing', 'Clauses'],
    },
  },
  {
    key: 'science', label: 'Science', symbol: 'Sc',
    description: 'EVS in Classes 1–2, structured Science from Class 3 onwards.',
    classes: {
      'Class 1 (EVS)': ['My Family', 'My Body', 'Plants Around Us', 'Animals Around Us', 'Food We Eat', 'Seasons & Weather'],
      'Class 2 (EVS)': ['Plants', 'Animals & Habitats', 'Food & Nutrition', 'Water', 'Shelter', 'Our Senses'],
      'Class 3': ['Plants', 'Animals', 'Food & Nutrition', 'Shelter', 'Water', 'Air', 'Our Body'],
      'Class 4': ['Living Things', 'Human Body', 'States of Matter', 'Force & Motion', 'Simple Machines', 'Photosynthesis', 'Animal Adaptation'],
      'Class 5': ['Circulatory System', 'Respiratory & Nervous System', 'Reproduction', 'Physical & Chemical Changes', 'Forms of Energy', 'Solar System', 'Ecosystem & Food Chains'],
    },
  },
  {
    key: 'hindi', label: 'Hindi', symbol: 'अ',
    description: 'Varnamala to creative writing in Devanagari script.',
    classes: {
      'Class 1': ['Varnamala Swar', 'Varnamala Vyanjan', 'Family Words', 'Simple Sentences'],
      'Class 2': ['Matras Introduction', 'Two Letter Words', 'Three Letter Words', 'Rhymes & Poems', 'Nature Vocabulary'],
      'Class 3': ['Varnamala', 'Matras', 'Shabd Rachna', 'Vakya Rachna', 'Kahani Lekhan'],
      'Class 4': ['Anusvaar & Visarg', 'Vachan & Ling', 'Kaal', 'Patra Lekhan', 'Comprehension Hindi'],
      'Class 5': ['Muhavare', 'Paryayvachi Shabd', 'Vilom Shabd', 'Samas', 'Samvad Lekhan'],
    },
  },
  {
    key: 'computer', label: 'Computer', symbol: '</>',
    description: 'Digital literacy from mouse clicks to Scratch programming.',
    classes: {
      'Class 1': ['Parts of Computer', 'Mouse & Keyboard'],
      'Class 2': ['Desktop & Icons', 'Basic Typing', 'Special Keys'],
      'Class 3': ['MS Paint Basics', 'Keyboard Shortcuts', 'Files & Folders'],
      'Class 4': ['MS Word Basics', 'Introduction to Scratch', 'Internet Safety'],
      'Class 5': ['Scratch Programming', 'Internet Basics', 'MS PowerPoint', 'Digital Citizenship'],
    },
  },
  {
    key: 'gk', label: 'GK', symbol: '★',
    description: 'World knowledge, India, science, and current awareness.',
    classes: {
      'Class 3': ['Famous Landmarks', 'National Symbols', 'Solar System Basics', 'Current Awareness'],
      'Class 4': ['Continents & Oceans', 'Famous Scientists', 'Festivals of India', 'Sports & Games'],
      'Class 5': ['Indian Constitution', 'World Heritage Sites', 'Space Missions', 'Environmental Awareness'],
    },
  },
  {
    key: 'moral', label: 'Moral Science', symbol: '♡',
    description: 'Values, empathy, leadership and character building.',
    classes: {
      'Class 1': ['Sharing', 'Honesty'],
      'Class 2': ['Kindness', 'Respecting Elders'],
      'Class 3': ['Teamwork', 'Empathy', 'Environmental Care'],
      'Class 4': ['Leadership'],
      'Class 5': ['Global Citizenship', 'Digital Ethics'],
    },
  },
  {
    key: 'health', label: 'Health & PE', symbol: '◎',
    description: 'Wellness, fitness, nutrition and healthy habits.',
    classes: {
      'Class 1': ['Personal Hygiene', 'Good Posture', 'Basic Physical Activities'],
      'Class 2': ['Healthy Eating Habits', 'Outdoor Play', 'Basic Stretching'],
      'Class 3': ['Balanced Diet', 'Team Sports Rules', 'Safety at Play'],
      'Class 4': ['First Aid Basics', 'Yoga Introduction', 'Importance of Sleep'],
      'Class 5': ['Fitness & Stamina', 'Nutrition Labels', 'Mental Health Awareness'],
    },
  },
]

const GOLD_STEPS = [
  {
    number: '01', title: 'Tiered Difficulty',
    subtitle: 'Foundation → Application → Stretch',
    desc: 'Every worksheet automatically groups questions into three tiers. Foundation builds confidence, Application checks understanding, Stretch reveals the ceiling — without the child ever feeling overwhelmed.',
    example: '★ Add 456 + 327  ·  ★★ Priya\'s word problem  ·  ★★★ Find Rahul\'s carry error',
  },
  {
    number: '02', title: 'Mastery-Personalised',
    subtitle: 'Adapts to your child\'s history',
    desc: 'The slot engine reads your child\'s mastery state and automatically shifts the question mix — more Recognition practice when struggling, more Thinking challenges when they\'re excelling.',
    example: 'Low mastery → 60% Recognition  ·  High mastery → 40% Thinking questions',
  },
  {
    number: '03', title: 'Hints on Stretch',
    subtitle: 'Collapsible scaffolding, always optional',
    desc: 'Thinking and Error-Detection questions include a hidden hint. Reveal it only when stuck — this teaches children to attempt independently before seeking help.',
    example: '→ Show Hint: "What happens to the tens digit when you carry?"',
  },
  {
    number: '04', title: 'Parent Insight Footer',
    subtitle: 'After every graded attempt',
    desc: 'After grading, each worksheet returns a specific watch-for warning and a clear next-step — written for parents, not educators. No tutoring degree required.',
    example: 'Watch for: Tens-digit carry errors  ·  Next step: Try 4-digit addition',
  },
  {
    number: '05', title: 'Learning Objective Header',
    subtitle: 'Printed on every worksheet',
    desc: 'Three clear checkpoints at the top of every worksheet tell the child and parent what success looks like before the first question is attempted.',
    example: '✓ Add 3-digit numbers with carry  ✓ Solve word problems  ✓ Spot errors',
  },
  {
    number: '06', title: 'Premium Print PDF',
    subtitle: 'A4, margin-safe, B&W friendly',
    desc: 'Export a print-ready PDF with name/date header, tiered sections, difficulty star badges, and a complete answer key on a separate page. School-ready in one click.',
    example: 'Objective box · 3 Tier sections · Star badges · Full answer key on page 2',
  },
]

const COMPARISON = [
  { feature: 'CBSE-aligned skill progression', us: true, free: false },
  { feature: 'Tiered difficulty (Foundation / Application / Stretch)', us: true, free: false },
  { feature: 'Mastery-aware question mix', us: true, free: false },
  { feature: 'Indian-context word problems', us: true, free: false },
  { feature: 'Collapsible hints for stretch questions', us: true, free: false },
  { feature: 'Parent insight after grading', us: true, free: false },
  { feature: 'Print-ready PDF with answer key', us: true, free: 'partial' },
  { feature: 'No repeated questions (dedup guard)', us: true, free: false },
]

// ── Scroll Reveal ─────────────────────────────────────────────────────────────
function Reveal({ children, delay = 0, className = '' }: { children: React.ReactNode; delay?: number; className?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const [show, setShow] = useState(false)
  useEffect(() => {
    const obs = new IntersectionObserver(([e]) => { if (e.isIntersecting) setShow(true) }, { threshold: 0.08 })
    if (ref.current) obs.observe(ref.current)
    return () => obs.disconnect()
  }, [])
  return (
    <div ref={ref} className={className} style={{ opacity: show ? 1 : 0, transform: show ? 'none' : 'translateY(22px)', transition: `opacity 0.6s ease ${delay}ms, transform 0.6s ease ${delay}ms` }}>
      {children}
    </div>
  )
}

// ── Component ─────────────────────────────────────────────────────────────────
export default function Landing({ onGetStarted, onSignIn }: Props) {
  const [scrolled, setScrolled] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [activeSubject, setActiveSubject] = useState(0)
  const [activeClass, setActiveClass] = useState('Class 3')
  const [activeStep, setActiveStep] = useState(0)

  useEffect(() => {
    const fn = () => setScrolled(window.scrollY > 24)
    window.addEventListener('scroll', fn, { passive: true })
    return () => window.removeEventListener('scroll', fn)
  }, [])

  useEffect(() => {
    const classes = Object.keys(SUBJECTS[activeSubject].classes)
    if (!classes.includes(activeClass)) setActiveClass(classes[0])
  }, [activeSubject])

  const scrollTo = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
    setMobileOpen(false)
  }

  const subj = SUBJECTS[activeSubject]
  const topics = (subj.classes as unknown as Record<string, string[]>)[activeClass] ?? []
  const availClasses = Object.keys(subj.classes)

  return (
    <div className="lr">

      {/* ── NAV ── */}
      <nav className={`ln ${scrolled ? 'ln-s' : ''}`}>
        <div className="ln-i">
          <button className="ll" onClick={() => scrollTo('hero')}>
            <span className="ll-mark">◆</span>
            <span className="ll-name">PracticeCraft</span>
          </button>
          <div className="ln-links">
            <button onClick={() => scrollTo('how')}>How it works</button>
            <button onClick={() => scrollTo('subjects')}>Subjects</button>
            <button onClick={() => scrollTo('pricing')}>Pricing</button>
          </div>
          <div className="ln-ctas">
            <button className="b-ghost" onClick={onSignIn}>Sign in</button>
            <button className="b-green" onClick={onGetStarted}>Start free</button>
          </div>
          <button className="ham" onClick={() => setMobileOpen(!mobileOpen)} aria-label="Menu">
            <span /><span /><span />
          </button>
        </div>
        {mobileOpen && (
          <div className="mm">
            <button onClick={() => scrollTo('how')}>How it works</button>
            <button onClick={() => scrollTo('subjects')}>Subjects</button>
            <button onClick={() => scrollTo('pricing')}>Pricing</button>
            <div className="mm-row">
              <button className="b-ghost" onClick={onSignIn}>Sign in</button>
              <button className="b-green" onClick={onGetStarted}>Start free →</button>
            </div>
          </div>
        )}
      </nav>

      {/* ── HERO ── */}
      <section id="hero" className="hero">
        <div className="hero-i">

          {/* Left */}
          <div className="hero-l">
            <span className="eyebrow">
              <span className="eyebrow-dot" />
              Curriculum-Aligned Practice Engine
            </span>
            <h1 className="hero-h">
              Worksheets that<br />
              <em className="hero-em">know your child.</em>
            </h1>
            <p className="hero-p">
              Generate CBSE-aligned worksheets for Classes 1–5 across 8 subjects.
              Mastery-aware, difficulty-tiered, Indian-contextual. Track skill gaps. Build lasting understanding.
            </p>
            <div className="hero-btns">
              <button className="b-green b-lg" onClick={onGetStarted}>
                Generate Worksheet <span className="b-arr">→</span>
              </button>
              <button className="b-outline b-lg" onClick={() => scrollTo('how')}>
                See how it works
              </button>
            </div>
            <div className="trust-row">
              {[
                { icon: <IcGradCap />, label: 'No card needed' },
                { icon: <IcBook />, label: '196 topics' },
                { icon: <IcFlag />, label: 'CBSE aligned' },
              ].map(t => (
                <span key={t.label} className="trust-chip">{t.icon} {t.label}</span>
              ))}
            </div>
          </div>

          {/* Worksheet mockup */}
          <div className="hero-r">
            <div className="ws">
              <div className="ws-hd">
                <div className="ws-badge">CBSE · Class 3 · Mathematics</div>
                <div className="ws-name-row">
                  <span>Name: <span className="ws-line" /></span>
                  <span>Date: <span className="ws-line ws-line-s" /></span>
                </div>
                <h3 className="ws-title">Addition with Carrying</h3>
                <div className="ws-objs">
                  <div>✓ Add 3-digit numbers with carry</div>
                  <div>✓ Solve real-life word problems</div>
                  <div>✓ Identify errors in calculations</div>
                </div>
              </div>
              <div className="ws-bar" />
              <div className="ws-body">
                <div className="ws-q">
                  <div className="ws-ql">
                    <span className="ws-num">1</span>
                    <div className="ws-col">
                      <div>&#8194;4 7 3</div>
                      <div className="ws-op">+ 2 8 9</div>
                      <div className="ws-ans">_______</div>
                      <div className="ws-box">□ □ □</div>
                    </div>
                  </div>
                  <span className="ws-tier ws-f">★ Foundation</span>
                </div>
                <div className="ws-q">
                  <div className="ws-ql">
                    <span className="ws-num">2</span>
                    <p className="ws-qt">Priya sold <strong>347</strong> books at the school mela. Rohan sold <strong>258</strong> more. How many in all?</p>
                  </div>
                  <span className="ws-tier ws-a">★★ Application</span>
                </div>
                <div className="ws-q ws-last">
                  <div className="ws-ql">
                    <span className="ws-num">3</span>
                    <p className="ws-qt"><span className="ws-err">Spot the error:</span> Rahul says 456 + 278 = 724. What mistake did he make?</p>
                  </div>
                  <span className="ws-tier ws-s">★★★ Stretch</span>
                </div>
              </div>
              <div className="ws-ft">
                <span>PracticeCraft</span>
                <span>📄 Answer key on next page</span>
              </div>
            </div>

            <div className="fb fb1">
              <span className="fb-icon"><IcTarget /></span>
              <div>
                <div className="fb-lbl">Mastery Progress</div>
                <div className="fb-bar"><div className="fb-fill" /></div>
              </div>
              <span className="fb-pct">72%</span>
            </div>
            <div className="fb fb2"><IcLightbulb /> Hint available on Q3</div>
          </div>
        </div>
      </section>

      {/* ── STATS BAR ── */}
      <section className="stats">
        <div className="stats-i">
          {[
            { n: '196', l: 'Topics' },
            { n: '8', l: 'Subjects' },
            { n: '5', l: 'Classes' },
            { n: '5', l: 'Question Types' },
            { n: '∞', l: 'Variations' },
          ].map(s => (
            <div key={s.l} className="stat">
              <span className="stat-n">{s.n}</span>
              <span className="stat-l">{s.l}</span>
            </div>
          ))}
        </div>
      </section>

      {/* ── PROBLEM ── */}
      <section className="prob">
        <Reveal>
          <div className="sec-ew">The Problem</div>
          <h2 className="sec-h">Free tools leave real gaps.</h2>
          <p className="sec-sub">Printable worksheets don't know your child's history. Random generators ignore the CBSE curriculum. The result: busy work that builds false confidence, not mastery.</p>
        </Reveal>
        <div className="prob-cards">
          {[
            { icon: <IcShuffle />, t: 'Random, not Structured', d: 'Generic PDFs skip the CBSE learning ladder. Children end up with questions that are either too easy or completely disconnected from this week\'s topic.' },
            { icon: <IcChart />, t: 'No Skill Tracking', d: 'Without mastery data, parents and tutors can\'t know whether the carry problem is actually fixed — or just temporarily avoided.' },
            { icon: <IcPrinter />, t: 'Print ≠ Real Practice', d: 'A 50-question drill on one operation is busywork. Real practice needs Recognition → Application → Stretch in every single session.' },
          ].map((c, i) => (
            <Reveal key={i} delay={i * 80} className="prob-card">
              <span className="prob-icon">{c.icon}</span>
              <h3>{c.t}</h3>
              <p>{c.d}</p>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ── HOW IT WORKS ── */}
      <section id="how" className="how">
        <Reveal>
          <div className="sec-ew">Gold Class Features</div>
          <h2 className="sec-h">Six things that make it different.</h2>
        </Reveal>
        <div className="how-layout">
          <div className="how-list">
            {GOLD_STEPS.map((s, i) => (
              <button key={i} className={`how-item ${activeStep === i ? 'how-active' : ''}`} onClick={() => setActiveStep(i)}>
                <span className="how-n">{s.number}</span>
                <div>
                  <div className="how-t">{s.title}</div>
                  <div className="how-sub">{s.subtitle}</div>
                </div>
              </button>
            ))}
          </div>
          <div className="how-detail">
            <div className="how-bg-n">{GOLD_STEPS[activeStep].number}</div>
            <h3 className="how-dt">{GOLD_STEPS[activeStep].title}</h3>
            <p className="how-ds">{GOLD_STEPS[activeStep].subtitle}</p>
            <p className="how-dd">{GOLD_STEPS[activeStep].desc}</p>
            <div className="how-ex">{GOLD_STEPS[activeStep].example}</div>
          </div>
        </div>
      </section>

      {/* ── SUBJECTS ── */}
      <section id="subjects" className="subjs">
        <Reveal>
          <div className="sec-ew">Subject Coverage</div>
          <h2 className="sec-h">Eight subjects. 196 topics. All CBSE.</h2>
        </Reveal>
        <div className="subj-tabs">
          {SUBJECTS.map((s, i) => (
            <button key={s.key} className={`subj-tab ${activeSubject === i ? 'subj-on' : ''}`} onClick={() => setActiveSubject(i)}>
              <span className="st-sym">{s.symbol}</span>
              {s.label}
            </button>
          ))}
        </div>
        <div className="cls-tabs">
          {availClasses.map(c => (
            <button key={c} className={`cls-tab ${activeClass === c ? 'cls-on' : ''}`} onClick={() => setActiveClass(c)}>{c}</button>
          ))}
        </div>
        <div className="topic-grid">
          {topics.map((t, i) => (
            <Reveal key={`${activeSubject}-${activeClass}-${i}`} delay={i * 25} className="topic-pill">
              {t}
            </Reveal>
          ))}
        </div>
        <p className="subj-desc">{subj.symbol} {subj.description}</p>
      </section>

      {/* ── COMPARISON ── */}
      <section className="comp">
        <Reveal>
          <div className="sec-ew">Why PracticeCraft</div>
          <h2 className="sec-h">vs free tools &amp; generic PDFs</h2>
        </Reveal>
        <div className="comp-wrap">
          <table className="comp-table">
            <thead>
              <tr>
                <th>Feature</th>
                <th className="th-us">PracticeCraft</th>
                <th>Free Tools</th>
              </tr>
            </thead>
            <tbody>
              {COMPARISON.map((r, i) => (
                <tr key={i}>
                  <td>{r.feature}</td>
                  <td className="td-us"><span className="ck-y">✓</span></td>
                  <td>{r.free === true ? <span className="ck-y">✓</span> : r.free === 'partial' ? <span className="ck-p">~</span> : <span className="ck-n">✗</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* ── SOCIAL PROOF ── */}
      <section className="social">
        <Reveal>
          <div className="sec-ew">Trusted by Educators</div>
          <h2 className="sec-h">What parents &amp; teachers say.</h2>
        </Reveal>
        <div className="testi-grid">
          {[
            { quote: "Finally, a tool that actually understands the CBSE curriculum. My daughter\'s carry addition improved in just two weeks of focused practice.", name: 'Priya S.', role: 'Parent, Bengaluru', initials: 'PS' },
            { quote: "I generate topic-wise worksheets for 32 students every week. It saves me 3 hours of prep time — and the question quality is genuinely impressive.", name: 'Rekha Sharma', role: 'Maths Teacher, Delhi', initials: 'RS' },
            { quote: "The mastery tracking pinpointed exactly where my son was struggling. We focused on fractions for 10 days and his test score jumped 18 marks.", name: 'Arjun M.', role: 'Parent, Mumbai', initials: 'AM' },
          ].map((t, i) => (
            <Reveal key={i} delay={i * 80} className="testi-card">
              <div className="testi-stars">★★★★★</div>
              <p className="testi-q">"{t.quote}"</p>
              <div className="testi-author">
                <div className="testi-avatar">{t.initials}</div>
                <div>
                  <div className="testi-name">{t.name}</div>
                  <div className="testi-role">{t.role}</div>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ── PERSONA CARDS ── */}
      <section className="persona">
        <div className="persona-grid">
          <Reveal className="pc pc-parent">
            <div className="pc-lbl">For Parents</div>
            <h3>Know exactly where your child stands.</h3>
            <ul>
              <li>Generate a focused worksheet in 30 seconds</li>
              <li>Choose the right topic for tonight's practice</li>
              <li>See mastery progress improve over time</li>
              <li>Understand what went wrong — no tutoring degree needed</li>
              <li>Print-ready A4 PDF, no formatting hassle</li>
            </ul>
            <button className="b-green" onClick={onGetStarted}>Start as Parent →</button>
          </Reveal>
          <Reveal className="pc pc-teacher" delay={120}>
            <div className="pc-lbl">For Teachers</div>
            <h3>Differentiated practice, at scale.</h3>
            <ul>
              <li>Generate topic-wise worksheets for the whole class</li>
              <li>Bulk generate across 5 topics in one click (paid)</li>
              <li>Share instantly via WhatsApp or print batches</li>
              <li>Track class-wide mastery and skill gaps</li>
              <li>CBSE chapter progression, already mapped</li>
            </ul>
            <button className="b-outline" onClick={onGetStarted}>Start as Teacher →</button>
          </Reveal>
        </div>
      </section>

      {/* ── PRICING ── */}
      <section id="pricing" className="pricing">
        <Reveal>
          <div className="sec-ew">Simple Pricing</div>
          <h2 className="sec-h">Start free. Upgrade when ready.</h2>
        </Reveal>
        <div className="pr-grid">
          <Reveal className="pr-card pr-free">
            <div className="pr-lbl">Free</div>
            <div className="pr-amt">₹0 <span>/month</span></div>
            <div className="pr-desc">No credit card required</div>
            <ul className="pr-feats">
              <li className="pr-yes">10 worksheets per month</li>
              <li className="pr-yes">All 8 subjects</li>
              <li className="pr-yes">PDF download</li>
              <li className="pr-yes">5 or 10 questions</li>
              <li className="pr-no">Mastery tracking</li>
              <li className="pr-no">Bulk generation</li>
              <li className="pr-no">Parent insights after grading</li>
            </ul>
            <button className="b-outline b-full" onClick={onGetStarted}>Get started free</button>
          </Reveal>
          <Reveal className="pr-card pr-paid" delay={100}>
            <div className="pr-badge">Most Popular</div>
            <div className="pr-lbl">Scholar</div>
            <div className="pr-amt">₹299 <span>/month</span></div>
            <div className="pr-desc">Everything a child needs to excel</div>
            <ul className="pr-feats">
              <li className="pr-yes">Unlimited worksheets</li>
              <li className="pr-yes">All 8 subjects</li>
              <li className="pr-yes">Premium tiered PDF + answer key</li>
              <li className="pr-yes">5, 10, 15 or 20 questions</li>
              <li className="pr-yes">Mastery tracking per skill</li>
              <li className="pr-yes">Bulk generation (up to 5 topics)</li>
              <li className="pr-yes">Parent insight after every attempt</li>
            </ul>
            <button className="b-amber b-full" onClick={onGetStarted}>Start 14-day trial</button>
          </Reveal>
        </div>
      </section>

      {/* ── PHILOSOPHY ── */}
      <section className="phil">
        <Reveal>
          <div className="sec-ew">Our Approach</div>
          <h2 className="sec-h">Built on one principle: real understanding, not rote practice.</h2>
        </Reveal>
        <div className="phil-grid">
          {[
            { n: 'I', t: 'Depth before breadth', d: 'One topic practised in five different ways is worth more than five topics practised once each. Our slot engine enforces this structure on every worksheet it generates.' },
            { n: 'II', t: 'Structured progression', d: 'Recognition → Application → Representation → Error Detection → Thinking. Every worksheet follows this arc, in every subject, at every class level.' },
            { n: 'III', t: 'Indian context, always', d: 'Priya at the mela. Rahul\'s cricket runs. Diwali lamps. Word problems a child in Bengaluru or Bhopal can picture immediately — not abstract fictions.' },
          ].map((p, i) => (
            <Reveal key={i} delay={i * 80} className="phil-card">
              <div className="phil-n">{p.n}</div>
              <h3>{p.t}</h3>
              <p>{p.d}</p>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ── CTA ── */}
      <section className="cta">
        <Reveal>
          <h2 className="cta-h">Ready to build real mastery?</h2>
          <p className="cta-sub">Start with 10 free worksheets. No card, no commitment.</p>
          <button className="b-amber b-xl" onClick={onGetStarted}>
            Generate your first worksheet →
          </button>
          <p className="cta-contact">Questions? Write to us at <a href="mailto:hello@practicecraft.in">hello@practicecraft.in</a></p>
        </Reveal>
      </section>

      {/* ── FOOTER ── */}
      <footer className="lf">
        <div className="lf-i">
          <div className="ll" style={{ cursor: 'default' }}>
            <span className="ll-mark">◆</span>
            <span className="ll-name" style={{ color: 'rgba(255,255,255,0.88)' }}>PracticeCraft</span>
          </div>
          <nav className="lf-nav">
            <button onClick={() => scrollTo('how')}>How it works</button>
            <button onClick={() => scrollTo('subjects')}>Subjects</button>
            <button onClick={() => scrollTo('pricing')}>Pricing</button>
            <a href="mailto:hello@practicecraft.in">Contact</a>
          </nav>
          <p className="lf-copy">© 2025 PracticeCraft · CBSE Classes 1–5</p>
        </div>
      </footer>

      {/* ══════════════════════════════════════════════════════════
          Warm Scholar Styles
          Deep Forest Green #1B4332 · Amber #D97706 · Parchment #FAF7F2
      ══════════════════════════════════════════════════════════ */}
      <style>{`
        .lr {
          --g:  #1B4332;
          --g2: #2D6A4F;
          --a:  #B45309;
          --a2: #D97706;
          --a3: #F59E0B;
          --pc: #FAF7F2;
          --sf: #F2ECE2;
          --wb: #E8DECA;
          --tx: #1C1917;
          --mt: #78716C;
          font-family: 'DM Sans', system-ui, sans-serif;
          background: var(--pc);
          color: var(--tx);
          overflow-x: hidden;
        }

        /* NAV */
        .ln {
          position: fixed; top: 0; left: 0; right: 0; z-index: 1000;
          background: var(--pc);
          border-bottom: 1px solid transparent;
          transition: border-color .3s, box-shadow .3s;
        }
        .ln-s { border-bottom-color: var(--wb); box-shadow: 0 1px 14px rgba(27,67,50,.07); }
        .ln-i {
          max-width: 1200px; margin: 0 auto;
          padding: 0 24px; height: 68px;
          display: flex; align-items: center; gap: 32px;
        }
        .ll {
          display: flex; align-items: center; gap: 9px;
          background: none; border: none; cursor: pointer; padding: 0; flex-shrink: 0;
        }
        .ll-mark {
          width: 30px; height: 30px; background: var(--g); color: #fff;
          display: flex; align-items: center; justify-content: center;
          border-radius: 7px; font-size: 13px;
        }
        .ll-name {
          font-family: 'Fraunces', Georgia, serif;
          font-weight: 600; font-size: 19px; color: var(--g); letter-spacing: -.01em;
        }
        .ln-links { display: flex; gap: 2px; flex: 1; }
        .ln-links button {
          background: none; border: none; cursor: pointer;
          font-size: 14px; color: var(--mt); padding: 8px 14px; border-radius: 7px;
          transition: color .2s, background .2s; font-family: 'DM Sans', sans-serif;
        }
        .ln-links button:hover { color: var(--g); background: rgba(27,67,50,.07); }
        .ln-ctas { display: flex; gap: 8px; align-items: center; }

        /* Buttons */
        .b-ghost {
          background: none; border: none; cursor: pointer; font-size: 14px; color: var(--mt);
          padding: 8px 14px; border-radius: 7px; transition: color .2s, background .2s;
          font-family: 'DM Sans', sans-serif;
        }
        .b-ghost:hover { color: var(--g); background: rgba(27,67,50,.07); }
        .b-green {
          background: var(--g); color: #fff; border: none; cursor: pointer;
          font-size: 14px; font-weight: 600; padding: 10px 20px; border-radius: 8px;
          transition: background .2s, transform .1s; font-family: 'DM Sans', sans-serif;
          display: inline-flex; align-items: center; gap: 6px;
        }
        .b-green:hover { background: var(--g2); }
        .b-green:active { transform: scale(.98); }
        .b-amber {
          background: var(--a2); color: #fff; border: none; cursor: pointer;
          font-size: 14px; font-weight: 600; padding: 10px 20px; border-radius: 8px;
          transition: background .2s, transform .1s; font-family: 'DM Sans', sans-serif;
          display: inline-flex; align-items: center; gap: 6px;
        }
        .b-amber:hover { background: var(--a); }
        .b-amber:active { transform: scale(.98); }
        .b-outline {
          background: transparent; color: var(--g); border: 1.5px solid var(--g);
          cursor: pointer; font-size: 14px; font-weight: 600; padding: 10px 20px;
          border-radius: 8px; transition: background .2s; font-family: 'DM Sans', sans-serif;
          display: inline-flex; align-items: center; gap: 6px;
        }
        .b-outline:hover { background: rgba(27,67,50,.07); }
        .b-lg { padding: 14px 28px; font-size: 16px; border-radius: 10px; }
        .b-xl { padding: 18px 38px; font-size: 17px; border-radius: 12px; }
        .b-full { width: 100%; justify-content: center; }
        .b-arr { transition: transform .2s; }
        .b-green:hover .b-arr { transform: translateX(3px); }

        /* Hamburger */
        .ham {
          display: none; flex-direction: column; gap: 5px;
          background: none; border: none; cursor: pointer; padding: 8px; margin-left: auto;
        }
        .ham span { display: block; width: 22px; height: 2px; background: var(--tx); border-radius: 2px; }
        .mm {
          background: var(--pc); border-top: 1px solid var(--wb);
          padding: 10px 24px 20px; display: flex; flex-direction: column; gap: 2px;
        }
        .mm button {
          background: none; border: none; cursor: pointer; font-size: 16px; color: var(--tx);
          padding: 10px 0; text-align: left; font-family: 'DM Sans', sans-serif;
        }
        .mm-row { display: flex; flex-direction: column; gap: 8px; margin-top: 12px; }

        /* HERO */
        .hero {
          padding: 124px 24px 80px; min-height: 100vh;
          display: flex; align-items: center;
          background: radial-gradient(ellipse 90% 60% at 55% 0%, rgba(27,67,50,.055) 0%, transparent 60%), var(--pc);
          position: relative;
        }
        .hero::before {
          content: ''; position: absolute; inset: 0;
          background-image: radial-gradient(circle, rgba(27,67,50,.11) 1px, transparent 1px);
          background-size: 26px 26px; pointer-events: none; z-index: 0;
        }
        .hero-i {
          max-width: 1200px; margin: 0 auto;
          display: grid; grid-template-columns: 1fr 1fr; gap: 64px; align-items: center;
          position: relative; z-index: 1;
        }
        .hero-l { display: flex; flex-direction: column; gap: 24px; }
        .eyebrow {
          display: inline-flex; align-items: center; gap: 8px;
          font-size: 12.5px; font-weight: 700; color: var(--g);
          text-transform: uppercase; letter-spacing: .09em;
          background: rgba(27,67,50,.09); border: 1px solid rgba(27,67,50,.16);
          padding: 6px 14px; border-radius: 100px; width: fit-content;
        }
        .eyebrow-dot {
          width: 6px; height: 6px; border-radius: 50%; background: var(--g);
          animation: pdot 2.2s ease-in-out infinite;
        }
        .hero-h {
          font-family: 'Fraunces', Georgia, serif;
          font-size: clamp(40px, 5.5vw, 68px); font-weight: 700;
          line-height: 1.07; letter-spacing: -.025em; color: var(--tx); margin: 0;
        }
        .hero-em {
          color: var(--g); font-style: italic;
          position: relative; display: inline-block;
        }
        .hero-em::after {
          content: ''; position: absolute; bottom: 4px; left: 0; right: 0;
          height: 4px; background: var(--a3); border-radius: 2px;
          transform: scaleX(0); transform-origin: left;
          animation: uline .9s ease .7s forwards;
        }
        .hero-p { font-size: 16px; line-height: 1.72; color: var(--mt); max-width: 480px; margin: 0; }
        .hero-btns { display: flex; gap: 12px; flex-wrap: wrap; }
        .trust-row { display: flex; gap: 8px; flex-wrap: wrap; }
        .trust-chip {
          font-size: 12.5px; color: var(--mt);
          background: var(--sf); border: 1px solid var(--wb);
          padding: 5px 13px; border-radius: 100px;
          display: inline-flex; align-items: center; gap: 6px;
        }

        /* Worksheet Mockup */
        .hero-r { position: relative; display: flex; align-items: center; justify-content: center; }
        .ws {
          background: #fff; border: 1px solid var(--wb); border-radius: 14px;
          box-shadow: 0 4px 6px rgba(0,0,0,.04), 0 20px 56px rgba(27,67,50,.11), 0 36px 90px rgba(27,67,50,.06);
          width: 100%; max-width: 440px; overflow: hidden; font-size: 13px;
          animation: fws 7s ease-in-out infinite;
        }
        .ws-hd { background: var(--g); color: #fff; padding: 18px 22px; }
        .ws-badge {
          font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .1em;
          background: rgba(255,255,255,.16); padding: 3px 10px; border-radius: 100px;
          width: fit-content; margin-bottom: 10px; color: rgba(255,255,255,.9);
        }
        .ws-name-row { display: flex; gap: 16px; font-size: 11px; color: rgba(255,255,255,.72); margin-bottom: 10px; }
        .ws-line { display: inline-block; width: 76px; border-bottom: 1px solid rgba(255,255,255,.45); vertical-align: bottom; }
        .ws-line-s { width: 48px; }
        .ws-title {
          font-family: 'Fraunces', Georgia, serif;
          font-size: 18px; font-weight: 600; margin: 0 0 10px; letter-spacing: -.01em; color: #fff; line-height: 1.2;
        }
        .ws-objs { display: flex; flex-direction: column; gap: 4px; }
        .ws-objs div { font-size: 11px; color: rgba(255,255,255,.78); }
        .ws-bar { height: 3px; background: linear-gradient(90deg, var(--a2) 0%, var(--a3) 50%, transparent 100%); }
        .ws-body { padding: 14px 22px; display: flex; flex-direction: column; gap: 12px; }
        .ws-q {
          display: flex; justify-content: space-between; align-items: flex-start; gap: 12px;
          padding-bottom: 12px; border-bottom: 1px solid #F0EBE3;
        }
        .ws-last { border-bottom: none; padding-bottom: 0; }
        .ws-ql { display: flex; gap: 10px; align-items: flex-start; flex: 1; }
        .ws-num {
          width: 22px; height: 22px; border-radius: 50%; background: var(--g); color: #fff;
          font-size: 11px; font-weight: 700; display: flex; align-items: center;
          justify-content: center; flex-shrink: 0; margin-top: 1px;
        }
        .ws-col { font-family: 'Courier New', monospace; font-size: 13px; line-height: 1.65; color: var(--tx); }
        .ws-op { border-bottom: 1px solid var(--tx); }
        .ws-ans { color: transparent; border-bottom: 1px solid #CBD5E1; }
        .ws-box { color: var(--mt); letter-spacing: 4px; }
        .ws-qt { font-size: 12.5px; line-height: 1.55; color: var(--tx); margin: 0; }
        .ws-err { font-weight: 700; color: #DC2626; font-size: 10.5px; text-transform: uppercase; letter-spacing: .05em; }
        .ws-tier { font-size: 10px; font-weight: 700; padding: 3px 9px; border-radius: 100px; white-space: nowrap; flex-shrink: 0; }
        .ws-f { background: #DCFCE7; color: #166534; }
        .ws-a { background: #FEF3C7; color: #92400E; }
        .ws-s { background: #FCE7F3; color: #9D174D; }
        .ws-ft {
          background: #F8F4EE; border-top: 1px solid var(--wb);
          padding: 8px 22px; display: flex; justify-content: space-between; font-size: 10px; color: var(--mt);
        }

        /* Floating badges */
        .fb {
          position: absolute; background: #fff; border: 1px solid var(--wb);
          border-radius: 10px; padding: 10px 14px;
          box-shadow: 0 4px 18px rgba(0,0,0,.09);
          display: flex; align-items: center; gap: 10px;
          font-size: 12px; font-weight: 600; color: var(--tx);
          animation: fbadge 4.5s ease-in-out infinite;
        }
        .fb1 { top: -18px; right: -18px; animation-delay: .4s; }
        .fb2 {
          bottom: 18px; right: -28px; animation-delay: 1.8s;
          font-size: 11px; background: #FFFBEB; border-color: #FDE68A; color: #92400E;
          display: flex; align-items: center; gap: 7px;
        }
        .fb-icon { display: flex; align-items: center; justify-content: center; color: var(--g); }
        .fb-lbl { font-size: 10px; color: var(--mt); font-weight: 400; margin-bottom: 4px; }
        .fb-bar { width: 80px; height: 4px; background: #E5E7EB; border-radius: 2px; overflow: hidden; }
        .fb-fill { height: 100%; width: 72%; background: var(--g); border-radius: 2px; animation: gbar 1.6s ease .9s both; }
        .fb-pct { font-size: 16px; font-weight: 700; color: var(--g); }

        /* STATS */
        .stats { background: var(--g); padding: 22px 24px; }
        .stats-i { max-width: 1200px; margin: 0 auto; display: flex; justify-content: center; gap: 52px; flex-wrap: wrap; }
        .stat { display: flex; flex-direction: column; align-items: center; gap: 2px; }
        .stat-n { font-family: 'Fraunces', Georgia, serif; font-size: 30px; font-weight: 700; color: #fff; line-height: 1; }
        .stat-l { font-size: 11px; text-transform: uppercase; letter-spacing: .08em; color: rgba(255,255,255,.6); font-weight: 600; }

        /* Section commons */
        .sec-ew { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .1em; color: var(--a); margin-bottom: 10px; }
        .sec-h {
          font-family: 'Fraunces', Georgia, serif;
          font-size: clamp(28px, 4vw, 44px); font-weight: 700;
          line-height: 1.1; letter-spacing: -.02em; color: var(--tx); margin: 0 0 14px;
        }
        .sec-sub { font-size: 16px; line-height: 1.68; color: var(--mt); max-width: 620px; margin: 0; }

        /* PROBLEM */
        .prob { padding: 88px 24px; background: var(--sf); text-align: center; }
        .prob .sec-ew, .prob .sec-h, .prob .sec-sub { margin-left: auto; margin-right: auto; }
        .prob-cards { max-width: 1100px; margin: 52px auto 0; display: grid; grid-template-columns: repeat(3,1fr); gap: 24px; }
        .prob-card {
          background: #fff; border: 1px solid var(--wb); border-radius: 12px;
          padding: 30px 26px; text-align: left; border-left: 3px solid var(--a2);
        }
        .prob-icon {
          width: 48px; height: 48px; border-radius: 12px;
          background: rgba(27,67,50,.09); color: var(--g);
          display: flex; align-items: center; justify-content: center;
          margin-bottom: 16px; flex-shrink: 0;
        }
        .prob-card h3 {
          font-family: 'Fraunces', Georgia, serif;
          font-size: 18px; font-weight: 600; margin: 0 0 10px; color: var(--tx);
        }
        .prob-card p { font-size: 14px; line-height: 1.68; color: var(--mt); margin: 0; }

        /* HOW */
        .how { padding: 88px 24px; background: var(--pc); }
        .how .sec-ew, .how .sec-h { max-width: 1200px; margin-left: auto; margin-right: auto; }
        .how-layout { max-width: 1200px; margin: 52px auto 0; display: grid; grid-template-columns: 320px 1fr; gap: 28px; align-items: start; }
        .how-list { display: flex; flex-direction: column; gap: 3px; }
        .how-item {
          display: flex; align-items: center; gap: 16px; padding: 14px 16px;
          background: none; border: 1px solid transparent; border-radius: 10px;
          cursor: pointer; text-align: left; transition: all .2s; width: 100%;
        }
        .how-item:hover { background: var(--sf); border-color: var(--wb); }
        .how-active { background: #fff !important; border-color: var(--wb) !important; box-shadow: 0 2px 10px rgba(0,0,0,.06); }
        .how-n {
          font-family: 'Fraunces', Georgia, serif;
          font-size: 24px; font-weight: 700; color: var(--g);
          opacity: .28; width: 42px; transition: opacity .2s; flex-shrink: 0;
        }
        .how-active .how-n { opacity: 1; }
        .how-t { font-weight: 600; font-size: 14px; color: var(--tx); margin-bottom: 2px; }
        .how-sub { font-size: 12px; color: var(--mt); }
        .how-detail { background: #fff; border: 1px solid var(--wb); border-radius: 14px; padding: 38px; position: sticky; top: 88px; }
        .how-bg-n {
          font-family: 'Fraunces', Georgia, serif;
          font-size: 80px; font-weight: 700; color: var(--g);
          opacity: .07; line-height: 1; margin-bottom: -22px;
        }
        .how-dt { font-family: 'Fraunces', Georgia, serif; font-size: 28px; font-weight: 700; color: var(--tx); margin: 0 0 6px; letter-spacing: -.01em; }
        .how-ds { font-size: 12px; font-weight: 700; color: var(--a); text-transform: uppercase; letter-spacing: .05em; margin: 0 0 18px; }
        .how-dd { font-size: 15px; line-height: 1.72; color: var(--mt); margin: 0 0 26px; }
        .how-ex {
          background: var(--sf); border: 1px solid var(--wb); border-left: 3px solid var(--g);
          border-radius: 8px; padding: 14px 18px;
          font-size: 13px; color: var(--tx); font-family: 'Courier New', monospace; line-height: 1.65;
        }

        /* SUBJECTS */
        .subjs { padding: 88px 24px; background: var(--sf); }
        .subjs .sec-ew, .subjs .sec-h { max-width: 1200px; margin-left: auto; margin-right: auto; }
        .subj-tabs { max-width: 1200px; margin: 32px auto 0; display: flex; gap: 8px; flex-wrap: wrap; }
        .subj-tab {
          display: flex; align-items: center; gap: 7px;
          background: #fff; border: 1px solid var(--wb); border-radius: 100px;
          padding: 8px 18px; font-size: 13.5px; font-weight: 600;
          cursor: pointer; transition: all .2s; color: var(--mt); font-family: 'DM Sans', sans-serif;
        }
        .subj-tab:hover { border-color: var(--g); color: var(--g); }
        .subj-on { background: var(--g) !important; color: #fff !important; border-color: var(--g) !important; }
        .st-sym { font-size: 16px; }
        .cls-tabs { max-width: 1200px; margin: 16px auto 0; display: flex; gap: 6px; flex-wrap: wrap; }
        .cls-tab {
          background: none; border: 1px solid var(--wb); border-radius: 6px;
          padding: 5px 14px; font-size: 13px; cursor: pointer; color: var(--mt);
          transition: all .2s; font-family: 'DM Sans', sans-serif;
        }
        .cls-tab:hover { color: var(--g); border-color: var(--g); }
        .cls-on { background: #fff; color: var(--g); border-color: var(--g); font-weight: 600; }
        .topic-grid { max-width: 1200px; margin: 20px auto 0; display: flex; flex-wrap: wrap; gap: 8px; min-height: 72px; }
        .topic-pill {
          background: #fff; border: 1px solid var(--wb); border-radius: 100px;
          padding: 6px 16px; font-size: 13px; color: var(--tx); transition: border-color .2s, color .2s;
          cursor: pointer;
        }
        .topic-pill:hover { border-color: var(--g); color: var(--g); }
        .subj-desc { max-width: 1200px; margin: 22px auto 0; font-size: 14px; color: var(--mt); }

        /* COMPARISON */
        .comp { padding: 88px 24px; background: var(--pc); text-align: center; }
        .comp .sec-ew, .comp .sec-h { margin-left: auto; margin-right: auto; }
        .comp-wrap { max-width: 680px; margin: 44px auto 0; overflow: auto; }
        .comp-table { width: 100%; border-collapse: collapse; font-size: 14px; }
        .comp-table th { padding: 12px 16px; text-align: left; font-size: 11.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; color: var(--mt); border-bottom: 2px solid var(--wb); }
        .th-us { color: var(--g) !important; }
        .comp-table td { padding: 13px 16px; border-bottom: 1px solid #F0EBE3; color: var(--tx); }
        .comp-table tr:last-child td { border-bottom: none; }
        .td-us { background: rgba(27,67,50,.04); }
        .ck-y { color: var(--g); font-weight: 700; font-size: 15px; }
        .ck-n { color: #EF4444; font-size: 15px; }
        .ck-p { color: var(--a2); font-size: 15px; font-weight: 700; }

        /* PERSONA */
        .persona { padding: 88px 24px; background: var(--sf); }
        .persona-grid { max-width: 900px; margin: 0 auto; display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
        .pc { background: #fff; border: 1px solid var(--wb); border-radius: 16px; padding: 36px; }
        .pc-parent { border-top: 4px solid var(--g); }
        .pc-teacher { border-top: 4px solid var(--a2); }
        .pc-lbl { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .1em; color: var(--mt); margin-bottom: 12px; }
        .pc h3 { font-family: 'Fraunces', Georgia, serif; font-size: 22px; font-weight: 600; margin: 0 0 20px; line-height: 1.25; color: var(--tx); }
        .pc ul { list-style: none; padding: 0; margin: 0 0 24px; display: flex; flex-direction: column; gap: 10px; }
        .pc li { font-size: 14px; color: var(--mt); line-height: 1.5; padding-left: 18px; position: relative; }
        .pc li::before { content: '✓'; color: var(--g); font-weight: 700; position: absolute; left: 0; }

        /* PRICING */
        .pricing { padding: 88px 24px; background: var(--pc); text-align: center; }
        .pricing .sec-ew, .pricing .sec-h { margin-left: auto; margin-right: auto; }
        .pr-grid { max-width: 760px; margin: 52px auto 0; display: grid; grid-template-columns: 1fr 1fr; gap: 24px; align-items: start; }
        .pr-card { background: #fff; border: 1px solid var(--wb); border-radius: 16px; padding: 32px; text-align: left; position: relative; }
        .pr-paid { background: var(--g); border-color: var(--g); }
        .pr-badge {
          position: absolute; top: -13px; right: 22px;
          background: var(--a2); color: #fff; font-size: 10.5px; font-weight: 700;
          padding: 4px 12px; border-radius: 100px; text-transform: uppercase; letter-spacing: .06em;
        }
        .pr-lbl { font-size: 11.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .1em; color: var(--mt); margin-bottom: 8px; }
        .pr-paid .pr-lbl { color: rgba(255,255,255,.6); }
        .pr-amt { font-family: 'Fraunces', Georgia, serif; font-size: 44px; font-weight: 700; color: var(--tx); line-height: 1; margin-bottom: 6px; }
        .pr-paid .pr-amt { color: #fff; }
        .pr-amt span { font-size: 16px; font-weight: 400; color: var(--mt); }
        .pr-paid .pr-amt span { color: rgba(255,255,255,.6); }
        .pr-desc { font-size: 13px; color: var(--mt); margin-bottom: 26px; }
        .pr-paid .pr-desc { color: rgba(255,255,255,.65); }
        .pr-feats { list-style: none; padding: 0; margin: 0 0 28px; display: flex; flex-direction: column; gap: 10px; }
        .pr-feats li { font-size: 13.5px; display: flex; gap: 8px; align-items: flex-start; }
        .pr-yes { color: var(--tx); }
        .pr-yes::before { content: '✓'; color: var(--g); font-weight: 700; }
        .pr-no { color: var(--mt); opacity: .6; }
        .pr-no::before { content: '✗'; color: var(--mt); }
        .pr-paid .pr-yes { color: rgba(255,255,255,.88); }
        .pr-paid .pr-yes::before { color: var(--a3); }
        .pr-paid .b-outline { border-color: rgba(255,255,255,.4); color: #fff; }
        .pr-paid .b-amber { background: #fff; color: var(--g); }
        .pr-paid .b-amber:hover { background: rgba(255,255,255,.9); }

        /* PHILOSOPHY */
        .phil { padding: 88px 24px; background: var(--sf); }
        .phil .sec-ew, .phil .sec-h { max-width: 1200px; margin-left: auto; margin-right: auto; }
        .phil-grid { max-width: 1200px; margin: 52px auto 0; display: grid; grid-template-columns: repeat(3,1fr); gap: 24px; }
        .phil-card { background: #fff; border: 1px solid var(--wb); border-radius: 12px; padding: 32px; }
        .phil-n { font-family: 'Fraunces', Georgia, serif; font-size: 52px; font-weight: 700; color: var(--g); opacity: .12; line-height: 1; margin-bottom: 14px; }
        .phil-card h3 { font-family: 'Fraunces', Georgia, serif; font-size: 20px; font-weight: 600; color: var(--tx); margin: 0 0 12px; }
        .phil-card p { font-size: 14px; line-height: 1.72; color: var(--mt); margin: 0; }

        /* CTA */
        .cta { padding: 100px 24px; background: var(--g); text-align: center; }
        .cta-h { font-family: 'Fraunces', Georgia, serif; font-size: clamp(30px, 5vw, 52px); font-weight: 700; color: #fff; margin: 0 0 16px; letter-spacing: -.02em; }
        .cta-sub { font-size: 16px; color: rgba(255,255,255,.7); margin: 0 0 38px; }
        .cta-contact { margin-top: 22px; font-size: 13px; color: rgba(255,255,255,.5); }
        .cta-contact a { color: rgba(255,255,255,.78); text-decoration: none; }
        .cta-contact a:hover { color: #fff; }

        /* FOOTER */
        .lf { background: #0F2419; padding: 30px 24px; }
        .lf-i { max-width: 1200px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px; }
        .lf .ll-mark { background: var(--g2); }
        .lf-nav { display: flex; gap: 2px; flex-wrap: wrap; }
        .lf-nav button, .lf-nav a {
          background: none; border: none; cursor: pointer;
          font-size: 13px; color: rgba(255,255,255,.48); padding: 6px 10px;
          text-decoration: none; transition: color .2s; font-family: 'DM Sans', sans-serif;
        }
        .lf-nav button:hover, .lf-nav a:hover { color: #fff; }
        .lf-copy { font-size: 12px; color: rgba(255,255,255,.32); margin: 0; }

        /* ANIMATIONS */
        @keyframes fws { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-10px); } }
        @keyframes fbadge { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-6px); } }
        @keyframes uline { to { transform: scaleX(1); } }
        @keyframes pdot { 0%,100% { opacity: 1; transform: scale(1); } 50% { opacity: .4; transform: scale(1.3); } }
        @keyframes gbar { from { width: 0; } to { width: 72%; } }

        /* SOCIAL PROOF */
        .social { padding: 88px 24px; background: var(--sf); text-align: center; }
        .social .sec-ew, .social .sec-h { margin-left: auto; margin-right: auto; }
        .testi-grid { max-width: 1100px; margin: 52px auto 0; display: grid; grid-template-columns: repeat(3,1fr); gap: 24px; }
        .testi-card {
          background: #fff; border: 1px solid var(--wb); border-radius: 16px; padding: 28px;
          text-align: left; display: flex; flex-direction: column; gap: 16px;
          border-top: 3px solid var(--g);
        }
        .testi-stars { color: var(--a2); font-size: 13px; letter-spacing: 2px; }
        .testi-q { font-size: 14px; line-height: 1.75; color: var(--tx); margin: 0; font-style: italic; flex: 1; }
        .testi-author { display: flex; align-items: center; gap: 12px; }
        .testi-avatar {
          width: 40px; height: 40px; border-radius: 50%; background: var(--g);
          color: #fff; font-size: 12px; font-weight: 700;
          display: flex; align-items: center; justify-content: center; flex-shrink: 0;
        }
        .testi-name { font-size: 13.5px; font-weight: 600; color: var(--tx); margin-bottom: 2px; }
        .testi-role { font-size: 12px; color: var(--mt); }

        /* REDUCED MOTION */
        @media (prefers-reduced-motion: reduce) {
          .ws, .fb, .eyebrow-dot, .hero-em::after, .fb-fill { animation: none !important; }
          .ws { transform: none !important; }
          * { transition-duration: 0.01ms !important; }
        }

        /* RESPONSIVE */
        @media (max-width: 1024px) {
          .hero-i { grid-template-columns: 1fr; gap: 48px; }
          .hero-r { order: -1; }
          .ws { max-width: 480px; margin: 0 auto; }
          .fb { display: none; }
          .how-layout { grid-template-columns: 1fr; }
          .how-detail { position: static; }
          .ln-links, .ln-ctas { display: none; }
          .ham { display: flex; }
        }
        @media (max-width: 768px) {
          .hero { padding: 100px 20px 60px; }
          .prob-cards { grid-template-columns: 1fr; }
          .phil-grid { grid-template-columns: 1fr; }
          .pr-grid { grid-template-columns: 1fr; }
          .persona-grid { grid-template-columns: 1fr; }
          .testi-grid { grid-template-columns: 1fr; }
          .stats-i { gap: 28px; }
          .how-detail { padding: 26px; }
        }
      `}</style>
    </div>
  )
}
