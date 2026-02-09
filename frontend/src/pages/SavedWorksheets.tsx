import { useState, useEffect, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { PageHeader } from '@/components/ui/page-header'
import { Section } from '@/components/ui/section'
import { EmptyState } from '@/components/ui/empty-state'
import { Skeleton } from '@/components/ui/skeleton'
import { api } from '@/lib/api'
import { useChildren } from '@/lib/children'
import { useClasses } from '@/lib/classes'
import { useProfile } from '@/lib/profile'

interface SavedWorksheetSummary {
  id: string
  title: string
  board: string | null
  grade: string
  subject: string
  topic: string
  difficulty: string
  language: string
  question_count: number
  created_at: string
  child_id: string | null
  child_name: string | null
  class_id: string | null
  class_name: string | null
  regeneration_count?: number
}

interface Question {
  id: string
  type: string
  text: string
  options?: string[]
  correct_answer?: string
  explanation?: string
}

interface FullWorksheet {
  id: string
  title: string
  board: string | null
  grade: string
  subject: string
  topic: string
  difficulty: string
  language: string
  questions: Question[]
  created_at: string
  regeneration_count?: number
}

export default function SavedWorksheets() {
  const { children } = useChildren()
  const { classes } = useClasses()
  const { activeRole } = useProfile()
  const isTeacher = activeRole === 'teacher'
  const [worksheets, setWorksheets] = useState<SavedWorksheetSummary[]>([])
  const [selectedWorksheet, setSelectedWorksheet] = useState<FullWorksheet | null>(null)
  const [loading, setLoading] = useState(true)
  const [regenerating, setRegenerating] = useState(false)
  const [downloadingPdfType, setDownloadingPdfType] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [filterChildId, setFilterChildId] = useState('all')
  const [filterClassId, setFilterClassId] = useState('all')

  const loadWorksheets = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const queryParts: string[] = []
      if (!isTeacher && filterChildId && filterChildId !== 'all') {
        queryParts.push(`child_id=${filterChildId}`)
      }
      if (isTeacher && filterClassId && filterClassId !== 'all') {
        queryParts.push(`class_id=${filterClassId}`)
      }
      const params = queryParts.length > 0 ? `?${queryParts.join('&')}` : ''
      const response = await api.get(`/api/worksheets/saved/list${params}`)
      setWorksheets(response.data.worksheets || [])
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status?: number; data?: { detail?: string } } }
      if (axiosErr.response?.status === 500 && axiosErr.response?.data?.detail?.includes('relation')) {
        setError('Database not set up. Please run the SQL schema in Supabase.')
      } else {
        setError('')
      }
      setWorksheets([])
      console.error(err)
    } finally {
      setLoading(false)
    }
  }, [filterChildId, filterClassId, isTeacher])

  useEffect(() => {
    loadWorksheets()
  }, [filterChildId, filterClassId, loadWorksheets])

  const viewWorksheet = async (id: string) => {
    try {
      const response = await api.get(`/api/worksheets/saved/${id}`)
      setSelectedWorksheet(response.data)
    } catch (err) {
      setError('Failed to load worksheet')
      console.error(err)
    }
  }

  const deleteWorksheet = async (id: string) => {
    if (!confirm('Are you sure you want to delete this worksheet?')) return

    try {
      await api.delete(`/api/worksheets/saved/${id}`)
      setWorksheets(worksheets.filter(w => w.id !== id))
      if (selectedWorksheet?.id === id) {
        setSelectedWorksheet(null)
      }
    } catch (err) {
      setError('Failed to delete worksheet')
      console.error(err)
    }
  }

  const downloadPdf = async (worksheet: FullWorksheet, pdfType: string = 'full') => {
    setDownloadingPdfType(pdfType)
    try {
      const response = await api.post('/api/worksheets/export-pdf', {
        worksheet: {
          title: worksheet.title,
          grade: worksheet.grade,
          subject: worksheet.subject,
          topic: worksheet.topic,
          difficulty: worksheet.difficulty,
          language: worksheet.language,
          questions: worksheet.questions,
        },
        pdf_type: pdfType,
      }, {
        responseType: 'blob',
      })

      const typeSuffix = pdfType !== 'full' ? `_${pdfType}` : ''
      const blob = new Blob([response.data], { type: 'application/pdf' })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${worksheet.title.replace(/\s+/g, '_')}${typeSuffix}.pdf`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
    } catch (err) {
      setError('Failed to download PDF')
      console.error(err)
    } finally {
      setDownloadingPdfType(null)
    }
  }

  const regenerateWorksheet = async (worksheetId: string) => {
    setRegenerating(true)
    setError('')
    try {
      const response = await api.post(`/api/worksheets/regenerate/${worksheetId}`)
      const newWorksheet = response.data.worksheet
      if (selectedWorksheet && selectedWorksheet.id === worksheetId) {
        setSelectedWorksheet({
          ...selectedWorksheet,
          questions: newWorksheet.questions,
          title: newWorksheet.title,
          regeneration_count: (selectedWorksheet.regeneration_count || 0) + 1,
        })
      }
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { status?: number; data?: { detail?: string } } }
        if (axiosErr.response?.status === 403) {
          setError('Free tier limit reached. Upgrade to Pro for unlimited regenerations.')
        } else {
          setError(axiosErr.response?.data?.detail || 'Failed to regenerate worksheet')
        }
      } else {
        setError('Failed to regenerate worksheet')
      }
      console.error(err)
    } finally {
      setRegenerating(false)
    }
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-IN', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    })
  }

  const groupedWorksheets = worksheets.reduce((groups, worksheet) => {
    const date = formatDate(worksheet.created_at)
    if (!groups[date]) {
      groups[date] = []
    }
    groups[date].push(worksheet)
    return groups
  }, {} as Record<string, SavedWorksheetSummary[]>)

  const dateGroups = Object.keys(groupedWorksheets).sort((a, b) => {
    return new Date(b).getTime() - new Date(a).getTime()
  })

  if (loading) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-12">
        <PageHeader className="mb-12">
          <Skeleton className="h-10 w-64 mb-4" />
          <Skeleton className="h-6 w-96" />
        </PageHeader>

        <div className="space-y-8">
          {[1, 2].map((i) => (
            <div key={i} className="space-y-4">
              <Skeleton className="h-5 w-32" />
              <div className="grid gap-4">
                <Skeleton className="h-24 w-full rounded-xl" />
                <Skeleton className="h-24 w-full rounded-xl" />
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-12 pb-24">
      {/* Header */}
      {!selectedWorksheet && (
        <PageHeader className="mb-12">
          <PageHeader.Title className="text-pretty">
            {isTeacher ? 'Classroom Repository' : 'Practice History'}
          </PageHeader.Title>
          <PageHeader.Subtitle className="text-pretty max-w-2xl">
            {isTeacher
              ? 'Access and manage all worksheets generated for your classes. Reuse or regenerate materials to suit your curriculum.'
              : 'Review your child’s past practice sessions. Track progress and revisit core concepts with ease.'
            }
          </PageHeader.Subtitle>
        </PageHeader>
      )}

      {error && (
        <div className="mb-6 p-4 bg-destructive/10 border border-destructive/20 text-destructive rounded-xl flex items-center gap-3 animate-in fade-in slide-in-from-top-2">
          <svg className="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <span className="text-sm font-medium">{error}</span>
        </div>
      )}

      {/* Role-aware Filter */}
      {!selectedWorksheet && (isTeacher ? classes.length > 0 : children.length > 0) && (
        <div className="mb-10 animate-in fade-in slide-in-from-top-2 duration-500 print:hidden">
          <div className="inline-flex items-center gap-4 p-2 pl-4 pr-3 bg-secondary/30 border border-border/50 rounded-2xl">
            <span className="text-sm font-semibold text-foreground/70 flex items-center gap-2">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 3c2.755 0 5.455.232 8.083.678.533.09.917.556.917 1.096v1.044a2.25 2.25 0 01-.659 1.591l-5.432 5.432a2.25 2.25 0 00-.659 1.591v2.927a2.25 2.25 0 01-1.244 2.013L9.75 21v-6.568a2.25 2.25 0 00-.659-1.591L3.659 7.409A2.25 2.25 0 013 5.818V4.774c0-.54.384-1.006.917-1.096A48.32 48.32 0 0112 3z" />
              </svg>
              Filter by {isTeacher ? 'Class' : 'Child'}
            </span>
            {isTeacher ? (
              <Select value={filterClassId} onValueChange={setFilterClassId}>
                <SelectTrigger id="filter-entity" className="w-[180px] h-9 bg-background border-none shadow-sm rounded-xl font-medium focus:ring-primary/20">
                  <SelectValue placeholder="All classes" />
                </SelectTrigger>
                <SelectContent className="rounded-xl">
                  <SelectItem value="all">All classes</SelectItem>
                  {classes.map((cls) => (
                    <SelectItem key={cls.id} value={cls.id}>
                      {cls.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <Select value={filterChildId} onValueChange={setFilterChildId}>
                <SelectTrigger id="filter-entity" className="w-[180px] h-9 bg-background border-none shadow-sm rounded-xl font-medium focus:ring-primary/20">
                  <SelectValue placeholder="All children" />
                </SelectTrigger>
                <SelectContent className="rounded-xl">
                  <SelectItem value="all">All children</SelectItem>
                  {children.map((child) => (
                    <SelectItem key={child.id} value={child.id}>
                      {child.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>
        </div>
      )}

      {/* Worksheet Detail View */}
      {selectedWorksheet ? (
        <Section className="animate-in fade-in slide-in-from-bottom-4 duration-500">
          <Section.Header>
            <div className="flex flex-col md:flex-row justify-between items-start gap-6 w-full">
              <div className="space-y-3">
                <Section.Title className="text-3xl md:text-4xl">
                  {selectedWorksheet.title}
                </Section.Title>
                <div className="flex flex-wrap gap-2">
                  {[selectedWorksheet.grade, selectedWorksheet.subject, selectedWorksheet.topic, selectedWorksheet.difficulty].map((tag, i) => (
                    <span key={i} className="inline-flex items-center px-2.5 py-0.5 rounded-lg text-xs font-semibold bg-primary/10 text-primary border border-primary/10">
                      {tag}
                    </span>
                  ))}
                </div>
              </div>

              <div className="flex gap-2 flex-wrap shrink-0 print:hidden">
                <Button
                  variant="outline"
                  onClick={() => regenerateWorksheet(selectedWorksheet.id)}
                  disabled={regenerating}
                  size="sm"
                  className="rounded-xl border-border/60 shadow-sm"
                >
                  {regenerating ? (
                    <>
                      <span className="spinner !w-3.5 !h-3.5 mr-2" />
                      Regenerating
                    </>
                  ) : (
                    <>
                      <svg className="w-4 h-4 mr-2 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
                      </svg>
                      Regenerate
                    </>
                  )}
                </Button>

                {isTeacher ? (
                  <>
                    <Button
                      onClick={() => downloadPdf(selectedWorksheet, 'student')}
                      disabled={!!downloadingPdfType}
                      size="sm"
                      className="bg-primary text-primary-foreground shadow-sm rounded-xl"
                    >
                      {downloadingPdfType === 'student' ? (
                        <>
                          <span className="spinner !w-3.5 !h-3.5 mr-2 !border-primary-foreground/30 !border-t-primary-foreground" />
                          Downloading
                        </>
                      ) : (
                        <>
                          <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9.75v6.75m0 0l-3-3m3 3l3-3m-8.25 6a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.233-2.33 3 3 0 013.758 3.848A3.752 3.752 0 0118 19.5H6.75z" />
                          </svg>
                          Student PDF
                        </>
                      )}
                    </Button>
                    <Button
                      onClick={() => downloadPdf(selectedWorksheet, 'answer_key')}
                      disabled={!!downloadingPdfType}
                      variant="outline"
                      size="sm"
                      className="rounded-xl border-border/60 shadow-sm"
                    >
                      {downloadingPdfType === 'answer_key' ? (
                        <>
                          <span className="spinner !w-3.5 !h-3.5 mr-2" />
                          Downloading
                        </>
                      ) : (
                        <>
                          <svg className="w-4 h-4 mr-2 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 5.25a3 3 0 013 3m3 0a6 6 0 01-7.029 5.912c-.563-.097-1.159.026-1.563.43L10.5 17.25H8.25v2.25H6v2.25H2.25v-2.818c0-.597.237-1.17.659-1.591l6.499-6.499c.404-.404.527-1 .43-1.563A6 6 0 1121.75 8.25z" />
                          </svg>
                          Answer Key
                        </>
                      )}
                    </Button>
                  </>
                ) : (
                  <Button
                    onClick={() => downloadPdf(selectedWorksheet)}
                    disabled={!!downloadingPdfType}
                    size="sm"
                    className="bg-primary text-primary-foreground shadow-sm rounded-xl"
                  >
                    {downloadingPdfType ? (
                      <>
                        <span className="spinner !w-3.5 !h-3.5 mr-2 !border-primary-foreground/30 !border-t-primary-foreground" />
                        Downloading
                      </>
                    ) : (
                      <>
                        <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
                        </svg>
                        Download PDF
                      </>
                    )}
                  </Button>
                )}

                <Button variant="ghost" size="sm" onClick={() => setSelectedWorksheet(null)} className="rounded-xl text-muted-foreground hover:bg-secondary/50">
                  <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
                  </svg>
                  Back
                </Button>
              </div>
            </div>
          </Section.Header>

          <Section.Content className="pt-8">
            <div className="space-y-12">
              <div className="p-5 bg-secondary/30 rounded-2xl border border-border/40 flex items-start gap-4">
                <div className="p-2 bg-primary/10 rounded-xl text-primary shrink-0">
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z" />
                  </svg>
                </div>
                <div>
                  <h4 className="font-bold text-foreground mb-1 font-jakarta">Instructions for Student</h4>
                  <p className="text-sm text-muted-foreground leading-relaxed">Please read each question carefully and provide the best possible answer. For multiple-choice questions, select the option that most accurately completes the statement.</p>
                </div>
              </div>

              <div className="space-y-10">
                {selectedWorksheet.questions.map((question, index) => (
                  <div key={question.id} className="relative pl-12">
                    <div className="absolute left-0 top-0 w-8 h-8 rounded-full bg-secondary/50 border border-border/50 flex items-center justify-center font-bold text-sm text-foreground/70">
                      {index + 1}
                    </div>
                    <div className="space-y-4">
                      <p className="text-lg font-medium text-foreground leading-snug">{question.text}</p>

                      {question.options && (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4">
                          {question.options.map((option, optIndex) => (
                            <div key={optIndex} className="p-3 pl-4 rounded-xl border border-border/40 bg-background flex items-center gap-3 group transition-colors hover:border-primary/20">
                              <span className="flex-shrink-0 w-6 h-6 rounded-md bg-secondary/40 border border-border/60 flex items-center justify-center text-[10px] font-bold text-muted-foreground group-hover:bg-primary/5 group-hover:text-primary group-hover:border-primary/20 transition-colors">
                                {String.fromCharCode(65 + optIndex)}
                              </span>
                              <span className="text-sm font-medium text-muted-foreground group-hover:text-foreground transition-colors">{option}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {/* Answer Key */}
              {!isTeacher && (
                <div className="mt-16 pt-10 border-t-2 border-dashed border-border/60">
                  <div className="flex items-center gap-3 mb-8">
                    <div className="p-2 bg-accent/10 rounded-xl text-accent shrink-0">
                      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 5.25a3 3 0 013 3m3 0a6 6 0 01-7.029 5.912c-.563-.097-1.159.026-1.563.43L10.5 17.25H8.25v2.25H6v2.25H2.25v-2.818c0-.597.237-1.17.659-1.591l6.499-6.499c.404-.404.527-1 .43-1.563A6 6 0 1121.75 8.25z" />
                      </svg>
                    </div>
                    <h3 className="text-xl font-bold font-jakarta">Answer Key</h3>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
                    {selectedWorksheet.questions.map((question, index) => (
                      <div key={question.id} className="p-3 rounded-xl bg-secondary/20 border border-border/30 flex justify-between items-center group hover:bg-accent/5 hover:border-accent/20 transition-all">
                        <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider group-hover:text-accent/70">Q{index + 1}</span>
                        <span className="font-bold text-foreground text-sm group-hover:text-accent transition-colors">{question.correct_answer}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </Section.Content>
        </Section>
      ) : (
        /* Worksheet List */
        <>
          {worksheets.length === 0 ? (
            <EmptyState
              icon={
                <svg className="w-full h-full" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                </svg>
              }
              title="No worksheets yet"
              description={
                filterChildId !== 'all' || filterClassId !== 'all'
                  ? "We couldn't find any worksheets for the selected filter."
                  : "Generate your first worksheet to start building your collection."
              }
              action={
                <Button size="lg" onClick={() => window.location.href = '/generate'} className="bg-primary text-primary-foreground shadow-sm rounded-xl px-8">
                  Generate Worksheet
                </Button>
              }
            />
          ) : (
            <div className="space-y-12 animate-in fade-in slide-in-from-bottom-2 duration-500">
              {dateGroups.map((date) => (
                <div key={date}>
                  <h2 className="text-xs font-bold text-muted-foreground/60 uppercase tracking-[0.2em] mb-4 flex items-center gap-3">
                    <span className="shrink-0">{date}</span>
                    <div className="h-px w-full bg-border/40" />
                  </h2>
                  <div className="grid gap-4">
                    {groupedWorksheets[date].map((worksheet) => (
                      <Card key={worksheet.id} className="card-hover border-border/50 bg-card/50 overflow-hidden rounded-2xl hover:shadow-lg transition-all duration-300">
                        <CardContent className="p-0">
                          <div className="flex flex-col md:flex-row justify-between items-stretch">
                            <div className="p-6 md:p-7 flex-1 space-y-4">
                              <div className="space-y-2">
                                <div className="flex items-center gap-2 flex-wrap">
                                  <h3 className="font-bold text-xl text-foreground font-jakarta">{worksheet.title}</h3>
                                  {worksheet.child_name && (
                                    <span className="text-[10px] font-bold uppercase tracking-wider bg-primary/10 text-primary px-2 py-0.5 rounded-md border border-primary/10">
                                      {worksheet.child_name}
                                    </span>
                                  )}
                                  {worksheet.class_name && (
                                    <span className="text-[10px] font-bold uppercase tracking-wider bg-accent/10 text-accent px-2 py-0.5 rounded-md border border-accent/10">
                                      {worksheet.class_name}
                                    </span>
                                  )}
                                </div>
                                <p className="text-sm font-medium text-muted-foreground/70">
                                  {worksheet.grade} • {worksheet.subject} • {worksheet.topic}
                                </p>
                              </div>

                              <div className="flex items-center gap-4 text-xs font-semibold text-muted-foreground/50">
                                <span className="flex items-center gap-1.5 bg-secondary/40 px-2 py-1 rounded-lg">
                                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                                  </svg>
                                  {worksheet.question_count} questions
                                </span>
                                <span className="flex items-center gap-1.5 bg-secondary/40 px-2 py-1 rounded-lg uppercase tracking-tight">
                                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125v-11.25zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
                                  </svg>
                                  {worksheet.difficulty}
                                </span>
                              </div>
                            </div>

                            <div className="flex flex-row md:flex-col items-center justify-center p-4 md:p-6 bg-secondary/10 gap-3 border-t md:border-t-0 md:border-l border-border/40 min-w-[140px]">
                              <Button
                                size="sm"
                                onClick={() => viewWorksheet(worksheet.id)}
                                className="w-full bg-background border-border shadow-sm text-foreground hover:bg-secondary/40 rounded-xl py-5 font-bold transition-all"
                                variant="outline"
                              >
                                View
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => deleteWorksheet(worksheet.id)}
                                className="w-10 h-10 md:w-full p-0 md:h-10 text-muted-foreground/40 hover:text-destructive hover:bg-destructive/5 rounded-xl transition-all"
                              >
                                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
                                </svg>
                                <span className="md:hidden ml-2 font-bold">Delete</span>
                              </Button>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
