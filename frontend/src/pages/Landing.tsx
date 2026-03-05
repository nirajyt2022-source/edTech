import { useState, useEffect, useRef } from 'react'
import { Button } from '@/components/ui/button'
import {
  ArrowRight,
  BookOpen,
  Sparkles,
  FileDown,
  Target,
  Globe,
  Lightbulb,
  CheckCircle,
  Calculator,
  Leaf,
  Languages,
  Monitor,
  Globe2,
  Heart,
  Activity,
  PenLine,
  Check,
  X,
  Menu,
  XIcon,
  ChevronDown,
  Users,
  GraduationCap,
  Mail,
  Camera,
  Quote,
} from 'lucide-react'

interface Props {
  onGetStarted: () => void
  onSignIn: () => void
}

const SUBJECTS = [
  { icon: Calculator, name: 'Mathematics', topics: ['Number System', 'Addition', 'Subtraction', 'Multiplication', 'Fractions', 'Geometry', 'Time', 'Money', 'Measurement', 'Data Handling'] },
  { icon: BookOpen, name: 'English', topics: ['Grammar', 'Comprehension', 'Vocabulary', 'Writing', 'Poems', 'Stories'] },
  { icon: Leaf, name: 'EVS / Science', topics: ['Plants', 'Animals', 'Human Body', 'Food', 'Shelter', 'Water', 'Weather', 'Solar System'] },
  { icon: PenLine, name: 'Hindi', topics: ['\u0935\u0930\u094D\u0923\u092E\u093E\u0932\u093E', '\u092E\u093E\u0924\u094D\u0930\u093E\u090F\u0901', '\u0936\u092C\u094D\u0926 \u0930\u091A\u0928\u093E', '\u0935\u093E\u0915\u094D\u092F \u0930\u091A\u0928\u093E', '\u0935\u093F\u0932\u094B\u092E \u0936\u092C\u094D\u0926', '\u0915\u0939\u093E\u0928\u0940 \u0932\u0947\u0916\u0928'] },
  { icon: Monitor, name: 'Computer', topics: ['Parts of Computer', 'MS Paint', 'Scratch', 'Internet Safety'] },
  { icon: Globe2, name: 'GK', topics: ['National Symbols', 'Landmarks', 'Festivals', 'Sports', 'Solar System'] },
  { icon: Heart, name: 'Moral Science', topics: ['Good Habits', 'Honesty', 'Kindness', 'Sharing'] },
  { icon: Activity, name: 'Health & PE', topics: ['Hygiene', 'Nutrition', 'Yoga', 'First Aid', 'Sports'] },
  { icon: Languages, name: 'Urdu', topics: ['Alphabets', 'Words', 'Sentences', 'Stories'] },
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
  { feature: 'Photo-based answer grading', skolar: true, free: false },
  { feature: 'AI homework tutor', skolar: true, free: false },
  { feature: 'Textbook page scanning', skolar: true, free: false },
]

const FAQ_ITEMS = [
  {
    q: 'What is Skolar?',
    a: 'Skolar is an AI-powered learning platform built for the CBSE curriculum, Classes 1 through 5. It offers seven tools: worksheets, revision notes, flashcards, photo grading, textbook scanning, syllabus upload, and an AI homework tutor \u2014 all across 9 subjects and 198 topics.',
  },
  {
    q: 'What subjects does Skolar cover?',
    a: 'Skolar covers 9 subjects: Mathematics, English, Hindi, EVS/Science, Computer, General Knowledge, Moral Science, Health & Physical Education, and Urdu. Each subject has carefully mapped topics aligned to CBSE textbooks.',
  },
  {
    q: 'How does Skolar generate worksheets?',
    a: 'Pick a topic and class level \u2014 or just photograph your textbook page. Our AI creates 10 questions across three difficulty tiers: Foundation, Application, and Stretch. You can also generate revision notes or flashcards from the same topic. After your child finishes, snap a photo of their answers and Skolar grades it instantly.',
  },
  {
    q: 'Is Skolar free to use?',
    a: 'Yes. You get 5 worksheets per month completely free, with access to all 9 subjects and PDF downloads. For unlimited worksheets, mastery tracking, and bulk generation, upgrade to the Scholar plan at \u20B9199/month.',
  },
  {
    q: 'What classes does Skolar support?',
    a: 'Skolar supports CBSE Classes 1 through 5. Topics are mapped to the NCERT curriculum for each class level, ensuring age-appropriate content and progressive difficulty.',
  },
  {
    q: 'Can teachers use Skolar?',
    a: 'Absolutely. Teachers can generate topic-wise worksheets for their entire class, use bulk generation across multiple topics, share via WhatsApp or print batches, and track class-wide mastery and skill gaps.',
  },
  {
    q: 'How is Skolar different from free worksheet sites?',
    a: 'Free sites offer static, generic PDFs. Skolar generates unique questions every time, uses three difficulty tiers with scaffolding hints, includes Indian names and contexts in word problems, provides mastery tracking, and never repeats questions.',
  },
  {
    q: 'Do I need to install anything?',
    a: 'No. Skolar is a web application that works in any modern browser. Sign up, pick a topic, and download your PDF. No apps, no plugins, no setup required.',
  },
  {
    q: 'What tools does Skolar offer besides worksheets?',
    a: 'Skolar includes seven tools: AI-generated worksheets, one-page revision notes with worked examples, printable flashcards for active recall, photo-based grading (snap your child\u2019s filled worksheet for instant scores), textbook scanning (photograph any NCERT page to generate practice), syllabus upload to guide topic selection, and Ask Skolar \u2014 an AI tutor that explains any homework question step-by-step.',
  },
]

const TESTIMONIALS = [
  {
    quote: 'My daughter went from dreading maths homework to asking for more worksheets. The three difficulty tiers are exactly what she needed.',
    name: 'Priya Sharma',
    role: 'Parent, Class 3',
    initials: 'PS',
    color: 'bg-indigo-500',
  },
  {
    quote: 'I generate topic-wise worksheets for my entire class in minutes. Bulk generation across 5 topics saves me hours every week.',
    name: 'Ankit Verma',
    role: 'Teacher, Kendriya Vidyalaya',
    initials: 'AV',
    color: 'bg-orange-500',
  },
  {
    quote: 'The photo grading feature is a game-changer. I snap my son\'s worksheet and get instant scores — no more waiting.',
    name: 'Meenakshi Iyer',
    role: 'Parent, Class 5',
    initials: 'MI',
    color: 'bg-violet-500',
  },
  {
    quote: 'Finally, worksheets with Indian names and contexts. My students connect with the problems immediately — Arjun\'s cricket runs, Diwali lamps.',
    name: 'Rajesh Patel',
    role: 'Teacher, DAV Public School',
    initials: 'RP',
    color: 'bg-emerald-500',
  },
]

export default function LandingPage({ onGetStarted, onSignIn }: Props) {
  const [scrolled, setScrolled] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [activeSubject, setActiveSubject] = useState(0)
  const [openFaq, setOpenFaq] = useState<number | null>(null)
  const [showFloatingCta, setShowFloatingCta] = useState(false)
  const sectionsRef = useRef<(HTMLElement | null)[]>([])
  const userInteractedRef = useRef(false)

  useEffect(() => {
    const handleScroll = () => {
      const y = window.scrollY
      setScrolled(y > 40)
      const nearBottom = y + window.innerHeight >= document.documentElement.scrollHeight - 600
      setShowFloatingCta(y > 700 && !nearBottom)
    }
    window.addEventListener('scroll', handleScroll, { passive: true })
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  useEffect(() => {
    if (userInteractedRef.current) return
    const interval = setInterval(() => {
      setActiveSubject(prev => (prev + 1) % SUBJECTS.length)
    }, 4000)
    return () => clearInterval(interval)
  }, [])

  // Intersection Observer for scroll-reveal
  useEffect(() => {
    const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (prefersReduced) {
      sectionsRef.current.forEach(el => {
        if (el) el.classList.add('visible')
      })
      return
    }

    const observer = new IntersectionObserver(
      entries => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            entry.target.classList.add('visible')
          }
        })
      },
      { threshold: 0.08, rootMargin: '0px 0px -40px 0px' }
    )

    sectionsRef.current.forEach(el => {
      if (el) observer.observe(el)
    })

    return () => observer.disconnect()
  }, [])

  const addSectionRef = (index: number) => (el: HTMLElement | null) => {
    sectionsRef.current[index] = el
  }

  const scrollTo = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
    setMobileOpen(false)
  }

  return (
    <div className="font-[Inter,system-ui,sans-serif] text-slate-900 overflow-x-hidden">

      {/* -- 1. GLASS NAV (sticky) -- */}
      <header
        className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
          scrolled
            ? 'backdrop-blur-xl bg-white/80 border-b border-slate-200/60 shadow-sm'
            : 'bg-transparent'
        }`}
      >
        <div className="max-w-[1200px] mx-auto px-6 h-16 flex items-center justify-between">
          <span
            className={`font-[Fraunces,Georgia,serif] text-2xl font-normal tracking-tight cursor-pointer transition-colors duration-300 ${
              scrolled ? 'text-[#1E1B4B]' : 'text-white'
            }`}
            onClick={() => scrollTo('hero')}
          >
            Skolar
          </span>

          {/* Desktop links */}
          <nav className="hidden lg:flex items-center gap-1" aria-label="Main navigation">
            <button
              onClick={() => scrollTo('how')}
              className={`bg-transparent border-none cursor-pointer text-sm px-3.5 py-2 rounded-lg transition-colors font-[Inter,system-ui,sans-serif] ${
                scrolled ? 'text-slate-500 hover:text-slate-900' : 'text-white/70 hover:text-white'
              }`}
            >
              How it works
            </button>
            <button
              onClick={() => scrollTo('subjects')}
              className={`bg-transparent border-none cursor-pointer text-sm px-3.5 py-2 rounded-lg transition-colors font-[Inter,system-ui,sans-serif] ${
                scrolled ? 'text-slate-500 hover:text-slate-900' : 'text-white/70 hover:text-white'
              }`}
            >
              Subjects
            </button>
            <button
              onClick={() => scrollTo('pricing')}
              className={`bg-transparent border-none cursor-pointer text-sm px-3.5 py-2 rounded-lg transition-colors font-[Inter,system-ui,sans-serif] ${
                scrolled ? 'text-slate-500 hover:text-slate-900' : 'text-white/70 hover:text-white'
              }`}
            >
              Pricing
            </button>
            <button
              onClick={onSignIn}
              className={`bg-transparent border-none cursor-pointer text-sm font-medium px-3.5 py-2 rounded-lg transition-colors font-[Inter,system-ui,sans-serif] ${
                scrolled ? 'text-slate-900' : 'text-white'
              }`}
            >
              Sign in
            </button>
            <Button
              size="sm"
              onClick={onGetStarted}
              className="bg-orange-500 hover:bg-orange-600 text-white rounded-lg px-5 font-[Inter,system-ui,sans-serif] font-semibold cursor-pointer"
            >
              Start free
            </Button>
          </nav>

          {/* Mobile hamburger */}
          <button
            className="lg:hidden flex items-center justify-center bg-transparent border-none cursor-pointer p-2"
            onClick={() => setMobileOpen(!mobileOpen)}
            aria-label="Toggle menu"
          >
            {mobileOpen ? <XIcon className={`w-6 h-6 ${scrolled ? 'text-slate-900' : 'text-white'}`} /> : <Menu className={`w-6 h-6 ${scrolled ? 'text-slate-900' : 'text-white'}`} />}
          </button>
        </div>

        {/* Mobile menu */}
        {mobileOpen && (
          <div className="lg:hidden bg-white/95 backdrop-blur-xl border-t border-slate-200/60 px-6 pt-3 pb-5 flex flex-col gap-1">
            <button onClick={() => scrollTo('how')} className="bg-transparent border-none cursor-pointer text-base text-slate-900 py-2.5 text-left font-[Inter,system-ui,sans-serif]">How it works</button>
            <button onClick={() => scrollTo('subjects')} className="bg-transparent border-none cursor-pointer text-base text-slate-900 py-2.5 text-left font-[Inter,system-ui,sans-serif]">Subjects</button>
            <button onClick={() => scrollTo('pricing')} className="bg-transparent border-none cursor-pointer text-base text-slate-900 py-2.5 text-left font-[Inter,system-ui,sans-serif]">Pricing</button>
            <div className="flex flex-col gap-2 mt-3">
              <button onClick={onSignIn} className="bg-transparent border border-[#1E1B4B] cursor-pointer text-sm text-[#1E1B4B] font-semibold py-2.5 px-5 rounded-lg font-[Inter,system-ui,sans-serif]">Sign in</button>
              <button onClick={onGetStarted} className="bg-orange-500 border-none cursor-pointer text-sm text-white font-semibold py-2.5 px-5 rounded-lg font-[Inter,system-ui,sans-serif]">Start free</button>
            </div>
          </div>
        )}
      </header>

      {/* -- 2. HERO SECTION -- */}
      <section id="hero" className="lp-hero relative pt-24 pb-16 md:pt-32 md:pb-24 overflow-hidden">
        <div className="lp-dot-grid" />

        {/* Decorative orbs — floating animation */}
        <div className="lp-orb lp-orb-indigo lp-orb-float-1 w-[500px] h-[500px] -top-40 -left-40 opacity-60" />
        <div className="lp-orb lp-orb-amber lp-orb-float-2 w-[350px] h-[350px] top-20 right-10 opacity-40" />
        <div className="lp-orb lp-orb-violet lp-orb-float-3 w-[300px] h-[300px] bottom-10 left-1/3 opacity-30" />

        <div className="relative z-10 max-w-[1200px] mx-auto px-6 grid grid-cols-1 lg:grid-cols-2 gap-16 items-center">
          {/* Left */}
          <div>
            <div className="lp-badge mb-6 lp-hero-text">
              CBSE Classes 1&ndash;5 &middot; Free to start
            </div>
            <h1 className="lp-hero-h1 mb-5 lp-hero-text-delay">
              Tired of worksheets with{' '}
              <em>wrong answers?</em>
            </h1>
            <p className="text-base lg:text-lg leading-relaxed text-indigo-200/80 max-w-[500px] mb-7 lp-hero-text-delay-2">
              Skolar generates CBSE worksheets where every maths answer is verified by code &mdash; not copy-pasted from the internet. Three difficulty levels. Indian contexts. Print-ready PDF with answer key.
            </p>
            <div className="lp-hero-text-delay-3">
              <Button
                size="lg"
                onClick={onGetStarted}
                className="bg-orange-500 hover:bg-orange-600 text-white px-8 py-3.5 text-base rounded-xl font-semibold font-[Inter,system-ui,sans-serif] cursor-pointer inline-flex items-center gap-2 shadow-lg shadow-orange-500/25 hover:shadow-xl hover:shadow-orange-500/30 transition-all duration-300 hover:-translate-y-0.5"
              >
                Generate a free worksheet
                <ArrowRight className="w-5 h-5" />
              </Button>
            </div>
            <div className="flex gap-2 md:gap-3 flex-wrap mt-6 lp-hero-text-delay-3">
              {['198 topics', '9 subjects', 'Classes 1\u20135', 'Every answer checked', 'Hindi worksheets too'].map(chip => (
                <span
                  key={chip}
                  className="text-xs text-indigo-200/70 bg-white/[0.08] border border-white/[0.12] py-1.5 px-4 rounded-full"
                >
                  {chip}
                </span>
              ))}
            </div>
          </div>

          {/* Right -- realistic worksheet mockup */}
          <div className="relative hidden lg:flex items-center justify-center lp-hero-cards-animate">
            {/* Main worksheet card */}
            <div className="w-[380px] bg-white rounded-2xl shadow-2xl shadow-black/30 overflow-hidden border border-white/20">
              {/* Worksheet header */}
              <div className="bg-[#1E1B4B] px-6 py-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-[Fraunces,Georgia,serif] text-lg text-white font-normal">Skolar</span>
                  <span className="text-[10px] font-bold text-white/50 uppercase tracking-wider">Worksheet</span>
                </div>
                <div className="text-white">
                  <p className="text-[15px] font-semibold leading-tight">Addition &amp; Subtraction</p>
                  <p className="text-[11px] text-white/60 mt-0.5">Class 2 &middot; Mathematics &middot; 10 Questions</p>
                </div>
                <div className="flex gap-1.5 mt-3">
                  {['Foundation', 'Application', 'Stretch'].map((tier, i) => (
                    <span key={tier} className={`text-[9px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full ${
                      i === 0 ? 'bg-emerald-400/20 text-emerald-200' :
                      i === 1 ? 'bg-amber-400/20 text-amber-200' :
                      'bg-red-400/20 text-red-200'
                    }`}>{tier}</span>
                  ))}
                </div>
              </div>

              {/* Questions preview */}
              <div className="px-6 py-5 space-y-4">
                {/* Q1 — Foundation */}
                <div className="flex gap-3">
                  <span className="text-[11px] font-bold text-slate-300 mt-0.5 shrink-0 w-4">1.</span>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className="text-[8px] font-bold uppercase tracking-wider text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded">Foundation</span>
                    </div>
                    <p className="text-[13px] text-slate-700 leading-snug">What is 34 + 25?</p>
                    <div className="mt-1.5 h-[1px] border-b border-dashed border-slate-200 w-24" />
                  </div>
                </div>

                {/* Q2 — Application */}
                <div className="flex gap-3">
                  <span className="text-[11px] font-bold text-slate-300 mt-0.5 shrink-0 w-4">2.</span>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className="text-[8px] font-bold uppercase tracking-wider text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">Application</span>
                    </div>
                    <p className="text-[13px] text-slate-700 leading-snug">Meera has &#x20B9;45. She buys a notebook for &#x20B9;28. How much money does she have left?</p>
                    <div className="mt-1.5 h-[1px] border-b border-dashed border-slate-200 w-24" />
                  </div>
                </div>

                {/* Q3 — Stretch */}
                <div className="flex gap-3">
                  <span className="text-[11px] font-bold text-slate-300 mt-0.5 shrink-0 w-4">3.</span>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className="text-[8px] font-bold uppercase tracking-wider text-red-600 bg-red-50 px-1.5 py-0.5 rounded">Stretch</span>
                      <span className="text-[8px] text-slate-400 italic">Hint available</span>
                    </div>
                    <p className="text-[13px] text-slate-700 leading-snug">Arjun had 72 stickers. He gave some to Kavya and now has 38. How many did he give?</p>
                    <div className="mt-1.5 h-[1px] border-b border-dashed border-slate-200 w-24" />
                  </div>
                </div>

                {/* Fade-out hint for more questions */}
                <div className="relative">
                  <div className="flex gap-3 opacity-40">
                    <span className="text-[11px] font-bold text-slate-300 mt-0.5 shrink-0 w-4">4.</span>
                    <div className="flex-1">
                      <p className="text-[13px] text-slate-700 leading-snug">Find the missing number: 56 &minus; ___ = 29</p>
                    </div>
                  </div>
                  <div className="absolute bottom-0 left-0 right-0 h-8 bg-gradient-to-t from-white to-transparent" />
                </div>
              </div>

              {/* Footer bar */}
              <div className="px-6 py-3 bg-slate-50 border-t border-slate-100 flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className="flex items-center gap-1.5">
                    <FileDown className="w-3.5 h-3.5 text-slate-400" />
                    <span className="text-[10px] font-semibold text-slate-400">PDF Ready</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <CheckCircle className="w-3.5 h-3.5 text-slate-400" />
                    <span className="text-[10px] font-semibold text-slate-400">Answer Key</span>
                  </div>
                </div>
                <span className="text-[10px] text-slate-300">+ 7 more questions</span>
              </div>
            </div>

            {/* Floating badge — top right */}
            <div className="absolute -top-2 -right-4 bg-white rounded-xl shadow-lg shadow-black/10 px-4 py-3 border border-slate-100 lp-orb-float-3">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-full bg-orange-100 flex items-center justify-center">
                  <Sparkles className="w-4 h-4 text-orange-500" />
                </div>
                <div>
                  <p className="text-[11px] font-bold text-slate-900">AI Generated</p>
                  <p className="text-[9px] text-slate-400">Unique every time</p>
                </div>
              </div>
            </div>

            {/* Floating badge — bottom left */}
            <div className="absolute -bottom-3 -left-6 bg-white rounded-xl shadow-lg shadow-black/10 px-4 py-3 border border-slate-100 lp-orb-float-2">
              <div className="flex items-center gap-3">
                <div className="flex -space-x-1.5">
                  <div className="w-6 h-6 rounded-full bg-indigo-500 border-2 border-white flex items-center justify-center text-[9px] font-bold text-white">P</div>
                  <div className="w-6 h-6 rounded-full bg-orange-500 border-2 border-white flex items-center justify-center text-[9px] font-bold text-white">R</div>
                  <div className="w-6 h-6 rounded-full bg-violet-500 border-2 border-white flex items-center justify-center text-[9px] font-bold text-white">A</div>
                </div>
                <div>
                  <p className="text-[11px] font-bold text-slate-900">Built for CBSE</p>
                  <p className="text-[9px] text-slate-400">Classes 1 to 5</p>
                </div>
              </div>
            </div>
          </div>

          {/* Mobile hero — shown below lg */}
          <div className="lg:hidden mt-8 mx-auto max-w-[300px]">
            <div className="bg-white rounded-2xl shadow-xl overflow-hidden border border-white/20">
              <div className="bg-[#1E1B4B] px-5 py-3">
                <p className="text-sm font-semibold text-white">Addition &amp; Subtraction</p>
                <p className="text-[10px] text-white/60">Class 2 &middot; Mathematics &middot; 10 Questions</p>
              </div>
              <div className="px-5 py-4 space-y-3">
                <p className="text-xs text-slate-600">1. What is 34 + 25?</p>
                <p className="text-xs text-slate-600">2. Meera has &#x20B9;45. She buys a notebook for &#x20B9;28...</p>
                <div className="h-6 bg-gradient-to-t from-white to-transparent" />
              </div>
            </div>
          </div>
        </div>

      </section>

      {/* -- 3. STATS RIBBON -- */}
      <section
        ref={addSectionRef(0)}
        className="section-fade-in bg-white py-10 md:py-16 px-6 border-t border-slate-200/50"
        aria-label="Key statistics"
      >
        <div className="max-w-[1000px] mx-auto flex justify-center gap-6 md:gap-16 flex-wrap">
          {[
            { n: '198', l: 'Topics' },
            { n: '9', l: 'Subjects' },
            { n: '7', l: 'Tools' },
            { n: '5', l: 'Classes' },
            { n: 'AI', l: 'Powered' },
          ].map(s => (
            <div key={s.l} className="text-center">
              <div className="lp-stats-number">{s.n}</div>
              <div className="text-[11px] uppercase tracking-[0.08em] text-slate-500 font-semibold mt-1.5">{s.l}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Social proof strip */}
      <section className="bg-white py-6 px-6 border-b border-slate-100">
        <p className="text-center text-sm text-slate-400">
          Trusted by parents across India &middot; <span className="font-semibold text-slate-600">CBSE Aligned</span> &middot; <span className="font-semibold text-slate-600">NCERT Mapped</span>
        </p>
      </section>

      {/* -- SAMPLE WORKSHEET PREVIEW -- */}
      <section className="bg-white py-12 md:py-20 px-6" aria-label="Sample worksheet">
        <div className="max-w-[900px] mx-auto text-center">
          <p className="text-xs font-bold uppercase tracking-[0.1em] text-orange-500 mb-2.5">See it in action</p>
          <h2 className="font-[Fraunces,Georgia,serif] text-[clamp(28px,4vw,40px)] font-normal text-slate-900 mb-3 tracking-tight">
            Here's what your child gets
          </h2>
          <p className="text-sm text-slate-500 mb-8 max-w-lg mx-auto">
            A real Class 3 Maths worksheet on Fractions — with easy, medium, and hard questions built around one micro-skill.
          </p>

          <div className="max-w-md mx-auto bg-stone-50 border border-slate-200 rounded-2xl p-6 text-left space-y-4">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-[10px] font-bold uppercase tracking-wider bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-md">Easy</span>
              <span className="text-sm text-slate-700">Colour <sup>1</sup>/<sub>4</sub> of this shape.</span>
            </div>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-[10px] font-bold uppercase tracking-wider bg-amber-100 text-amber-700 px-2 py-0.5 rounded-md">Medium</span>
              <span className="text-sm text-slate-700">Which is greater: <sup>2</sup>/<sub>5</sub> or <sup>3</sup>/<sub>5</sub>?</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-bold uppercase tracking-wider bg-red-100 text-red-700 px-2 py-0.5 rounded-md">Hard</span>
              <span className="text-sm text-slate-700">Riya ate <sup>1</sup>/<sub>4</sub> of a pizza. Her brother ate <sup>2</sup>/<sub>4</sub>. How much is left?</span>
            </div>
          </div>

          <button
            onClick={onGetStarted}
            className="mt-8 inline-flex items-center gap-2 bg-[#1E1B4B] text-white cursor-pointer text-sm font-semibold py-3 px-8 rounded-lg font-[Inter,system-ui,sans-serif] hover:bg-[#2d2a5e] transition-colors"
          >
            Generate a free worksheet
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </section>

      {/* -- 4. HOW IT WORKS -- */}
      <section
        id="how"
        ref={addSectionRef(1)}
        className="section-fade-in bg-stone-50 py-12 md:py-20 px-6"
        aria-label="How it works"
      >
        <div className="max-w-[900px] mx-auto text-center">
          <p className="text-xs font-bold uppercase tracking-[0.1em] text-orange-500 mb-2.5">How it works</p>
          <h2 className="font-[Fraunces,Georgia,serif] text-[clamp(28px,4vw,40px)] font-normal text-slate-900 mb-8 md:mb-12 tracking-tight">
            Three steps. Thirty seconds.
          </h2>

          {/* Dotted connector line -- desktop only */}
          <div className="relative">
            <div className="hidden md:block absolute top-14 left-[16.67%] right-[16.67%] border-t-2 border-dashed border-slate-200 z-0" />

            <div className="relative z-10 grid grid-cols-1 md:grid-cols-3 gap-8">
              {[
                { step: 1, title: 'Pick a topic or snap your textbook', desc: 'Choose from 198 CBSE topics \u2014 or photograph any textbook page and we\u2019ll read it for you.', Icon: BookOpen },
                { step: 2, title: 'AI creates your study material', desc: 'Worksheets, revision notes, or flashcards \u2014 three difficulty tiers with Indian context and hints.', Icon: Sparkles },
                { step: 3, title: 'Practice, grade, improve', desc: 'Download PDFs, grade from photo, track progress. The complete learning loop.', Icon: Target },
              ].map(item => (
                <div
                  key={item.step}
                  className="stagger-child bg-white border border-slate-200 rounded-2xl p-5 md:p-8 text-left transition-all duration-300 hover:shadow-lg hover:-translate-y-1 cursor-default"
                >
                  <div className="w-10 h-10 rounded-full bg-[#1E1B4B] text-white flex items-center justify-center text-sm font-bold mb-5">
                    {item.step}
                  </div>
                  <item.Icon className="w-6 h-6 text-[#3730A3] mb-3" />
                  <h3 className="font-[Fraunces,Georgia,serif] text-xl font-normal text-slate-900 mb-2">{item.title}</h3>
                  <p className="text-sm leading-relaxed text-slate-500">{item.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* -- 5. WHAT MAKES US DIFFERENT -- */}
      <section
        ref={addSectionRef(2)}
        className="section-fade-in bg-white py-12 md:py-20 px-6"
        aria-label="Why Skolar"
      >
        <div className="max-w-[900px] mx-auto text-center">
          <p className="text-xs font-bold uppercase tracking-[0.1em] text-orange-500 mb-2.5">Why Skolar</p>
          <h2 className="font-[Fraunces,Georgia,serif] text-[clamp(28px,4vw,40px)] font-normal text-slate-900 mb-8 md:mb-12 tracking-tight">
            What makes Skolar different
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[
              { title: 'Three-Tier Difficulty', desc: 'Every worksheet has Foundation, Application, and Stretch questions. Builds confidence first, then pushes boundaries.', Icon: Target },
              { title: 'Indian Context', desc: 'Meera at the mela. Arjun\u2019s cricket runs. Diwali lamps. Word problems your child can picture immediately.', Icon: Globe },
              { title: 'Hints That Teach', desc: 'Stretch questions include collapsible hints. Children attempt first, then get scaffolding \u2014 not answers.', Icon: Lightbulb },
              { title: 'Complete Answer Key', desc: 'Every worksheet comes with a separate answer key page. Verify work instantly. No guessing.', Icon: CheckCircle },
              { title: 'Grade from Photo', desc: 'Snap a photo of your child\u2019s filled worksheet. AI reads the answers and grades instantly \u2014 8/10, here\u2019s what went wrong.', Icon: Camera },
              { title: 'Learn from Textbook', desc: 'Photograph any NCERT page. We\u2019ll read it and generate a worksheet, revision notes, or flashcards from that exact content.', Icon: BookOpen },
            ].map(card => (
              <div
                key={card.title}
                className="stagger-child bg-stone-50 border border-slate-200 rounded-2xl p-5 md:p-7 text-left transition-all duration-300 hover:shadow-lg hover:-translate-y-1 cursor-default"
              >
                <div className="w-11 h-11 rounded-full bg-indigo-100 flex items-center justify-center mb-4">
                  <card.Icon className="w-5 h-5 text-[#3730A3]" />
                </div>
                <h3 className="font-[Fraunces,Georgia,serif] text-lg font-normal text-slate-900 mb-2">{card.title}</h3>
                <p className="text-sm leading-relaxed text-slate-500">{card.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* -- 5.5. MORE THAN WORKSHEETS -- */}
      <section
        ref={addSectionRef(3)}
        className="section-fade-in bg-stone-50 py-12 md:py-20 px-6"
        aria-label="All tools"
      >
        <div className="max-w-[1000px] mx-auto text-center">
          <p className="text-xs font-bold uppercase tracking-[0.1em] text-orange-500 mb-2.5">The Complete Toolkit</p>
          <h2 className="font-[Fraunces,Georgia,serif] text-[clamp(28px,4vw,40px)] font-normal text-slate-900 mb-4 tracking-tight">
            More than worksheets
          </h2>
          <p className="text-base text-slate-500 mb-8 md:mb-12 max-w-[600px] mx-auto">
            Seven tools that work together. Revise a topic, practice it, grade the answers, see progress — all in one place.
          </p>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {[
              { icon: '\ud83d\udcdd', name: 'Worksheets', desc: '10-question PDFs with 3 difficulty tiers' },
              { icon: '\ud83d\udcd6', name: 'Revision Notes', desc: '1-page topic summaries with worked examples' },
              { icon: '\ud83c\udccf', name: 'Flashcards', desc: 'Printable study cards for active recall' },
              { icon: '\ud83d\udcf8', name: 'Photo Grading', desc: 'Snap answers, AI grades instantly' },
              { icon: '\ud83d\udcda', name: 'Textbook Scan', desc: 'Photograph any page, generate practice' },
              { icon: '\ud83d\udccb', name: 'Syllabus Upload', desc: 'Upload your school syllabus to guide practice' },
              { icon: '\ud83e\udde0', name: 'Ask Skolar', desc: 'AI tutor for homework doubts, step-by-step' },
            ].map(tool => (
              <div
                key={tool.name}
                className="stagger-child bg-white border border-slate-200 rounded-xl p-5 text-center transition-all duration-300 hover:shadow-lg hover:-translate-y-1 cursor-default"
              >
                <div className="text-3xl mb-3">{tool.icon}</div>
                <h3 className="text-sm font-semibold text-slate-900 mb-1" style={{ fontFamily: "'Inter', system-ui, sans-serif" }}>{tool.name}</h3>
                <p className="text-xs text-slate-500 leading-relaxed">{tool.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* -- 5.75. DASHBOARD PREVIEW -- */}
      <section
        ref={addSectionRef(4)}
        className="section-fade-in bg-white py-12 md:py-20 px-6"
        aria-label="Progress dashboard preview"
      >
        <div className="max-w-[900px] mx-auto">
          <div className="text-center mb-8 md:mb-12">
            <p className="text-xs font-bold uppercase tracking-[0.1em] text-orange-500 mb-2.5">Progress Dashboard</p>
            <h2 className="font-[Fraunces,Georgia,serif] text-[clamp(28px,4vw,40px)] font-normal text-slate-900 mb-4 tracking-tight">
              Know exactly where your child stands
            </h2>
            <p className="text-base text-slate-500 max-w-[500px] mx-auto">
              Every graded worksheet feeds into a dashboard that shows strengths, gaps, and what to practice next.
            </p>
          </div>

          {/* Dashboard mockup */}
          <div className="stagger-child bg-stone-50 border border-slate-200 rounded-2xl p-6 md:p-8 shadow-lg">

            {/* Top stats row */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              {[
                { label: 'Worksheets', value: '24', sub: 'this month' },
                { label: 'Average Score', value: '82%', sub: '\u2191 8% from last month' },
                { label: 'Strongest', value: 'EVS', sub: '94% average' },
                { label: 'Needs Work', value: 'Fractions', sub: '62% \u2014 practice more' },
              ].map(stat => (
                <div key={stat.label} className="bg-white rounded-xl p-4 border border-slate-100">
                  <p className="text-xs text-slate-400 font-medium uppercase tracking-wide">{stat.label}</p>
                  <p className="text-2xl font-bold text-slate-900 mt-1" style={{ fontFamily: "'Fraunces', serif" }}>{stat.value}</p>
                  <p className="text-xs text-slate-500 mt-0.5">{stat.sub}</p>
                </div>
              ))}
            </div>

            {/* Subject progress bars */}
            <div className="bg-white rounded-xl p-5 border border-slate-100 mb-6">
              <p className="text-sm font-semibold text-slate-900 mb-4">Subject Progress</p>
              <div className="space-y-3">
                {[
                  { subject: 'EVS / Science', pct: 94, color: '#16A34A' },
                  { subject: 'English', pct: 86, color: '#3730A3' },
                  { subject: 'Hindi', pct: 78, color: '#DC2626' },
                  { subject: 'Mathematics', pct: 72, color: '#F97316' },
                  { subject: 'GK', pct: 68, color: '#8B5CF6' },
                ].map(s => (
                  <div key={s.subject} className="flex items-center gap-3">
                    <span className="text-xs text-slate-600 w-24 shrink-0">{s.subject}</span>
                    <div className="flex-1 bg-slate-100 rounded-full h-2.5 overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-1000"
                        style={{ width: `${s.pct}%`, backgroundColor: s.color }}
                      />
                    </div>
                    <span className="text-xs font-semibold text-slate-700 w-10 text-right">{s.pct}%</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Recent grading results */}
            <div className="bg-white rounded-xl p-5 border border-slate-100">
              <p className="text-sm font-semibold text-slate-900 mb-3">Recent Results</p>
              <div className="space-y-2.5">
                {[
                  { topic: 'Animals Around Us', subject: 'EVS', score: '9/10', date: 'Today', color: '#16A34A' },
                  { topic: 'Addition 5-digit', subject: 'Maths', score: '7/10', date: 'Yesterday', color: '#F97316' },
                  { topic: 'Summary Writing', subject: 'English', score: '8/10', date: '2 days ago', color: '#3730A3' },
                ].map(r => (
                  <div key={r.topic} className="flex items-center justify-between py-2 border-b border-slate-50 last:border-0">
                    <div className="flex items-center gap-2.5">
                      <span
                        className="text-[10px] font-bold uppercase py-0.5 px-2 rounded-full"
                        style={{ color: r.color, backgroundColor: `${r.color}15` }}
                      >
                        {r.subject}
                      </span>
                      <span className="text-sm text-slate-700">{r.topic}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-sm font-bold text-slate-900">{r.score}</span>
                      <span className="text-xs text-slate-400">{r.date}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <p className="text-center text-xs text-slate-400 mt-4">
              Live dashboard preview — your child's actual data appears after grading
            </p>
          </div>
        </div>
      </section>

      {/* -- 6. SUBJECT BROWSER -- */}
      <section
        id="subjects"
        ref={addSectionRef(5)}
        className="section-fade-in bg-stone-50 py-12 md:py-20 px-6"
        aria-label="Subject coverage"
      >
        <div className="max-w-[1000px] mx-auto">
          <div className="text-center mb-9">
            <p className="text-xs font-bold uppercase tracking-[0.1em] text-orange-500 mb-2.5">Subject Coverage</p>
            <h2 className="font-[Fraunces,Georgia,serif] text-[clamp(28px,4vw,40px)] font-normal text-slate-900 tracking-tight">
              Nine subjects. 198 topics. All CBSE.
            </h2>
          </div>

          {/* Subject tabs */}
          <div className="flex gap-2 flex-wrap justify-center mb-7">
            {SUBJECTS.map((s, i) => {
              const IconComp = s.icon
              return (
                <button
                  key={s.name}
                  onClick={() => { userInteractedRef.current = true; setActiveSubject(i) }}
                  className={`flex items-center gap-2 rounded-full px-3 py-1.5 text-[12px] md:px-4 md:py-2 md:text-[13px] font-semibold cursor-pointer transition-all duration-200 border font-[Inter,system-ui,sans-serif] ${
                    activeSubject === i
                      ? 'bg-[#1E1B4B] text-white border-[#1E1B4B]'
                      : 'bg-white text-slate-500 border-slate-200 hover:text-slate-700 hover:border-slate-300'
                  }`}
                >
                  <IconComp className="w-4 h-4" />
                  {s.name}
                </button>
              )
            })}
          </div>

          {/* Topic pills */}
          <div className="flex flex-wrap gap-2 justify-center min-h-[60px]">
            {SUBJECTS[activeSubject].topics.map(topic => (
              <span
                key={topic}
                className="bg-white border border-slate-200 rounded-lg py-1.5 px-4 text-sm text-slate-900"
              >
                {topic}
              </span>
            ))}
          </div>
          <p className="text-center text-xs text-slate-400 mt-4">
            Topics shown for Classes 1&ndash;5 &middot; {SUBJECTS[activeSubject].name}
          </p>
        </div>
      </section>

      {/* -- 7. SAMPLE WORKSHEETS -- */}
      <section
        ref={addSectionRef(6)}
        className="section-fade-in bg-white py-12 md:py-20 px-6"
        aria-label="Sample questions"
      >
        <div className="max-w-[1000px] mx-auto">
          <div className="text-center mb-8 md:mb-12">
            <p className="text-xs font-bold uppercase tracking-[0.1em] text-orange-500 mb-2.5">Sample Questions</p>
            <h2 className="font-[Fraunces,Georgia,serif] text-[clamp(28px,4vw,40px)] font-normal text-slate-900 tracking-tight">
              See what your child gets
            </h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
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
                accent: '#F97316',
              },
              {
                subj: 'English',
                cls: 'Class 5',
                q: 'Ritika read a story about a little bird that learned to fly. What is the main idea of the story?',
                options: '(A) Birds are colourful \u00a0 (B) Never give up \u00a0 (C) Fly south in winter \u00a0 (D) Eat seeds',
                accent: '#3730A3',
              },
              {
                subj: 'Hindi',
                cls: 'Class 3',
                q: '\u0926\u093F\u090F \u0917\u090F \u0905\u0915\u094D\u0937\u0930\u094B\u0902 \u0915\u094B \u0938\u0939\u0940 \u0915\u094D\u0930\u092E \u092E\u0947\u0902 \u0930\u0916\u0915\u0930 \u0936\u092C\u094D\u0926 \u092C\u0928\u093E\u0907\u090F: \u2018\u0932\u2019, \u2018\u092E\u2019, \u2018\u0915\u2019',
                options: '(\u0905) \u0932\u092E\u0915 \u00a0 (\u092C) \u0915\u092E\u0932 \u00a0 (\u0938) \u092E\u0932\u0915 \u00a0 (\u0926) \u0915\u0932\u092E',
                accent: '#DC2626',
              },
            ].map(sample => (
              <article
                key={sample.subj}
                className="stagger-child bg-white border border-slate-200 rounded-2xl p-6 transition-all duration-300 hover:shadow-lg hover:-translate-y-1"
                style={{ borderLeft: `4px solid ${sample.accent}` }}
              >
                <div className="flex gap-2 mb-3.5">
                  <span
                    className="text-[11px] font-bold uppercase tracking-[0.05em] py-0.5 px-2.5 rounded-full"
                    style={{ color: sample.accent, background: `${sample.accent}15` }}
                  >
                    {sample.subj}
                  </span>
                  <span className="text-[11px] font-semibold text-slate-400 py-0.5">{sample.cls}</span>
                </div>
                <p className="text-sm leading-relaxed text-slate-900 mb-2">{sample.q}</p>
                <p className="text-[13px] text-slate-500 mb-4 font-mono">{sample.options}</p>
                <button
                  onClick={onGetStarted}
                  className="bg-transparent border-none cursor-pointer text-[13px] font-semibold text-[#3730A3] p-0 hover:text-[#1E1B4B] transition-colors font-[Inter,system-ui,sans-serif]"
                >
                  Try this topic free &rarr;
                </button>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* -- 8. COMPARISON TABLE -- */}
      <section
        ref={addSectionRef(7)}
        className="section-fade-in bg-stone-50 py-12 md:py-20 px-6"
        aria-label="Feature comparison"
      >
        <div className="max-w-[700px] mx-auto text-center">
          <p className="text-xs font-bold uppercase tracking-[0.1em] text-orange-500 mb-2.5">Comparison</p>
          <h2 className="font-[Fraunces,Georgia,serif] text-[clamp(28px,4vw,40px)] font-normal text-slate-900 mb-9 tracking-tight">
            Skolar vs Generic Worksheet Sites
          </h2>
          <div className="overflow-auto rounded-xl border border-slate-200 shadow-sm">
            <table className="w-full border-collapse text-sm bg-white">
              <thead>
                <tr>
                  <th className="p-3.5 px-3 md:px-5 text-left text-[11.5px] font-bold uppercase tracking-[0.06em] text-slate-400 border-b-2 border-slate-200">Feature</th>
                  <th className="p-3.5 px-3 md:px-5 text-center text-[11.5px] font-bold uppercase tracking-[0.06em] text-[#1E1B4B] border-b-2 border-slate-200">Skolar</th>
                  <th className="p-3.5 px-3 md:px-5 text-center text-[11.5px] font-bold uppercase tracking-[0.06em] text-slate-400 border-b-2 border-slate-200">Others</th>
                </tr>
              </thead>
              <tbody>
                {COMPARISON_FEATURES.map((r, i) => (
                  <tr key={i}>
                    <td className="py-3 px-3 md:px-5 border-b border-slate-100 text-slate-900 text-left">{r.feature}</td>
                    <td className="py-3 px-3 md:px-5 border-b border-slate-100 text-center bg-indigo-50/40">
                      <Check className="w-5 h-5 text-emerald-600 inline-block" />
                    </td>
                    <td className="py-3 px-3 md:px-5 border-b border-slate-100 text-center">
                      {r.free === true
                        ? <Check className="w-5 h-5 text-emerald-600 inline-block" />
                        : r.free === 'partial'
                        ? <span className="text-orange-500 font-bold text-base">~</span>
                        : <X className="w-5 h-5 text-red-400 inline-block" />
                      }
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* -- 9. PRICING -- */}
      <section
        id="pricing"
        ref={addSectionRef(8)}
        className="section-fade-in bg-white py-12 md:py-20 px-6"
        aria-label="Pricing"
      >
        <div className="max-w-[960px] mx-auto text-center">
          <p className="text-xs font-bold uppercase tracking-[0.1em] text-orange-500 mb-2.5">Pricing</p>
          <h2 className="font-[Fraunces,Georgia,serif] text-[clamp(28px,4vw,40px)] font-normal text-slate-900 mb-8 md:mb-12 tracking-tight">
            Start free. Upgrade when ready.
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5 items-start">

            {/* Free */}
            <div className="bg-white border border-slate-200 rounded-2xl p-8 text-left transition-all duration-300 hover:shadow-lg hover:-translate-y-1">
              <div className="text-[11.5px] font-bold uppercase tracking-[0.1em] text-slate-400 mb-2">Free</div>
              <div className="font-[Fraunces,Georgia,serif] text-[40px] font-normal text-slate-900 leading-none mb-1">
                {'\u20B9'}0<span className="text-[15px] font-normal text-slate-400"> /month</span>
              </div>
              <p className="text-[13px] text-slate-400 mb-6 mt-1">5 worksheets per month</p>
              <ul className="list-none p-0 m-0 mb-6 flex flex-col gap-2.5">
                {['All 9 subjects', 'PDF download + answer key', '3 difficulty levels', '1 child profile'].map(f => (
                  <li key={f} className="text-[13.5px] text-slate-900 flex items-center gap-2">
                    <Check className="w-4 h-4 text-emerald-600 flex-shrink-0" /> {f}
                  </li>
                ))}
              </ul>
              <button
                onClick={onGetStarted}
                className="w-full bg-transparent border-2 border-orange-500 text-orange-500 cursor-pointer text-sm font-semibold py-3 px-5 rounded-xl font-[Inter,system-ui,sans-serif] hover:bg-orange-50 transition-colors"
              >
                Generate a free worksheet
              </button>
            </div>

            {/* Scholar */}
            <div className="bg-[#1E1B4B] border border-[#1E1B4B] rounded-2xl p-8 text-left relative transition-all duration-300 hover:shadow-xl hover:shadow-indigo-950/30 hover:-translate-y-1">
              <div className="absolute -top-3 right-5 bg-orange-500 text-white text-[10.5px] font-bold py-1 px-3 rounded-full uppercase tracking-[0.06em]">
                Most Popular
              </div>
              <div className="text-[11.5px] font-bold uppercase tracking-[0.1em] text-white/60 mb-2">Scholar</div>
              <div className="font-[Fraunces,Georgia,serif] text-[40px] font-normal text-white leading-none mb-1">
                {'\u20B9'}199<span className="text-[15px] font-normal text-white/60"> /month</span>
              </div>
              <p className="text-[13px] text-white/60 mb-1 mt-1">Unlimited worksheets</p>
              <p className="text-[11px] text-white/40 mb-1">Just {'\u20B9'}6.6/day &middot; Cancel anytime</p>
              <p className="text-[11px] text-white/40 mb-6">AED 29/mo</p>
              <ul className="list-none p-0 m-0 mb-6 flex flex-col gap-2.5">
                {['Unlimited worksheets', 'Photo grading', 'Revision notes + flashcards', 'Progress tracking', 'Up to 5 children', 'Ask Skolar AI tutor'].map(f => (
                  <li key={f} className="text-[13.5px] text-white/90 flex items-center gap-2">
                    <Check className="w-4 h-4 text-orange-400 flex-shrink-0" /> {f}
                  </li>
                ))}
              </ul>
              <button
                onClick={onGetStarted}
                className="w-full bg-white border-none text-[#1E1B4B] cursor-pointer text-sm font-semibold py-3 px-5 rounded-xl font-[Inter,system-ui,sans-serif] hover:bg-white/90 transition-colors"
              >
                Go unlimited
              </button>
            </div>

            {/* Annual */}
            <div className="bg-white border border-slate-200 rounded-2xl p-8 text-left relative transition-all duration-300 hover:shadow-lg hover:-translate-y-1">
              <div className="absolute -top-3 right-5 bg-emerald-500 text-white text-[10.5px] font-bold py-1 px-3 rounded-full uppercase tracking-[0.06em]">
                Save 37%
              </div>
              <div className="text-[11.5px] font-bold uppercase tracking-[0.1em] text-slate-400 mb-2">Annual</div>
              <div className="font-[Fraunces,Georgia,serif] text-[40px] font-normal text-slate-900 leading-none mb-1">
                {'\u20B9'}1,499<span className="text-[15px] font-normal text-slate-400"> /year</span>
              </div>
              <p className="text-[13px] text-emerald-600 font-semibold mb-1 mt-1">{'\u20B9'}125/month, billed yearly</p>
              <p className="text-[11px] text-slate-400 mb-6">AED 229/yr &middot; Save {'\u20B9'}889</p>
              <ul className="list-none p-0 m-0 mb-6 flex flex-col gap-2.5">
                {['Everything in Scholar', '12 months access', 'Best value for families', 'Just \u20B94.1/day'].map(f => (
                  <li key={f} className="text-[13.5px] text-slate-900 flex items-center gap-2">
                    <Check className="w-4 h-4 text-emerald-600 flex-shrink-0" /> {f}
                  </li>
                ))}
              </ul>
              <button
                onClick={onGetStarted}
                className="w-full bg-orange-500 border-none text-white cursor-pointer text-sm font-semibold py-3 px-5 rounded-xl font-[Inter,system-ui,sans-serif] hover:bg-orange-600 transition-colors"
              >
                Save 37% — go annual
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* -- 10. FOR PARENTS / FOR TEACHERS -- */}
      <section
        ref={addSectionRef(9)}
        className="section-fade-in bg-stone-50 py-12 md:py-20 px-6"
        aria-label="For parents and teachers"
      >
        <div className="max-w-[900px] mx-auto grid grid-cols-1 md:grid-cols-2 gap-6">

          {/* Parents */}
          <article className="stagger-child bg-white border border-slate-200 rounded-2xl p-6 md:p-9 border-t-4 border-t-[#3730A3]">
            <div className="w-10 h-10 rounded-full bg-indigo-100 flex items-center justify-center mb-4">
              <Users className="w-5 h-5 text-[#3730A3]" />
            </div>
            <div className="text-[11px] font-bold uppercase tracking-[0.1em] text-slate-400 mb-3">For Parents</div>
            <h3 className="font-[Fraunces,Georgia,serif] text-[22px] font-normal text-slate-900 mb-5 leading-snug">Know exactly where your child stands.</h3>
            <ul className="list-none p-0 m-0 mb-6 flex flex-col gap-2.5">
              {[
                'Generate worksheets, revision notes, or flashcards in 30 seconds',
                'Photograph a textbook page \u2014 we\u2019ll create practice from it',
                'Grade answers from a photo \u2014 know the score instantly',
                'Ask Skolar any homework question \u2014 step-by-step explanations',
                'Track progress across subjects \u2014 see exactly where they stand',
              ].map(item => (
                <li key={item} className="text-sm text-slate-500 leading-relaxed flex items-start gap-2">
                  <Check className="w-4 h-4 text-[#3730A3] flex-shrink-0 mt-0.5" />
                  {item}
                </li>
              ))}
            </ul>
            <button
              onClick={onGetStarted}
              className="bg-[#1E1B4B] border-none text-white cursor-pointer text-sm font-semibold py-2.5 px-6 rounded-lg font-[Inter,system-ui,sans-serif] hover:bg-[#312E81] transition-colors"
            >
              Start as Parent &rarr;
            </button>
          </article>

          {/* Teachers */}
          <article className="stagger-child bg-white border border-slate-200 rounded-2xl p-6 md:p-9 border-t-4 border-t-orange-500">
            <div className="w-10 h-10 rounded-full bg-orange-100 flex items-center justify-center mb-4">
              <GraduationCap className="w-5 h-5 text-orange-600" />
            </div>
            <div className="text-[11px] font-bold uppercase tracking-[0.1em] text-slate-400 mb-3">For Teachers</div>
            <h3 className="font-[Fraunces,Georgia,serif] text-[22px] font-normal text-slate-900 mb-5 leading-snug">Differentiated practice, at scale.</h3>
            <ul className="list-none p-0 m-0 mb-6 flex flex-col gap-2.5">
              {[
                'Generate topic-wise worksheets for the whole class',
                'Bulk generate across 5 topics in one click',
                'Share instantly via WhatsApp or print batches',
                'Track class-wide mastery and skill gaps',
                'CBSE chapter progression, already mapped',
              ].map(item => (
                <li key={item} className="text-sm text-slate-500 leading-relaxed flex items-start gap-2">
                  <Check className="w-4 h-4 text-orange-500 flex-shrink-0 mt-0.5" />
                  {item}
                </li>
              ))}
            </ul>
            <button
              onClick={onGetStarted}
              className="bg-transparent border-2 border-[#1E1B4B] text-[#1E1B4B] cursor-pointer text-sm font-semibold py-2.5 px-6 rounded-lg font-[Inter,system-ui,sans-serif] hover:bg-slate-50 transition-colors"
            >
              Start as Teacher &rarr;
            </button>
          </article>
        </div>
      </section>

      {/* -- TRUST BADGES -- */}
      <section className="bg-stone-50 py-12 md:py-16 px-6 border-t border-slate-100" aria-label="Trust signals">
        <div className="max-w-[900px] mx-auto">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6 text-center">
            <div>
              <p className="text-3xl md:text-4xl font-bold text-[#1E1B4B] font-[Fraunces,Georgia,serif]">198</p>
              <p className="text-xs font-medium text-slate-500 mt-1">CBSE topics covered</p>
            </div>
            <div>
              <p className="text-3xl md:text-4xl font-bold text-[#1E1B4B] font-[Fraunces,Georgia,serif]">9</p>
              <p className="text-xs font-medium text-slate-500 mt-1">Subjects across Classes 1-5</p>
            </div>
            <div>
              <p className="text-3xl md:text-4xl font-bold text-[#1E1B4B] font-[Fraunces,Georgia,serif]">3</p>
              <p className="text-xs font-medium text-slate-500 mt-1">Difficulty levels per sheet</p>
            </div>
            <div>
              <p className="text-3xl md:text-4xl font-bold text-[#1E1B4B] font-[Fraunces,Georgia,serif]">100%</p>
              <p className="text-xs font-medium text-slate-500 mt-1">Maths answers verified by code</p>
            </div>
          </div>
        </div>
      </section>

      {/* -- 11. TESTIMONIALS -- */}
      {/* TODO: Replace with real testimonials after launch */}
      <section
        ref={addSectionRef(10)}
        className="section-fade-in bg-white py-12 md:py-20 px-6"
        aria-label="Testimonials"
      >
        <div className="max-w-[900px] mx-auto">
          <div className="text-center mb-8 md:mb-12">
            <p className="text-xs font-bold uppercase tracking-[0.1em] text-orange-500 mb-2.5">Built for CBSE parents</p>
            <h2 className="font-[Fraunces,Georgia,serif] text-[clamp(28px,4vw,40px)] font-normal text-slate-900 tracking-tight">
              Trusted by parents &amp; teachers
            </h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {TESTIMONIALS.map(t => (
              <article
                key={t.name}
                className="stagger-child bg-stone-50 border border-slate-200 rounded-2xl p-5 md:p-7 relative"
              >
                <Quote className="w-8 h-8 text-slate-200 mb-3" />
                <p className="text-sm leading-relaxed text-slate-600 italic mb-5">"{t.quote}"</p>
                <div className="flex items-center gap-3">
                  <div className={`w-9 h-9 rounded-full ${t.color} text-white flex items-center justify-center text-xs font-bold`}>
                    {t.initials}
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-slate-900">{t.name}</p>
                    <p className="text-xs text-slate-400">{t.role}</p>
                  </div>
                </div>
              </article>
            ))}
          </div>
          <p className="text-center text-xs text-slate-400 mt-5">Quotes are representative feedback from beta users.</p>
        </div>
      </section>

      {/* -- 12. FAQ SECTION -- */}
      <section
        ref={addSectionRef(11)}
        className="section-fade-in bg-white py-12 md:py-20 px-6"
        aria-label="Frequently asked questions"
        itemScope
        itemType="https://schema.org/FAQPage"
      >
        <div className="max-w-[720px] mx-auto">
          <div className="text-center mb-12">
            <p className="text-xs font-bold uppercase tracking-[0.1em] text-orange-500 mb-2.5">FAQ</p>
            <h2 className="font-[Fraunces,Georgia,serif] text-[clamp(28px,4vw,40px)] font-normal text-slate-900 tracking-tight">
              Frequently asked questions
            </h2>
          </div>
          <div className="flex flex-col gap-3">
            {FAQ_ITEMS.map((item, i) => (
              <div
                key={i}
                itemScope
                itemProp="mainEntity"
                itemType="https://schema.org/Question"
                className="border border-slate-200 rounded-xl overflow-hidden bg-white"
              >
                <button
                  onClick={() => setOpenFaq(openFaq === i ? null : i)}
                  className="w-full flex items-center justify-between p-5 text-left bg-transparent border-none cursor-pointer gap-4"
                  aria-expanded={openFaq === i}
                >
                  <span itemProp="name" className="text-sm font-semibold text-slate-900 font-[Inter,system-ui,sans-serif]">{item.q}</span>
                  <ChevronDown className={`w-5 h-5 text-slate-400 flex-shrink-0 transition-transform duration-200 ${openFaq === i ? 'rotate-180' : ''}`} />
                </button>
                <div
                  className={`overflow-hidden transition-all duration-300 ${openFaq === i ? 'max-h-[500px] opacity-100' : 'max-h-0 opacity-0'}`}
                  itemScope
                  itemProp="acceptedAnswer"
                  itemType="https://schema.org/Answer"
                >
                  <p itemProp="text" className="px-5 pb-5 pt-0 text-sm leading-relaxed text-slate-500 m-0">
                    {item.a}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* -- 13. CTA + FOOTER -- */}
      <section
        ref={addSectionRef(12)}
        className="section-fade-in lp-cta-section relative py-12 md:py-20 px-6 text-center overflow-hidden"
        aria-label="Call to action"
      >
        <div className="lp-dot-grid" />
        <div className="relative z-10 max-w-[560px] mx-auto">
          <h2 className="font-[Fraunces,Georgia,serif] text-[clamp(28px,4.5vw,44px)] font-normal mb-4 leading-tight tracking-tight" style={{ color: '#FFFFFF' }}>
            Generate your first worksheet in 30 seconds
          </h2>
          <p className="text-base mb-8 leading-relaxed" style={{ color: 'rgba(255,255,255,0.7)' }}>
            No setup. No credit card. Pick a topic and go.
          </p>
          <button
            onClick={onGetStarted}
            className="bg-orange-500 hover:bg-orange-600 border-none text-white cursor-pointer text-base font-semibold py-4 px-10 rounded-xl font-[Inter,system-ui,sans-serif] transition-all duration-300 shadow-lg shadow-orange-500/30 hover:shadow-xl hover:shadow-orange-500/40 hover:-translate-y-0.5 inline-flex items-center gap-2"
          >
            Generate a free worksheet
            <ArrowRight className="w-5 h-5" />
          </button>
          <p className="text-xs text-white/30 mt-5">
            Your data stays private. No ads, no spam, no sharing.
          </p>
          <p className="text-sm text-white/40 mt-3 flex items-center justify-center gap-1.5">
            <Mail className="w-4 h-4" />
            hello@skolar.in
          </p>
        </div>
      </section>

      <footer className="bg-[#0F0E2A] py-8 px-6" aria-label="Footer">
        <div className="max-w-[1000px] mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-6">
            <span className="font-[Fraunces,Georgia,serif] text-lg text-white/70">Skolar</span>
            <div className="hidden md:flex items-center gap-5 text-xs text-white/35">
              <button onClick={() => scrollTo('how')} className="bg-transparent border-none cursor-pointer text-white/35 hover:text-white/60 transition-colors font-[Inter,system-ui,sans-serif] text-xs">How it works</button>
              <button onClick={() => scrollTo('subjects')} className="bg-transparent border-none cursor-pointer text-white/35 hover:text-white/60 transition-colors font-[Inter,system-ui,sans-serif] text-xs">Subjects</button>
              <button onClick={() => scrollTo('pricing')} className="bg-transparent border-none cursor-pointer text-white/35 hover:text-white/60 transition-colors font-[Inter,system-ui,sans-serif] text-xs">Pricing</button>
            </div>
          </div>
          <div className="flex items-center gap-4 text-xs text-white/35">
            <span>hello@skolar.in</span>
            <span>&middot;</span>
            <span>skolar.in</span>
            <span>&middot;</span>
            <span>&copy; 2025–2026</span>
          </div>
        </div>
      </footer>

      {/* Floating CTA — desktop pill */}
      {showFloatingCta && (
        <>
          <button
            onClick={onGetStarted}
            className="hidden md:inline-flex fixed bottom-24 right-6 z-40 items-center gap-2 bg-orange-500 hover:bg-orange-600 text-white text-sm font-semibold py-3 px-6 rounded-full shadow-lg shadow-orange-500/30 transition-all duration-300 hover:-translate-y-0.5 cursor-pointer border-none font-[Inter,system-ui,sans-serif]"
            style={{ animation: 'float-cta-in 0.4s ease-out both' }}
          >
            <Sparkles className="w-4 h-4" />
            Try free — takes 30 sec
          </button>

          {/* Mobile bottom bar */}
          <div
            className="md:hidden fixed bottom-0 left-0 right-0 z-50 bg-[#1E1B4B] px-4 py-3 flex items-center justify-between border-t border-white/10"
            style={{ paddingBottom: 'max(0.75rem, env(safe-area-inset-bottom))' , animation: 'float-cta-in 0.3s ease-out both' }}
          >
            <div>
              <p className="text-xs font-semibold text-white">CBSE worksheets, free</p>
              <p className="text-[10px] text-white/50">198 topics · 9 subjects</p>
            </div>
            <button
              onClick={onGetStarted}
              className="bg-white text-[#1E1B4B] text-xs font-bold py-2 px-4 rounded-lg border-none cursor-pointer font-[Inter,system-ui,sans-serif] whitespace-nowrap"
            >
              Start free →
            </button>
          </div>
        </>
      )}

      {scrolled && !showFloatingCta && (
        <button
          onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
          className="fixed bottom-6 right-6 z-40 w-10 h-10 rounded-full bg-[#1E1B4B] text-white shadow-lg flex items-center justify-center hover:bg-[#312E81] transition-colors"
          aria-label="Back to top"
        >
          <ChevronDown className="w-5 h-5 rotate-180" />
        </button>
      )}

      {/* -- SCROLL-REVEAL ANIMATION CSS -- */}
      <style>{`
        .section-fade-in {
          opacity: 0;
          transform: translateY(24px);
          transition: opacity 0.7s ease-out, transform 0.7s ease-out;
        }
        .section-fade-in.visible {
          opacity: 1;
          transform: translateY(0);
        }
        @keyframes float-cta-in {
          from { opacity: 0; transform: translateY(16px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @media (prefers-reduced-motion: reduce) {
          .section-fade-in {
            opacity: 1;
            transform: none;
            transition: none;
          }
        }
      `}</style>
    </div>
  )
}
