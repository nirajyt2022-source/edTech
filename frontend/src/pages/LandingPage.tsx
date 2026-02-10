import { Button } from '@/components/ui/button'

interface Props {
  onGetStarted: () => void
  onSignIn: () => void
}

export default function LandingPage({ onGetStarted, onSignIn }: Props) {
  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Header */}
      <header className="px-6 py-5 flex items-center justify-between max-w-5xl mx-auto w-full">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-primary flex items-center justify-center">
            <svg className="w-5 h-5 text-primary-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
            </svg>
          </div>
          <span className="text-xl font-semibold tracking-tight">
            <span className="text-foreground">Practice</span>
            <span className="text-primary">Craft</span>
          </span>
        </div>
        <Button variant="ghost" size="sm" onClick={onSignIn}>
          Sign in
        </Button>
      </header>

      {/* Hero */}
      <main className="flex-1 flex flex-col items-center justify-center px-6 pb-24 bg-paper-texture">
        <div className="max-w-xl text-center space-y-6">
          <h1 className="text-3xl sm:text-4xl md:text-5xl font-semibold text-foreground leading-tight tracking-tight">
            Create calm, syllabus-aligned practice for Classes 1–5.
          </h1>
          <p className="text-base sm:text-lg text-muted-foreground leading-relaxed">
            CBSE-aligned. Print-ready. Designed for parents and teachers.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2">
            <Button size="lg" onClick={onGetStarted} className="w-full sm:w-auto px-8">
              Create today's practice
            </Button>
            <Button variant="outline" size="lg" onClick={onSignIn} className="w-full sm:w-auto px-8">
              Sign in
            </Button>
          </div>
        </div>
      </main>

      {/* Trust line */}
      <footer className="px-6 py-8 text-center">
        <p className="text-xs text-muted-foreground">
          Aligned with NCERT and commonly followed CBSE school curricula.
        </p>
      </footer>
    </div>
  )
}
