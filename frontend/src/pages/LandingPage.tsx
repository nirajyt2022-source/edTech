import { Button } from '@/components/ui/button'

interface Props {
  onGetStarted: () => void
  onSignIn: () => void
}

const SAMPLE_SUBJECTS = [
  { icon: '\u{1F522}', name: 'Mathematics', desc: 'Addition, fractions, geometry' },
  { icon: '\u{1F4D6}', name: 'English', desc: 'Grammar, comprehension, writing' },
  { icon: '\u{1F33F}', name: 'EVS / Science', desc: 'Plants, human body, solar system' },
  { icon: '\u{1F4DD}', name: 'Hindi', desc: 'Varnamala, matras, kahani lekhan' },
  { icon: '\u{1F4BB}', name: 'Computer', desc: 'MS Paint, Scratch, internet safety' },
  { icon: '\u{1F30D}', name: 'GK & More', desc: 'Moral science, health, general knowledge' },
]

const WHAT_MAKES_IT_DIFFERENT = [
  {
    icon: '\u{1F3AF}',
    title: 'Exactly your child\'s chapter',
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
    quote: "My daughter's Maths teacher noticed improvement in just 3 weeks. The worksheets match exactly what she's learning in class.",
    name: "Priya S.",
    role: "Parent, Class 3",
    location: "Mumbai",
  },
  {
    quote: "I use this to generate practice worksheets for my entire class. Saves me 2 hours every week.",
    name: "Ms. Kavitha R.",
    role: "Class Teacher, Grade 4",
    location: "Bengaluru",
  },
  {
    quote: "Finally a tool that works for UAE CBSE schools. The content is age-appropriate and my son actually enjoys doing these.",
    name: "Arjun M.",
    role: "Parent, Class 2",
    location: "Dubai",
  },
]

export default function LandingPage({ onGetStarted, onSignIn }: Props) {
  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      <header className="px-6 py-4 flex items-center justify-between max-w-6xl mx-auto">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
            <span className="text-white text-sm font-bold">P</span>
          </div>
          <span className="text-lg font-semibold">
            <span className="text-gray-900">Practice</span>
            <span className="text-primary">Craft</span>
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-400 hidden sm:block">India & UAE · Classes 1\u20135 · CBSE</span>
          <Button variant="ghost" size="sm" onClick={onSignIn}>Sign in</Button>
          <Button size="sm" onClick={onGetStarted}>Start free \u2192</Button>
        </div>
      </header>

      {/* Hero */}
      <section className="max-w-4xl mx-auto px-6 py-16 text-center">
        <div className="inline-flex items-center gap-2 bg-green-50 text-green-700 text-xs font-medium px-3 py-1.5 rounded-full mb-6 border border-green-200">
          \u2713 Aligned with CBSE/NCERT 2024 curriculum
        </div>
        <h1 className="text-4xl sm:text-5xl font-bold text-gray-900 leading-tight mb-4">
          Worksheets that match<br />
          <span className="text-primary">exactly what's being taught</span>
        </h1>
        <p className="text-lg text-gray-500 max-w-2xl mx-auto mb-8 leading-relaxed">
          Generate topic-specific practice for Classes 1\u20135 in under 30 seconds.
          Track progress. See which topics need more work. For parents and teachers.
        </p>
        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Button size="lg" onClick={onGetStarted} className="px-8 text-base">
            Create free worksheet \u2192
          </Button>
          <Button size="lg" variant="outline" onClick={onSignIn} className="px-8 text-base">
            Sign in
          </Button>
        </div>
        <p className="text-xs text-gray-400 mt-4">Free · No credit card · Works for India & UAE schools</p>
      </section>

      {/* Subjects grid */}
      <section className="bg-gray-50 py-12">
        <div className="max-w-4xl mx-auto px-6">
          <p className="text-center text-sm font-medium text-gray-500 uppercase tracking-wide mb-6">
            6 subjects · Classes 1\u20135 · 196 topics covered
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {SAMPLE_SUBJECTS.map(s => (
              <div key={s.name} className="bg-white rounded-xl p-4 border border-gray-100 shadow-sm">
                <span className="text-2xl">{s.icon}</span>
                <p className="font-semibold text-gray-800 text-sm mt-2">{s.name}</p>
                <p className="text-xs text-gray-400 mt-0.5">{s.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* What makes it different */}
      <section className="max-w-4xl mx-auto px-6 py-16">
        <h2 className="text-2xl font-bold text-gray-900 text-center mb-10">
          Why parents and teachers trust PracticeCraft
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          {WHAT_MAKES_IT_DIFFERENT.map(item => (
            <div key={item.title} className="flex gap-4">
              <span className="text-3xl flex-shrink-0">{item.icon}</span>
              <div>
                <p className="font-semibold text-gray-800 mb-1">{item.title}</p>
                <p className="text-sm text-gray-500 leading-relaxed">{item.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Sample worksheet preview \u2014 static */}
      <section className="bg-blue-50 py-12">
        <div className="max-w-3xl mx-auto px-6">
          <p className="text-center text-sm font-medium text-blue-600 uppercase tracking-wide mb-6">
            Sample worksheet
          </p>
          <div className="bg-white rounded-2xl shadow-lg border border-blue-100 p-6">
            <div className="border-b pb-4 mb-4">
              <p className="font-bold text-gray-900">Addition up to 20 · Class 1 · Hard</p>
              <p className="text-xs text-gray-400 mt-0.5">Maths · 5 questions · CBSE aligned</p>
            </div>
            <div className="space-y-3">
              {[
                { num: 'Q1', type: 'Recognition', q: 'Which of these equals 12? (a) 5+6  (b) 7+5  (c) 4+7  (d) 6+5', role: 'bg-blue-50 text-blue-700' },
                { num: 'Q2', type: 'Application', q: 'Priya had 8 pencils. She got 6 more. How many does she have now? ___', role: 'bg-green-50 text-green-700' },
                { num: 'Q3', type: 'Error Detection', q: 'Ravi wrote: 9 + 4 = 14. Is he correct? If not, what is the right answer?', role: 'bg-red-50 text-red-700' },
              ].map(q => (
                <div key={q.num} className="flex gap-3 items-start">
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-md flex-shrink-0 ${q.role}`}>{q.type}</span>
                  <p className="text-sm text-gray-700">{q.q}</p>
                </div>
              ))}
            </div>
            <p className="text-xs text-gray-400 mt-4 text-center">+ 2 more questions including a thinking challenge</p>
          </div>
        </div>
      </section>

      {/* Testimonials */}
      <section className="max-w-4xl mx-auto px-6 py-16">
        <h2 className="text-2xl font-bold text-gray-900 text-center mb-10">
          Trusted by parents and teachers
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
          {TESTIMONIALS.map(t => (
            <div key={t.name} className="bg-gray-50 rounded-xl p-5 border border-gray-100">
              <p className="text-sm text-gray-700 leading-relaxed mb-4">"{t.quote}"</p>
              <div>
                <p className="font-semibold text-gray-900 text-sm">{t.name}</p>
                <p className="text-xs text-gray-500">{t.role} · {t.location}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Final CTA */}
      <section className="bg-primary text-white py-16 text-center">
        <h2 className="text-3xl font-bold mb-4">Start with one free worksheet</h2>
        <p className="text-primary-foreground/80 mb-8 max-w-md mx-auto">
          No setup. No credit card. Generate a worksheet for your child's topic right now.
        </p>
        <Button
          size="lg"
          variant="secondary"
          onClick={onGetStarted}
          className="px-10 text-base font-semibold"
        >
          Create free worksheet \u2192
        </Button>
        <p className="text-xs text-primary-foreground/60 mt-4">
          India · UAE · CBSE · Classes 1\u20135
        </p>
      </section>

      {/* Footer */}
      <footer className="px-6 py-6 text-center border-t">
        <p className="text-xs text-gray-400">
          PracticeCraft · Aligned with NCERT and CBSE curriculum · Classes 1\u20135 · India & UAE
        </p>
      </footer>
    </div>
  )
}
