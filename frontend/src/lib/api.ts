import axios from 'axios'
import { supabase } from './supabase'

const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export const api = axios.create({
  baseURL: apiUrl,
  headers: {
    'Content-Type': 'application/json',
  },
})

// ── Cached session token ─────────────────────────────────────────────────
// Avoids awaiting supabase.auth.getSession() on every single API request.
// The onAuthStateChange listener keeps it fresh on login/logout/refresh.
let _cachedToken: string | null = null

supabase.auth.getSession().then(({ data: { session } }) => {
  _cachedToken = session?.access_token ?? null
})

supabase.auth.onAuthStateChange((_event, session) => {
  _cachedToken = session?.access_token ?? null
})

// Request interceptor — synchronous when token is cached
api.interceptors.request.use(
  async (config) => {
    // Fast path: use cached token (no await)
    if (_cachedToken) {
      config.headers.Authorization = `Bearer ${_cachedToken}`
      return config
    }
    // Fallback: fetch session (first request before listener fires)
    const { data: { session } } = await supabase.auth.getSession()
    if (session?.access_token) {
      _cachedToken = session.access_token
      config.headers.Authorization = `Bearer ${session.access_token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor for handling errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Invalidate cache so next request re-fetches
      _cachedToken = null
      console.error('Unauthorized request')
    }
    return Promise.reject(error)
  }
)
