import { useState, useEffect, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { api } from '@/lib/api'
import { useChildren } from '@/lib/children'
import { useClasses } from '@/lib/classes'
import { useProfile } from '@/lib/profile'
import { useSubscription } from '@/lib/subscription'
import TopicSelector from '@/components/TopicSelector'
import CBSESyllabusViewer from '@/components/CBSESyllabusViewer'
import TemplateSelector, { TEMPLATES, type WorksheetTemplate } from '@/components/TemplateSelector'
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
  const { classes } = useClasses()
  const { activeRole } = useProfile()
  const { status: subscription, incrementUsage, upgrade } = useSubscription()
  const { recordCompletion, lastCompletion, clearLastCompletion } = useEngagement()
  const [selectedChildId, setSelectedChildId] = useState('none')
  const [selectedClassId, setSelectedClassId] = useState('none')
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null)
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
  const [downloadingPdfType, setDownloadingPdfType] = useState<string | null>(null)
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
    if (childId && childId !== 'none') {
      const child = children.find(c => c.id === childId)
      if (child) {
        setGrade(child.grade)
        if (child.board) {
          setBoard(child.board)
        }
      }
    }
  }

  // Handle class selection - pre-fill grade, subject, and board (teacher mode)
  const handleClassSelect = (classId: string) => {
    setSelectedClassId(classId)
    if (classId && classId !== 'none') {
      const cls = classes.find(c => c.id === classId)
      if (cls) {
        setGrade(cls.grade)
        setSubject(cls.subject)
        setBoard(cls.board)
      }
    }
  }

  // Handle template selection - pre-fill difficulty, question count, and instructions
  const handleTemplateSelect = (template: WorksheetTemplate | null) => {
    if (template) {
      setSelectedTemplate(template.id)
      setDifficulty(template.difficulty)
      setQuestionCount(String(template.questionCount))
      setCustomInstructions(template.customInstructions)
    } else {
      setSelectedTemplate('custom')
      setDifficulty('')
      setQuestionCount('10')
      setCustomInstructions('')
    }
  }

  const isTeacher = activeRole === 'teacher'

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

  const handleDownloadPdf = async (pdfType: string = 'full') => {
    if (!worksheet) return

    setDownloadingPdf(true)
    setDownloadingPdfType(pdfType)
    try {
      const response = await api.post('/api/worksheets/export-pdf', {
        worksheet,
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

      // Record completion for engagement tracking (if child selected)
      if (selectedChildId && selectedChildId !== 'none') {
        await recordCompletion(selectedChildId)
      }
    } catch (err) {
      console.error('Failed to download PDF:', err)
      setError('Failed to download PDF')
    } finally {
      setDownloadingPdf(false)
      setDownloadingPdfType(null)
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
        child_id: !isTeacher && selectedChildId !== 'none' ? selectedChildId : undefined,
        class_id: isTeacher && selectedClassId !== 'none' ? selectedClassId : undefined,
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
    <div className="py-8 px-4">
      <div className="max-w-4xl mx-auto">
        {/* Hero Section */}
        <div className="text-center mb-8 animate-fade-in">
          <div className="decorative-dots mb-4" />
          <h1 className="text-3xl md:text-4xl mb-3">Create Your Worksheet</h1>
          <p className="text-muted-foreground text-lg max-w-xl mx-auto">
            {activeRole === 'teacher'
              ? 'Generate AI-powered worksheets aligned to your class syllabus'
              : 'Thoughtfully designed practice materials aligned to your child\'s learning journey'
            }
          </p>
        </div>

        {/* Trust Micro-copy */}
        <div className="flex flex-wrap justify-center gap-3 mb-8 print:hidden animate-fade-in-delayed">
          <span className="trust-badge">
            <svg viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
            </svg>
            CBSE-aligned
          </span>
          <span className="trust-badge">
            <svg viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M4 4a2 2 0 012-2h8a2 2 0 012 2v12a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 0v12h8V4H6z" clipRule="evenodd" />
            </svg>
            Printable
          </span>
          <span className="trust-badge">
            <svg viewBox="0 0 20 20" fill="currentColor">
              <path d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" />
            </svg>
            For parents
          </span>
        </div>

        {/* Upgrade Banner */}
        {subscription && !subscription.can_generate && (
          <div className="mb-6 p-5 bg-gradient-to-r from-accent/10 via-accent/5 to-transparent border border-accent/30 rounded-xl print:hidden animate-fade-in">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 rounded-full bg-accent/20 flex items-center justify-center">
                  <svg className="w-5 h-5 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                  </svg>
                </div>
                <div>
                  <p className="font-semibold text-foreground">Free tier limit reached</p>
                  <p className="text-sm text-muted-foreground">
                    You've used all 3 free worksheets. Upgrade for unlimited access.
                  </p>
                </div>
              </div>
              <Button onClick={() => upgrade()} className="btn-animate bg-accent hover:bg-accent/90 text-accent-foreground">
                Upgrade to Pro
              </Button>
            </div>
          </div>
        )}

        {/* Usage Info for Free Tier */}
        {subscription && subscription.tier === 'free' && subscription.can_generate && (
          <div className="mb-6 p-4 bg-secondary/50 border border-border rounded-xl print:hidden">
            <div className="flex items-center gap-3">
              <div className="flex gap-1">
                {[1, 2, 3].map((i) => (
                  <div
                    key={i}
                    className={`w-2.5 h-2.5 rounded-full ${
                      i <= (3 - (subscription.worksheets_remaining || 0))
                        ? 'bg-primary'
                        : 'bg-border'
                    }`}
                  />
                ))}
              </div>
              <p className="text-sm text-muted-foreground">
                <span className="font-medium text-foreground">{subscription.worksheets_remaining}</span> of 3 free worksheets remaining this month
              </p>
            </div>
          </div>
        )}

        {/* Syllabus Banner */}
        {syllabus && (
          <div className="mb-6 p-4 bg-primary/5 border border-primary/20 rounded-xl flex items-center justify-between print:hidden">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                <svg className="w-5 h-5 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <div>
                <p className="font-medium text-foreground">Using syllabus: {syllabus.name}</p>
                <p className="text-sm text-muted-foreground">
                  {syllabus.grade} {syllabus.subject && `• ${syllabus.subject}`} • {syllabus.chapters.length} chapters
                </p>
              </div>
            </div>
            <Button variant="outline" size="sm" onClick={onClearSyllabus} className="border-primary/30 text-primary hover:bg-primary/10">
              Clear
            </Button>
          </div>
        )}

        {/* CBSE Syllabus Viewer - show as reference when custom syllabus uploaded */}
        {syllabus && grade && syllabus.subject && (
          <div className="mb-6 print:hidden">
            <details className="group">
              <summary className="cursor-pointer text-sm text-muted-foreground hover:text-foreground transition-colors mb-2 flex items-center gap-2">
                <svg className="w-4 h-4 transition-transform group-open:rotate-90" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </svg>
                View official CBSE syllabus for comparison
              </summary>
              <CBSESyllabusViewer grade={grade} subject={syllabus.subject} />
            </details>
          </div>
        )}

        {/* Generator Form */}
        <Card className="mb-8 print:hidden card-hover paper-texture border-border/50 shadow-lg">
          <CardHeader className="pb-4">
            <div className="flex items-center gap-3 mb-2">
              <div className="decorative-line" />
            </div>
            <CardTitle className="text-xl">Configure Your Worksheet</CardTitle>
            <CardDescription>
              {syllabus
                ? 'Select a chapter and topic from your syllabus'
                : 'Choose options to create a personalized practice worksheet'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {/* Template Selector */}
            <div className="mb-6">
              <TemplateSelector
                selectedTemplate={selectedTemplate}
                onSelect={handleTemplateSelect}
              />
            </div>

            {/* Difficulty Preview - shown when template is selected */}
            {selectedTemplate && selectedTemplate !== 'custom' && (() => {
              const tmpl = TEMPLATES.find(t => t.id === selectedTemplate)
              if (!tmpl) return null
              return (
                <div className="mb-6 p-4 bg-secondary/30 border border-border/50 rounded-xl">
                  <div className="flex items-center gap-3 mb-2">
                    <svg className="w-4 h-4 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
                      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                    <span className="text-sm font-medium text-foreground">Preview: {tmpl.name}</span>
                  </div>
                  <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
                    <span className="flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-primary" />
                      {tmpl.questionCount} questions
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span className={`w-2 h-2 rounded-full ${
                        tmpl.difficulty === 'Easy' ? 'bg-emerald-500' :
                        tmpl.difficulty === 'Medium' ? 'bg-amber-500' : 'bg-red-500'
                      }`} />
                      {tmpl.difficulty} difficulty
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-accent" />
                      Mixed question types
                    </span>
                  </div>
                </div>
              )
            })()}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Class Selector (teacher mode) */}
              {isTeacher && classes.length > 0 && (
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="class">Generate for Class</Label>
                  <Select value={selectedClassId} onValueChange={handleClassSelect}>
                    <SelectTrigger id="class">
                      <SelectValue placeholder="Select a class (optional)" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">No class selected</SelectItem>
                      {classes.map((cls) => (
                        <SelectItem key={cls.id} value={cls.id}>
                          {cls.name} ({cls.grade} — {cls.subject})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              {/* Child Selector (parent mode) */}
              {!isTeacher && children.length > 0 && (
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="child">Generate for</Label>
                  <Select value={selectedChildId} onValueChange={handleChildSelect}>
                    <SelectTrigger id="child">
                      <SelectValue placeholder="Select a child (optional)" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">No child selected</SelectItem>
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
                <Select value={grade} onValueChange={setGrade} disabled={isTeacher && selectedClassId !== 'none'}>
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
                  <Select value={subject} onValueChange={(val) => { setSubject(val); setTopic('') }} disabled={isTeacher && selectedClassId !== 'none'}>
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
                      childId={selectedChildId !== 'none' ? selectedChildId : undefined}
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
              <div className="mt-4 p-4 bg-destructive/10 border border-destructive/20 text-destructive rounded-lg flex items-center gap-3 animate-fade-in">
                <svg className="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                {error}
              </div>
            )}

            <Button
              className="w-full mt-6 btn-animate bg-primary hover:bg-primary/90 py-6 text-base font-medium"
              onClick={handleGenerate}
              disabled={loading}
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <span className="spinner !w-5 !h-5 !border-primary-foreground/30 !border-t-primary-foreground" />
                  Crafting your worksheet...
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456z" />
                  </svg>
                  Generate Worksheet
                </span>
              )}
            </Button>
          </CardContent>
        </Card>

        {/* Completion Feedback */}
        {lastCompletion && selectedChildId && selectedChildId !== 'none' && (
          <div className="mb-6 p-5 bg-gradient-to-r from-primary/10 via-primary/5 to-transparent border border-primary/20 rounded-xl print:hidden animate-fade-in">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-full bg-primary/20 flex items-center justify-center star-animate">
                  <svg className="w-6 h-6 text-primary" fill="currentColor" viewBox="0 0 20 20">
                    <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                  </svg>
                </div>
                <div>
                  <p className="font-semibold text-foreground">Worksheet completed!</p>
                  <p className="text-sm text-muted-foreground flex items-center gap-3">
                    <span className="flex items-center gap-1">
                      <svg className="w-4 h-4 text-accent" fill="currentColor" viewBox="0 0 20 20">
                        <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                      </svg>
                      {lastCompletion.stars_earned} star earned
                    </span>
                    <span className="flex items-center gap-1">
                      <svg className="w-4 h-4 text-orange-500" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M12.395 2.553a1 1 0 00-1.45-.385c-.345.23-.614.558-.822.88-.214.33-.403.713-.57 1.116-.334.804-.614 1.768-.84 2.734a31.365 31.365 0 00-.613 3.58 2.64 2.64 0 01-.945-1.067c-.328-.68-.398-1.534-.398-2.654A1 1 0 005.05 6.05 6.981 6.981 0 003 11a7 7 0 1011.95-4.95c-.592-.591-.98-.985-1.348-1.467-.363-.476-.724-1.063-1.207-2.03zM12.12 15.12A3 3 0 017 13s.879.5 2.5.5c0-1 .5-4 1.25-4.5.5 1 .786 1.293 1.371 1.879A2.99 2.99 0 0113 13a2.99 2.99 0 01-.879 2.121z" clipRule="evenodd" />
                      </svg>
                      {lastCompletion.current_streak}-day streak
                    </span>
                  </p>
                </div>
              </div>
              <button
                onClick={clearLastCompletion}
                className="text-muted-foreground hover:text-foreground transition-colors"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>
        )}

        {/* Generated Worksheet */}
        {worksheet && (
          <Card className="print:shadow-none print:border-none paper-texture animate-fade-in">
            <CardHeader className="print:pb-2">
              <div className="flex flex-col md:flex-row justify-between items-start gap-4">
                <div>
                  <div className="decorative-line mb-3 print:hidden" />
                  <CardTitle className="text-2xl md:text-3xl">{worksheet.title}</CardTitle>
                  <div className="flex flex-wrap gap-2 mt-3">
                    {[worksheet.grade, worksheet.subject, worksheet.topic, worksheet.difficulty].map((tag, i) => (
                      <span key={i} className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-secondary text-secondary-foreground">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="flex gap-2 print:hidden">
                  <Button
                    onClick={handleSave}
                    disabled={saving}
                    variant={saveSuccess ? "outline" : "default"}
                    className={saveSuccess ? "border-primary text-primary" : ""}
                  >
                    {saving ? (
                      <span className="flex items-center gap-2">
                        <span className="spinner !w-4 !h-4" />
                        Saving...
                      </span>
                    ) : saveSuccess ? (
                      <span className="flex items-center gap-2">
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                        Saved!
                      </span>
                    ) : (
                      <span className="flex items-center gap-2">
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
                        </svg>
                        Save
                      </span>
                    )}
                  </Button>
                  {isTeacher ? (
                    <>
                      <Button onClick={() => handleDownloadPdf('student')} disabled={downloadingPdf} className="btn-animate">
                        {downloadingPdfType === 'student' ? (
                          <span className="flex items-center gap-2">
                            <span className="spinner !w-4 !h-4 !border-primary-foreground/30 !border-t-primary-foreground" />
                            Downloading...
                          </span>
                        ) : (
                          <span className="flex items-center gap-2">
                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                            </svg>
                            Student PDF
                          </span>
                        )}
                      </Button>
                      <Button onClick={() => handleDownloadPdf('answer_key')} disabled={downloadingPdf} variant="outline">
                        {downloadingPdfType === 'answer_key' ? (
                          <span className="flex items-center gap-2">
                            <span className="spinner !w-4 !h-4" />
                            Downloading...
                          </span>
                        ) : (
                          <span className="flex items-center gap-2">
                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
                            </svg>
                            Answer Key
                          </span>
                        )}
                      </Button>
                    </>
                  ) : (
                    <Button onClick={() => handleDownloadPdf('full')} disabled={downloadingPdf} className="btn-animate">
                      {downloadingPdf ? (
                        <span className="flex items-center gap-2">
                          <span className="spinner !w-4 !h-4 !border-primary-foreground/30 !border-t-primary-foreground" />
                          Downloading...
                        </span>
                      ) : (
                        <span className="flex items-center gap-2">
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                          </svg>
                          PDF
                        </span>
                      )}
                    </Button>
                  )}
                  <Button onClick={handlePrint} variant="outline">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" />
                    </svg>
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="mb-6 p-4 bg-secondary/50 border border-border rounded-lg print:bg-gray-100">
                <p className="font-semibold text-foreground flex items-center gap-2">
                  <svg className="w-5 h-5 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Instructions
                </p>
                <p className="text-sm text-muted-foreground mt-1">Answer all questions. Show your work where applicable.</p>
              </div>

              <div className="space-y-6 stagger-children">
                {worksheet.questions.map((question, index) => (
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
                    {question.type === 'fill_blank' && (
                      <div className="ml-9 mt-3">
                        <p className="text-muted-foreground">Answer: <span className="border-b-2 border-dashed border-border inline-block w-40"></span></p>
                      </div>
                    )}
                    {question.type === 'short_answer' && (
                      <div className="ml-9 mt-3 space-y-3">
                        <div className="border-b border-border/50 h-8"></div>
                        <div className="border-b border-border/50 h-8"></div>
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {/* Answer Key Section (hidden for teachers — they use Answer Key PDF) */}
              {!isTeacher && (
                <div className="mt-10 pt-6 border-t-2 border-dashed border-border print:break-before-page">
                  <h3 className="font-semibold text-lg mb-4 flex items-center gap-2">
                    <svg className="w-5 h-5 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
                    </svg>
                    Answer Key
                  </h3>
                  <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                    {worksheet.questions.map((question, index) => (
                      <div key={question.id} className="flex items-center gap-2 p-2 bg-secondary/30 rounded-lg text-sm">
                        <span className="font-medium text-primary">Q{index + 1}:</span>
                        <span className="text-foreground">{question.correct_answer}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
