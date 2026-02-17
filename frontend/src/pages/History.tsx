import { useState, useEffect, useCallback, useMemo } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { PageHeader } from '@/components/ui/page-header'
import { EmptyState } from '@/components/ui/empty-state'
import { Skeleton } from '@/components/ui/skeleton'
import { api, apiV1WithFallback } from '@/lib/api'
import { useChildren } from '@/lib/children'
import { useProfile } from '@/lib/profile'
import { notify } from '@/lib/toast'

interface WorksheetHistoryItem {
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
  questions: { id: string; text: string; correct_answer?: string; explanation?: string; sample_answer?: string }[]
  created_at: string
}

const PAGE_SIZE = 20

export default function History({ onNavigateToGenerator }: { onNavigateToGenerator?: (preFill?: { grade?: string; subject?: string; topic?: string }) => void }) {
  const { children } = useChildren()
  const { activeRole } = useProfile()
  const isTeacher = activeRole === 'teacher'

  const [worksheets, setWorksheets] = useState<WorksheetHistoryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [filterChildId, setFilterChildId] = useState('all')
  const [filterTopic, setFilterTopic] = useState('all')
  const [currentPageNum, setCurrentPageNum] = useState(1)
  const [downloadingId, setDownloadingId] = useState<string | null>(null)
  const [viewingWorksheet, setViewingWorksheet] = useState<FullWorksheet | null>(null)
  const [showAnswers, setShowAnswers] = useState(false)
  const [viewLoading, setViewLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')

  const loadWorksheets = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const queryParts: string[] = []
      if (!isTeacher && filterChildId && filterChildId !== 'all') {
        queryParts.push(`child_id=${filterChildId}`)
      }
      const params = queryParts.length > 0 ? `?${queryParts.join('&')}` : ''
      const response = await api.get(`/api/worksheets/saved/list${params}`)
      setWorksheets(response.data.worksheets || [])
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status?: number; data?: { detail?: string } } }
      if (axiosErr.response?.status === 500 && axiosErr.response?.data?.detail?.includes('relation')) {
        setError('Database not set up. Please run the SQL schema in Supabase.')
      } else {
        setError('Failed to load worksheets. Please try again.')
      }
      setWorksheets([])
      console.warn('Failed to load worksheet history:', err)
    } finally {
      setLoading(false)
    }
  }, [filterChildId, isTeacher])

  useEffect(() => {
    loadWorksheets()
  }, [loadWorksheets])

  // Reset to page 1 when filters change
  useEffect(() => {
    setCurrentPageNum(1)
  }, [filterChildId, filterTopic, searchQuery])

  // Derive unique topics from loaded worksheets
  const uniqueTopics = useMemo(() => {
    const topics = new Set<string>()
    worksheets.forEach((w) => {
      if (w.topic) topics.add(w.topic)
    })
    return Array.from(topics).sort()
  }, [worksheets])

  // Apply client-side topic filter + search
  const filteredWorksheets = useMemo(() => {
    let result = worksheets
    if (filterTopic !== 'all') {
      result = result.filter((w) => w.topic === filterTopic)
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim()
      result = result.filter((w) =>
        w.topic?.toLowerCase().includes(q) ||
        w.subject?.toLowerCase().includes(q) ||
        w.grade?.toLowerCase().includes(q) ||
        w.title?.toLowerCase().includes(q)
      )
    }
    return result
  }, [worksheets, filterTopic, searchQuery])

  // Pagination
  const totalPages = Math.max(1, Math.ceil(filteredWorksheets.length / PAGE_SIZE))
  const paginatedWorksheets = useMemo(() => {
    const start = (currentPageNum - 1) * PAGE_SIZE
    return filteredWorksheets.slice(start, start + PAGE_SIZE)
  }, [filteredWorksheets, currentPageNum])

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-IN', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    })
  }

  const viewWorksheet = async (id: string) => {
    setViewLoading(true)
    setError('')
    try {
      const response = await api.get(`/api/worksheets/saved/${id}`)
      setViewingWorksheet(response.data)
    } catch (err) {
      setError('Failed to load worksheet details.')
      console.warn('Failed to load worksheet:', err)
    } finally {
      setViewLoading(false)
    }
  }

  const downloadPdf = async (worksheet: WorksheetHistoryItem) => {
    setDownloadingId(worksheet.id)
    try {
      // Need full worksheet data for PDF export
      const fullResponse = await api.get(`/api/worksheets/saved/${worksheet.id}`)
      const fullWorksheet = fullResponse.data

      const response = await apiV1WithFallback<BlobPart>('post', '/api/worksheets/export-pdf', {
        worksheet: {
          title: fullWorksheet.title,
          grade: fullWorksheet.grade,
          subject: fullWorksheet.subject,
          topic: fullWorksheet.topic,
          difficulty: fullWorksheet.difficulty,
          language: fullWorksheet.language,
          questions: fullWorksheet.questions,
        },
        pdf_type: 'full',
      }, {
        responseType: 'blob',
      })

      const blob = new Blob([response.data], { type: 'application/pdf' })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${worksheet.title.replace(/\s+/g, '_')}.pdf`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
      notify.success('PDF downloaded')
    } catch (err) {
      notify.error('Failed to download PDF')
      setError('Failed to download PDF.')
      console.warn('Failed to download PDF:', err)
    } finally {
      setDownloadingId(null)
    }
  }

  // Loading state
  if (loading) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-12">
        <PageHeader className="mb-12">
          <PageHeader.Title className="text-pretty">Worksheet History</PageHeader.Title>
          <PageHeader.Subtitle className="text-pretty max-w-2xl">
            Loading your worksheet history...
          </PageHeader.Subtitle>
        </PageHeader>

        <div className="space-y-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-28 w-full rounded-2xl" />
          ))}
        </div>
      </div>
    )
  }

  // Detail view
  if (viewingWorksheet) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-12 pb-24 animate-in fade-in slide-in-from-bottom-4 duration-500">
        <div className="flex flex-col md:flex-row justify-between items-start gap-6 mb-10">
          <div className="space-y-3">
            <h1 className="text-3xl md:text-4xl font-semibold">{viewingWorksheet.title}</h1>
            <div className="flex flex-wrap gap-2">
              {[viewingWorksheet.grade, viewingWorksheet.subject, viewingWorksheet.topic, viewingWorksheet.difficulty].map((tag, i) => (
                <span key={i} className="inline-flex items-center px-2.5 py-0.5 rounded-lg text-xs font-semibold bg-primary/10 text-primary border border-primary/10">
                  {tag}
                </span>
              ))}
            </div>
            <p className="text-sm text-muted-foreground">
              {formatDate(viewingWorksheet.created_at)} &middot; {viewingWorksheet.questions.length} questions
            </p>
          </div>
          <div className="flex gap-2 shrink-0 print:hidden">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowAnswers(!showAnswers)}
              className="rounded-xl"
            >
              <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                {showAnswers
                  ? <path strokeLinecap="round" strokeLinejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
                  : <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178zM15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                }
              </svg>
              {showAnswers ? 'Hide Answers' : 'Show Answers'}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => { setViewingWorksheet(null); setShowAnswers(false) }}
              className="rounded-xl text-muted-foreground hover:bg-secondary/50"
            >
              <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
              </svg>
              Back
            </Button>
          </div>
        </div>

        <div className="space-y-10">
          {viewingWorksheet.questions.map((question, index) => (
            <div key={question.id} className="relative pl-12">
              <div className="absolute left-0 top-0 w-8 h-8 rounded-full bg-secondary/50 border border-border/50 flex items-center justify-center font-bold text-sm text-foreground/70">
                {index + 1}
              </div>
              <p className="text-lg font-medium text-foreground leading-snug">{question.text}</p>
            </div>
          ))}
        </div>

        {/* Answer Key — visible when showAnswers is true */}
        {showAnswers && (
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
              {viewingWorksheet.questions.map((question, index) => (
                <div key={question.id} className="p-3 rounded-xl bg-secondary/20 border border-border/30 flex justify-between items-center group hover:bg-accent/5 hover:border-accent/20 transition-all">
                  <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider group-hover:text-accent/70">Q{index + 1}</span>
                  <span className="font-bold text-foreground text-sm group-hover:text-accent transition-colors">
                    {question.correct_answer || question.explanation || question.sample_answer || <span className="text-muted-foreground text-xs italic">Open-ended</span>}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-12 pb-24">
      <PageHeader className="mb-12">
        <PageHeader.Title className="text-pretty">Worksheet History</PageHeader.Title>
        <PageHeader.Subtitle className="text-pretty max-w-2xl">
          Browse all worksheets you have generated. Filter by child or topic, download PDFs, or review past practice.
        </PageHeader.Subtitle>
      </PageHeader>

      {/* Error state */}
      {error && (
        <div className="mb-6 p-4 bg-destructive/10 border border-destructive/20 text-destructive rounded-xl flex items-center justify-between animate-in fade-in slide-in-from-top-2">
          <div className="flex items-center gap-3">
            <svg className="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <span className="text-sm font-medium">{error}</span>
          </div>
          <Button variant="outline" size="sm" onClick={loadWorksheets} className="rounded-xl border-destructive/30 text-destructive hover:bg-destructive/10 shrink-0 ml-4">
            Retry
          </Button>
        </div>
      )}

      {/* Search + Filters */}
      {worksheets.length > 0 && (
        <div className="mb-10 animate-in fade-in slide-in-from-top-2 duration-500 print:hidden">
          <div className="inline-flex items-center gap-4 p-2 pl-4 pr-3 bg-secondary/30 border border-border/50 rounded-2xl flex-wrap">
            {/* Search input */}
            <div className="relative">
              <svg className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/50" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
              </svg>
              <input
                type="text"
                placeholder="Search topic, subject, grade..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="h-9 w-[220px] pl-8 pr-3 bg-background border-none shadow-sm rounded-xl text-sm font-medium placeholder:text-muted-foreground/40 focus:outline-none focus:ring-2 focus:ring-primary/20"
              />
            </div>

            {/* Child filter (parent only) */}
            {!isTeacher && children.length > 0 && (
              <Select value={filterChildId} onValueChange={setFilterChildId}>
                <SelectTrigger className="w-[180px] h-9 bg-background border-none shadow-sm rounded-xl font-medium focus:ring-primary/20">
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

            {/* Topic filter */}
            {uniqueTopics.length > 1 && (
              <Select value={filterTopic} onValueChange={setFilterTopic}>
                <SelectTrigger className="w-[200px] h-9 bg-background border-none shadow-sm rounded-xl font-medium focus:ring-primary/20">
                  <SelectValue placeholder="All topics" />
                </SelectTrigger>
                <SelectContent className="rounded-xl">
                  <SelectItem value="all">All topics</SelectItem>
                  {uniqueTopics.map((topic) => (
                    <SelectItem key={topic} value={topic}>
                      {topic}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>
        </div>
      )}

      {/* View loading overlay */}
      {viewLoading && (
        <div className="mb-6 p-4 bg-secondary/30 border border-border/40 rounded-xl flex items-center gap-3 animate-in fade-in">
          <div className="w-5 h-5 border-2 border-primary/20 border-t-primary rounded-full animate-spin" />
          <span className="text-sm font-medium text-muted-foreground">Loading worksheet...</span>
        </div>
      )}

      {/* Empty state */}
      {filteredWorksheets.length === 0 && !error ? (
        <EmptyState
          icon={
            <svg className="w-12 h-12" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
            </svg>
          }
          title={filterTopic !== 'all' || filterChildId !== 'all' ? 'No worksheets match your filters' : 'No worksheets yet'}
          description={
            filterTopic !== 'all' || filterChildId !== 'all'
              ? 'Try changing the filters to see more results.'
              : 'Generate your first worksheet! It takes under a minute.'
          }
          action={
            filterTopic === 'all' && filterChildId === 'all' && onNavigateToGenerator ? (
              <Button
                size="lg"
                onClick={() => onNavigateToGenerator()}
                className="bg-primary text-primary-foreground shadow-sm rounded-xl px-8"
              >
                Create your first worksheet
              </Button>
            ) : undefined
          }
        />
      ) : (
        /* Worksheet list */
        <div className="space-y-4 animate-in fade-in slide-in-from-bottom-2 duration-500">
          {paginatedWorksheets.map((worksheet) => (
            <Card key={worksheet.id} className="card-hover border-border/50 bg-card/50 overflow-hidden rounded-2xl hover:shadow-lg transition-all duration-300">
              <CardContent className="p-0">
                <div className="flex flex-col md:flex-row justify-between items-stretch">
                  {/* Info section */}
                  <div className="p-6 md:p-7 flex-1 space-y-3">
                    <div className="space-y-1.5">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="font-bold text-lg text-foreground font-jakarta">{worksheet.title}</h3>
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
                        {worksheet.topic} &middot; {worksheet.grade} &middot; {formatDate(worksheet.created_at)}
                      </p>
                    </div>

                    <div className="flex items-center gap-3 text-xs font-semibold text-muted-foreground/50">
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

                  {/* Actions section */}
                  <div className="flex flex-row md:flex-col items-center justify-center p-4 md:p-6 bg-secondary/10 gap-3 border-t md:border-t-0 md:border-l border-border/40 min-w-[160px]">
                    <Button
                      size="sm"
                      onClick={() => viewWorksheet(worksheet.id)}
                      className="w-full bg-background border-border shadow-sm text-foreground hover:bg-secondary/40 rounded-xl py-4 font-bold transition-all"
                      variant="outline"
                    >
                      View
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => downloadPdf(worksheet)}
                      disabled={downloadingId === worksheet.id}
                      className="w-full bg-primary text-primary-foreground shadow-sm rounded-xl py-4 font-bold transition-all"
                    >
                      {downloadingId === worksheet.id ? (
                        <>
                          <span className="spinner !w-3.5 !h-3.5 mr-2 !border-primary-foreground/30 !border-t-primary-foreground" />
                          PDF...
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
                    {onNavigateToGenerator && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => onNavigateToGenerator({ grade: worksheet.grade, subject: worksheet.subject, topic: worksheet.topic })}
                        className="w-full text-muted-foreground hover:text-primary hover:bg-primary/5 rounded-xl py-4 font-bold transition-all"
                      >
                        Generate similar
                        <svg className="w-4 h-4 ml-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
                        </svg>
                      </Button>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 pt-8">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setCurrentPageNum((p) => Math.max(1, p - 1))}
                disabled={currentPageNum === 1}
                className="rounded-xl"
              >
                <svg className="w-4 h-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
                </svg>
                Previous
              </Button>
              <span className="text-sm font-medium text-muted-foreground px-4">
                Page {currentPageNum} of {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setCurrentPageNum((p) => Math.min(totalPages, p + 1))}
                disabled={currentPageNum === totalPages}
                className="rounded-xl"
              >
                Next
                <svg className="w-4 h-4 ml-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                </svg>
              </Button>
            </div>
          )}

          {/* Result count */}
          <p className="text-center text-xs text-muted-foreground/50 pt-2">
            Showing {((currentPageNum - 1) * PAGE_SIZE) + 1}--{Math.min(currentPageNum * PAGE_SIZE, filteredWorksheets.length)} of {filteredWorksheets.length} worksheets
          </p>
        </div>
      )}
    </div>
  )
}
