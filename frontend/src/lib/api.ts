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
