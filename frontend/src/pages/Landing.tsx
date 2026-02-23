import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'

interface Props {
  onGetStarted: () => void
  onSignIn: () => void
}

const SUBJECTS = [
  { icon: '\u{1F522}', name: 'Mathematics', topics: ['Number System', 'Addition', 'Subtraction', 'Multiplication', 'Fractions', 'Geometry', 'Time', 'Money', 'Measurement', 'Data Handling'] },
  { icon: '\u{1F4D6}', name: 'English', topics: ['Grammar', 'Comprehension', 'Vocabulary', 'Writing', 'Poems', 'Stories'] },
  { icon: '\u{1F33F}', name: 'EVS / Science', topics: ['Plants', 'Animals', 'Human Body', 'Food', 'Shelter', 'Water', 'Weather', 'Solar System'] },
  { icon: '\u{1F4DD}', name: 'Hindi', topics: ['\u0935\u0930\u094D\u0923\u092E\u093E\u0932\u093E', '\u092E\u093E\u0924\u094D\u0930\u093E\u090F\u0901', '\u0936\u092C\u094D\u0926 \u0930\u091A\u0928\u093E', '\u0935\u093E\u0915\u094D\u092F \u0930\u091A\u0928\u093E', '\u0935\u093F\u0932\u094B\u092E \u0936\u092C\u094D\u0926', '\u0915\u0939\u093E\u0928\u0940 \u0932\u0947\u0916\u0928'] },
  { icon: '\u{1F4BB}', name: 'Computer', topics: ['Parts of Computer', 'MS Paint', 'Scratch', 'Internet Safety'] },
  { icon: '\u{1F30D}', name: 'GK', topics: ['National Symbols', 'Landmarks', 'Festivals', 'Sports', 'Solar System'] },
  { icon: '\u{1F91D}', name: 'Moral Science', topics: ['Good Habits', 'Honesty', 'Kindness', 'Sharing'] },
  { icon: '\u{1F3C3}', name: 'Health & PE', topics: ['Hygiene', 'Nutrition', 'Yoga', 'First Aid', 'Sports'] },
]

const COMPARISON_FEATURES = [
  { feature: 'CBSE-aligned questions', skolar: true, free: false },
  { feature: 'Three-tier difficulty', skolar: true, free: false },
  { feature: 'Mastery tracking', skolar: true, free: false },
  { feature: 'Indian context word problems', skolar: true, free: false },
  { feature: 'Hints on hard questions', skolar: true, free: false },
  { feature: 'Parent insights after grading', skolar: true, free: false },
  { feature: 'Print-ready PDF with answer key', skolar: true, free: 'partial' as const },
  { feature: 'No repeated questions', skolar: true, free: false },
]

export default function LandingPage({ onGetStarted, onSignIn }: Props) {
  const [scrolled, setScrolled] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [activeSubject, setActiveSubject] = useState(0)

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 40)
    window.addEventListener('scroll', handleScroll, { passive: true })
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  const scrollTo = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
    setMobileOpen(false)
  }

  return (
    <div style={{ fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif", color: '#1E293B', overflowX: 'hidden' as const }}>

      {/* ── 1. STICKY NAV ── */}
      <header
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          zIndex: 50,
          transition: 'all 0.3s ease',
          backgroundColor: scrolled ? 'rgba(250,247,242,0.97)' : '#FAF7F2',
          backdropFilter: scrolled ? 'blur(12px)' : 'none',
          borderBottom: scrolled ? '1px solid #E5E0D8' : '1px solid transparent',
          boxShadow: scrolled ? '0 1px 16px rgba(0,0,0,0.06)' : 'none',
        }}
      >
        <div style={{ maxWidth: 1200, margin: '0 auto', padding: '0 24px', height: 64, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontFamily: "'DM Serif Display', Georgia, serif", fontSize: 24, fontWeight: 400, color: '#1B4332', letterSpacing: '-0.01em', cursor: 'pointer' }} onClick={() => scrollTo('hero')}>
            Skolar
          </span>

          {/* Desktop links */}
          <nav style={{ display: 'flex', alignItems: 'center', gap: 8 }} className="sk-nav-desktop">
            <button onClick={() => scrollTo('how')} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 14, color: '#64748B', padding: '8px 14px', borderRadius: 8, fontFamily: "'Plus Jakarta Sans', sans-serif" }}>How it works</button>
            <button onClick={() => scrollTo('subjects')} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 14, color: '#64748B', padding: '8px 14px', borderRadius: 8, fontFamily: "'Plus Jakarta Sans', sans-serif" }}>Subjects</button>
            <button onClick={() => scrollTo('pricing')} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 14, color: '#64748B', padding: '8px 14px', borderRadius: 8, fontFamily: "'Plus Jakarta Sans', sans-serif" }}>Pricing</button>
            <button onClick={onSignIn} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 14, color: '#1E293B', fontWeight: 500, padding: '8px 14px', borderRadius: 8, fontFamily: "'Plus Jakarta Sans', sans-serif" }}>Sign in</button>
            <Button size="sm" onClick={onGetStarted} style={{ backgroundColor: '#1B4332', color: '#fff', borderRadius: 8, fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
              Start free
            </Button>
          </nav>

          {/* Mobile hamburger */}
          <button
            className="sk-hamburger"
            onClick={() => setMobileOpen(!mobileOpen)}
            aria-label="Menu"
            style={{ display: 'none', flexDirection: 'column', gap: 5, background: 'none', border: 'none', cursor: 'pointer', padding: 8 }}
          >
            <span style={{ display: 'block', width: 22, height: 2, background: '#1E293B', borderRadius: 2 }} />
            <span style={{ display: 'block', width: 22, height: 2, background: '#1E293B', borderRadius: 2 }} />
            <span style={{ display: 'block', width: 16, height: 2, background: '#1E293B', borderRadius: 2 }} />
          </button>
        </div>

        {/* Mobile menu */}
        {mobileOpen && (
          <div style={{ background: '#FAF7F2', borderTop: '1px solid #E5E0D8', padding: '12px 24px 20px', display: 'flex', flexDirection: 'column', gap: 4 }}>
            <button onClick={() => scrollTo('how')} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 16, color: '#1E293B', padding: '10px 0', textAlign: 'left', fontFamily: "'Plus Jakarta Sans', sans-serif" }}>How it works</button>
            <button onClick={() => scrollTo('subjects')} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 16, color: '#1E293B', padding: '10px 0', textAlign: 'left', fontFamily: "'Plus Jakarta Sans', sans-serif" }}>Subjects</button>
            <button onClick={() => scrollTo('pricing')} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 16, color: '#1E293B', padding: '10px 0', textAlign: 'left', fontFamily: "'Plus Jakarta Sans', sans-serif" }}>Pricing</button>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 12 }}>
              <button onClick={onSignIn} style={{ background: 'none', border: '1px solid #1B4332', cursor: 'pointer', fontSize: 14, color: '#1B4332', fontWeight: 600, padding: '10px 20px', borderRadius: 8, fontFamily: "'Plus Jakarta Sans', sans-serif" }}>Sign in</button>
              <button onClick={onGetStarted} style={{ background: '#1B4332', border: 'none', cursor: 'pointer', fontSize: 14, color: '#fff', fontWeight: 600, padding: '10px 20px', borderRadius: 8, fontFamily: "'Plus Jakarta Sans', sans-serif" }}>Start free</button>
            </div>
          </div>
        )}
      </header>

      {/* ── 2. HERO ── */}
      <section id="hero" style={{ backgroundColor: '#FAF7F2', paddingTop: 120, paddingBottom: 80 }}>
        <div style={{ maxWidth: 1200, margin: '0 auto', padding: '0 24px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 64, alignItems: 'center' }} className="sk-hero-grid">
          {/* Left */}
          <div>
            <h1 style={{ fontFamily: "'DM Serif Display', Georgia, serif", fontSize: 'clamp(36px, 5vw, 56px)', fontWeight: 400, lineHeight: 1.1, letterSpacing: '-0.02em', color: '#1B4332', margin: '0 0 20px' }}>
              Practice that knows<br />your syllabus.
            </h1>
            <p style={{ fontSize: 17, lineHeight: 1.7, color: '#64748B', maxWidth: 480, margin: '0 0 28px' }}>
              AI-powered CBSE worksheets for Classes 1&ndash;5. Pick a topic. Get 10 questions. Download the PDF.
            </p>
            <Button size="lg" onClick={onGetStarted} style={{ backgroundColor: '#1B4332', color: '#fff', padding: '14px 32px', fontSize: 16, borderRadius: 10, fontWeight: 600, fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
              Generate your first worksheet &mdash; free
            </Button>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 24 }}>
              {['198 topics', '9 subjects', 'Classes 1\u20135', 'No card needed'].map(chip => (
                <span key={chip} style={{ fontSize: 13, color: '#64748B', background: 'rgba(27,67,50,0.07)', border: '1px solid rgba(27,67,50,0.12)', padding: '5px 14px', borderRadius: 100 }}>
                  {chip}
                </span>
              ))}
            </div>
          </div>

          {/* Right — fanned worksheet cards */}
          <div style={{ position: 'relative', height: 380, display: 'flex', alignItems: 'center', justifyContent: 'center' }} className="sk-hero-right">
            {[
              { topic: 'Animals Around Us', cls: 'Class 1', subj: 'EVS', rotate: -6, offset: 0, bg: '#E8F5E9' },
              { topic: 'Addition & Subtraction', cls: 'Class 4', subj: 'Maths', rotate: -2, offset: 20, bg: '#FFF8E1' },
              { topic: 'Summary Writing', cls: 'Class 5', subj: 'English', rotate: 2, offset: 40, bg: '#E3F2FD' },
              { topic: '\u0936\u092C\u094D\u0926 \u0930\u091A\u0928\u093E', cls: 'Class 3', subj: 'Hindi', rotate: 6, offset: 60, bg: '#FFF3E0' },
            ].map((card, i) => (
              <div
                key={i}
                style={{
                  position: 'absolute',
                  width: 220,
                  background: '#fff',
                  border: '1px solid #E5E0D8',
                  borderRadius: 12,
                  padding: '20px 18px',
                  boxShadow: '0 4px 20px rgba(0,0,0,0.08)',
                  transform: `rotate(${card.rotate}deg) translateY(${card.offset}px)`,
                  zIndex: 4 - i,
                  transition: 'transform 0.3s ease',
                }}
              >
                <div style={{ width: 40, height: 6, borderRadius: 3, background: card.bg, marginBottom: 12 }} />
                <p style={{ fontFamily: "'DM Serif Display', Georgia, serif", fontSize: 15, fontWeight: 400, color: '#1E293B', margin: '0 0 6px', lineHeight: 1.3 }}>{card.topic}</p>
                <p style={{ fontSize: 12, color: '#94A3B8', margin: 0 }}>{card.cls} &middot; {card.subj}</p>
                <div style={{ display: 'flex', gap: 4, marginTop: 14 }}>
                  {[1, 2, 3, 4, 5].map(n => (
                    <div key={n} style={{ flex: 1, height: 3, borderRadius: 2, background: '#E5E0D8' }} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── 3. STATS BAR ── */}
      <section style={{ backgroundColor: '#1B4332', padding: '24px 24px' }}>
        <div style={{ maxWidth: 1000, margin: '0 auto', display: 'flex', justifyContent: 'center', gap: 48, flexWrap: 'wrap' }}>
          {[
            { n: '198', l: 'Topics' },
            { n: '9', l: 'Subjects' },
            { n: '5', l: 'Classes' },
            { n: '6', l: 'Question Types' },
            { n: '220', l: 'Images' },
          ].map(s => (
            <div key={s.l} style={{ textAlign: 'center' }}>
              <div style={{ fontFamily: "'DM Serif Display', Georgia, serif", fontSize: 28, fontWeight: 400, color: '#fff', lineHeight: 1 }}>{s.n}</div>
              <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'rgba(255,255,255,0.6)', fontWeight: 600, marginTop: 4 }}>{s.l}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── 4. HOW IT WORKS ── */}
      <section id="how" style={{ backgroundColor: '#FAF7F2', padding: '80px 24px' }}>
        <div style={{ maxWidth: 900, margin: '0 auto', textAlign: 'center' }}>
          <p style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#D97706', marginBottom: 10 }}>How it works</p>
          <h2 style={{ fontFamily: "'DM Serif Display', Georgia, serif", fontSize: 'clamp(28px, 4vw, 40px)', fontWeight: 400, color: '#1E293B', margin: '0 0 48px' }}>
            Three steps. Thirty seconds.
          </h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 32 }} className="sk-3col">
            {[
              { step: '01', title: 'Pick a topic', desc: 'Choose from 198 CBSE-aligned topics across 9 subjects for Classes 1\u20135.', icon: '\u{1F4DA}' },
              { step: '02', title: 'AI generates 10 questions', desc: 'Three difficulty tiers \u2014 Foundation (\u2605), Application (\u2605\u2605), Stretch (\u2605\u2605\u2605) \u2014 with Indian context.', icon: '\u2728' },
              { step: '03', title: 'Download the PDF', desc: 'Print-ready worksheet with answer key. No formatting, no fuss.', icon: '\u{1F4C4}' },
            ].map(item => (
              <div key={item.step} style={{ background: '#fff', border: '1px solid #E5E0D8', borderRadius: 14, padding: '32px 24px', textAlign: 'left' }}>
                <div style={{ fontSize: 32, marginBottom: 16 }}>{item.icon}</div>
                <div style={{ fontSize: 12, fontWeight: 700, color: '#D97706', marginBottom: 6 }}>STEP {item.step}</div>
                <h3 style={{ fontFamily: "'DM Serif Display', Georgia, serif", fontSize: 20, fontWeight: 400, color: '#1E293B', margin: '0 0 8px' }}>{item.title}</h3>
                <p style={{ fontSize: 14, lineHeight: 1.7, color: '#64748B', margin: 0 }}>{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── 5. WHAT MAKES SKOLAR DIFFERENT ── */}
      <section style={{ backgroundColor: '#fff', padding: '80px 24px' }}>
        <div style={{ maxWidth: 900, margin: '0 auto', textAlign: 'center' }}>
          <p style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#D97706', marginBottom: 10 }}>Why Skolar</p>
          <h2 style={{ fontFamily: "'DM Serif Display', Georgia, serif", fontSize: 'clamp(28px, 4vw, 40px)', fontWeight: 400, color: '#1E293B', margin: '0 0 48px' }}>
            What makes Skolar different
          </h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 24 }} className="sk-2col">
            {[
              { title: 'Three-Tier Difficulty', desc: 'Every worksheet has Foundation, Application, and Stretch questions. Builds confidence first, then pushes boundaries.', icon: '\u{1F3AF}' },
              { title: 'Indian Context', desc: 'Priya at the mela. Rahul\u2019s cricket runs. Diwali lamps. Word problems your child can picture immediately.', icon: '\u{1F1EE}\u{1F1F3}' },
              { title: 'Hints That Teach', desc: 'Stretch questions include collapsible hints. Children attempt first, then get scaffolding \u2014 not answers.', icon: '\u{1F4A1}' },
              { title: 'Complete Answer Key', desc: 'Every worksheet comes with a separate answer key page. Verify work instantly. No guessing.', icon: '\u2705' },
            ].map(card => (
              <div key={card.title} style={{ background: '#FAF7F2', border: '1px solid #E5E0D8', borderRadius: 14, padding: '28px 24px', textAlign: 'left' }}>
                <div style={{ fontSize: 28, marginBottom: 12 }}>{card.icon}</div>
                <h3 style={{ fontFamily: "'DM Serif Display', Georgia, serif", fontSize: 18, fontWeight: 400, color: '#1E293B', margin: '0 0 8px' }}>{card.title}</h3>
                <p style={{ fontSize: 14, lineHeight: 1.7, color: '#64748B', margin: 0 }}>{card.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── 6. SUBJECT COVERAGE ── */}
      <section id="subjects" style={{ backgroundColor: '#FAF7F2', padding: '80px 24px' }}>
        <div style={{ maxWidth: 1000, margin: '0 auto' }}>
          <div style={{ textAlign: 'center', marginBottom: 36 }}>
            <p style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#D97706', marginBottom: 10 }}>Subject Coverage</p>
            <h2 style={{ fontFamily: "'DM Serif Display', Georgia, serif", fontSize: 'clamp(28px, 4vw, 40px)', fontWeight: 400, color: '#1E293B', margin: 0 }}>
              Nine subjects. 198 topics. All CBSE.
            </h2>
          </div>

          {/* Subject tabs */}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'center', marginBottom: 28 }}>
            {SUBJECTS.map((s, i) => (
              <button
                key={s.name}
                onClick={() => setActiveSubject(i)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 7,
                  background: activeSubject === i ? '#1B4332' : '#fff',
                  color: activeSubject === i ? '#fff' : '#64748B',
                  border: `1px solid ${activeSubject === i ? '#1B4332' : '#E5E0D8'}`,
                  borderRadius: 100,
                  padding: '8px 18px',
                  fontSize: 13.5,
                  fontWeight: 600,
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                  fontFamily: "'Plus Jakarta Sans', sans-serif",
                }}
              >
                <span style={{ fontSize: 16 }}>{s.icon}</span>
                {s.name}
              </button>
            ))}
          </div>

          {/* Topic pills */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'center', minHeight: 60 }}>
            {SUBJECTS[activeSubject].topics.map(topic => (
              <span
                key={topic}
                style={{
                  background: '#fff',
                  border: '1px solid #E5E0D8',
                  borderRadius: 100,
                  padding: '6px 16px',
                  fontSize: 13,
                  color: '#1E293B',
                  cursor: 'default',
                }}
              >
                {topic}
              </span>
            ))}
          </div>
          <p style={{ textAlign: 'center', fontSize: 13, color: '#94A3B8', marginTop: 16 }}>
            Topics shown for Classes 1&ndash;5 &middot; {SUBJECTS[activeSubject].name}
          </p>
        </div>
      </section>

      {/* ── 7. SAMPLE WORKSHEETS ── */}
      <section style={{ backgroundColor: '#fff', padding: '80px 24px' }}>
        <div style={{ maxWidth: 1000, margin: '0 auto' }}>
          <div style={{ textAlign: 'center', marginBottom: 48 }}>
            <p style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#D97706', marginBottom: 10 }}>Sample Questions</p>
            <h2 style={{ fontFamily: "'DM Serif Display', Georgia, serif", fontSize: 'clamp(28px, 4vw, 40px)', fontWeight: 400, color: '#1E293B', margin: 0 }}>
              See what your child gets
            </h2>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 20 }} className="sk-2col">
            {[
              {
                subj: 'EVS',
                cls: 'Class 1',
                q: 'Myra saw an animal that lives in a den and has a majestic mane. Which animal is it?',
                options: '(A) Tiger \u00a0 (B) Lion \u00a0 (C) Bear \u00a0 (D) Wolf',
                accent: '#16A34A',
              },
              {
                subj: 'Maths',
                cls: 'Class 4',
                q: 'Zara had \u20B950,000. She spent \u20B918,500 on a bicycle. How much money does she have left?',
                options: 'Answer: \u20B9 ________',
                accent: '#D97706',
              },
              {
                subj: 'English',
                cls: 'Class 5',
                q: 'Ritika read a story about a little bird that learned to fly. What is the main idea of the story?',
                options: '(A) Birds are colourful \u00a0 (B) Never give up \u00a0 (C) Fly south in winter \u00a0 (D) Eat seeds',
                accent: '#2563EB',
              },
              {
                subj: 'Hindi',
                cls: 'Class 3',
                q: '\u0926\u093F\u090F \u0917\u090F \u0905\u0915\u094D\u0937\u0930\u094B\u0902 \u0915\u094B \u0938\u0939\u0940 \u0915\u094D\u0930\u092E \u092E\u0947\u0902 \u0930\u0916\u0915\u0930 \u0936\u092C\u094D\u0926 \u092C\u0928\u093E\u0907\u090F: \u2018\u0932\u2019, \u2018\u092E\u2019, \u2018\u0915\u2019',
                options: '(\u0905) \u0932\u092E\u0915 \u00a0 (\u092C) \u0915\u092E\u0932 \u00a0 (\u0938) \u092E\u0932\u0915 \u00a0 (\u0926) \u0915\u0932\u092E',
                accent: '#DC2626',
              },
            ].map(sample => (
              <div key={sample.subj} style={{ background: '#FAF7F2', border: '1px solid #E5E0D8', borderRadius: 14, padding: '24px', borderLeft: `4px solid ${sample.accent}` }}>
                <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
                  <span style={{ fontSize: 11, fontWeight: 700, color: sample.accent, background: `${sample.accent}15`, padding: '3px 10px', borderRadius: 100, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{sample.subj}</span>
                  <span style={{ fontSize: 11, fontWeight: 600, color: '#94A3B8', padding: '3px 0' }}>{sample.cls}</span>
                </div>
                <p style={{ fontSize: 14, lineHeight: 1.7, color: '#1E293B', margin: '0 0 8px' }}>{sample.q}</p>
                <p style={{ fontSize: 13, color: '#64748B', margin: '0 0 16px', fontFamily: "'Plus Jakarta Sans', monospace" }}>{sample.options}</p>
                <button
                  onClick={onGetStarted}
                  style={{
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    fontSize: 13,
                    fontWeight: 600,
                    color: '#1B4332',
                    padding: 0,
                    fontFamily: "'Plus Jakarta Sans', sans-serif",
                  }}
                >
                  Try this topic free &rarr;
                </button>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── 8. COMPARISON TABLE ── */}
      <section style={{ backgroundColor: '#FAF7F2', padding: '80px 24px' }}>
        <div style={{ maxWidth: 700, margin: '0 auto', textAlign: 'center' }}>
          <p style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#D97706', marginBottom: 10 }}>Comparison</p>
          <h2 style={{ fontFamily: "'DM Serif Display', Georgia, serif", fontSize: 'clamp(28px, 4vw, 40px)', fontWeight: 400, color: '#1E293B', margin: '0 0 36px' }}>
            Skolar vs Free Tools
          </h2>
          <div style={{ overflow: 'auto', borderRadius: 14, border: '1px solid #E5E0D8' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14, background: '#fff' }}>
              <thead>
                <tr>
                  <th style={{ padding: '14px 18px', textAlign: 'left', fontSize: 11.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#94A3B8', borderBottom: '2px solid #E5E0D8' }}>Feature</th>
                  <th style={{ padding: '14px 18px', textAlign: 'center', fontSize: 11.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#1B4332', borderBottom: '2px solid #E5E0D8' }}>Skolar</th>
                  <th style={{ padding: '14px 18px', textAlign: 'center', fontSize: 11.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#94A3B8', borderBottom: '2px solid #E5E0D8' }}>Free Tools</th>
                </tr>
              </thead>
              <tbody>
                {COMPARISON_FEATURES.map((r, i) => (
                  <tr key={i}>
                    <td style={{ padding: '13px 18px', borderBottom: '1px solid #F0EBE3', color: '#1E293B' }}>{r.feature}</td>
                    <td style={{ padding: '13px 18px', borderBottom: '1px solid #F0EBE3', textAlign: 'center', background: 'rgba(27,67,50,0.04)' }}>
                      <span style={{ color: '#1B4332', fontWeight: 700, fontSize: 16 }}>{'\u2713'}</span>
                    </td>
                    <td style={{ padding: '13px 18px', borderBottom: '1px solid #F0EBE3', textAlign: 'center' }}>
                      {r.free === true
                        ? <span style={{ color: '#1B4332', fontWeight: 700, fontSize: 16 }}>{'\u2713'}</span>
                        : r.free === 'partial'
                        ? <span style={{ color: '#D97706', fontWeight: 700, fontSize: 16 }}>~</span>
                        : <span style={{ color: '#EF4444', fontSize: 16 }}>{'\u2717'}</span>
                      }
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* ── 9. PRICING ── */}
      <section id="pricing" style={{ backgroundColor: '#fff', padding: '80px 24px' }}>
        <div style={{ maxWidth: 960, margin: '0 auto', textAlign: 'center' }}>
          <p style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#D97706', marginBottom: 10 }}>Pricing</p>
          <h2 style={{ fontFamily: "'DM Serif Display', Georgia, serif", fontSize: 'clamp(28px, 4vw, 40px)', fontWeight: 400, color: '#1E293B', margin: '0 0 48px' }}>
            Start free. Upgrade when ready.
          </h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 20, alignItems: 'start' }} className="sk-3col">
            {/* Free */}
            <div style={{ background: '#FAF7F2', border: '1px solid #E5E0D8', borderRadius: 16, padding: '32px 24px', textAlign: 'left' }}>
              <div style={{ fontSize: 11.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#94A3B8', marginBottom: 8 }}>Free</div>
              <div style={{ fontFamily: "'DM Serif Display', Georgia, serif", fontSize: 40, fontWeight: 400, color: '#1E293B', lineHeight: 1, marginBottom: 4 }}>
                {'\u20B9'}0<span style={{ fontSize: 15, fontWeight: 400, color: '#94A3B8' }}> /month</span>
              </div>
              <p style={{ fontSize: 13, color: '#94A3B8', marginBottom: 24, marginTop: 4 }}>5 worksheets per month</p>
              <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 24px', display: 'flex', flexDirection: 'column', gap: 10 }}>
                {['All 9 subjects', 'PDF download', '10 questions per sheet', 'Answer key included'].map(f => (
                  <li key={f} style={{ fontSize: 13.5, color: '#1E293B', display: 'flex', gap: 8 }}>
                    <span style={{ color: '#1B4332', fontWeight: 700 }}>{'\u2713'}</span> {f}
                  </li>
                ))}
              </ul>
              <button onClick={onGetStarted} style={{ width: '100%', background: 'transparent', border: '1.5px solid #1B4332', color: '#1B4332', cursor: 'pointer', fontSize: 14, fontWeight: 600, padding: '12px 20px', borderRadius: 10, fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
                Get started free
              </button>
            </div>

            {/* Scholar */}
            <div style={{ background: '#1B4332', border: '1px solid #1B4332', borderRadius: 16, padding: '32px 24px', textAlign: 'left', position: 'relative' }}>
              <div style={{ position: 'absolute', top: -13, right: 20, background: '#D97706', color: '#fff', fontSize: 10.5, fontWeight: 700, padding: '4px 12px', borderRadius: 100, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Most Popular</div>
              <div style={{ fontSize: 11.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'rgba(255,255,255,0.6)', marginBottom: 8 }}>Scholar</div>
              <div style={{ fontFamily: "'DM Serif Display', Georgia, serif", fontSize: 40, fontWeight: 400, color: '#fff', lineHeight: 1, marginBottom: 4 }}>
                {'\u20B9'}199<span style={{ fontSize: 15, fontWeight: 400, color: 'rgba(255,255,255,0.6)' }}> /month</span>
              </div>
              <p style={{ fontSize: 13, color: 'rgba(255,255,255,0.6)', marginBottom: 24, marginTop: 4 }}>Unlimited worksheets</p>
              <p style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)', margin: '-18px 0 24px' }}>AED 29/mo</p>
              <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 24px', display: 'flex', flexDirection: 'column', gap: 10 }}>
                {['Unlimited worksheets', 'Mastery tracking', 'Bulk generation', 'Parent insights', 'Priority support'].map(f => (
                  <li key={f} style={{ fontSize: 13.5, color: 'rgba(255,255,255,0.88)', display: 'flex', gap: 8 }}>
                    <span style={{ color: '#D97706', fontWeight: 700 }}>{'\u2713'}</span> {f}
                  </li>
                ))}
              </ul>
              <button onClick={onGetStarted} style={{ width: '100%', background: '#fff', border: 'none', color: '#1B4332', cursor: 'pointer', fontSize: 14, fontWeight: 600, padding: '12px 20px', borderRadius: 10, fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
                Start Scholar plan
              </button>
            </div>

            {/* Annual */}
            <div style={{ background: '#FAF7F2', border: '1px solid #E5E0D8', borderRadius: 16, padding: '32px 24px', textAlign: 'left' }}>
              <div style={{ fontSize: 11.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#94A3B8', marginBottom: 8 }}>Annual</div>
              <div style={{ fontFamily: "'DM Serif Display', Georgia, serif", fontSize: 40, fontWeight: 400, color: '#1E293B', lineHeight: 1, marginBottom: 4 }}>
                {'\u20B9'}1,499<span style={{ fontSize: 15, fontWeight: 400, color: '#94A3B8' }}> /year</span>
              </div>
              <p style={{ fontSize: 13, color: '#16A34A', fontWeight: 600, marginBottom: 24, marginTop: 4 }}>Save 37%</p>
              <p style={{ fontSize: 11, color: '#94A3B8', margin: '-18px 0 24px' }}>AED 229/yr</p>
              <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 24px', display: 'flex', flexDirection: 'column', gap: 10 }}>
                {['Everything in Scholar', '12 months access', 'Best value for families', 'Lock in price forever'].map(f => (
                  <li key={f} style={{ fontSize: 13.5, color: '#1E293B', display: 'flex', gap: 8 }}>
                    <span style={{ color: '#1B4332', fontWeight: 700 }}>{'\u2713'}</span> {f}
                  </li>
                ))}
              </ul>
              <button onClick={onGetStarted} style={{ width: '100%', background: '#D97706', border: 'none', color: '#fff', cursor: 'pointer', fontSize: 14, fontWeight: 600, padding: '12px 20px', borderRadius: 10, fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
                Start annual plan
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* ── 10. FOR PARENTS / FOR TEACHERS ── */}
      <section style={{ backgroundColor: '#FAF7F2', padding: '80px 24px' }}>
        <div style={{ maxWidth: 900, margin: '0 auto', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }} className="sk-2col">
          {/* Parents */}
          <div style={{ background: '#fff', border: '1px solid #E5E0D8', borderRadius: 16, padding: '36px 28px', borderTop: '4px solid #1B4332' }}>
            <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#94A3B8', marginBottom: 14 }}>For Parents</div>
            <h3 style={{ fontFamily: "'DM Serif Display', Georgia, serif", fontSize: 22, fontWeight: 400, color: '#1E293B', margin: '0 0 20px', lineHeight: 1.3 }}>Know exactly where your child stands.</h3>
            <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 24px', display: 'flex', flexDirection: 'column', gap: 10 }}>
              {[
                'Generate a focused worksheet in 30 seconds',
                'Choose the right topic for tonight\u2019s practice',
                'See mastery progress improve over time',
                'Understand skill gaps \u2014 no tutoring degree needed',
                'Print-ready A4 PDF, no formatting hassle',
              ].map(item => (
                <li key={item} style={{ fontSize: 14, color: '#64748B', lineHeight: 1.5, paddingLeft: 20, position: 'relative' }}>
                  <span style={{ position: 'absolute', left: 0, color: '#1B4332', fontWeight: 700 }}>{'\u2713'}</span>
                  {item}
                </li>
              ))}
            </ul>
            <button onClick={onGetStarted} style={{ background: '#1B4332', border: 'none', color: '#fff', cursor: 'pointer', fontSize: 14, fontWeight: 600, padding: '10px 24px', borderRadius: 8, fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
              Start as Parent &rarr;
            </button>
          </div>

          {/* Teachers */}
          <div style={{ background: '#fff', border: '1px solid #E5E0D8', borderRadius: 16, padding: '36px 28px', borderTop: '4px solid #D97706' }}>
            <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#94A3B8', marginBottom: 14 }}>For Teachers</div>
            <h3 style={{ fontFamily: "'DM Serif Display', Georgia, serif", fontSize: 22, fontWeight: 400, color: '#1E293B', margin: '0 0 20px', lineHeight: 1.3 }}>Differentiated practice, at scale.</h3>
            <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 24px', display: 'flex', flexDirection: 'column', gap: 10 }}>
              {[
                'Generate topic-wise worksheets for the whole class',
                'Bulk generate across 5 topics in one click',
                'Share instantly via WhatsApp or print batches',
                'Track class-wide mastery and skill gaps',
                'CBSE chapter progression, already mapped',
              ].map(item => (
                <li key={item} style={{ fontSize: 14, color: '#64748B', lineHeight: 1.5, paddingLeft: 20, position: 'relative' }}>
                  <span style={{ position: 'absolute', left: 0, color: '#1B4332', fontWeight: 700 }}>{'\u2713'}</span>
                  {item}
                </li>
              ))}
            </ul>
            <button onClick={onGetStarted} style={{ background: 'transparent', border: '1.5px solid #1B4332', color: '#1B4332', cursor: 'pointer', fontSize: 14, fontWeight: 600, padding: '10px 24px', borderRadius: 8, fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
              Start as Teacher &rarr;
            </button>
          </div>
        </div>
      </section>

      {/* ── 11. CTA ── */}
      <section style={{ backgroundColor: '#1B4332', padding: '80px 24px', textAlign: 'center' }}>
        <div style={{ maxWidth: 560, margin: '0 auto' }}>
          <h2 style={{ fontFamily: "'DM Serif Display', Georgia, serif", fontSize: 'clamp(28px, 4.5vw, 44px)', fontWeight: 400, color: '#fff', margin: '0 0 16px', lineHeight: 1.15 }}>
            Generate your first worksheet in 30 seconds
          </h2>
          <p style={{ fontSize: 16, color: 'rgba(255,255,255,0.65)', margin: '0 0 32px', lineHeight: 1.7 }}>
            No setup. No credit card. Pick a topic and go.
          </p>
          <button onClick={onGetStarted} style={{ background: '#D97706', border: 'none', color: '#fff', cursor: 'pointer', fontSize: 16, fontWeight: 600, padding: '16px 40px', borderRadius: 12, fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
            Create free worksheet &rarr;
          </button>
          <p style={{ fontSize: 13, color: 'rgba(255,255,255,0.4)', marginTop: 20 }}>
            hello@skolar.in
          </p>
        </div>
      </section>

      {/* ── 12. FOOTER ── */}
      <footer style={{ backgroundColor: '#0F2419', padding: '24px', textAlign: 'center' }}>
        <p style={{ fontFamily: "'DM Serif Display', Georgia, serif", fontSize: 18, color: 'rgba(255,255,255,0.7)', margin: '0 0 8px' }}>Skolar</p>
        <p style={{ fontSize: 12, color: 'rgba(255,255,255,0.35)', margin: 0 }}>
          skolar.in &middot; &copy; 2025
        </p>
      </footer>

      {/* ── RESPONSIVE STYLES ── */}
      <style>{`
        @media (max-width: 1024px) {
          .sk-nav-desktop { display: none !important; }
          .sk-hamburger { display: flex !important; }
          .sk-hero-grid { grid-template-columns: 1fr !important; }
          .sk-hero-right { display: none !important; }
        }
        @media (min-width: 1025px) {
          .sk-hamburger { display: none !important; }
        }
        @media (max-width: 768px) {
          .sk-3col { grid-template-columns: 1fr !important; }
          .sk-2col { grid-template-columns: 1fr !important; }
        }
        @media (max-width: 480px) {
          .sk-3col { grid-template-columns: 1fr !important; }
        }
      `}</style>
    </div>
  )
}
