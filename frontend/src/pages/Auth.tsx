import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/lib/auth'
import { supabase } from '@/lib/supabase'

type AuthMode = 'login' | 'signup'

interface Props {
  defaultMode?: AuthMode
  onBack?: () => void
}

const AUTH_ERRORS: Record<string, string> = {
  'Invalid login credentials': 'Wrong email or password.',
  'Email not confirmed': 'Check your inbox for a confirmation email.',
  'User already registered': 'Account exists. Sign in instead.',
  'Email rate limit exceeded': 'Too many attempts. Wait 60 seconds.',
  'Password should be at least 6 characters': 'Password must be at least 6 characters.',
}

function getReadableError(message: string): string {
  return AUTH_ERRORS[message] || message
}

export default function Auth({ defaultMode = 'login', onBack }: Props) {
  const [mode, setMode] = useState<AuthMode>(defaultMode)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const { signIn, signUp } = useAuth()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    setMessage('')

    if (mode === 'login') {
      const { error } = await signIn(email, password)
      if (error) {
        setError(getReadableError(error.message))
      }
    } else {
      const { error } = await signUp(email, password, name)
      if (error) {
        setError(getReadableError(error.message))
      } else {
        setMessage('Check your email to confirm your account!')
      }
    }

    setLoading(false)
  }

  const handleGoogleSignIn = async () => {
    const siteUrl = import.meta.env.VITE_SITE_URL || window.location.origin
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: `${siteUrl}/`,
        queryParams: {
          access_type: 'offline',
          prompt: 'consent',
        },
      },
    })
    if (error) {
      setError('Google sign-in failed. Try email instead.')
    }
  }

  const handleForgotPassword = async () => {
    if (!email) {
      setError('Enter your email first.')
      return
    }
    setError('')
    const { error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/reset-password`,
    })
    if (error) {
      setError(getReadableError(error.message))
    } else {
      setMessage('Reset link sent! Check your inbox.')
    }
  }

  const toggleMode = () => {
    setMode(mode === 'login' ? 'signup' : 'login')
    setError('')
    setMessage('')
  }

  return (
    <div className="min-h-screen flex" style={{ backgroundColor: '#FAFAF9' }}>
      {/* LEFT PANEL — desktop only */}
      <div
        className="hidden lg:flex lg:w-[480px] xl:w-[520px] flex-col justify-between p-10 xl:p-12 shrink-0"
        style={{ backgroundColor: '#1E1B4B' }}
      >
        <div>
          {/* Back button */}
          {onBack && (
            <button
              onClick={onBack}
              className="flex items-center gap-1.5 text-sm mb-10 transition-colors cursor-pointer bg-transparent border-none"
              style={{ color: 'rgba(255,255,255,0.6)' }}
              onMouseEnter={(e) => (e.currentTarget.style.color = 'rgba(255,255,255,0.9)')}
              onMouseLeave={(e) => (e.currentTarget.style.color = 'rgba(255,255,255,0.6)')}
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
              </svg>
              Back
            </button>
          )}

          {/* Wordmark */}
          <h1
            className="text-4xl font-bold mb-3"
            style={{ fontFamily: "'Fraunces', serif", color: '#FFFFFF' }}
          >
            Skolar
          </h1>
          <p className="text-lg mb-12" style={{ color: 'rgba(255,255,255,0.7)', fontFamily: "'Inter', sans-serif" }}>
            Practice that knows your syllabus
          </p>

          {/* Feature checkpoints */}
          <div className="space-y-4">
            {[
              { text: '198 topics across 9 subjects', detail: 'Maths, English, Hindi, EVS, Science & more' },
              { text: 'Three difficulty tiers per worksheet', detail: 'Foundation, Application & Stretch' },
              { text: 'Print-ready PDFs with answer keys', detail: 'Download and print instantly' },
              { text: 'Mastery tracking & progress insights', detail: 'See exactly where your child stands' },
              { text: 'Free to start, no card needed', detail: '5 worksheets per month at no cost' },
            ].map((item) => (
              <div key={item.text} className="flex items-start gap-3">
                <svg className="w-5 h-5 mt-0.5 shrink-0" style={{ color: '#F97316' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                </svg>
                <div>
                  <span className="text-sm font-medium block" style={{ color: 'rgba(255,255,255,0.9)', fontFamily: "'Inter', sans-serif" }}>
                    {item.text}
                  </span>
                  <span className="text-xs" style={{ color: 'rgba(255,255,255,0.45)', fontFamily: "'Inter', sans-serif" }}>
                    {item.detail}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Sample mini worksheet card */}
        <div className="mt-auto pt-8">
          <div className="bg-white/[0.08] border border-white/[0.1] rounded-xl p-4 backdrop-blur-sm">
            <div className="flex items-center gap-2 mb-3">
              <div className="w-6 h-6 rounded-md bg-orange-500/20 flex items-center justify-center">
                <svg className="w-3 h-3 text-orange-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                </svg>
              </div>
              <span className="text-xs font-medium text-white/60">Sample worksheet</span>
            </div>
            <p className="text-[13px] text-white/80 leading-relaxed mb-2" style={{ fontFamily: "'Inter', sans-serif" }}>
              &ldquo;Meera has 45 marbles. She wins 28 more. How many does she have now?&rdquo;
            </p>
            <div className="flex items-center gap-2">
              <span className="text-[9px] font-bold uppercase px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300">Foundation</span>
              <span className="text-[10px] text-white/40">Class 2 &middot; Maths</span>
            </div>
          </div>
          <div className="flex items-center gap-6 mt-4">
            <div className="text-center">
              <div className="text-lg font-bold text-white/80" style={{ fontFamily: "'Inter', sans-serif" }}>198</div>
              <div className="text-[9px] uppercase tracking-wider text-white/30 font-medium">Topics</div>
            </div>
            <div className="text-center">
              <div className="text-lg font-bold text-white/80" style={{ fontFamily: "'Inter', sans-serif" }}>9</div>
              <div className="text-[9px] uppercase tracking-wider text-white/30 font-medium">Subjects</div>
            </div>
            <div className="text-center">
              <div className="text-lg font-bold text-white/80" style={{ fontFamily: "'Inter', sans-serif" }}>5</div>
              <div className="text-[9px] uppercase tracking-wider text-white/30 font-medium">Classes</div>
            </div>
          </div>
        </div>
      </div>

      {/* RIGHT PANEL */}
      <div className="flex-1 flex flex-col items-center justify-center px-6 py-12 relative">
        <div className="w-full max-w-sm animate-fade-in">
          {/* Mobile back button */}
          {onBack && (
            <button
              onClick={onBack}
              className="lg:hidden flex items-center gap-1.5 text-sm mb-6 transition-colors cursor-pointer bg-transparent border-none"
              style={{ color: '#1E1B4B' }}
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
              </svg>
              Back
            </button>
          )}

          {/* Small Skolar logo at top — centered */}
          <div className="mb-8 text-center">
            <h2
              className="text-2xl font-bold"
              style={{ fontFamily: "'Fraunces', serif", color: '#1E1B4B' }}
            >
              Skolar
            </h2>
          </div>

          {/* Heading — centered */}
          <h3
            className="text-2xl font-semibold mb-1 text-center"
            style={{ fontFamily: "'Fraunces', serif", color: '#1E293B' }}
          >
            {mode === 'signup' ? 'Create your account' : 'Welcome back'}
          </h3>
          <p className="text-sm mb-6 text-center" style={{ color: '#64748B', fontFamily: "'Inter', sans-serif" }}>
            {mode === 'signup' ? 'Start with 5 free worksheets — no card needed' : 'Sign in to your workspace'}
          </p>

          {/* Google sign-in */}
          <button
            type="button"
            onClick={handleGoogleSignIn}
            className="w-full flex items-center justify-center gap-3 py-2.5 px-4 rounded-xl transition-colors text-sm font-medium cursor-pointer"
            style={{
              border: '1px solid #E2E8F0',
              backgroundColor: '#FFFFFF',
              color: '#1E293B',
              fontFamily: "'Inter', sans-serif",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#F8FAFC')}
            onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = '#FFFFFF')}
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24">
              <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4" />
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
              <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18A10.96 10.96 0 001 12c0 1.77.42 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05" />
              <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
            </svg>
            Continue with Google
          </button>

          {/* Divider */}
          <div className="relative my-5">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full" style={{ borderTop: '1px solid #E2E8F0' }} />
            </div>
            <div className="relative flex justify-center text-xs" style={{ color: '#94A3B8' }}>
              <span className="px-2" style={{ backgroundColor: '#FAFAF9' }}>or continue with email</span>
            </div>
          </div>

          {/* Email/password form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            {mode === 'signup' && (
              <div className="space-y-2 animate-fade-in">
                <Label htmlFor="name" style={{ color: '#1E293B', fontFamily: "'Inter', sans-serif" }}>Name</Label>
                <Input
                  id="name"
                  type="text"
                  placeholder="Your name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="rounded-xl"
                  style={{ backgroundColor: '#FFFFFF', borderColor: '#E2E8F0' }}
                />
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="email" style={{ color: '#1E293B', fontFamily: "'Inter', sans-serif" }}>Email</Label>
              <Input
                id="email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="rounded-xl"
                style={{ backgroundColor: '#FFFFFF', borderColor: '#E2E8F0' }}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="password" style={{ color: '#1E293B', fontFamily: "'Inter', sans-serif" }}>Password</Label>
              <Input
                id="password"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={6}
                className="rounded-xl"
                style={{ backgroundColor: '#FFFFFF', borderColor: '#E2E8F0' }}
              />
              {mode === 'login' && (
                <div className="flex justify-end mt-1">
                  <button
                    type="button"
                    onClick={handleForgotPassword}
                    className="text-xs hover:underline cursor-pointer bg-transparent border-none"
                    style={{ color: '#3730A3' }}
                  >
                    Forgot password?
                  </button>
                </div>
              )}
            </div>

            {error && (
              <div role="alert" className="p-3.5 rounded-lg text-sm flex items-start gap-2.5 animate-fade-in" style={{ backgroundColor: '#FEF2F2', border: '1px solid #FECACA', color: '#DC2626' }}>
                <svg className="w-4 h-4 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <span>{error}</span>
              </div>
            )}

            {message && (
              <div role="status" className="p-3.5 rounded-lg text-sm flex items-start gap-2.5 animate-fade-in" style={{ backgroundColor: '#F0FDF4', border: '1px solid #BBF7D0', color: '#166534' }}>
                <svg className="w-4 h-4 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>{message}</span>
              </div>
            )}

            <Button
              type="submit"
              className="w-full rounded-xl text-white"
              size="lg"
              disabled={loading}
              aria-busy={loading}
              style={{ backgroundColor: '#1E1B4B', fontFamily: "'Inter', sans-serif" }}
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <span className="spinner !w-4 !h-4 !border-white/30 !border-t-white" />
                  {mode === 'login' ? 'Signing in...' : 'Creating your account...'}
                </span>
              ) : (
                mode === 'login' ? 'Sign in' : 'Create account'
              )}
            </Button>
          </form>

          <div className="mt-5 text-center text-sm" style={{ fontFamily: "'Inter', sans-serif" }}>
            <span style={{ color: '#64748B' }}>
              {mode === 'login' ? "Don't have an account? " : 'Already have an account? '}
            </span>
            <button
              type="button"
              onClick={toggleMode}
              className="font-medium transition-colors cursor-pointer bg-transparent border-none hover:underline"
              style={{ color: '#3730A3' }}
            >
              {mode === 'login' ? 'Sign up' : 'Sign in'}
            </button>
          </div>

          {/* Trust indicators */}
          <div className="mt-8 flex flex-wrap justify-center gap-3 text-xs" style={{ color: '#94A3B8' }}>
            <div className="flex items-center gap-1.5">
              <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M10 1a4.5 4.5 0 00-4.5 4.5V9H5a2 2 0 00-2 2v6a2 2 0 002 2h10a2 2 0 002-2v-6a2 2 0 00-2-2h-.5V5.5A4.5 4.5 0 0010 1zm3 8V5.5a3 3 0 10-6 0V9h6z" clipRule="evenodd" />
              </svg>
              <span>Secure &amp; private</span>
            </div>
            <span style={{ color: '#CBD5E1' }}>&bull;</span>
            <div className="flex items-center gap-1.5">
              <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor">
                <path d="M10 1l2.928 6.472 6.572.574-4.928 4.428 1.428 6.526L10 15.5l-6 3.5 1.428-6.526L.5 8.046l6.572-.574L10 1z" />
              </svg>
              <span>AI-powered</span>
            </div>
            <span style={{ color: '#CBD5E1' }}>&bull;</span>
            <div className="flex items-center gap-1.5">
              <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M5.75 2a.75.75 0 01.75.75V4h7V2.75a.75.75 0 011.5 0V4h.25A2.75 2.75 0 0118 6.75v8.5A2.75 2.75 0 0115.25 18H4.75A2.75 2.75 0 012 15.25v-8.5A2.75 2.75 0 014.75 4H5V2.75A.75.75 0 015.75 2zm-1 5.5c-.69 0-1.25.56-1.25 1.25v6.5c0 .69.56 1.25 1.25 1.25h10.5c.69 0 1.25-.56 1.25-1.25v-6.5c0-.69-.56-1.25-1.25-1.25H4.75z" clipRule="evenodd" />
              </svg>
              <span>5 free worksheets</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
