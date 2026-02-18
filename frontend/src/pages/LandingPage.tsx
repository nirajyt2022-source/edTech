import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'

interface Props {
  onGetStarted: () => void
  onSignIn: () => void
}

const STATS = [
  { value: '196', label: 'Topics covered' },
  { value: '9', label: 'Subjects available' },
  { value: 'Class 1–5', label: 'CBSE curriculum' },
  { value: '<30s', label: 'To generate' },
]

const SUBJECTS = [
  { icon: '\u{1F522}', name: 'Mathematics', desc: 'Addition, fractions, geometry' },
  { icon: '\u{1F4D6}', name: 'English', desc: 'Grammar, comprehension, writing' },
  { icon: '\u{1F33F}', name: 'EVS / Science', desc: 'Plants, human body, solar system' },
  { icon: '\u{1F4DD}', name: 'Hindi', desc: 'Varnamala, matras, kahani lekhan' },
  { icon: '\u{1F4BB}', name: 'Computer', desc: 'MS Paint, Scratch, internet safety' },
  { icon: '\u{1F30D}', name: 'GK & More', desc: 'Moral science, health, general knowledge' },
]

const FEATURES = [
  {
    icon: '\u{1F3AF}',
    title: "Exactly your child's chapter",
    desc: 'Every worksheet matches the specific topic from CBSE/NCERT curriculum \u2014 not generic practice.',
  },
  {
    icon: '\u{1F4CA}',
    title: 'See what needs work',
    desc: 'After each worksheet, accuracy is tracked per topic. Know exactly where to focus next.',
  },
  {
    icon: '\u2705',
    title: 'Verified answers',
    desc: 'Maths answers are computationally verified. No wrong answers shipped to your child.',
  },
  {
    icon: '\u{1F5A8}\uFE0F',
    title: 'Print-ready in seconds',
    desc: 'Download clean PDF. No ads, no clutter. Works offline once printed.',
  },
]

const TESTIMONIALS = [
  {
    quote: "My daughter\u2019s Maths teacher noticed improvement in just 3 weeks. The worksheets match exactly what she\u2019s learning in class.",
    name: 'Priya S.',
    role: 'Parent, Class 3',
    location: 'Mumbai',
    initial: 'P',
  },
  {
    quote: 'I use this to generate practice worksheets for my entire class. Saves me 2 hours every week.',
    name: 'Ms. Kavitha R.',
    role: 'Class Teacher, Grade 4',
    location: 'Bengaluru',
    initial: 'K',
  },
  {
    quote: 'Finally a tool that works for UAE CBSE schools. The content is age-appropriate and my son actually enjoys doing these.',
    name: 'Arjun M.',
    role: 'Parent, Class 2',
    location: 'Dubai',
    initial: 'A',
  },
]

const SAMPLE_QUESTIONS = [
  { tag: 'Recognition', cls: 'bg-primary/10 text-primary', q: 'Which of these equals 12?\n(a) 5+6  \u00a0(b) 7+5  \u00a0(c) 4+7  \u00a0(d) 6+5' },
  { tag: 'Application', cls: 'bg-accent/10 text-accent', q: 'Priya had 8 pencils. She got 6 more. How many does she have now? ___' },
  { tag: 'Error Detection', cls: 'bg-destructive/10 text-destructive', q: 'Ravi wrote: 9 + 4 = 14. Find his mistake.' },
  { tag: 'Thinking', cls: 'bg-success/10 text-success', q: 'What comes next?\u2003 3, 6, 9, 12, ___' },
]

export default function LandingPage({ onGetStarted, onSignIn }: Props) {
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 60)
    window.addEventListener('scroll', handleScroll, { passive: true })
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  return (
    <div className="min-h-screen bg-white">

      {/* Sticky Nav */}
      <header
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          zIndex: 50,
          transition: 'background-color 0.3s ease, box-shadow 0.3s ease, border-color 0.3s ease',
          backgroundColor: scrolled ? 'rgba(255,255,255,0.96)' : 'transparent',
          backdropFilter: scrolled ? 'blur(12px)' : 'none',
          WebkitBackdropFilter: scrolled ? 'blur(12px)' : 'none',
          borderBottom: scrolled ? '1px solid hsl(214 32% 88%)' : '1px solid transparent',
          boxShadow: scrolled ? '0 1px 20px rgba(0,0,0,0.07)' : 'none',
        }}
      >
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
              <span className="text-primary-foreground text-sm font-bold">P</span>
            </div>
            <span className="text-lg font-semibold">
              <span style={{ color: scrolled ? 'hsl(222 47% 11%)' : 'white', transition: 'color 0.3s' }}>Practice</span>
              <span style={{ color: scrolled ? 'hsl(221 83% 53%)' : 'hsl(199 89% 72%)', transition: 'color 0.3s' }}>Craft</span>
            </span>
          </div>
          <div className="flex items-center gap-3">
            <span
              className="text-xs hidden sm:block"
              style={{ color: scrolled ? 'hsl(215 16% 47%)' : 'rgba(255,255,255,0.45)', transition: 'color 0.3s' }}
            >
              India &amp; UAE \u00b7 Classes 1\u20135 \u00b7 CBSE
            </span>
            <button
              onClick={onSignIn}
              className="text-sm font-medium px-3 py-1.5 rounded-lg transition-colors"
              style={{
                color: scrolled ? 'hsl(222 47% 11%)' : 'rgba(255,255,255,0.85)',
                backgroundColor: 'transparent',
              }}
              onMouseEnter={e => (e.currentTarget.style.backgroundColor = scrolled ? 'hsl(214 32% 94%)' : 'rgba(255,255,255,0.1)')}
              onMouseLeave={e => (e.currentTarget.style.backgroundColor = 'transparent')}
            >
              Sign in
            </button>
            <Button
              size="sm"
              onClick={onGetStarted}
              style={scrolled ? {} : { backgroundColor: 'white', color: 'hsl(221 83% 53%)' }}
            >
              Start free \u2192
            </Button>
          </div>
        </div>
      </header>

      {/* Hero — dark navy */}
      <section className="lp-hero relative overflow-hidden pt-20">
        <div className="lp-dot-grid" aria-hidden="true" />
        <div className="relative z-10 max-w-6xl mx-auto px-6 py-24 lg:py-36">
          <div className="grid lg:grid-cols-2 gap-16 items-center">

            {/* Left — headline + CTA */}
            <div className="animate-fade-in">
              <div className="lp-badge mb-8">
                <span style={{ color: '#60a5fa' }}>&#10003;</span>
                Aligned with CBSE/NCERT 2024 curriculum
              </div>
              <h1 className="lp-hero-h1 mb-6">
                Worksheets that know<br />
                <em>exactly</em> what&apos;s<br />
                being taught
              </h1>
              <p style={{ color: 'rgba(255,255,255,0.62)', fontSize: '1.0625rem', lineHeight: 1.75, maxWidth: '28rem', marginBottom: '2.5rem' }}>
                Generate topic-specific practice for Classes 1\u20135 in under 30 seconds.
                Track progress. See which topics need more work. For parents and teachers.
              </p>
              <div className="flex flex-col sm:flex-row gap-3">
                <Button size="lg" onClick={onGetStarted} className="px-8 text-base">
                  Create free worksheet \u2192
                </Button>
                <button
                  onClick={onSignIn}
                  className="px-8 py-3 text-base font-medium rounded-lg transition-colors"
                  style={{
                    border: '1px solid rgba(255,255,255,0.22)',
                    color: 'white',
                    backgroundColor: 'transparent',
                  }}
                  onMouseEnter={e => (e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.08)')}
                  onMouseLeave={e => (e.currentTarget.style.backgroundColor = 'transparent')}
                >
                  Sign in
                </button>
              </div>
              <p style={{ color: 'rgba(255,255,255,0.32)', fontSize: '0.75rem', marginTop: '1rem' }}>
                Free \u00b7 No credit card \u00b7 Works for India &amp; UAE schools
              </p>
            </div>

            {/* Right — floating worksheet preview */}
            <div className="animate-fade-in-delayed hidden lg:block">
              <div className="lp-preview-card">
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <p className="font-bold text-foreground text-sm">Addition up to 20 \u00b7 Class 1</p>
                    <p className="text-xs text-muted-foreground mt-0.5">Maths \u00b7 5 questions \u00b7 CBSE aligned \u00b7 Hard</p>
                  </div>
                  <div className="bg-primary/10 text-primary text-xs font-semibold px-2.5 py-1 rounded-lg">
                    5 Qs
                  </div>
                </div>
                <div>
                  {SAMPLE_QUESTIONS.map((q, i) => (
                    <div key={i} className={`flex gap-3 items-start py-3 ${i > 0 ? 'border-t border-border/50' : ''}`}>
                      <span className={`text-xs font-semibold px-2 py-0.5 rounded-md flex-shrink-0 whitespace-nowrap ${q.cls}`}>
                        {q.tag}
                      </span>
                      <p className="text-xs text-foreground leading-snug whitespace-pre-line">{q.q}</p>
                    </div>
                  ))}
                </div>
                <div className="mt-3 pt-3 border-t border-border/50 flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">+ 1 representation question</span>
                  <span className="text-xs text-primary font-medium">Answer key included \u2192</span>
                </div>
              </div>
            </div>

          </div>
        </div>
        <div className="lp-hero-fade" aria-hidden="true" />
      </section>

      {/* Stats strip */}
      <section className="bg-white border-b border-border">
        <div className="max-w-4xl mx-auto px-6 py-10">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-6 text-center">
            {STATS.map(s => (
              <div key={s.label}>
                <p className="lp-stats-number">{s.value}</p>
                <p className="text-sm text-muted-foreground mt-1.5">{s.label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Subjects */}
      <section className="py-16" style={{ backgroundColor: 'hsl(214 32% 97%)' }}>
        <div className="max-w-4xl mx-auto px-6">
          <div className="text-center mb-10">
            <h2 className="text-2xl font-bold text-foreground">Every subject. Every chapter.</h2>
            <p className="text-muted-foreground mt-2 text-sm">9 subjects \u00b7 Classes 1\u20135 \u00b7 196 topics covered</p>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 stagger-children">
            {SUBJECTS.map(s => (
              <div key={s.name} className="bg-card rounded-xl p-4 border border-border shadow-sm card-hover">
                <span className="text-2xl">{s.icon}</span>
                <p className="font-semibold text-foreground text-sm mt-2">{s.name}</p>
                <p className="text-xs text-muted-foreground mt-0.5">{s.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="bg-white py-16">
        <div className="max-w-4xl mx-auto px-6">
          <h2 className="text-2xl font-bold text-foreground text-center mb-12">
            Why parents and teachers trust PracticeCraft
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-8">
            {FEATURES.map(item => (
              <div key={item.title} className="flex gap-4">
                <div className="w-11 h-11 rounded-xl bg-primary/10 flex items-center justify-center flex-shrink-0">
                  <span className="text-xl">{item.icon}</span>
                </div>
                <div>
                  <p className="font-semibold text-foreground mb-1">{item.title}</p>
                  <p className="text-sm text-muted-foreground leading-relaxed">{item.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Testimonials */}
      <section className="py-16" style={{ backgroundColor: 'hsl(214 32% 97%)' }}>
        <div className="max-w-4xl mx-auto px-6">
          <h2 className="text-2xl font-bold text-foreground text-center mb-12">
            Trusted by parents and teachers
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 stagger-children">
            {TESTIMONIALS.map(t => (
              <div key={t.name} className="bg-card rounded-xl p-6 border border-border shadow-sm relative overflow-hidden">
                <div
                  aria-hidden="true"
                  style={{
                    position: 'absolute',
                    top: '0.25rem',
                    right: '0.875rem',
                    fontSize: '5.5rem',
                    lineHeight: 1,
                    color: 'hsl(221 83% 53%)',
                    opacity: 0.05,
                    fontFamily: "'DM Serif Display', Georgia, serif",
                    userSelect: 'none',
                    pointerEvents: 'none',
                  }}
                >
                  &ldquo;
                </div>
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-9 h-9 rounded-full bg-primary flex items-center justify-center flex-shrink-0">
                    <span className="text-primary-foreground text-sm font-bold">{t.initial}</span>
                  </div>
                  <div>
                    <p className="font-semibold text-foreground text-sm">{t.name}</p>
                    <p className="text-xs text-muted-foreground">{t.role} \u00b7 {t.location}</p>
                  </div>
                </div>
                <p className="text-sm text-foreground leading-relaxed">&ldquo;{t.quote}&rdquo;</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Final CTA — dark navy matching hero */}
      <section className="lp-cta-section py-20 text-center relative overflow-hidden">
        <div className="lp-dot-grid" aria-hidden="true" style={{ opacity: 0.35 }} />
        <div className="relative z-10 max-w-md mx-auto px-6">
          <h2
            style={{
              fontFamily: "'DM Serif Display', Georgia, serif",
              fontSize: 'clamp(1.875rem, 4vw, 2.5rem)',
              color: 'white',
              fontWeight: 400,
              lineHeight: 1.2,
              marginBottom: '1rem',
            }}
          >
            Start with one free worksheet
          </h2>
          <p style={{ color: 'rgba(255,255,255,0.62)', marginBottom: '2rem', lineHeight: 1.7, fontSize: '0.9375rem' }}>
            No setup. No credit card. Generate a worksheet for your child&apos;s topic right now.
          </p>
          <Button
            size="lg"
            onClick={onGetStarted}
            style={{ backgroundColor: 'white', color: 'hsl(221 83% 53%)', fontWeight: 600, padding: '0 2.5rem' }}
            className="text-base"
          >
            Create free worksheet \u2192
          </Button>
          <p style={{ color: 'rgba(255,255,255,0.32)', fontSize: '0.75rem', marginTop: '1rem' }}>
            India \u00b7 UAE \u00b7 CBSE \u00b7 Classes 1\u20135
          </p>
        </div>
      </section>

      {/* Footer */}
      <footer className="px-6 py-6 text-center bg-white border-t border-border">
        <p className="text-xs text-muted-foreground">
          PracticeCraft \u00b7 Aligned with NCERT and CBSE curriculum \u00b7 Classes 1\u20135 \u00b7 India &amp; UAE
        </p>
      </footer>

    </div>
  )
}
