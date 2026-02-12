import axios from 'axios'
import { supabase } from './supabase'

const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export const api = axios.create({
  baseURL: apiUrl,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor for adding auth token from Supabase
api.interceptors.request.use(
  async (config) => {
    // Get session from Supabase
    const { data: { session } } = await supabase.auth.getSession()
    if (session?.access_token) {
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
      // Handle unauthorized access - let the auth context handle logout
      console.error('Unauthorized request')
    }
    return Promise.reject(error)
  }
)

/**
 * Call v1 endpoint first; if it returns 404, retry on legacy path once.
 * Use for endpoints that have been migrated to /api/v1/worksheets/*.
 */
export async function apiV1WithFallback<T = unknown>(
  method: 'get' | 'post' | 'delete',
  legacyPath: string,
  data?: unknown,
  config?: Record<string, unknown>,
): Promise<{ data: T }> {
  const v1Path = legacyPath.replace('/api/worksheets/', '/api/v1/worksheets/')
  try {
    if (method === 'get') return await api.get(v1Path, config)
    if (method === 'delete') return await api.delete(v1Path, config)
    return await api.post(v1Path, data, config)
  } catch (err: unknown) {
    const axErr = err as { response?: { status?: number } }
    if (axErr.response?.status === 404) {
      // Fallback to legacy
      if (method === 'get') return await api.get(legacyPath, config)
      if (method === 'delete') return await api.delete(legacyPath, config)
      return await api.post(legacyPath, data, config)
    }
    throw err
  }
}
