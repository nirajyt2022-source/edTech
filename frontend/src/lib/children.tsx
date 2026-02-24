import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from 'react'
import { api } from './api'
import { useAuth } from './auth'

export interface Child {
  id: string
  user_id: string
  name: string
  grade: string
  board: string | null
  notes: string | null
  created_at: string
  updated_at: string
}

interface CreateChildData {
  name: string
  grade: string
  board?: string
  notes?: string
}

interface UpdateChildData {
  name?: string
  grade?: string
  board?: string
  notes?: string
}

interface ChildrenContextType {
  children: Child[]
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  createChild: (data: CreateChildData) => Promise<Child>
  updateChild: (id: string, data: UpdateChildData) => Promise<Child>
  deleteChild: (id: string) => Promise<void>
  activeChildId: string | null
  activeChild: Child | null
  setActiveChildId: (id: string) => void
}

const ChildrenContext = createContext<ChildrenContextType | undefined>(undefined)

const ACTIVE_CHILD_KEY = 'skolar_active_child'

export function ChildrenProvider({ children: childrenProp }: { children: ReactNode }) {
  const [childrenList, setChildrenList] = useState<Child[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeChildId, setActiveChildIdState] = useState<string | null>(null)
  const { user } = useAuth()

  // Persist active child selection in localStorage
  const setActiveChildId = useCallback((id: string) => {
    setActiveChildIdState(id)
    localStorage.setItem(ACTIVE_CHILD_KEY, id)
  }, [])

  // Restore from localStorage or auto-select first child
  useEffect(() => {
    if (childrenList.length === 0) {
      setActiveChildIdState(null)
      return
    }

    const saved = localStorage.getItem(ACTIVE_CHILD_KEY)
    const savedExists = saved && childrenList.some(c => c.id === saved)

    if (savedExists) {
      setActiveChildIdState(saved)
    } else {
      // Auto-select first child (also handles deleted child case)
      setActiveChildIdState(childrenList[0].id)
      localStorage.setItem(ACTIVE_CHILD_KEY, childrenList[0].id)
    }
  }, [childrenList])

  const activeChild = childrenList.find(c => c.id === activeChildId) || null

  const fetchChildren = useCallback(async () => {
    if (!user) {
      setChildrenList([])
      setLoading(false)
      return
    }

    setLoading(true)
    setError(null)
    try {
      const response = await api.get('/api/children/')
      setChildrenList(response.data.children || [])
    } catch (err: unknown) {
      // Check if it's a database setup issue
      const axiosErr = err as { response?: { status?: number; data?: { detail?: string } } }
      if (axiosErr.response?.status === 500 && axiosErr.response?.data?.detail?.includes('relation')) {
        setError('Database not set up. Please run the SQL schema in Supabase.')
      } else {
        setError(null) // Don't show error for empty data
      }
      setChildrenList([])
      console.error(err)
    } finally {
      setLoading(false)
    }
  }, [user])

  useEffect(() => {
    fetchChildren()
  }, [fetchChildren])

  const createChild = async (data: CreateChildData): Promise<Child> => {
    const response = await api.post('/api/children/', data)
    const newChild = response.data.child
    setChildrenList(prev => [...prev, newChild])
    return newChild
  }

  const updateChild = async (id: string, data: UpdateChildData): Promise<Child> => {
    const response = await api.put(`/api/children/${id}`, data)
    const updatedChild = response.data.child
    setChildrenList(prev => prev.map(c => c.id === id ? updatedChild : c))
    return updatedChild
  }

  const deleteChild = async (id: string): Promise<void> => {
    await api.delete(`/api/children/${id}`)
    setChildrenList(prev => prev.filter(c => c.id !== id))
  }

  return (
    <ChildrenContext.Provider value={{
      children: childrenList,
      loading,
      error,
      refresh: fetchChildren,
      createChild,
      updateChild,
      deleteChild,
      activeChildId,
      activeChild,
      setActiveChildId,
    }}>
      {childrenProp}
    </ChildrenContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useChildren() {
  const context = useContext(ChildrenContext)
  if (context === undefined) {
    throw new Error('useChildren must be used within a ChildrenProvider')
  }
  return context
}
