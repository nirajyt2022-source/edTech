import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { api } from '@/lib/api'
import { useChildren } from '@/lib/children'

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
  const [worksheets, setWorksheets] = useState<SavedWorksheetSummary[]>([])
  const [selectedWorksheet, setSelectedWorksheet] = useState<FullWorksheet | null>(null)
  const [loading, setLoading] = useState(true)
  const [regenerating, setRegenerating] = useState(false)
  const [error, setError] = useState('')
  const [filterChildId, setFilterChildId] = useState('')

  useEffect(() => {
    loadWorksheets()
  }, [filterChildId])

  const loadWorksheets = async () => {
    setLoading(true)
    setError('')
    try {
      const params = filterChildId ? `?child_id=${filterChildId}` : ''
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
  }

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

  const downloadPdf = async (worksheet: FullWorksheet) => {
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
        include_answer_key: true,
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
    } catch (err) {
      setError('Failed to download PDF')
      console.error(err)
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
      <div className="py-8 px-4">
        <div className="max-w-4xl mx-auto flex flex-col items-center justify-center py-16">
          <div className="spinner mb-4" />
          <p className="text-muted-foreground">Loading your worksheets...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="py-8 px-4">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="text-center mb-8 animate-fade-in">
          <div className="decorative-dots mb-4" />
          <h1 className="text-3xl md:text-4xl mb-3">Saved Worksheets</h1>
          <p className="text-muted-foreground text-lg">
            Your collection of practice materials, ready when you are
          </p>
        </div>

        {error && (
          <div className="mb-6 p-4 bg-destructive/10 border border-destructive/20 text-destructive rounded-lg flex items-center gap-3 animate-fade-in">
            <svg className="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            {error}
          </div>
        )}

        {/* Child Filter */}
        {children.length > 0 && !selectedWorksheet && (
          <div className="mb-6 animate-fade-in">
            <div className="flex items-center gap-4 p-4 bg-card border border-border rounded-xl">
              <Label htmlFor="filter-child" className="whitespace-nowrap text-muted-foreground flex items-center gap-2">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
                </svg>
                Filter by child:
              </Label>
              <Select value={filterChildId} onValueChange={setFilterChildId}>
                <SelectTrigger id="filter-child" className="w-[200px] bg-background">
                  <SelectValue placeholder="All children" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">All children</SelectItem>
                  {children.map((child) => (
                    <SelectItem key={child.id} value={child.id}>
                      {child.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        )}

        {/* Worksheet Detail View */}
        {selectedWorksheet ? (
          <Card className="mb-8 paper-texture animate-fade-in">
            <CardHeader>
              <div className="flex flex-col md:flex-row justify-between items-start gap-4">
                <div>
                  <div className="decorative-line mb-3" />
                  <CardTitle className="text-2xl md:text-3xl">{selectedWorksheet.title}</CardTitle>
                  <div className="flex flex-wrap gap-2 mt-3">
                    {[selectedWorksheet.grade, selectedWorksheet.subject, selectedWorksheet.topic, selectedWorksheet.difficulty].map((tag, i) => (
                      <span key={i} className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-secondary text-secondary-foreground">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="flex gap-2 flex-wrap">
                  <Button
                    variant="secondary"
                    onClick={() => regenerateWorksheet(selectedWorksheet.id)}
                    disabled={regenerating}
                    className="relative"
                  >
                    {regenerating ? (
                      <span className="flex items-center gap-2">
                        <span className="spinner !w-4 !h-4" />
                        Regenerating...
                      </span>
                    ) : (
                      <span className="flex items-center gap-2">
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                        </svg>
                        Regenerate
                        {(selectedWorksheet.regeneration_count || 0) === 0 && (
                          <span className="ml-1 text-xs bg-primary/20 text-primary px-1.5 py-0.5 rounded">
                            Free
                          </span>
                        )}
                      </span>
                    )}
                  </Button>
                  <Button onClick={() => downloadPdf(selectedWorksheet)} className="btn-animate">
                    <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    PDF
                  </Button>
                  <Button variant="outline" onClick={() => setSelectedWorksheet(null)}>
                    <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                    </svg>
                    Back
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="mb-6 p-4 bg-secondary/50 border border-border rounded-lg">
                <p className="font-semibold text-foreground flex items-center gap-2">
                  <svg className="w-5 h-5 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Instructions
                </p>
                <p className="text-sm text-muted-foreground mt-1">Answer all questions. Show your work where applicable.</p>
              </div>

              <div className="space-y-6 stagger-children">
                {selectedWorksheet.questions.map((question, index) => (
                  <div key={question.id} className="border-b border-border pb-5 last:border-b-0">
                    <p className="font-medium mb-3 text-foreground">
                      <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-primary/10 text-primary text-sm font-semibold mr-2">
                        {index + 1}
                      </span>
                      {question.text}
                    </p>
                    {question.options && (
                      <div className="ml-9 space-y-2">
                        {question.options.map((option, optIndex) => (
                          <p key={optIndex} className="text-muted-foreground flex items-center gap-2">
                            <span className="w-6 h-6 rounded border border-border flex items-center justify-center text-xs font-medium">
                              {String.fromCharCode(65 + optIndex)}
                            </span>
                            {option}
                          </p>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {/* Answer Key */}
              <div className="mt-10 pt-6 border-t-2 border-dashed border-border">
                <h3 className="font-semibold text-lg mb-4 flex items-center gap-2">
                  <svg className="w-5 h-5 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
                  </svg>
                  Answer Key
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                  {selectedWorksheet.questions.map((question, index) => (
                    <div key={question.id} className="flex items-center gap-2 p-2 bg-secondary/30 rounded-lg text-sm">
                      <span className="font-medium text-primary">Q{index + 1}:</span>
                      <span className="text-foreground">{question.correct_answer}</span>
                    </div>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
        ) : (
          /* Worksheet List */
          <>
            {worksheets.length === 0 ? (
              <Card className="paper-texture animate-fade-in">
                <CardContent className="py-16 text-center">
                  <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-secondary/50 flex items-center justify-center">
                    <svg className="w-8 h-8 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                    </svg>
                  </div>
                  <p className="text-foreground font-medium mb-2">No worksheets saved yet</p>
                  <p className="text-sm text-muted-foreground">
                    Generate a worksheet and click "Save" to build your collection
                  </p>
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-8 animate-fade-in">
                {dateGroups.map((date) => (
                  <div key={date}>
                    <h2 className="text-sm font-medium text-muted-foreground mb-3 flex items-center gap-2 sticky top-16 bg-background/80 backdrop-blur-sm py-2 z-10">
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                      </svg>
                      {date}
                    </h2>
                    <div className="grid gap-3">
                      {groupedWorksheets[date].map((worksheet) => (
                        <Card key={worksheet.id} className="card-hover border-border/50">
                          <CardContent className="py-4">
                            <div className="flex justify-between items-start">
                              <div className="flex-1">
                                <div className="flex items-center gap-2 flex-wrap">
                                  <h3 className="font-semibold text-lg text-foreground">{worksheet.title}</h3>
                                  {worksheet.child_name && (
                                    <span className="text-xs bg-primary/10 text-primary px-2 py-0.5 rounded-full flex items-center gap-1">
                                      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                        <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                                      </svg>
                                      {worksheet.child_name}
                                    </span>
                                  )}
                                </div>
                                <p className="text-sm text-muted-foreground mt-1">
                                  {worksheet.grade} | {worksheet.subject} | {worksheet.topic}
                                </p>
                                <p className="text-xs text-muted-foreground mt-1 flex items-center gap-2">
                                  <span className="flex items-center gap-1">
                                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                                    </svg>
                                    {worksheet.question_count} questions
                                  </span>
                                  <span className="w-1 h-1 rounded-full bg-border" />
                                  <span>{worksheet.difficulty}</span>
                                </p>
                              </div>
                              <div className="flex gap-2">
                                <Button size="sm" onClick={() => viewWorksheet(worksheet.id)} className="btn-animate">
                                  <svg className="w-4 h-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                                  </svg>
                                  View
                                </Button>
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={() => deleteWorksheet(worksheet.id)}
                                  className="text-muted-foreground hover:text-destructive hover:border-destructive"
                                >
                                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                  </svg>
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
    </div>
  )
}
