import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useAuth } from '@/lib/auth'
import { useClasses } from '@/lib/classes'
import { useProfile } from '@/lib/profile'
import { api } from '@/lib/api'

interface SavedWorksheet {
  id: string
  title: string
  subject: string
  grade: string
  topic: string
  created_at: string
}

interface TeacherDashboardProps {
  onNavigate: (page: string) => void
}

export default function TeacherDashboard({ onNavigate }: TeacherDashboardProps) {
  const { user } = useAuth()
  const { classes, loading: classesLoading } = useClasses()
  const { profile } = useProfile()
  const [recentWorksheets, setRecentWorksheets] = useState<SavedWorksheet[]>([])
  const [worksheetsLoading, setWorksheetsLoading] = useState(true)

  const displayName = user?.user_metadata?.name || user?.email?.split('@')[0] || 'Teacher'

  useEffect(() => {
    const fetchRecent = async () => {
      try {
        const response = await api.get('/api/worksheets/saved/list?limit=5')
        setRecentWorksheets(response.data.worksheets || [])
      } catch (err) {
        console.error('Failed to fetch recent worksheets:', err)
      } finally {
        setWorksheetsLoading(false)
      }
    }
    fetchRecent()
  }, [])

  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr)
    return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
  }

  // Unique subjects across all classes
  const uniqueSubjects = [...new Set(classes.map(c => c.subject))]

  return (
    <div className="py-8 px-4">
      <div className="max-w-4xl mx-auto">
        {/* Welcome Section */}
        <div className="mb-10 animate-fade-in">
          <div className="decorative-dots mb-4" />
          <h1 className="text-3xl md:text-4xl mb-2">
            Good {new Date().getHours() < 12 ? 'morning' : new Date().getHours() < 17 ? 'afternoon' : 'evening'}, {displayName}
          </h1>
          <p className="text-muted-foreground text-lg">
            {classes.length > 0
              ? `You have ${classes.length} class${classes.length !== 1 ? 'es' : ''} set up. Ready to create worksheets?`
              : 'Welcome to your teaching dashboard. Start by creating your first class.'
            }
          </p>
        </div>

        {/* Quick Stats Row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8 animate-fade-in-delayed">
          {/* Classes count */}
          <Card className="border-border/50">
            <CardContent className="py-5 text-center">
              <div className="w-10 h-10 mx-auto mb-2 rounded-xl bg-gradient-to-br from-primary/15 to-primary/5 flex items-center justify-center">
                <svg className="w-5 h-5 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4.26 10.147a60.438 60.438 0 00-.491 6.347A48.62 48.62 0 0112 20.904a48.62 48.62 0 018.232-4.41 60.46 60.46 0 00-.491-6.347m-15.482 0a50.636 50.636 0 00-2.658-.813A59.906 59.906 0 0112 3.493a59.903 59.903 0 0110.399 5.84c-.896.248-1.783.52-2.658.814m-15.482 0A50.717 50.717 0 0112 13.489a50.702 50.702 0 017.74-3.342M6.75 15a.75.75 0 100-1.5.75.75 0 000 1.5zm0 0v-3.675A55.378 55.378 0 0112 8.443m-7.007 11.55A5.981 5.981 0 006.75 15.75v-1.5" />
                </svg>
              </div>
              <p className="text-2xl font-semibold text-foreground">{classesLoading ? '...' : classes.length}</p>
              <p className="text-xs text-muted-foreground mt-0.5">Classes</p>
            </CardContent>
          </Card>

          {/* Subjects count */}
          <Card className="border-border/50">
            <CardContent className="py-5 text-center">
              <div className="w-10 h-10 mx-auto mb-2 rounded-xl bg-gradient-to-br from-accent/15 to-accent/5 flex items-center justify-center">
                <svg className="w-5 h-5 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25" />
                </svg>
              </div>
              <p className="text-2xl font-semibold text-foreground">{classesLoading ? '...' : uniqueSubjects.length}</p>
              <p className="text-xs text-muted-foreground mt-0.5">Subjects</p>
            </CardContent>
          </Card>

          {/* Worksheets count */}
          <Card className="border-border/50">
            <CardContent className="py-5 text-center">
              <div className="w-10 h-10 mx-auto mb-2 rounded-xl bg-gradient-to-br from-emerald-500/15 to-emerald-500/5 flex items-center justify-center">
                <svg className="w-5 h-5 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                </svg>
              </div>
              <p className="text-2xl font-semibold text-foreground">{worksheetsLoading ? '...' : recentWorksheets.length}</p>
              <p className="text-xs text-muted-foreground mt-0.5">Saved</p>
            </CardContent>
          </Card>

          {/* School */}
          <Card className="border-border/50">
            <CardContent className="py-5 text-center">
              <div className="w-10 h-10 mx-auto mb-2 rounded-xl bg-gradient-to-br from-rose-500/15 to-rose-500/5 flex items-center justify-center">
                <svg className="w-5 h-5 text-rose-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 21v-8.25M15.75 21v-8.25M8.25 21v-8.25M3 9l9-6 9 6m-1.5 12V10.332A48.36 48.36 0 0012 9.75c-2.551 0-5.056.2-7.5.582V21M3 21h18M12 6.75h.008v.008H12V6.75z" />
                </svg>
              </div>
              <p className="text-sm font-medium text-foreground truncate px-1">
                {profile?.school_name || 'Not set'}
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">School</p>
            </CardContent>
          </Card>
        </div>

        {/* Action Cards Row */}
        <div className="grid md:grid-cols-2 gap-4 mb-8 animate-fade-in-delayed-2">
          {/* Create Worksheet CTA */}
          <Card className="card-hover border-primary/20 bg-gradient-to-br from-primary/5 to-transparent cursor-pointer" onClick={() => onNavigate('generator')}>
            <CardContent className="py-6">
              <div className="flex items-start gap-4">
                <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center flex-shrink-0">
                  <svg className="w-6 h-6 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456z" />
                  </svg>
                </div>
                <div>
                  <h3 className="font-semibold text-foreground mb-1">Create Worksheet</h3>
                  <p className="text-sm text-muted-foreground">
                    Generate AI-powered worksheets aligned to your class syllabus
                  </p>
                </div>
                <svg className="w-5 h-5 text-muted-foreground ml-auto mt-1 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                </svg>
              </div>
            </CardContent>
          </Card>

          {/* Manage Classes CTA */}
          <Card className="card-hover border-accent/20 bg-gradient-to-br from-accent/5 to-transparent cursor-pointer" onClick={() => onNavigate('classes')}>
            <CardContent className="py-6">
              <div className="flex items-start gap-4">
                <div className="w-12 h-12 rounded-xl bg-accent/10 flex items-center justify-center flex-shrink-0">
                  <svg className="w-6 h-6 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4.26 10.147a60.438 60.438 0 00-.491 6.347A48.62 48.62 0 0112 20.904a48.62 48.62 0 018.232-4.41 60.46 60.46 0 00-.491-6.347m-15.482 0a50.636 50.636 0 00-2.658-.813A59.906 59.906 0 0112 3.493a59.903 59.903 0 0110.399 5.84c-.896.248-1.783.52-2.658.814m-15.482 0A50.717 50.717 0 0112 13.489a50.702 50.702 0 017.74-3.342M6.75 15a.75.75 0 100-1.5.75.75 0 000 1.5zm0 0v-3.675A55.378 55.378 0 0112 8.443m-7.007 11.55A5.981 5.981 0 006.75 15.75v-1.5" />
                  </svg>
                </div>
                <div>
                  <h3 className="font-semibold text-foreground mb-1">Manage Classes</h3>
                  <p className="text-sm text-muted-foreground">
                    {classes.length > 0
                      ? `${classes.length} class${classes.length !== 1 ? 'es' : ''} configured`
                      : 'Set up your first class to get started'
                    }
                  </p>
                </div>
                <svg className="w-5 h-5 text-muted-foreground ml-auto mt-1 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                </svg>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* My Classes Quick View */}
        {classes.length > 0 && (
          <div className="mb-8 animate-fade-in-delayed-2">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl">My Classes</h2>
              <Button variant="ghost" size="sm" onClick={() => onNavigate('classes')} className="text-muted-foreground hover:text-foreground">
                View All
                <svg className="w-4 h-4 ml-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                </svg>
              </Button>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
              {classes.slice(0, 6).map((cls) => (
                <Card key={cls.id} className="border-border/50 hover:border-border transition-colors">
                  <CardContent className="py-4">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-primary/15 to-accent/15 flex items-center justify-center flex-shrink-0">
                        <span className="text-xs font-bold text-primary">
                          {cls.subject[0]}
                        </span>
                      </div>
                      <div className="min-w-0">
                        <p className="font-medium text-sm text-foreground truncate">{cls.name}</p>
                        <p className="text-xs text-muted-foreground">{cls.grade} &middot; {cls.subject}</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        )}

        {/* Recent Worksheets */}
        <div className="animate-fade-in-delayed-2">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl">Recent Worksheets</h2>
            {recentWorksheets.length > 0 && (
              <Button variant="ghost" size="sm" onClick={() => onNavigate('saved')} className="text-muted-foreground hover:text-foreground">
                View All
                <svg className="w-4 h-4 ml-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                </svg>
              </Button>
            )}
          </div>

          {worksheetsLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="spinner" />
            </div>
          ) : recentWorksheets.length === 0 ? (
            <Card className="border-border/50">
              <CardContent className="py-8 text-center">
                <p className="text-sm text-muted-foreground">
                  No worksheets saved yet. Create your first worksheet to see it here.
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-2">
              {recentWorksheets.map((ws) => (
                <Card key={ws.id} className="border-border/50 hover:border-border transition-colors">
                  <CardContent className="py-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3 min-w-0">
                        <svg className="w-4 h-4 text-muted-foreground flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                        </svg>
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-foreground truncate">{ws.title}</p>
                          <p className="text-xs text-muted-foreground">{ws.subject} &middot; {ws.grade} &middot; {ws.topic}</p>
                        </div>
                      </div>
                      <Badge variant="outline" className="text-xs text-muted-foreground flex-shrink-0 ml-2">
                        {formatDate(ws.created_at)}
                      </Badge>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
