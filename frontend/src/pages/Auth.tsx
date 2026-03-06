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
  const [showPassword, setShowPassword] = useState(false)
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
            className="text-4xl font-bold mb-3 font-fraunces"
            style={{ color: '#FFFFFF' }}
          >
            Skolar
          </h1>
          <p className="text-lg mb-12" style={{ color: 'rgba(255,255,255,0.7)' }}>
            CBSE worksheets with verified answers.
          </p>

          {/* Feature checkpoints */}
          <div className="space-y-4">
            {[
              { text: 'Every maths answer verified by code', detail: 'No wrong answers — unlike free worksheet sites' },
              { text: '198 topics across 9 subjects', detail: 'Maths, English, Hindi, EVS, Science & more' },
              { text: '3 difficulty levels per worksheet', detail: 'Foundation, Application, and Stretch questions' },
              { text: 'Grade answers from a photo', detail: 'Snap filled worksheet — get scores instantly' },
              { text: 'Hindi worksheets in Devanagari', detail: 'Proper conjuncts, not broken characters' },
              { text: 'Free to start, no card needed', detail: '5 worksheets per month at no cost' },
            ].map((item) => (
              <div key={item.text} className="flex items-start gap-3">
                <svg className="w-5 h-5 mt-0.5 shrink-0" style={{ color: '#F97316' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                </svg>
                <div>
                  <span className="text-sm font-medium block" style={{ color: 'rgba(255,255,255,0.9)' }}>
                    {item.text}
                  </span>
                  <span className="text-xs" style={{ color: 'rgba(255,255,255,0.45)' }}>
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
            <p className="text-[13px] text-white/80 leading-relaxed mb-2">
              &ldquo;Meera has 45 marbles. She wins 28 more. How many does she have now?&rdquo;
            </p>
            <div className="flex items-center gap-2">
              <span className="text-[9px] font-bold uppercase px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300">Foundation</span>
              <span className="text-[10px] text-white/40">Class 2 &middot; Maths</span>
            </div>
          </div>
          <div className="flex items-center gap-6 mt-4">
            <div className="text-center">
              <div className="text-lg font-bold text-white/80" >198</div>
              <div className="text-[9px] uppercase tracking-wider text-white/30 font-medium">Topics</div>
            </div>
            <div className="text-center">
              <div className="text-lg font-bold text-white/80" >9</div>
              <div className="text-[9px] uppercase tracking-wider text-white/30 font-medium">Subjects</div>
            </div>
            <div className="text-center">
              <div className="text-lg font-bold text-white/80" >5</div>
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
              className="text-2xl font-bold font-fraunces"
              style={{ color: '#1E1B4B' }}
            >
              Skolar
            </h2>
          </div>

          {/* Heading — centered */}
          <h3
            className="text-2xl font-semibold mb-1 text-center font-fraunces"
            style={{ color: '#1E293B' }}
          >
            {mode === 'signup' ? 'Create your free account' : 'Welcome back'}
          </h3>
          <p className="text-sm mb-6 text-center" style={{ color: '#64748B' }}>
            {mode === 'signup' ? '5 free worksheets every month — no card needed' : 'Sign in to continue'}
          </p>

          {/* Google sign-in — PRIMARY */}
          <button
            type="button"
            onClick={handleGoogleSignIn}
            className="w-full flex items-center justify-center gap-3 py-3 px-4 rounded-xl transition-all text-sm font-semibold cursor-pointer shadow-sm hover:shadow-md"
            style={{
              border: '1px solid #E2E8F0',
              backgroundColor: '#FFFFFF',
              color: '#1E293B',
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
            {mode === 'signup' ? 'Sign up with Google' : 'Continue with Google'}
          </button>
          <p className="text-center text-[11px] mt-2 mb-1" style={{ color: '#94A3B8' }}>
            Fastest way — one tap on mobile
          </p>

          {/* Divider */}
          <div className="relative my-5">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full" style={{ borderTop: '1px solid #E2E8F0' }} />
            </div>
            <div className="relative flex justify-center text-xs" style={{ color: '#94A3B8' }}>
              <span className="px-2" style={{ backgroundColor: '#FAFAF9' }}>or use email instead</span>
            </div>
          </div>

          {/* Email/password form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            {mode === 'signup' && (
              <div className="space-y-2 animate-fade-in">
                <Label htmlFor="name" style={{ color: '#1E293B' }}>Name</Label>
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
              <Label htmlFor="email" style={{ color: '#1E293B' }}>Email</Label>
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
              <Label htmlFor="password" style={{ color: '#1E293B' }}>Password</Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  placeholder="6+ characters"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={6}
                  className="rounded-xl pr-10"
                  style={{ backgroundColor: '#FFFFFF', borderColor: '#E2E8F0' }}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 bg-transparent border-none cursor-pointer p-0"
                  style={{ color: '#94A3B8' }}
                  tabIndex={-1}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? (
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
                    </svg>
                  ) : (
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
                      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                  )}
                </button>
              </div>
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
              style={{ backgroundColor: '#1E1B4B' }}
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <span className="spinner !w-4 !h-4 !border-white/30 !border-t-white" />
                  {mode === 'login' ? 'Signing in...' : 'Creating account...'}
                </span>
              ) : (
                mode === 'login' ? 'Sign in' : 'Create free account'
              )}
            </Button>
          </form>

          <div className="mt-5 text-center text-sm" >
            <span style={{ color: '#64748B' }}>
              {mode === 'login' ? "Don't have an account? " : 'Already have an account? '}
            </span>
            <button
              type="button"
              onClick={toggleMode}
              className="font-medium transition-colors cursor-pointer bg-transparent border-none hover:underline"
              style={{ color: '#3730A3' }}
            >
              {mode === 'login' ? 'Sign up free' : 'Sign in'}
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
                <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
              </svg>
              <span>Verified answers</span>
            </div>
            <span style={{ color: '#CBD5E1' }}>&bull;</span>
            <div className="flex items-center gap-1.5">
              <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M5.75 2a.75.75 0 01.75.75V4h7V2.75a.75.75 0 011.5 0V4h.25A2.75 2.75 0 0118 6.75v8.5A2.75 2.75 0 0115.25 18H4.75A2.75 2.75 0 012 15.25v-8.5A2.75 2.75 0 014.75 4H5V2.75A.75.75 0 015.75 2zm-1 5.5c-.69 0-1.25.56-1.25 1.25v6.5c0 .69.56 1.25 1.25 1.25h10.5c.69 0 1.25-.56 1.25-1.25v-6.5c0-.69-.56-1.25-1.25-1.25H4.75z" clipRule="evenodd" />
              </svg>
              <span>No card needed</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
