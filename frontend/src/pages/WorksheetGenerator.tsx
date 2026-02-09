import { useState, useEffect, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { PageHeader } from '@/components/ui/page-header'
import { Section } from '@/components/ui/section'
import { api } from '@/lib/api'
import { useChildren } from '@/lib/children'
import { useClasses } from '@/lib/classes'
import { useProfile } from '@/lib/profile'
import { useSubscription } from '@/lib/subscription'
import TopicSelector from '@/components/TopicSelector'
import CBSESyllabusViewer from '@/components/CBSESyllabusViewer'
import { Skeleton } from '@/components/ui/skeleton'
import TemplateSelector, { type WorksheetTemplate } from '@/components/TemplateSelector'
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
    <div className="py-10 px-4 max-w-5xl mx-auto">
      {/* Hero Section */}
      <PageHeader className="text-center md:text-left mb-12">
        <PageHeader.Title className="text-pretty">
          {activeRole === 'teacher' ? 'Classroom Question Bank' : 'Targeted Practice for Your Child'}
        </PageHeader.Title>
        <PageHeader.Subtitle className="max-w-2xl mx-auto md:mx-0 text-pretty">
          {activeRole === 'teacher'
            ? 'Generate classroom-ready worksheets perfectly aligned to your school syllabus and difficulty requirements.'
            : 'Personalized practice materials that follow your child’s actual school curriculum. No more generic worksheets—just what they need to learn today.'
          }
        </PageHeader.Subtitle>

        {/* Value Differentiation Badges */}
        <div className="flex flex-wrap justify-center md:justify-start gap-3 mt-6 print:hidden">
          <div className="trust-badge">
            <svg viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
            </svg>
            CBSE + School Syllabus
          </div>
          <div className="trust-badge">
            <svg viewBox="0 0 20 20" fill="currentColor">
              <path d="M10.394 2.08a1 1 0 00-.788 0l-7 3a1 1 0 000 1.84L5.25 8.051a.999.999 0 01.356-.257l4-1.714a1 1 0 11.788 1.838L7.667 9.088c-.34.146-.34.628 0 .774l2.726 1.168a1 1 0 00.788 0l7-3a1 1 0 000-1.84l-7-3z" />
              <path d="M9.25 13.23l-4.75-2.035v1.645a1 1 0 00.57.908l4 1.715a1 1 0 00.84 0l4-1.715a1 1 0 00.57-.908v-1.645L9.75 13.23a1 1 0 00-.5 0z" />
            </svg>
            8+ Regional Languages
          </div>
          <div className="trust-badge">
            <svg viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M5 4v3H4a2 2 0 00-2 2v3a2 2 0 002 2h1v2a2 2 0 002 2h6a2 2 0 002-2v-2h1a2 2 0 002-2V9a2 2 0 00-2-2h-1V4a2 2 0 00-2-2H7a2 2 0 00-2 2zm8 0v3H7V4h6zm-1 9H8v2h4v-2z" clipRule="evenodd" />
            </svg>
            Printable On-demand
          </div>
          <div className="trust-badge">
            <svg viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M2.166 4.999A11.954 11.954 0 0010 1.944 11.954 11.954 0 0017.834 5c.11.65.166 1.32.166 2.001 0 4.946-2.56 9.29-6.433 11.779A11.954 11.954 0 0110 19.056a11.954 11.954 0 01-7.567-2.277C1.44 14.29 1 10.946 1 7c0-.68.056-1.35.166-2.001zm10.54 3.708a1 1 0 00-1.414-1.414L9 9.586 7.707 8.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
            </svg>
            Grade-Safe & Private
          </div>
        </div>
      </PageHeader>

      {/* Upgrade Banner */}
      {subscription && !subscription.can_generate && (
        <div className="mb-8 p-6 bg-accent/5 border border-accent/20 rounded-2xl print:hidden animate-fade-in">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-6">
            <div className="flex items-center gap-5">
              <div className="w-12 h-12 rounded-xl bg-accent/10 flex items-center justify-center text-accent">
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                </svg>
              </div>
              <div>
                <p className="font-semibold text-lg text-foreground">Unlock Unlimited Practice</p>
                <p className="text-sm text-muted-foreground">
                  You've used all free worksheets for this month. Upgrade to Pro for unlimited generation.
                </p>
              </div>
            </div>
            <Button onClick={() => upgrade()} size="lg" className="shrink-0">
              Get Unlimited Access
            </Button>
          </div>
        </div>
      )}

      {/* Usage Info for Free Tier */}
      {subscription && subscription.tier === 'free' && subscription.can_generate && (
        <div className="mb-8 p-4 bg-secondary border border-border rounded-xl print:hidden">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="flex gap-1.5">
                {[1, 2, 3].map((i) => (
                  <div
                    key={i}
                    className={`w-3 h-3 rounded-full transition-colors ${i <= (3 - (subscription.worksheets_remaining || 0))
                      ? 'bg-primary'
                      : 'bg-border'
                      }`}
                  />
                ))}
              </div>
              <p className="text-sm">
                <span className="font-semibold text-foreground">{subscription.worksheets_remaining}</span> free worksheets remaining this month
              </p>
            </div>
            {subscription.worksheets_remaining === 1 && (
              <p className="text-xs text-muted-foreground animate-pulse">Running low! Upgrade to never run out.</p>
            )}
          </div>
        </div>
      )}

      {/* Syllabus Banner */}
      {syllabus && (
        <div className="mb-8 p-5 bg-primary/5 border border-primary/10 rounded-2xl flex flex-col sm:flex-row items-center justify-between gap-4 print:hidden">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center text-primary">
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <div>
              <p className="font-semibold text-foreground leading-none mb-1">Active Syllabus: {syllabus.name}</p>
              <p className="text-sm text-muted-foreground italic">
                {syllabus.grade} {syllabus.subject && `• ${syllabus.subject}`} • {syllabus.chapters.length} chapters loaded
              </p>
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={onClearSyllabus} className="border-primary/20 text-primary hover:bg-primary/10">
            Switch Syllabus
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
      <Card className="mb-12 print:hidden overflow-hidden border-border/50 shadow-xl bg-background/50 backdrop-blur-sm">
        <CardContent className="p-0">
          <div className="divide-y divide-border/50">
            {/* Step 1: Student Context */}
            {(classes.length > 0 || children.length > 0) && (
              <Section className="p-6 md:p-8">
                <Section.Header>
                  <Section.Title className="flex items-center gap-2">
                    <span className="flex items-center justify-center w-6 h-6 rounded-full bg-primary/10 text-primary text-xs font-bold">1</span>
                    Student Profile
                  </Section.Title>
                </Section.Header>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-4">
                  {isTeacher && classes.length > 0 && (
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="class" className="text-sm font-semibold">Generate for Class</Label>
                      <Select value={selectedClassId} onValueChange={handleClassSelect}>
                        <SelectTrigger id="class" className="bg-background">
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

                  {!isTeacher && children.length > 0 && (
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="child" className="text-sm font-semibold">Generate for</Label>
                      <Select value={selectedChildId} onValueChange={handleChildSelect}>
                        <SelectTrigger id="child" className="bg-background">
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
                </div>
              </Section>
            )}

            {/* Step 2: Syllabus & Topic */}
            <Section className="p-6 md:p-8 bg-primary/[0.02]">
              <Section.Header>
                <Section.Title className="flex items-center gap-2">
                  <span className="flex items-center justify-center w-6 h-6 rounded-full bg-primary/10 text-primary text-xs font-bold">
                    {(classes.length > 0 || children.length > 0) ? '2' : '1'}
                  </span>
                  Syllabus & Topic
                </Section.Title>
              </Section.Header>

              <div className="mt-6 space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {/* Board & Grade */}
                  <div className="space-y-4">
                    <div className="space-y-2">
                      <Label htmlFor="board" className="text-sm font-semibold">Board *</Label>
                      <Select value={board} onValueChange={setBoard}>
                        <SelectTrigger id="board" className="bg-background">
                          <SelectValue placeholder="Select board" />
                        </SelectTrigger>
                        <SelectContent>
                          {BOARDS.map((b) => (
                            <SelectItem key={b} value={b}>{b}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="grade" className="text-sm font-semibold">Grade *</Label>
                      <Select value={grade} onValueChange={setGrade} disabled={isTeacher && selectedClassId !== 'none'}>
                        <SelectTrigger id="grade" className="bg-background">
                          <SelectValue placeholder="Select grade" />
                        </SelectTrigger>
                        <SelectContent>
                          {GRADES.map((g) => (
                            <SelectItem key={g} value={g}>{g}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  {/* Subject & Chapter/Topic */}
                  <div className="space-y-4">
                    {!syllabus && (
                      <div className="space-y-2">
                        <Label htmlFor="subject" className="text-sm font-semibold">Subject *</Label>
                        <Select value={subject} onValueChange={(val) => { setSubject(val); setTopic('') }} disabled={isTeacher && selectedClassId !== 'none'}>
                          <SelectTrigger id="subject" className="bg-background">
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

                    {syllabus && (
                      <div className="space-y-2">
                        <Label htmlFor="chapter" className="text-sm font-semibold">Chapter *</Label>
                        <Select value={chapter} onValueChange={(val) => { setChapter(val); setTopic('') }}>
                          <SelectTrigger id="chapter" className="bg-background">
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

                    {(syllabus || cbseSyllabus.length === 0) && (
                      <div className="space-y-2">
                        <Label htmlFor="topic" className="text-sm font-semibold">Topic *</Label>
                        <Select
                          value={topic}
                          onValueChange={setTopic}
                          disabled={syllabus ? !chapter : !subject}
                        >
                          <SelectTrigger id="topic" className="bg-background">
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
                  </div>
                </div>

                {/* Advanced Topic Selector */}
                {!syllabus && cbseSyllabus.length > 0 && (
                  <div className="pt-2">
                    {loadingSyllabus ? (
                      <div className="space-y-4 p-4 rounded-xl border border-border/50 bg-secondary/20">
                        <div className="flex items-center gap-3">
                          <Skeleton className="h-4 w-4 rounded-full" />
                          <Skeleton className="h-4 w-1/3" />
                        </div>
                        <div className="grid grid-cols-2 gap-3">
                          <Skeleton className="h-10 w-full" />
                          <Skeleton className="h-10 w-full" />
                          <Skeleton className="h-10 w-full" />
                          <Skeleton className="h-10 w-full" />
                        </div>
                      </div>
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
              </div>
            </Section>

            {/* Step 3: Practice Settings */}
            <Section className="p-6 md:p-8">
              <Section.Header>
                <Section.Title className="flex items-center gap-2">
                  <span className="flex items-center justify-center w-6 h-6 rounded-full bg-primary/10 text-primary text-xs font-bold">
                    {(classes.length > 0 || children.length > 0) ? '3' : '2'}
                  </span>
                  Practice Settings
                </Section.Title>
              </Section.Header>
              <div className="mt-6 space-y-6">
                <TemplateSelector
                  selectedTemplate={selectedTemplate}
                  onSelect={handleTemplateSelect}
                />

                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <div className="space-y-2">
                    <Label htmlFor="difficulty" className="text-sm font-semibold">Difficulty *</Label>
                    <Select value={difficulty} onValueChange={setDifficulty}>
                      <SelectTrigger id="difficulty" className="bg-background">
                        <SelectValue placeholder="Select difficulty" />
                      </SelectTrigger>
                      <SelectContent>
                        {DIFFICULTIES.map((d) => (
                          <SelectItem key={d} value={d}>{d}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="questionCount" className="text-sm font-semibold">Questions</Label>
                    <Select value={questionCount} onValueChange={setQuestionCount}>
                      <SelectTrigger id="questionCount" className="bg-background">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {QUESTION_COUNTS.map((c) => (
                          <SelectItem key={c} value={c}>{c} questions</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="language" className="text-sm font-semibold">Language</Label>
                    <Select value={language} onValueChange={setLanguage}>
                      <SelectTrigger id="language" className="bg-background">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {LANGUAGES.map((l) => (
                          <SelectItem key={l} value={l}>{l}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="customInstructions" className="text-sm font-semibold">Custom Instructions (Optional)</Label>
                  <Textarea
                    id="customInstructions"
                    placeholder="E.g., Focus on geometry, include word problems, or emphasize specific concepts..."
                    className="min-h-[100px] bg-background resize-none"
                    value={customInstructions}
                    onChange={(e) => setCustomInstructions(e.target.value)}
                  />
                </div>
              </div>
            </Section>
          </div>

          {/* Action Footer */}
          <div className="p-6 md:p-8 bg-background border-t border-border/50">
            {error && (
              <div className="mb-6 p-4 bg-destructive/5 border border-destructive/20 text-destructive text-sm rounded-xl flex items-center gap-3 animate-fade-in font-medium">
                <svg className="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                {error}
              </div>
            )}

            <Button
              className="w-full py-7 text-lg font-bold shadow-lg shadow-primary/20 transition-all hover:scale-[1.01] active:scale-[0.99] rounded-2xl"
              onClick={handleGenerate}
              disabled={loading}
              size="lg"
            >
              {loading ? (
                <span className="flex items-center gap-3">
                  <span className="spinner !w-5 !h-5 !border-primary-foreground/30 !border-t-primary-foreground" />
                  Generating Worksheet...
                </span>
              ) : (
                <span className="flex items-center gap-3">
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 001.423 1.423l1.183.394-1.183.394a2.25 2.25 0 00-1.423 1.423z" />
                  </svg>
                  Generate Practice Worksheet
                </span>
              )}
            </Button>
            <p className="mt-4 text-center text-xs text-muted-foreground">
              By clicking generate, you use one worksheet credit. Aligned to CBSE & School standards.
            </p>
          </div>
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
        <Card className="print:shadow-none print:border-none paper-texture animate-fade-in border-border/40 shadow-2xl relative overflow-hidden">
          {/* Subtle Academic Header Accent */}
          <div className="absolute top-0 left-0 right-0 h-1.5 bg-primary/20 print:hidden" />

          <CardHeader className="print:pb-6 pt-10 px-8">
            <div className="flex flex-col md:flex-row justify-between items-start gap-6">
              <div className="space-y-4">
                <CardTitle className="text-3xl md:text-4xl font-serif text-foreground leading-tight">
                  {worksheet.title}
                </CardTitle>
                <div className="flex flex-wrap gap-2 print:mt-4">
                  {[worksheet.grade, worksheet.subject, worksheet.topic, worksheet.difficulty].map((tag, i) => (
                    <span key={i} className="inline-flex items-center px-3 py-1 rounded-md text-[10px] uppercase tracking-wider font-bold bg-secondary text-secondary-foreground border border-border/50">
                      {tag}
                    </span>
                  ))}
                </div>
              </div>

              <div className="flex flex-wrap gap-2 print:hidden shrink-0">
                <Button
                  onClick={handleSave}
                  disabled={saving}
                  variant={saveSuccess ? "outline" : "secondary"}
                  className={saveSuccess ? "border-primary text-primary bg-primary/5" : "bg-white"}
                  size="sm"
                >
                  {saving ? (
                    <>
                      <span className="spinner !w-3.5 !h-3.5 mr-2" />
                      Saving
                    </>
                  ) : saveSuccess ? (
                    <>
                      <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                      </svg>
                      Saved
                    </>
                  ) : (
                    <>
                      <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M17.593 3.322c1.1.128 1.907 1.077 1.907 2.185V21L12 17.25 4.5 21V5.507c0-1.108.806-2.057 1.907-2.185a48.507 48.507 0 0113.186 0z" />
                      </svg>
                      Save
                    </>
                  )}
                </Button>

                <div className="h-8 w-px bg-border/50 mx-1 hidden sm:block" />

                {isTeacher ? (
                  <>
                    <Button onClick={() => handleDownloadPdf('student')} disabled={downloadingPdf} size="sm" className="bg-primary text-primary-foreground shadow-sm">
                      {downloadingPdf && downloadingPdfType === 'student' ? (
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
                    <Button onClick={() => handleDownloadPdf('answer_key')} disabled={downloadingPdf} variant="outline" size="sm">
                      {downloadingPdf && downloadingPdfType === 'answer_key' ? (
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
                  <Button onClick={() => handleDownloadPdf('full')} disabled={downloadingPdf} size="sm" className="bg-primary text-primary-foreground shadow-sm">
                    {downloadingPdf ? (
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

                <Button onClick={handlePrint} variant="outline" size="sm" className="px-3">
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6.72 13.829c-.24.03-.48.062-.72.096m.72-.096a42.415 42.415 0 0110.56 0m-10.56 0L6.34 18m10.94-4.171c.24.03.48.062.72.096m-.72-.096L17.66 18m0 0l.229 2.523a1.125 1.125 0 01-1.12 1.227H7.231c-.618 0-1.103-.508-1.12-1.227L6.34 18m11.318-8.22L16.5 3a.75.75 0 00-.75-.75h-7.5a.75.75 0 00-.75.75l-1.15 6.756M16.5 9.78h.008v.008H16.5V9.78zm-.45-2.88h.008v.008h-.008V6.9zm-2.25.45h.008v.008h-.008V7.35zm0 1.8h.008v.008h-.008V9.15zm-2.25-2.25h.008v.008h-.008V6.9zm0 1.8h.008v.008h-.008V8.7zm-2.25-1.8h.008V7h-.008V6.9zm0 1.8h.008v.008h-.008V8.7zm2.25 4.5h.008v.008h-.008v-.008zm0-1.8h.008v.008h-.008v-.008zm1.8 1.8h.008v.008h-.008v-.008zm0-1.8h.008v.008h-.008v-.008z" />
                  </svg>
                </Button>
              </div>
            </div>
          </CardHeader>

          <CardContent className="px-8 pb-12">
            <div className="mb-8 p-5 bg-primary/[0.03] border border-primary/10 rounded-xl print:border-border print:bg-transparent">
              <p className="font-bold text-foreground flex items-center gap-2 mb-1 uppercase tracking-tight text-xs">
                Instructions for Student
              </p>
              <p className="text-sm text-muted-foreground">Please read each question carefully and provide your best answer. Show all necessary workings in the space provided. Good luck!</p>
            </div>

            <div className="space-y-10 mt-8">
              {worksheet.questions.map((question, index) => (
                <div key={question.id} className="relative group stagger-item">
                  <div className="flex gap-5">
                    <span className="flex-shrink-0 inline-flex items-center justify-center w-8 h-8 rounded bg-foreground text-background text-sm font-bold mt-0.5">
                      {index + 1}
                    </span>
                    <div className="flex-grow space-y-4">
                      <p className="text-lg font-medium text-foreground leading-snug">
                        {question.text}
                      </p>

                      {question.options && (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-4">
                          {question.options.map((option, optIndex) => (
                            <div key={optIndex} className="flex items-center gap-3 p-3 rounded-lg border border-border/60 bg-white/50 print:bg-transparent print:border-border">
                              <span className="w-6 h-6 rounded-full border border-border flex items-center justify-center text-[10px] font-bold text-muted-foreground flex-shrink-0">
                                {String.fromCharCode(65 + optIndex)}
                              </span>
                              <span className="text-sm text-foreground">{option}</span>
                            </div>
                          ))}
                        </div>
                      )}

                      {question.type === 'fill_blank' && (
                        <div className="mt-4 pt-4">
                          <div className="border-b-2 border-dotted border-border w-2/3 h-6"></div>
                        </div>
                      )}

                      {question.type === 'short_answer' && (
                        <div className="mt-4 space-y-4">
                          <div className="border-b border-border/40 h-8"></div>
                          <div className="border-b border-border/40 h-8"></div>
                          <div className="border-b border-border/40 h-8"></div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Answer Key Section (hidden for teachers — they use Answer Key PDF) */}
            {!isTeacher && (
              <div className="mt-16 pt-10 border-t-2 border-dashed border-border/50 print:break-before-page">
                <h3 className="font-serif text-2xl mb-6 flex items-center gap-2 text-foreground/80">
                  <svg className="w-5 h-5 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 5.25a3 3 0 013 3m3 0a6 6 0 01-7.029 5.912c-.563-.097-1.159.026-1.563.43L10.5 17.25H8.25v2.25H6v2.25H2.25v-2.818c0-.597.237-1.17.659-1.591l6.499-6.499c.404-.404.527-1 .43-1.563A6 6 0 1121.75 8.25z" />
                  </svg>
                  Answer Key Reference
                </h3>
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                  {worksheet.questions.map((question, index) => (
                    <div key={question.id} className="flex items-center gap-3 p-3 bg-secondary/20 rounded-lg text-sm border border-border/50">
                      <span className="font-bold text-primary">Q{index + 1}</span>
                      <span className="text-foreground font-medium">{question.correct_answer}</span>
                    </div>
                  ))}
                </div>
                <p className="mt-4 text-[10px] text-muted-foreground italic">Use this section for evaluation or guidance.</p>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
