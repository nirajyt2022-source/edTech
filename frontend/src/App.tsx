import { useState } from 'react'
import WorksheetGenerator from './pages/WorksheetGenerator'
import SyllabusUpload from './pages/SyllabusUpload'
import SavedWorksheets from './pages/SavedWorksheets'
import ChildProfiles from './pages/ChildProfiles'
import Auth from './pages/Auth'
import { Button } from '@/components/ui/button'
import { AuthProvider, useAuth } from '@/lib/auth'
import { ChildrenProvider } from '@/lib/children'
import './index.css'

type Page = 'generator' | 'syllabus' | 'saved' | 'children'

interface ParsedSyllabus {
  id: string
  name: string
  board?: string
  grade?: string
  subject?: string
  chapters: {
    name: string
    topics: { name: string; subtopics?: string[] }[]
  }[]
}

function AppContent() {
  const [currentPage, setCurrentPage] = useState<Page>('generator')
  const [syllabus, setSyllabus] = useState<ParsedSyllabus | null>(null)
  const { user, loading, signOut } = useAuth()

  // Show loading state
  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <p className="text-gray-600">Loading...</p>
      </div>
    )
  }

  // Show auth page if not logged in
  if (!user) {
    return <Auth />
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Navigation */}
      <nav className="bg-white shadow-sm print:hidden">
        <div className="max-w-4xl mx-auto px-4 py-3">
          <div className="flex items-center justify-between">
            <h1 className="text-xl font-bold text-gray-900">PracticeCraft AI</h1>
            <div className="flex items-center gap-4">
              <div className="flex gap-2">
                <Button
                  variant={currentPage === 'generator' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setCurrentPage('generator')}
                >
                  Create
                </Button>
                <Button
                  variant={currentPage === 'syllabus' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setCurrentPage('syllabus')}
                >
                  Syllabus
                </Button>
                <Button
                  variant={currentPage === 'saved' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setCurrentPage('saved')}
                >
                  Saved
                </Button>
                <Button
                  variant={currentPage === 'children' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setCurrentPage('children')}
                >
                  Children
                </Button>
              </div>

              {/* User Menu */}
              <div className="flex items-center gap-3 ml-4 pl-4 border-l">
                <span className="text-sm text-gray-600 hidden md:inline">
                  {user.user_metadata?.name || user.email}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => signOut()}
                >
                  Logout
                </Button>
              </div>
            </div>
          </div>
        </div>
      </nav>

      {/* Page Content */}
      {currentPage === 'generator' && (
        <WorksheetGenerator
          syllabus={syllabus}
          onClearSyllabus={() => setSyllabus(null)}
        />
      )}
      {currentPage === 'syllabus' && (
        <SyllabusUpload
          onSyllabusReady={(parsedSyllabus) => {
            setSyllabus(parsedSyllabus)
            setCurrentPage('generator')
          }}
        />
      )}
      {currentPage === 'saved' && <SavedWorksheets />}
      {currentPage === 'children' && <ChildProfiles />}
    </div>
  )
}

function App() {
  return (
    <AuthProvider>
      <ChildrenProvider>
        <AppContent />
      </ChildrenProvider>
    </AuthProvider>
  )
}

export default App
