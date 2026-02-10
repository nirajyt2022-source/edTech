import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'
import { api } from './api'

export interface EngagementStats {
  child_id: string
  total_stars: number
  current_streak: number
  longest_streak: number
  total_worksheets_completed: number
  last_activity_date: string | null
}

interface CompletionResult {
  stars_earned: number
  total_stars: number
  current_streak: number
  total_completed: number
}

interface EngagementContextType {
  stats: Record<string, EngagementStats>
  loading: boolean
  fetchStats: (childId: string) => Promise<EngagementStats | null>
  recordCompletion: (childId: string) => Promise<CompletionResult | null>
  lastCompletion: CompletionResult | null
  clearLastCompletion: () => void
}

const EngagementContext = createContext<EngagementContextType | undefined>(undefined)

export function EngagementProvider({ children }: { children: ReactNode }) {
  const [stats, setStats] = useState<Record<string, EngagementStats>>({})
  const [loading, setLoading] = useState(false)
  const [lastCompletion, setLastCompletion] = useState<CompletionResult | null>(null)

  const fetchStats = useCallback(async (childId: string): Promise<EngagementStats | null> => {
    if (!childId) return null

    setLoading(true)
    try {
      const response = await api.get(`/api/engagement/${childId}`)
      const engagementStats = response.data as EngagementStats
      setStats(prev => ({ ...prev, [childId]: engagementStats }))
      return engagementStats
    } catch (err) {
      console.error('Failed to fetch engagement:', err)
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  const recordCompletion = useCallback(async (childId: string): Promise<CompletionResult | null> => {
    if (!childId) return null

    try {
      const response = await api.post(`/api/engagement/${childId}/complete`)
      const result = response.data as CompletionResult
      setLastCompletion(result)

      // Update local stats
      setStats(prev => {
        const existing = prev[childId]
        if (existing) {
          return {
            ...prev,
            [childId]: {
              ...existing,
              total_stars: result.total_stars,
              current_streak: result.current_streak,
              total_worksheets_completed: result.total_completed,
            }
          }
        }
        return prev
      })

      return result
    } catch (err) {
      console.error('Failed to record completion:', err)
      return null
    }
  }, [])

  const clearLastCompletion = useCallback(() => {
    setLastCompletion(null)
  }, [])

  return (
    <EngagementContext.Provider value={{
      stats,
      loading,
      fetchStats,
      recordCompletion,
      lastCompletion,
      clearLastCompletion,
    }}>
      {children}
    </EngagementContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useEngagement() {
  const context = useContext(EngagementContext)
  if (context === undefined) {
    throw new Error('useEngagement must be used within an EngagementProvider')
  }
  return context
}
