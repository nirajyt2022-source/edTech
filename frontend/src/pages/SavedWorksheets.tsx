import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
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
        setError('') // Don't show error, just show empty state
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
      // Update the selected worksheet with new questions
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

  // Group worksheets by date for better organization
  const groupedWorksheets = worksheets.reduce((groups, worksheet) => {
    const date = formatDate(worksheet.created_at)
    if (!groups[date]) {
      groups[date] = []
    }
    groups[date].push(worksheet)
    return groups
  }, {} as Record<string, SavedWorksheetSummary[]>)

  const dateGroups = Object.keys(groupedWorksheets).sort((a, b) => {
    // Sort newest first
    return new Date(b).getTime() - new Date(a).getTime()
  })

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 py-8 px-4">
        <div className="max-w-4xl mx-auto text-center">
          <p className="text-gray-600">Loading worksheets...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 py-8 px-4">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold text-center mb-2">Saved Worksheets</h1>
        <p className="text-center text-gray-600 mb-8">View and manage your saved worksheets</p>

        {error && (
          <div className="mb-4 p-3 bg-red-50 text-red-700 rounded-md">
            {error}
          </div>
        )}

        {/* Child Filter */}
        {children.length > 0 && !selectedWorksheet && (
          <div className="mb-6">
            <div className="flex items-center gap-4">
              <Label htmlFor="filter-child" className="whitespace-nowrap">Filter by child:</Label>
              <Select value={filterChildId} onValueChange={setFilterChildId}>
                <SelectTrigger id="filter-child" className="w-[200px]">
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
          <Card className="mb-8">
            <CardHeader>
              <div className="flex justify-between items-start">
                <div>
                  <CardTitle className="text-2xl">{selectedWorksheet.title}</CardTitle>
                  <CardDescription className="text-base mt-1">
                    {selectedWorksheet.grade} | {selectedWorksheet.subject} | {selectedWorksheet.topic} | {selectedWorksheet.difficulty}
                  </CardDescription>
                </div>
                <div className="flex gap-2 flex-wrap">
                  <Button
                    variant="secondary"
                    onClick={() => regenerateWorksheet(selectedWorksheet.id)}
                    disabled={regenerating}
                  >
                    {regenerating ? 'Regenerating...' : 'Regenerate'}
                    {(selectedWorksheet.regeneration_count || 0) === 0 && (
                      <span className="ml-1 text-xs bg-green-100 text-green-800 px-1.5 py-0.5 rounded">
                        Free
                      </span>
                    )}
                  </Button>
                  <Button onClick={() => downloadPdf(selectedWorksheet)}>
                    Download PDF
                  </Button>
                  <Button variant="outline" onClick={() => setSelectedWorksheet(null)}>
                    Back to List
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="mb-4 p-3 bg-blue-50 rounded-md">
                <p className="font-medium">Instructions:</p>
                <p className="text-sm text-gray-700">Answer all questions. Show your work where applicable.</p>
              </div>

              <div className="space-y-6">
                {selectedWorksheet.questions.map((question, index) => (
                  <div key={question.id} className="border-b pb-4 last:border-b-0">
                    <p className="font-medium mb-2">
                      Q{index + 1}. {question.text}
                    </p>
                    {question.options && (
                      <div className="ml-4 space-y-1">
                        {question.options.map((option, optIndex) => (
                          <p key={optIndex} className="text-gray-700">
                            {String.fromCharCode(65 + optIndex)}. {option}
                          </p>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {/* Answer Key */}
              <div className="mt-8 pt-4 border-t-2 border-dashed">
                <h3 className="font-bold text-lg mb-4">Answer Key</h3>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                  {selectedWorksheet.questions.map((question, index) => (
                    <p key={question.id} className="text-sm">
                      Q{index + 1}: {question.correct_answer}
                    </p>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
        ) : (
          /* Worksheet List */
          <>
            {worksheets.length === 0 ? (
              <Card>
                <CardContent className="py-12 text-center">
                  <p className="text-gray-600 mb-4">You haven't saved any worksheets yet.</p>
                  <p className="text-sm text-gray-500">
                    Generate a worksheet and click "Save" to store it here.
                  </p>
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-6">
                {dateGroups.map((date) => (
                  <div key={date}>
                    <h2 className="text-sm font-medium text-gray-500 mb-3 sticky top-0 bg-gray-50 py-1">
                      {date}
                    </h2>
                    <div className="grid gap-3">
                      {groupedWorksheets[date].map((worksheet) => (
                        <Card key={worksheet.id} className="hover:shadow-md transition-shadow">
                          <CardContent className="py-4">
                            <div className="flex justify-between items-start">
                              <div className="flex-1">
                                <div className="flex items-center gap-2">
                                  <h3 className="font-semibold text-lg">{worksheet.title}</h3>
                                  {worksheet.child_name && (
                                    <span className="text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded-full">
                                      {worksheet.child_name}
                                    </span>
                                  )}
                                </div>
                                <p className="text-sm text-gray-600 mt-1">
                                  {worksheet.grade} | {worksheet.subject} | {worksheet.topic}
                                </p>
                                <p className="text-xs text-gray-500 mt-1">
                                  {worksheet.question_count} questions • {worksheet.difficulty}
                                </p>
                              </div>
                              <div className="flex gap-2">
                                <Button size="sm" onClick={() => viewWorksheet(worksheet.id)}>
                                  View
                                </Button>
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={() => deleteWorksheet(worksheet.id)}
                                >
                                  Delete
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
