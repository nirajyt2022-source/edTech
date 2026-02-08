import { useState } from 'react'
import WorksheetGenerator from './pages/WorksheetGenerator'
import SyllabusUpload from './pages/SyllabusUpload'
import SavedWorksheets from './pages/SavedWorksheets'
import ChildProfiles from './pages/ChildProfiles'
import Auth from './pages/Auth'
import RoleSelector from '@/components/RoleSelector'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Badge } from '@/components/ui/badge'
import { AuthProvider, useAuth } from '@/lib/auth'
import { ChildrenProvider } from '@/lib/children'
import { SubscriptionProvider, useSubscription } from '@/lib/subscription'
import { ProfileProvider, useProfile } from '@/lib/profile'
import { EngagementProvider } from '@/lib/engagement'
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

function UsageBadge() {
  const { status } = useSubscription()

  if (!status) return null

  if (status.tier === 'paid') {
    return (
      <span className="trust-badge">
        <svg viewBox="0 0 20 20" fill="currentColor">
          <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clipRule="evenodd" />
        </svg>
        Pro
      </span>
    )
  }

  const isExhausted = status.worksheets_remaining === 0
  const isLow = status.worksheets_remaining && status.worksheets_remaining <= 1

  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium transition-colors ${
      isExhausted
        ? 'bg-red-50 text-red-700 border border-red-200'
        : isLow
        ? 'bg-amber-50 text-amber-700 border border-amber-200'
        : 'bg-secondary text-secondary-foreground border border-border'
    }`}>
      <span className={`w-1.5 h-1.5 rounded-full ${
        isExhausted ? 'bg-red-500' : isLow ? 'bg-amber-500' : 'bg-primary'
      }`} />
      {status.worksheets_remaining}/{3} free
    </span>
  )
}

function AppContent() {
  const [currentPage, setCurrentPage] = useState<Page>('generator')
  const [syllabus, setSyllabus] = useState<ParsedSyllabus | null>(null)
  const { user, loading, signOut } = useAuth()
  const { activeRole, profile, switchRole } = useProfile()

  // Show loading state
  if (loading) {
    return (
      <div className="min-h-screen gradient-bg flex flex-col items-center justify-center gap-4">
        <div className="spinner" />
        <p className="text-muted-foreground font-medium animate-pulse">Loading your workspace...</p>
      </div>
    )
  }

  // Show auth page if not logged in
  if (!user) {
    return <Auth />
  }

  return (
    <div className="min-h-screen gradient-bg">
      <RoleSelector />
      {/* Navigation */}
      <nav className="bg-card/80 backdrop-blur-md border-b border-border sticky top-0 z-50 print:hidden">
        <div className="max-w-5xl mx-auto px-4 py-3">
          <div className="flex items-center justify-between">
            {/* Logo */}
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-primary to-primary/70 flex items-center justify-center shadow-sm">
                <svg className="w-5 h-5 text-primary-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                </svg>
              </div>
              <h1 className="text-xl font-semibold tracking-tight">
                <span className="text-primary">Practice</span>
                <span className="text-accent">Craft</span>
              </h1>
            </div>

            {/* Navigation Tabs */}
            <div className="flex items-center gap-1 bg-muted/50 p-1 rounded-xl">
              {[
                { id: 'generator' as Page, label: 'Create', icon: (
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456z" />
                  </svg>
                )},
                { id: 'syllabus' as Page, label: 'Syllabus', icon: (
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25" />
                  </svg>
                )},
                { id: 'saved' as Page, label: 'Saved', icon: (
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M17.593 3.322c1.1.128 1.907 1.077 1.907 2.185V21L12 17.25 4.5 21V5.507c0-1.108.806-2.057 1.907-2.185a48.507 48.507 0 0111.186 0z" />
                  </svg>
                )},
                { id: 'children' as Page, label: 'Children', icon: (
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
                  </svg>
                )},
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setCurrentPage(tab.id)}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                    currentPage === tab.id
                      ? 'bg-card text-primary shadow-sm'
                      : 'text-muted-foreground hover:text-foreground hover:bg-card/50'
                  }`}
                >
                  {tab.icon}
                  <span className="hidden sm:inline">{tab.label}</span>
                </button>
              ))}
            </div>

            {/* User Menu */}
            <div className="flex items-center gap-3">
              <UsageBadge />
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="sm" className="flex items-center gap-2 text-muted-foreground hover:text-foreground">
                    <div className="w-7 h-7 rounded-full bg-gradient-to-br from-primary/20 to-accent/20 flex items-center justify-center">
                      <span className="text-xs font-semibold text-primary">
                        {(user.user_metadata?.name || user.email || 'U')[0].toUpperCase()}
                      </span>
                    </div>
                    <span className="hidden md:inline max-w-[120px] truncate text-sm">
                      {user.user_metadata?.name || user.email}
                    </span>
                    {activeRole && (
                      <Badge variant="secondary" className="hidden md:inline-flex text-xs capitalize">
                        {activeRole}
                      </Badge>
                    )}
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
                    </svg>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-56">
                  <DropdownMenuLabel className="font-normal">
                    <div className="flex flex-col space-y-1">
                      <p className="text-sm font-medium">{user.user_metadata?.name || user.email}</p>
                      {activeRole && (
                        <p className="text-xs text-muted-foreground capitalize">
                          Active as {activeRole}
                        </p>
                      )}
                    </div>
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  {profile && (
                    <>
                      <DropdownMenuItem
                        onClick={() => switchRole(activeRole === 'parent' ? 'teacher' : 'parent')}
                        className="cursor-pointer"
                      >
                        <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5" />
                        </svg>
                        Switch to {activeRole === 'parent' ? 'Teacher' : 'Parent'} View
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                    </>
                  )}
                  <DropdownMenuItem
                    onClick={() => signOut()}
                    className="cursor-pointer text-destructive focus:text-destructive"
                  >
                    <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9" />
                    </svg>
                    Sign Out
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        </div>
      </nav>

      {/* Page Content */}
      <main className="animate-fade-in">
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
      </main>
    </div>
  )
}

function App() {
  return (
    <AuthProvider>
      <ProfileProvider>
        <SubscriptionProvider>
          <ChildrenProvider>
            <EngagementProvider>
              <AppContent />
            </EngagementProvider>
          </ChildrenProvider>
        </SubscriptionProvider>
      </ProfileProvider>
    </AuthProvider>
  )
}

export default App
