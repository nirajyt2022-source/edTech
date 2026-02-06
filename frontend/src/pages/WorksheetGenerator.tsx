import { useState, useEffect, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { api } from '@/lib/api'
import { useChildren } from '@/lib/children'
import { useSubscription } from '@/lib/subscription'
import TopicSelector from '@/components/TopicSelector'
import CBSESyllabusViewer from '@/components/CBSESyllabusViewer'
import { useEngagement } from '@/lib/engagement'

const BOARDS = ['CBSE']
const GRADES = ['Class 1', 'Class 2', 'Class 3', 'Class 4', 'Class 5']
const SUBJECTS = ['Maths', 'English', 'EVS', 'Hindi', 'Science', 'Computer']
const DIFFICULTIES = ['Easy', 'Medium', 'Hard']
const LANGUAGES = ['English', 'Hindi', 'Marathi', 'Tamil', 'Telugu', 'Kannada', 'Arabic', 'Urdu']
const QUESTION_COUNTS = ['5', '10', '15', '20']

const DEFAULT_TOPICS: Record<string, string[]> = {
  Maths: ['Addition', 'Subtraction', 'Multiplication', 'Division', 'Fractions', 'Word Problems'],
  English: ['Grammar', 'Vocabulary', 'Reading Comprehension', 'Sentence Formation'],
  EVS: ['Environment', 'Family & Community', 'Daily Life', 'Plants & Animals'],
  Hindi: ['Varnamala', 'Matras', 'Shabd Rachna', 'Vakya Rachna', 'Kahani Lekhan'],
  Science: ['Living Things', 'Matter', 'Force and Motion', 'Earth and Space', 'Human Body'],
  Computer: ['Computer Basics', 'Parts of Computer', 'MS Paint', 'MS Word', 'Internet Safety'],
}

interface Question {
  id: string
  type: string
  text: string
  options?: string[]
  correct_answer?: string
  explanation?: string
}

interface Worksheet {
  title: string
  grade: string
  subject: string
  topic: string
  difficulty: string
  language: string
  questions: Question[]
}

interface SyllabusTopic {
  name: string
  subtopics?: string[]
}

interface SyllabusChapter {
  name: string
  topics: SyllabusTopic[]
}

interface ParsedSyllabus {
  id: string
  name: string
  board?: string
  grade?: string
  subject?: string
  chapters: SyllabusChapter[]
}

interface Props {
  syllabus?: ParsedSyllabus | null
  onClearSyllabus?: () => void
}

export default function WorksheetGenerator({ syllabus, onClearSyllabus }: Props) {
  const { children } = useChildren()
  const { status: subscription, incrementUsage, upgrade } = useSubscription()
  const { recordCompletion, lastCompletion, clearLastCompletion } = useEngagement()
  const [selectedChildId, setSelectedChildId] = useState('')
  const [board, setBoard] = useState('')
  const [grade, setGrade] = useState('')
  const [subject, setSubject] = useState('')
  const [chapter, setChapter] = useState('')
  const [topic, setTopic] = useState('')
  const [difficulty, setDifficulty] = useState('')
  const [questionCount, setQuestionCount] = useState('10')
  const [language, setLanguage] = useState('English')
  const [customInstructions, setCustomInstructions] = useState('')

  const [loading, setLoading] = useState(false)
  const [downloadingPdf, setDownloadingPdf] = useState(false)
  const [saving, setSaving] = useState(false)
  const [worksheet, setWorksheet] = useState<Worksheet | null>(null)
  const [error, setError] = useState('')
  const [saveSuccess, setSaveSuccess] = useState(false)

  // CBSE syllabus state
  const [cbseSyllabus, setCbseSyllabus] = useState<SyllabusChapter[]>([])
  const [selectedTopics, setSelectedTopics] = useState<string[]>([])
  const [loadingSyllabus, setLoadingSyllabus] = useState(false)

  // Handle child selection - pre-fill grade and board
  const handleChildSelect = (childId: string) => {
    setSelectedChildId(childId)
    if (childId) {
      const child = children.find(c => c.id === childId)
      if (child) {
        setGrade(child.grade)
        if (child.board) {
          setBoard(child.board)
        }
      }
    }
  }

  // Pre-fill form when syllabus is provided
  useEffect(() => {
    if (syllabus) {
      if (syllabus.board) setBoard(syllabus.board)
      if (syllabus.grade) setGrade(syllabus.grade)
      if (syllabus.subject) setSubject(syllabus.subject)
      setChapter('')
      setTopic('')
    }
  }, [syllabus])

  // Fetch CBSE syllabus when grade and subject are selected
  useEffect(() => {
    const fetchCbseSyllabus = async () => {
      if (syllabus || !grade || !subject) {
        setCbseSyllabus([])
        return
      }

      setLoadingSyllabus(true)
      try {
        const response = await api.get(`/api/cbse-syllabus/${grade}/${subject}`)
        if (response.data && response.data.chapters) {
          setCbseSyllabus(response.data.chapters)
        }
      } catch (err) {
        console.error('Failed to load CBSE syllabus:', err)
        setCbseSyllabus([])
      } finally {
        setLoadingSyllabus(false)
      }
    }

    fetchCbseSyllabus()
  }, [grade, subject, syllabus])

  // Handle topic selection changes
  const handleTopicSelectionChange = useCallback((topics: string[]) => {
    setSelectedTopics(topics)
  }, [])

  // Get available chapters from syllabus or use default subjects
  const availableChapters = syllabus ? syllabus.chapters : []

  // Get available topics based on selection
  const getAvailableTopics = () => {
    if (syllabus && chapter) {
      const selectedChapter = syllabus.chapters.find(ch => ch.name === chapter)
      return selectedChapter ? selectedChapter.topics.map(t => t.name) : []
    }
    if (!syllabus && subject) {
      return DEFAULT_TOPICS[subject] || []
    }
    return []
  }

  const availableTopics = getAvailableTopics()

  const handleGenerate = async () => {
    // Check subscription limits
    if (subscription && !subscription.can_generate) {
      setError('You have reached your free tier limit. Upgrade to continue generating worksheets.')
      return
    }

    // Check language restrictions for free tier
    if (subscription && !subscription.can_use_regional_languages && language !== 'English') {
      setError('Regional languages are available on the paid plan. Please select English or upgrade.')
      return
    }

    // Determine which topic(s) to use
    const useAdvancedSelection = !syllabus && cbseSyllabus.length > 0
    const topicsToUse = useAdvancedSelection ? selectedTopics : [topic]

    if (!board || !grade || !difficulty) {
      setError('Please fill in all required fields')
      return
    }
    if (!syllabus && !subject) {
      setError('Please select a subject')
      return
    }
    if (useAdvancedSelection && selectedTopics.length === 0) {
      setError('Please select at least one topic')
      return
    }
    if (!useAdvancedSelection && !topic) {
      setError('Please select a topic')
      return
    }

    setLoading(true)
    setError('')
    setWorksheet(null)

    // Use chapter name as context if from syllabus, or combine selected topics
    const topicWithContext = syllabus && chapter
      ? `${chapter} - ${topic}`
      : useAdvancedSelection
      ? topicsToUse.slice(0, 5).join(', ')  // Limit to 5 topics for better worksheet focus
      : topic

    try {
      const response = await api.post('/api/worksheets/generate', {
        board,
        grade_level: grade,
        subject: syllabus?.subject || subject,
        topic: topicWithContext,
        difficulty: difficulty.toLowerCase(),
        num_questions: parseInt(questionCount),
        language,
        custom_instructions: customInstructions || undefined,
      })
      setWorksheet(response.data.worksheet)

      // Track usage for free tier
      await incrementUsage()
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to generate worksheet'
      setError(errorMessage)
    } finally {
      setLoading(false)
    }
  }

  const handlePrint = () => {
    window.print()
  }

  const handleDownloadPdf = async () => {
    if (!worksheet) return

    setDownloadingPdf(true)
    try {
      const response = await api.post('/api/worksheets/export-pdf', {
        worksheet,
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

      // Record completion for engagement tracking (if child selected)
      if (selectedChildId) {
        await recordCompletion(selectedChildId)
      }
    } catch (err) {
      console.error('Failed to download PDF:', err)
      setError('Failed to download PDF')
    } finally {
      setDownloadingPdf(false)
    }
  }

  const handleSave = async () => {
    if (!worksheet) return

    setSaving(true)
    setSaveSuccess(false)
    try {
      await api.post('/api/worksheets/save', {
        worksheet,
        board,
        child_id: selectedChildId || undefined,
      })
      setSaveSuccess(true)
      setTimeout(() => setSaveSuccess(false), 3000)
    } catch (err) {
      console.error('Failed to save worksheet:', err)
      setError('Failed to save worksheet')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 py-8 px-4">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-semibold text-center mb-2 text-slate-800">PracticeCraft AI</h1>
        <p className="text-center text-slate-600 mb-4">Create practice worksheets aligned to your child's syllabus</p>

        {/* Trust Micro-copy */}
        <div className="flex justify-center gap-4 mb-8 text-xs print:hidden">
          <span className="inline-flex items-center gap-1.5 text-green-700">
            <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
            </svg>
            CBSE-aligned
          </span>
          <span className="inline-flex items-center gap-1.5 text-blue-700">
            <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M4 4a2 2 0 012-2h8a2 2 0 012 2v12a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 0v12h8V4H6z" clipRule="evenodd" />
            </svg>
            Printable worksheets
          </span>
          <span className="inline-flex items-center gap-1.5 text-purple-700">
            <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
              <path d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" />
            </svg>
            Built for parents
          </span>
        </div>

        {/* Upgrade Banner */}
        {subscription && !subscription.can_generate && (
          <div className="mb-6 p-4 bg-amber-50 border border-amber-200 rounded-lg print:hidden">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium text-amber-900">Free tier limit reached</p>
                <p className="text-sm text-amber-700">
                  You've used all 3 free worksheets this month. Upgrade for unlimited access.
                </p>
              </div>
              <Button onClick={() => upgrade()} variant="default" size="sm">
                Upgrade to Pro
              </Button>
            </div>
          </div>
        )}

        {/* Usage Info for Free Tier */}
        {subscription && subscription.tier === 'free' && subscription.can_generate && (
          <div className="mb-6 p-3 bg-gray-50 border border-gray-200 rounded-lg print:hidden">
            <p className="text-sm text-gray-600">
              Free tier: {subscription.worksheets_remaining} of 3 worksheets remaining this month
            </p>
          </div>
        )}

        {/* Syllabus Banner */}
        {syllabus && (
          <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-lg flex items-center justify-between print:hidden">
            <div>
              <p className="font-medium text-blue-900">Using syllabus: {syllabus.name}</p>
              <p className="text-sm text-blue-700">
                {syllabus.grade} {syllabus.subject && `• ${syllabus.subject}`} • {syllabus.chapters.length} chapters
              </p>
            </div>
            <Button variant="outline" size="sm" onClick={onClearSyllabus}>
              Clear Syllabus
            </Button>
          </div>
        )}

        {/* CBSE Syllabus Viewer - show as reference when custom syllabus uploaded */}
        {syllabus && grade && syllabus.subject && (
          <div className="mb-6 print:hidden">
            <details className="group">
              <summary className="cursor-pointer text-sm text-slate-600 hover:text-slate-800 mb-2">
                View official CBSE syllabus for comparison
              </summary>
              <CBSESyllabusViewer grade={grade} subject={syllabus.subject} />
            </details>
          </div>
        )}

        {/* Generator Form */}
        <Card className="mb-8 print:hidden shadow-sm border-slate-200">
          <CardHeader className="pb-4">
            <CardTitle className="text-xl font-semibold text-slate-800">Create Worksheet</CardTitle>
            <CardDescription className="text-slate-600">
              {syllabus
                ? 'Select a chapter and topic from your syllabus'
                : 'Select options to create a practice worksheet'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Child Selector */}
              {children.length > 0 && (
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="child">Generate for</Label>
                  <Select value={selectedChildId} onValueChange={handleChildSelect}>
                    <SelectTrigger id="child">
                      <SelectValue placeholder="Select a child (optional)" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="">No child selected</SelectItem>
                      {children.map((child) => (
                        <SelectItem key={child.id} value={child.id}>
                          {child.name} ({child.grade})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              {/* Board */}
              <div className="space-y-2">
                <Label htmlFor="board">Board *</Label>
                <Select value={board} onValueChange={setBoard}>
                  <SelectTrigger id="board">
                    <SelectValue placeholder="Select board" />
                  </SelectTrigger>
                  <SelectContent>
                    {BOARDS.map((b) => (
                      <SelectItem key={b} value={b}>{b}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Grade */}
              <div className="space-y-2">
                <Label htmlFor="grade">Grade *</Label>
                <Select value={grade} onValueChange={setGrade}>
                  <SelectTrigger id="grade">
                    <SelectValue placeholder="Select grade" />
                  </SelectTrigger>
                  <SelectContent>
                    {GRADES.map((g) => (
                      <SelectItem key={g} value={g}>{g}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Subject (only show if no syllabus) */}
              {!syllabus && (
                <div className="space-y-2">
                  <Label htmlFor="subject">Subject *</Label>
                  <Select value={subject} onValueChange={(val) => { setSubject(val); setTopic('') }}>
                    <SelectTrigger id="subject">
                      <SelectValue placeholder="Select subject" />
                    </SelectTrigger>
                    <SelectContent>
                      {SUBJECTS.map((s) => (
                        <SelectItem key={s} value={s}>{s}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              {/* Chapter (only show if syllabus) */}
              {syllabus && (
                <div className="space-y-2">
                  <Label htmlFor="chapter">Chapter *</Label>
                  <Select value={chapter} onValueChange={(val) => { setChapter(val); setTopic('') }}>
                    <SelectTrigger id="chapter">
                      <SelectValue placeholder="Select chapter" />
                    </SelectTrigger>
                    <SelectContent>
                      {availableChapters.map((ch) => (
                        <SelectItem key={ch.name} value={ch.name}>{ch.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              {/* Topic - only show dropdown if using custom syllabus or no CBSE syllabus */}
              {(syllabus || cbseSyllabus.length === 0) && (
                <div className="space-y-2">
                  <Label htmlFor="topic">Topic *</Label>
                  <Select
                    value={topic}
                    onValueChange={setTopic}
                    disabled={syllabus ? !chapter : !subject}
                  >
                    <SelectTrigger id="topic">
                      <SelectValue placeholder={
                        syllabus
                          ? (chapter ? "Select topic" : "Select chapter first")
                          : (subject ? "Select topic" : "Select subject first")
                      } />
                    </SelectTrigger>
                    <SelectContent>
                      {availableTopics.map((t) => (
                        <SelectItem key={t} value={t}>{t}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              {/* Advanced Topic Selector - show when CBSE syllabus available and no custom syllabus */}
              {!syllabus && cbseSyllabus.length > 0 && (
                <div className="md:col-span-2">
                  {loadingSyllabus ? (
                    <p className="text-sm text-gray-500">Loading CBSE syllabus...</p>
                  ) : (
                    <TopicSelector
                      chapters={cbseSyllabus}
                      childId={selectedChildId || undefined}
                      subject={subject}
                      onSelectionChange={handleTopicSelectionChange}
                    />
                  )}
                </div>
              )}

              {/* Difficulty */}
              <div className="space-y-2">
                <Label htmlFor="difficulty">Difficulty *</Label>
                <Select value={difficulty} onValueChange={setDifficulty}>
                  <SelectTrigger id="difficulty">
                    <SelectValue placeholder="Select difficulty" />
                  </SelectTrigger>
                  <SelectContent>
                    {DIFFICULTIES.map((d) => (
                      <SelectItem key={d} value={d}>{d}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Question Count */}
              <div className="space-y-2">
                <Label htmlFor="questionCount">Number of Questions</Label>
                <Select value={questionCount} onValueChange={setQuestionCount}>
                  <SelectTrigger id="questionCount">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {QUESTION_COUNTS.map((c) => (
                      <SelectItem key={c} value={c}>{c} questions</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Language */}
              <div className="space-y-2">
                <Label htmlFor="language">Language</Label>
                <Select value={language} onValueChange={setLanguage}>
                  <SelectTrigger id="language">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {LANGUAGES.map((l) => (
                      <SelectItem key={l} value={l}>{l}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Custom Instructions */}
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="customInstructions">Custom Instructions (Optional)</Label>
                <Textarea
                  id="customInstructions"
                  placeholder="E.g., Focus on 2-digit numbers, include word problems..."
                  value={customInstructions}
                  onChange={(e) => setCustomInstructions(e.target.value)}
                />
              </div>
            </div>

            {error && (
              <div className="mt-4 p-3 bg-red-50 text-red-700 rounded-md">
                {error}
              </div>
            )}

            <Button
              className="w-full mt-6"
              onClick={handleGenerate}
              disabled={loading}
            >
              {loading ? 'Generating...' : 'Generate Worksheet'}
            </Button>
          </CardContent>
        </Card>

        {/* Completion Feedback */}
        {lastCompletion && selectedChildId && (
          <div className="mb-6 p-4 bg-green-50 border border-green-200 rounded-lg print:hidden">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <span className="text-2xl">✅</span>
                <div>
                  <p className="font-medium text-green-800">Worksheet completed!</p>
                  <p className="text-sm text-green-700">
                    ⭐ {lastCompletion.stars_earned} star earned • 🔥 {lastCompletion.current_streak}-day streak
                  </p>
                </div>
              </div>
              <button
                onClick={clearLastCompletion}
                className="text-green-600 hover:text-green-800 text-sm"
              >
                Dismiss
              </button>
            </div>
          </div>
        )}

        {/* Generated Worksheet */}
        {worksheet && (
          <Card className="print:shadow-none print:border-none">
            <CardHeader className="print:pb-2">
              <div className="flex justify-between items-start">
                <div>
                  <CardTitle className="text-2xl">{worksheet.title}</CardTitle>
                  <CardDescription className="text-base mt-1">
                    {worksheet.grade} | {worksheet.subject} | {worksheet.topic} | {worksheet.difficulty}
                  </CardDescription>
                </div>
                <div className="flex gap-2 print:hidden">
                  <Button onClick={handleSave} disabled={saving} variant={saveSuccess ? "outline" : "default"}>
                    {saving ? 'Saving...' : saveSuccess ? 'Saved!' : 'Save'}
                  </Button>
                  <Button onClick={handleDownloadPdf} disabled={downloadingPdf}>
                    {downloadingPdf ? 'Downloading...' : 'Download PDF'}
                  </Button>
                  <Button onClick={handlePrint} variant="outline">
                    Print
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="mb-4 p-3 bg-blue-50 rounded-md print:bg-gray-100">
                <p className="font-medium">Instructions:</p>
                <p className="text-sm text-gray-700">Answer all questions. Show your work where applicable.</p>
              </div>

              <div className="space-y-6">
                {worksheet.questions.map((question, index) => (
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
                    {question.type === 'fill_blank' && (
                      <div className="ml-4 mt-2">
                        <p className="text-gray-500">Answer: _________________</p>
                      </div>
                    )}
                    {question.type === 'short_answer' && (
                      <div className="ml-4 mt-2">
                        <div className="border-b border-gray-300 h-8"></div>
                        <div className="border-b border-gray-300 h-8"></div>
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {/* Answer Key Section */}
              <div className="mt-8 pt-4 border-t-2 border-dashed print:break-before-page">
                <h3 className="font-bold text-lg mb-4">Answer Key</h3>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                  {worksheet.questions.map((question, index) => (
                    <p key={question.id} className="text-sm">
                      Q{index + 1}: {question.correct_answer}
                    </p>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
