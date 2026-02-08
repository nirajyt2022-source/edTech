import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from 'react'
import { api } from './api'
import { useAuth } from './auth'

export interface TeacherClass {
  id: string
  user_id: string
  name: string
  grade: string
  subject: string
  board: string
  syllabus_source: 'cbse' | 'custom'
  custom_syllabus: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

interface CreateClassData {
  name: string
  grade: string
  subject: string
  board?: string
  syllabus_source?: string
  custom_syllabus?: Record<string, unknown>
}

interface UpdateClassData {
  name?: string
  grade?: string
  subject?: string
  board?: string
  syllabus_source?: string
  custom_syllabus?: Record<string, unknown>
}

interface ClassesContextType {
  classes: TeacherClass[]
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  createClass: (data: CreateClassData) => Promise<TeacherClass>
  updateClass: (id: string, data: UpdateClassData) => Promise<TeacherClass>
  deleteClass: (id: string) => Promise<void>
}

const ClassesContext = createContext<ClassesContextType | undefined>(undefined)

export function ClassesProvider({ children }: { children: ReactNode }) {
  const [classList, setClassList] = useState<TeacherClass[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const { user } = useAuth()

  const fetchClasses = useCallback(async () => {
    if (!user) {
      setClassList([])
      setLoading(false)
      return
    }

    setLoading(true)
    setError(null)
    try {
      const response = await api.get('/api/classes/')
      setClassList(response.data.classes || [])
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status?: number; data?: { detail?: string } } }
      if (axiosErr.response?.status === 500 && axiosErr.response?.data?.detail?.includes('relation')) {
        setError('Database not set up. Please run the SQL schema in Supabase.')
      } else {
        setError(null)
      }
      setClassList([])
      console.error(err)
    } finally {
      setLoading(false)
    }
  }, [user])

  useEffect(() => {
    fetchClasses()
  }, [fetchClasses])

  const createClass = async (data: CreateClassData): Promise<TeacherClass> => {
    const response = await api.post('/api/classes/', data)
    const newClass = response.data.class
    setClassList(prev => [...prev, newClass])
    return newClass
  }

  const updateClass = async (id: string, data: UpdateClassData): Promise<TeacherClass> => {
    const response = await api.put(`/api/classes/${id}`, data)
    const updatedClass = response.data.class
    setClassList(prev => prev.map(c => c.id === id ? updatedClass : c))
    return updatedClass
  }

  const deleteClass = async (id: string): Promise<void> => {
    await api.delete(`/api/classes/${id}`)
    setClassList(prev => prev.filter(c => c.id !== id))
  }

  return (
    <ClassesContext.Provider value={{
      classes: classList,
      loading,
      error,
      refresh: fetchClasses,
      createClass,
      updateClass,
      deleteClass,
    }}>
      {children}
    </ClassesContext.Provider>
  )
}

export function useClasses() {
  const context = useContext(ClassesContext)
  if (context === undefined) {
    throw new Error('useClasses must be used within a ClassesProvider')
  }
  return context
}
