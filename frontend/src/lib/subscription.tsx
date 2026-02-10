import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from 'react'
import { api } from './api'
import { useAuth } from './auth'

export interface SubscriptionStatus {
  tier: 'free' | 'paid'
  worksheets_generated_this_month: number
  worksheets_remaining: number | null
  can_generate: boolean
  can_use_regional_languages: boolean
  can_upload_syllabus: boolean
  can_use_multi_child: boolean
}

interface SubscriptionContextType {
  status: SubscriptionStatus | null
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  incrementUsage: () => Promise<void>
  upgrade: () => Promise<void>
}

const defaultFreeStatus: SubscriptionStatus = {
  tier: 'free',
  worksheets_generated_this_month: 0,
  worksheets_remaining: 3,
  can_generate: true,
  can_use_regional_languages: false,
  can_upload_syllabus: false,
  can_use_multi_child: false,
}

const SubscriptionContext = createContext<SubscriptionContextType | undefined>(undefined)

export function SubscriptionProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SubscriptionStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const { user } = useAuth()

  const fetchStatus = useCallback(async () => {
    if (!user) {
      setStatus(null)
      setLoading(false)
      return
    }

    setLoading(true)
    setError(null)
    try {
      const response = await api.get('/api/subscription/status')
      setStatus(response.data)
    } catch (err) {
      // If subscription doesn't exist yet, use default free status
      setStatus(defaultFreeStatus)
      console.error('Failed to fetch subscription:', err)
    } finally {
      setLoading(false)
    }
  }, [user])

  useEffect(() => {
    fetchStatus()
  }, [fetchStatus])

  const incrementUsage = async () => {
    try {
      const response = await api.post('/api/subscription/increment-usage')
      if (response.data.remaining !== undefined) {
        setStatus(prev => prev ? {
          ...prev,
          worksheets_generated_this_month: response.data.new_count,
          worksheets_remaining: response.data.remaining,
          can_generate: response.data.remaining > 0,
        } : null)
      }
    } catch (err) {
      console.error('Failed to increment usage:', err)
    }
  }

  const upgrade = async () => {
    try {
      await api.post('/api/subscription/upgrade')
      await fetchStatus()
    } catch (err) {
      setError('Failed to upgrade')
      throw err
    }
  }

  return (
    <SubscriptionContext.Provider value={{
      status,
      loading,
      error,
      refresh: fetchStatus,
      incrementUsage,
      upgrade,
    }}>
      {children}
    </SubscriptionContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useSubscription() {
  const context = useContext(SubscriptionContext)
  if (context === undefined) {
    throw new Error('useSubscription must be used within a SubscriptionProvider')
  }
  return context
}
