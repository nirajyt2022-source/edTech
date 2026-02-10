import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from 'react'
import { api } from './api'
import { useAuth } from './auth'

export interface UserProfile {
  user_id: string
  role: 'parent' | 'teacher'
  active_role: 'parent' | 'teacher'
  subjects: string[]
  grades: string[]
  school_name: string | null
  created_at: string
  updated_at: string
}

interface TeacherFields {
  subjects: string[]
  grades: string[]
  school_name?: string
}

interface ProfileContextType {
  profile: UserProfile | null
  loading: boolean
  needsRoleSelection: boolean
  activeRole: 'parent' | 'teacher' | null
  setRole: (role: 'parent' | 'teacher', teacherFields?: TeacherFields) => Promise<void>
  switchRole: (role: 'parent' | 'teacher') => Promise<void>
  updateTeacherProfile: (fields: TeacherFields) => Promise<void>
  refresh: () => Promise<void>
}

const ProfileContext = createContext<ProfileContextType | undefined>(undefined)

export function ProfileProvider({ children }: { children: ReactNode }) {
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const { user } = useAuth()

  const fetchProfile = useCallback(async () => {
    if (!user) {
      setProfile(null)
      setLoading(false)
      return
    }

    setLoading(true)
    try {
      const response = await api.get('/api/users/profile')
      setProfile(response.data.profile)
    } catch (err) {
      console.error('Failed to fetch profile:', err)
      setProfile(null)
    } finally {
      setLoading(false)
    }
  }, [user])

  useEffect(() => {
    fetchProfile()
  }, [fetchProfile])

  const needsRoleSelection = !loading && user != null && profile == null

  const activeRole = profile?.active_role ?? null

  const setRole = async (role: 'parent' | 'teacher', teacherFields?: TeacherFields) => {
    const payload = {
      role,
      active_role: role,
      subjects: teacherFields?.subjects ?? [],
      grades: teacherFields?.grades ?? [],
      school_name: teacherFields?.school_name ?? null,
    }
    const response = await api.put('/api/users/profile', payload)
    setProfile(response.data.profile)
  }

  const switchRole = async (role: 'parent' | 'teacher') => {
    // Optimistic update
    setProfile(prev => prev ? { ...prev, active_role: role } : null)
    try {
      const response = await api.post('/api/users/switch-role', { active_role: role })
      setProfile(response.data.profile)
    } catch (err) {
      // Revert on failure
      await fetchProfile()
      throw err
    }
  }

  const updateTeacherProfile = async (fields: TeacherFields) => {
    if (!profile) return
    const payload = {
      role: profile.role,
      subjects: fields.subjects,
      grades: fields.grades,
      school_name: fields.school_name ?? profile.school_name,
    }
    const response = await api.put('/api/users/profile', payload)
    setProfile(response.data.profile)
  }

  return (
    <ProfileContext.Provider value={{
      profile,
      loading,
      needsRoleSelection,
      activeRole,
      setRole,
      switchRole,
      updateTeacherProfile,
      refresh: fetchProfile,
    }}>
      {children}
    </ProfileContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useProfile() {
  const context = useContext(ProfileContext)
  if (context === undefined) {
    throw new Error('useProfile must be used within a ProfileProvider')
  }
  return context
}
