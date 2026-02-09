import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { PageHeader } from '@/components/ui/page-header'
import { Section } from '@/components/ui/section'
import { Skeleton } from '@/components/ui/skeleton'
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

  const getGreeting = () => {
    const hours = new Date().getHours()
    if (hours < 12) return 'Good Morning'
    if (hours < 17) return 'Good Afternoon'
    return 'Good Evening'
  }

  // Unique subjects across all classes
  const uniqueSubjects = [...new Set(classes.map(c => c.subject))]

  return (
    <div className="max-w-5xl mx-auto px-4 py-12 pb-24 space-y-12">
      {/* Welcome Section */}
      <PageHeader className="animate-in fade-in slide-in-from-top-4 duration-500">
        <PageHeader.Title className="text-pretty">
          {getGreeting()}, <span className="text-primary">{displayName}</span>
        </PageHeader.Title>
        <PageHeader.Subtitle className="text-pretty max-w-2xl">
          {classes.length > 0
            ? `Overseeing ${classes.length} distinct classroom groups. Your curriculum sets the pace for excellence.`
            : 'Welcome to your pedagogical command center. Let\'s begin by organizing your first classroom group.'
          }
        </PageHeader.Subtitle>
      </PageHeader>

      {/* Quick Stats Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 animate-in fade-in slide-in-from-bottom-2 duration-700">
        {[
          { label: 'Classes', value: classes.length, icon: 'M4.26 10.147a60.438 60.438 0 00-.491 6.347A48.62 48.62 0 0112 20.904a48.62 48.62 0 018.232-4.41 60.46 60.46 0 00-.491-6.347m-15.482 0a50.636 50.636 0 00-2.658-.813A59.906 59.906 0 0112 3.493a59.903 59.903 0 0110.399 5.84c-.896.248-1.783.52-2.658.814m-15.482 0A50.717 50.717 0 0112 13.489a50.702 50.702 0 017.74-3.342M6.75 15a.75.75 0 100-1.5.75.75 0 000 1.5zm0 0v-3.675A55.378 55.378 0 0112 8.443m-7.007 11.55A5.981 5.981 0 006.75 15.75v-1.5', color: 'primary' },
          { label: 'Subjects', value: uniqueSubjects.length, icon: 'M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25', color: 'accent' },
          { label: 'Worksheets', value: recentWorksheets.length, icon: 'M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z', color: 'emerald' },
          { label: 'Institution', value: profile?.school_name || 'Personal', icon: 'M12 21v-8.25M15.75 21v-8.25M8.25 21v-8.25M3 9l9-6 9 6m-1.5 12V10.332A48.36 48.36 0 0012 9.75c-2.551 0-5.056.2-7.5.582V21M3 21h18M12 6.75h.008v.008H12V6.75z', color: 'rose' }
        ].map((stat, i) => (
          <Card key={i} className="border-border/50 bg-card/40 hover:bg-card/60 transition-colors rounded-2xl overflow-hidden shadow-sm">
            <CardContent className="p-6 text-center">
              <div className={`w-11 h-11 mx-auto mb-3 rounded-xl bg-${stat.color === 'primary' ? 'primary/10' : stat.color === 'accent' ? 'accent/10' : stat.color + '-500/10'} flex items-center justify-center shrink-0 border border-border/10`}>
                <svg className={`w-5 h-5 text-${stat.color === 'primary' ? 'primary' : stat.color === 'accent' ? 'accent' : stat.color + '-600'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d={stat.icon} />
                </svg>
              </div>
              {classesLoading || worksheetsLoading ? (
                <Skeleton className="h-8 w-12 mx-auto mb-1" />
              ) : (
                <p className={`text-2xl font-black font-jakarta text-foreground leading-tight ${stat.color === 'rose' ? 'text-sm truncate' : ''}`}>{stat.value}</p>
              )}
              <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest mt-1">{stat.label}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Action Cards Row */}
      <div className="grid md:grid-cols-2 gap-6 animate-in fade-in slide-in-from-bottom-4 duration-700">
        <Card
          className="group card-hover border-primary/20 bg-gradient-to-br from-primary/5 via-primary/[0.02] to-transparent cursor-pointer rounded-3xl p-1"
          onClick={() => onNavigate('generator')}
        >
          <CardContent className="p-7">
            <div className="flex items-start gap-6">
              <div className="w-14 h-14 rounded-2xl bg-primary text-primary-foreground flex items-center justify-center shrink-0 shadow-lg shadow-primary/20 group-hover:scale-110 transition-transform duration-300">
                <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456z" />
                </svg>
              </div>
              <div className="space-y-1.5 pr-8">
                <h3 className="font-bold text-xl text-foreground font-fraunces">Draft Worksheets</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  Leverage AI to craft high-quality academic worksheets aligned perfectly with your curriculum standards.
                </p>
              </div>
              <div className="absolute top-8 right-8 text-muted-foreground/30 group-hover:text-primary group-hover:translate-x-1 transition-all duration-300">
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
                </svg>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card
          className="group card-hover border-accent/20 bg-gradient-to-br from-accent/5 via-accent/[0.02] to-transparent cursor-pointer rounded-3xl p-1"
          onClick={() => onNavigate('classes')}
        >
          <CardContent className="p-7">
            <div className="flex items-start gap-6">
              <div className="w-14 h-14 rounded-2xl bg-accent text-accent-foreground flex items-center justify-center shrink-0 shadow-lg shadow-accent/20 group-hover:scale-110 transition-transform duration-300">
                <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
                </svg>
              </div>
              <div className="space-y-1.5 pr-8">
                <h3 className="font-bold text-xl text-foreground font-fraunces">Roster Management</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  Configure your classroom groups, subjects, and specific syllabus requirements for streamlined content generation.
                </p>
              </div>
              <div className="absolute top-8 right-8 text-muted-foreground/30 group-hover:text-accent group-hover:translate-x-1 transition-all duration-300">
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
                </svg>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid lg:grid-cols-5 gap-10">
        {/* Classes Explorer */}
        <div className="lg:col-span-3 space-y-6">
          <Section>
            <Section.Header className="flex items-center justify-between border-none pb-0 mb-6">
              <h2 className="text-2xl font-bold font-jakarta text-foreground">Classroom Roster</h2>
              <Button variant="ghost" size="sm" onClick={() => onNavigate('classes')} className="text-primary font-bold hover:bg-primary/5 rounded-xl">
                Manage All
              </Button>
            </Section.Header>
            <Section.Content>
              {classesLoading ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-20 w-full rounded-2xl" />)}
                </div>
              ) : classes.length === 0 ? (
                <div className="p-8 text-center bg-secondary/20 rounded-3xl border border-dashed border-border/60">
                  <p className="text-sm text-muted-foreground font-medium mb-4">You haven't defined any classroom groups yet.</p>
                  <Button onClick={() => onNavigate('classes')} variant="outline" className="rounded-xl font-bold">Initialize Class</Button>
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {classes.slice(0, 4).map((cls) => (
                    <Card key={cls.id} className="group border-border/50 bg-card/40 hover:bg-card/80 hover:border-primary/20 transition-all rounded-2xl overflow-hidden cursor-pointer" onClick={() => onNavigate('classes')}>
                      <CardContent className="p-5">
                        <div className="flex items-center gap-4">
                          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-primary/10 to-accent/10 flex items-center justify-center shrink-0 border border-primary/10 group-hover:scale-105 transition-transform">
                            <span className="text-lg font-black text-primary font-jakarta">
                              {cls.subject[0]}
                            </span>
                          </div>
                          <div className="min-w-0 flex-1">
                            <p className="font-bold text-base text-foreground truncate font-jakarta leading-tight group-hover:text-primary transition-colors">{cls.name}</p>
                            <div className="flex items-center gap-2 mt-1">
                              <span className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/50">{cls.grade}</span>
                              <span className="w-1 h-1 rounded-full bg-border" />
                              <span className="text-[10px] font-black uppercase tracking-widest text-primary/70">{cls.subject}</span>
                            </div>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </Section.Content>
          </Section>
        </div>

        {/* Recent Content */}
        <div className="lg:col-span-2 space-y-6">
          <Section>
            <Section.Header className="flex items-center justify-between border-none pb-0 mb-6">
              <h2 className="text-2xl font-bold font-jakarta text-foreground">Archived Worksheets</h2>
              <Button variant="ghost" size="sm" onClick={() => onNavigate('saved')} className="text-primary font-bold hover:bg-primary/5 rounded-xl">
                Library
              </Button>
            </Section.Header>
            <Section.Content>
              {worksheetsLoading ? (
                <div className="space-y-3">
                  {[1, 2, 3].map(i => <Skeleton key={i} className="h-16 w-full rounded-2xl" />)}
                </div>
              ) : recentWorksheets.length === 0 ? (
                <div className="p-8 text-center bg-secondary/20 rounded-3xl border border-dashed border-border/60">
                  <p className="text-sm text-muted-foreground font-medium mb-4">No content has been generated yet.</p>
                  <Button onClick={() => onNavigate('generator')} variant="outline" className="rounded-xl font-bold">Generate Now</Button>
                </div>
              ) : (
                <div className="space-y-3">
                  {recentWorksheets.map((ws) => (
                    <Card key={ws.id} className="group border-border/40 bg-card/60 hover:bg-background hover:shadow-lg hover:shadow-black/5 hover:border-primary/10 transition-all rounded-2xl cursor-pointer" onClick={() => onNavigate('saved')}>
                      <CardContent className="p-4">
                        <div className="flex items-center justify-between gap-4">
                          <div className="flex items-center gap-3 min-w-0">
                            <div className="w-8 h-8 rounded-lg bg-secondary/80 flex items-center justify-center shrink-0 group-hover:text-primary transition-colors">
                              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                              </svg>
                            </div>
                            <div className="min-w-0">
                              <p className="text-sm font-bold text-foreground truncate group-hover:text-primary transition-colors">{ws.title}</p>
                              <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">{ws.subject} &middot; {ws.topic}</p>
                            </div>
                          </div>
                          <Badge variant="secondary" className="bg-secondary/40 text-[9px] font-black uppercase tracking-tighter px-1.5 py-0 rounded-md border-none text-muted-foreground/60 shrink-0">
                            {formatDate(ws.created_at)}
                          </Badge>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </Section.Content>
          </Section>
        </div>
      </div>
    </div>
  )
}
