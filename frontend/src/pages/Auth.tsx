import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/lib/auth'

type AuthMode = 'login' | 'signup'

export default function Auth() {
  const [mode, setMode] = useState<AuthMode>('login')
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
        setError(error.message)
      }
    } else {
      const { error } = await signUp(email, password, name)
      if (error) {
        setError(error.message)
      } else {
        setMessage('Check your email to confirm your account!')
      }
    }

    setLoading(false)
  }

  const toggleMode = () => {
    setMode(mode === 'login' ? 'signup' : 'login')
    setError('')
    setMessage('')
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <CardTitle className="text-2xl">
            {mode === 'login' ? 'Welcome Back' : 'Create Account'}
          </CardTitle>
          <CardDescription>
            {mode === 'login'
              ? 'Sign in to access your worksheets'
              : 'Sign up to start creating worksheets'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {mode === 'signup' && (
              <div className="space-y-2">
                <Label htmlFor="name">Name</Label>
                <Input
                  id="name"
                  type="text"
                  placeholder="Your name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={6}
              />
            </div>

            {error && (
              <div className="p-3 bg-red-50 text-red-700 rounded-md text-sm">
                {error}
              </div>
            )}

            {message && (
              <div className="p-3 bg-green-50 text-green-700 rounded-md text-sm">
                {message}
              </div>
            )}

            <Button type="submit" className="w-full" disabled={loading}>
              {loading
                ? 'Please wait...'
                : mode === 'login'
                ? 'Sign In'
                : 'Create Account'}
            </Button>
          </form>

          <div className="mt-6 text-center text-sm">
            <span className="text-gray-600">
              {mode === 'login' ? "Don't have an account? " : 'Already have an account? '}
            </span>
            <button
              type="button"
              onClick={toggleMode}
              className="text-blue-600 hover:underline font-medium"
            >
              {mode === 'login' ? 'Sign up' : 'Sign in'}
            </button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
