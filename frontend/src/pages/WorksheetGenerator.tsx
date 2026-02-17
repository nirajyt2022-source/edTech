import { useState, useEffect, useCallback, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { PageHeader } from '@/components/ui/page-header'
import { api, apiV1WithFallback } from '@/lib/api'
import { useChildren } from '@/lib/children'
import { useClasses } from '@/lib/classes'
import { useProfile } from '@/lib/profile'
import { useSubscription } from '@/lib/subscription'
import { fetchSubjects, fetchSkills, type CurriculumSubject } from '@/lib/curriculum'
import TopicSelector from '@/components/TopicSelector'
import SkillSelector from '@/components/SkillSelector'
import CBSESyllabusViewer from '@/components/CBSESyllabusViewer'
import { Skeleton } from '@/components/ui/skeleton'
import TemplateSelector, { type WorksheetTemplate } from '@/components/TemplateSelector'
import VisualProblem from '@/components/VisualProblem'
import { useEngagement } from '@/lib/engagement'

const BOARDS = ['CBSE']
const GRADES = ['Class 1', 'Class 2', 'Class 3', 'Class 4', 'Class 5']
const DIFFICULTIES = ['Easy', 'Medium', 'Hard']
const LANGUAGES = ['English', 'Hindi', 'Marathi', 'Tamil', 'Telugu', 'Kannada', 'Arabic', 'Urdu']
const QUESTION_COUNTS = ['5', '10', '15', '20']
const PROBLEM_STYLES = [
  { value: 'standard', label: 'Standard' },
  { value: 'visual', label: 'Visual' },
  { value: 'mixed', label: 'Mixed' },
]
const VISUAL_THEMES = [
  { value: 'mono', label: 'Print-safe (Monochrome)' },
  { value: 'color', label: 'Color on screen' },
]

// Fallback topics for when curriculum API is unavailable
const DEFAULT_TOPICS: Record<string, string[]> = {
  Maths: ['Addition', 'Subtraction', 'Multiplication', 'Division', 'Fractions', 'Word Problems'],
  English: ['Nouns', 'Verbs', 'Pronouns', 'Sentences', 'Punctuation', 'Vocabulary'],
  EVS: ['Environment', 'Family & Community', 'Daily Life', 'Plants & Animals'],
  Hindi: ['Varnamala', 'Matras', 'Shabd Rachna', 'Vakya Rachna', 'Kahani Lekhan'],
  Science: ['Living Things', 'Matter', 'Force and Motion', 'Earth and Space', 'Human Body'],
  Computer: ['Computer Basics', 'Parts of Computer', 'MS Paint', 'MS Word', 'Internet Safety'],
}

// Grade-aware English topics (matching backend TOPIC_PROFILES keys)
const ENGLISH_TOPICS_BY_GRADE: Record<number, string[]> = {
  2: ['Nouns (Class 2)', 'Verbs (Class 2)', 'Pronouns (Class 2)', 'Sentences (Class 2)', 'Rhyming Words (Class 2)', 'Punctuation (Class 2)'],
  3: ['Nouns (Class 3)', 'Verbs (Class 3)', 'Adjectives (Class 3)', 'Pronouns (Class 3)', 'Tenses (Class 3)', 'Punctuation (Class 3)', 'Vocabulary (Class 3)', 'Reading Comprehension (Class 3)'],
  4: ['Tenses (Class 4)', 'Sentence Types (Class 4)', 'Conjunctions (Class 4)', 'Prepositions (Class 4)', 'Adverbs (Class 4)', 'Prefixes and Suffixes (Class 4)', 'Vocabulary (Class 4)', 'Reading Comprehension (Class 4)'],
}

// Grade-aware Science topics (matching backend TOPIC_PROFILES keys)
const SCIENCE_TOPICS_BY_GRADE: Record<number, string[]> = {
  3: ['Plants (Class 3)', 'Animals (Class 3)', 'Food and Nutrition (Class 3)', 'Shelter (Class 3)', 'Water (Class 3)', 'Air (Class 3)', 'Our Body (Class 3)'],
}

// Grade-aware Hindi topics (matching backend TOPIC_PROFILES keys)
const HINDI_TOPICS_BY_GRADE: Record<number, string[]> = {
  3: ['Varnamala (Class 3)', 'Matras (Class 3)', 'Shabd Rachna (Class 3)', 'Vakya Rachna (Class 3)', 'Kahani Lekhan (Class 3)'],
}

interface Question {
  id: string
  type: string
  text: string
  options?: string[]
  correct_answer?: string
  explanation?: string
  visual_type?: string
  visual_data?: Record<string, unknown>
  role?: string
  difficulty?: string
}

interface Worksheet {
  title: string
  grade: string
  subject: string
  topic: string
  difficulty: string
  language: string
  questions: Question[]
  learning_objectives?: string[]
  mastery_snapshot?: {
    mastery_level: string
    last_error_type: string | null
    avg_streak: number
    total_attempts: number
  } | null
}

interface GenerateResponse {
  worksheet: Worksheet
  worksheets?: Worksheet[]
  generation_time_ms?: number
  warnings?: unknown
  verdict?: string
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
  const { activeRole, region } = useProfile()
  const { status: subscription, incrementUsage, upgrade, refresh: refreshSubscription } = useSubscription()
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
  const [problemStyle, setProblemStyle] = useState('standard')
  const [visualTheme, setVisualTheme] = useState<'mono' | 'color'>('mono')
  const [customInstructions, setCustomInstructions] = useState('')

  const [loading, setLoading] = useState(false)
  const [downloadingPdf, setDownloadingPdf] = useState(false)
  const [downloadingPdfType, setDownloadingPdfType] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [worksheet, setWorksheet] = useState<Worksheet | null>(null)
  const [worksheets, setWorksheets] = useState<Worksheet[] | null>(null)
  const [activeIdx, setActiveIdx] = useState(0)
  const [error, setError] = useState('')
  const [saveSuccess, setSaveSuccess] = useState(false)
  const [savedWorksheetId, setSavedWorksheetId] = useState<string | null>(null)
  const [sharing, setSharing] = useState(false)
  const [copySuccess, setCopySuccess] = useState(false)
  const [showAnswers, setShowAnswers] = useState(false)
  const [revealedHints, setRevealedHints] = useState<Set<string>>(new Set())
  const [mobileView, setMobileView] = useState<'edit' | 'preview'>('edit')

  // Curriculum-based state
  const [curriculumSubjects, setCurriculumSubjects] = useState<CurriculumSubject[]>([])
  const [curriculumSkills, setCurriculumSkills] = useState<string[]>([])
  const [curriculumLogicTags, setCurriculumLogicTags] = useState<string[]>([])
  const [selectedSkills, setSelectedSkills] = useState<string[]>([])
  const [selectedLogicTags, setSelectedLogicTags] = useState<string[]>([])
  const [loadingCurriculum, setLoadingCurriculum] = useState(false)

  // CBSE syllabus state
  const [cbseSyllabus, setCbseSyllabus] = useState<SyllabusChapter[]>([])
  const [selectedTopics, setSelectedTopics] = useState<string[]>([])
  const [studentAnswers, setStudentAnswers] = useState<Record<string, string>>({})

  const handleStudentAnswer = useCallback((questionId: string, value: string) => {
    setStudentAnswers(prev => ({ ...prev, [questionId]: value }))
  }, [])
  const [loadingSyllabus, setLoadingSyllabus] = useState(false)

  // Selection version guard for async race prevention
  const selectionVersionRef = useRef(0)
  useEffect(() => {
    selectionVersionRef.current += 1
  }, [region, board, grade, subject, topic, selectedSkills, selectedLogicTags, selectedTopics, selectedTemplate, difficulty, questionCount, language, problemStyle, visualTheme, customInstructions])

  // Reset subject and topic when region changes
  useEffect(() => {
    setSubject('')
    setTopic('')
    setSelectedSkills([])
    setSelectedLogicTags([])
    setSelectedTopics([])
  }, [region])

  // Fetch curriculum subjects when grade or region changes
  useEffect(() => {
    if (syllabus || !grade) {
      setCurriculumSubjects([])
      return
    }
    const gradeNum = parseInt(grade.replace('Class ', ''))
    if (isNaN(gradeNum)) return

    let cancelled = false
    setLoadingCurriculum(true)
    fetchSubjects(gradeNum, region, true).then(subjects => {
      if (!cancelled) {
        setCurriculumSubjects(subjects)
        setLoadingCurriculum(false)
      }
    }).catch(() => {
      if (!cancelled) {
        setCurriculumSubjects([])
        setLoadingCurriculum(false)
      }
    })
    return () => { cancelled = true }
  }, [grade, region, syllabus])

  // Fetch skills when subject changes (curriculum-based)
  useEffect(() => {
    if (syllabus || !grade || !subject || curriculumSubjects.length === 0) {
      setCurriculumSkills([])
      setCurriculumLogicTags([])
      setSelectedSkills([])
      setSelectedLogicTags([])
      return
    }
    const gradeNum = parseInt(grade.replace('Class ', ''))
    if (isNaN(gradeNum)) return

    let cancelled = false
    fetchSkills(gradeNum, subject, region).then(detail => {
      if (!cancelled) {
        setCurriculumSkills(detail.skills)
        setCurriculumLogicTags(detail.logic_tags)
        setSelectedSkills(detail.skills)
        setSelectedLogicTags(detail.logic_tags)
      }
    }).catch(() => {
      if (!cancelled) {
        setCurriculumSkills([])
        setCurriculumLogicTags([])
      }
    })
    return () => { cancelled = true }
  }, [grade, subject, region, syllabus, curriculumSubjects.length])

  // Handle skill selection changes from SkillSelector
  const handleSkillSelectionChange = useCallback((skills: string[], logicTags: string[]) => {
    setSelectedSkills(skills)
    setSelectedLogicTags(logicTags)
  }, [])

  // Whether to use curriculum skill-based flow
  const useCurriculumFlow = !syllabus && curriculumSubjects.length > 0

  // Topic dropdown only needed for chapter-bounded worksheet types
  const needsTopic = selectedTemplate === 'chapter-test'

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
    const newId = template?.id ?? 'custom'
    if (newId !== 'chapter-test') {
      setTopic('')
    }
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
      // Grade-aware English topics
      if (subject === 'English' && grade) {
        const gradeNum = parseInt(grade.replace('Class ', ''))
        if (!isNaN(gradeNum) && ENGLISH_TOPICS_BY_GRADE[gradeNum]) {
          return ENGLISH_TOPICS_BY_GRADE[gradeNum]
        }
      }
      // Grade-aware Science topics
      if (subject === 'Science' && grade) {
        const gradeNum = parseInt(grade.replace('Class ', ''))
        if (!isNaN(gradeNum) && SCIENCE_TOPICS_BY_GRADE[gradeNum]) {
          return SCIENCE_TOPICS_BY_GRADE[gradeNum]
        }
      }
      // Grade-aware Hindi topics
      if (subject === 'Hindi' && grade) {
        const gradeNum = parseInt(grade.replace('Class ', ''))
        if (!isNaN(gradeNum) && HINDI_TOPICS_BY_GRADE[gradeNum]) {
          return HINDI_TOPICS_BY_GRADE[gradeNum]
        }
      }
      return DEFAULT_TOPICS[subject] || []
    }
    return []
  }

  const availableTopics = getAvailableTopics()

  const handleGenerate = async () => {
    // Refresh subscription status to get accurate count before generation
    await refreshSubscription()

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
    const useAdvancedSelection = !syllabus && !useCurriculumFlow && cbseSyllabus.length > 0
    const topicsToUse = useAdvancedSelection ? selectedTopics : [topic]

    if (!board || !grade || !difficulty) {
      setError('Please fill in all required fields')
      return
    }
    if (!syllabus && !subject) {
      setError('Please select a subject')
      return
    }
    // Validate skill/topic selection
    if (useCurriculumFlow && selectedSkills.length === 0) {
      setError('Please select at least one skill')
      return
    }
    if (!useCurriculumFlow && useAdvancedSelection && selectedTopics.length === 0) {
      setError('Please select at least one topic')
      return
    }
    if (!useCurriculumFlow && !useAdvancedSelection && !topic) {
      setError('Please select a topic')
      return
    }

    setLoading(true)
    setError('')
    setWorksheet(null)
    setWorksheets(null)
    setActiveIdx(0)

    const requestVersion = selectionVersionRef.current

    // Use chapter name as context if from syllabus, or combine selected topics/skills
    const topicWithContext = syllabus && chapter
      ? `${chapter} - ${topic}`
      : useCurriculumFlow
        ? selectedSkills.slice(0, 5).join(', ')
        : useAdvancedSelection
          ? topicsToUse.slice(0, 5).join(', ')
          : topic

    try {
      const response = await apiV1WithFallback<GenerateResponse>('post', '/api/worksheets/generate', {
        board,
        grade_level: grade,
        subject: syllabus?.subject || subject,
        topic: topicWithContext,
        difficulty: difficulty.toLowerCase(),
        num_questions: parseInt(questionCount),
        language,
        problem_style: problemStyle,
        custom_instructions: customInstructions || undefined,
        skills: useCurriculumFlow ? selectedSkills : undefined,
        logic_tags: useCurriculumFlow ? selectedLogicTags : undefined,
        region,
      })
      // Discard stale result if selections changed during request
      if (selectionVersionRef.current !== requestVersion) return
      const wsList = response.data.worksheets?.length ? response.data.worksheets : [response.data.worksheet]
      setWorksheets(wsList)
      setActiveIdx(0)
      setWorksheet(wsList[0])
      setMobileView('preview')

      // Track usage for free tier
      await incrementUsage()
    } catch (err: unknown) {
      if (selectionVersionRef.current !== requestVersion) return
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
      const response = await apiV1WithFallback<BlobPart>('post', '/api/worksheets/export-pdf', {
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
      const saveRes = await api.post('/api/worksheets/save', {
        worksheet,
        board,
        child_id: !isTeacher && selectedChildId !== 'none' ? selectedChildId : undefined,
        class_id: isTeacher && selectedClassId !== 'none' ? selectedClassId : undefined,
        region,
      })
      if (saveRes.data?.worksheet_id) {
        setSavedWorksheetId(saveRes.data.worksheet_id)
      }
      setSaveSuccess(true)
      setTimeout(() => setSaveSuccess(false), 3000)
    } catch (err) {
      console.error('Failed to save worksheet:', err)
      setError('Failed to save worksheet')
    } finally {
      setSaving(false)
    }
  }

  const getShareUrl = async (): Promise<string | null> => {
    if (!savedWorksheetId) return null
    setSharing(true)
    try {
      const res = await api.post(`/api/worksheets/${savedWorksheetId}/share`)
      return res.data?.share_url || null
    } catch (err) {
      console.error('Failed to generate share link:', err)
      setError('Failed to generate share link. Please save the worksheet first.')
      return null
    } finally {
      setSharing(false)
    }
  }

  const handleShareWhatsApp = async () => {
    const url = await getShareUrl()
    if (url) {
      const text = encodeURIComponent(`Check out this ${worksheet?.topic || ''} worksheet on PracticeCraft: ${url}`)
      window.open(`https://wa.me/?text=${text}`, '_blank')
    }
  }

  const handleCopyLink = async () => {
    const url = await getShareUrl()
    if (url) {
      try {
        await navigator.clipboard.writeText(url)
        setCopySuccess(true)
        setTimeout(() => setCopySuccess(false), 2500)
      } catch (err) {
        console.warn('Clipboard write failed, using fallback:', err)
        // Fallback for older browsers
        const textArea = document.createElement('textarea')
        textArea.value = url
        document.body.appendChild(textArea)
        textArea.select()
        document.execCommand('copy')
        document.body.removeChild(textArea)
        setCopySuccess(true)
        setTimeout(() => setCopySuccess(false), 2500)
      }
    }
  }

  return (
    <div className="py-10 px-4 max-w-7xl mx-auto print:p-0 print:max-w-none bg-paper-texture">
      {/* Hero Section */}
      <PageHeader className="text-center md:text-left mb-12 print:hidden">
        <PageHeader.Title className="text-pretty">
          {activeRole === 'teacher' ? 'Teacher Toolkit' : 'Personalized Practice'}
        </PageHeader.Title>
        <PageHeader.Subtitle className="max-w-2xl mx-auto md:mx-0 text-pretty">
          {activeRole === 'teacher'
            ? 'Create worksheets aligned to your school syllabus and specific classroom needs.'
            : 'Worksheets that follow your child’s actual school curriculum for effective learning.'
          }
        </PageHeader.Subtitle>

        {/* Value Differentiation Badges */}
        <div className="flex flex-wrap justify-center md:justify-start gap-3 mt-6 print:hidden">
          <div className="trust-badge">
            <svg viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
            </svg>
            CBSE-aligned Primary Curriculum
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

      {/* Split-screen Workspace */}
      <div className="lg:flex lg:gap-10 print:block">
        {/* Left Panel — Controls */}
        <div className={`lg:w-[40%] lg:min-w-0 lg:shrink-0 print:hidden ${mobileView === 'preview' && worksheet ? 'hidden lg:block' : ''}`}>
          {/* Generator Controls */}
          <div className="print:hidden space-y-7">
            {/* Student Profile — anchored starting context */}
            {(classes.length > 0 || children.length > 0) && (
              <div className="px-5 py-4 bg-secondary/25 border border-border/30 rounded-xl">
                <p className="text-[11px] font-semibold text-muted-foreground/70 tracking-wide mb-3">Student Profile</p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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
              </div>
            )}

            {/* Skills & Practice Focus */}
            <div>
              <p className="text-[11px] font-semibold text-muted-foreground/70 tracking-wide mb-3">Skills & Practice Focus</p>
              <div className="space-y-5">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
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
                    <Select value={grade} onValueChange={(val) => { setGrade(val); setSubject(''); setTopic(''); setSelectedSkills([]); setSelectedLogicTags([]); setSelectedTopics([]) }} disabled={isTeacher && selectedClassId !== 'none'}>
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

                  {!syllabus && (
                    <div className="space-y-2">
                      <Label htmlFor="subject" className="text-sm font-semibold">Subject *</Label>
                      <Select value={subject} onValueChange={(val) => { setSubject(val); setTopic(''); setSelectedSkills([]); setSelectedLogicTags([]); setSelectedTopics([]) }} disabled={isTeacher && selectedClassId !== 'none'}>
                        <SelectTrigger id="subject" className="bg-background">
                          <SelectValue placeholder={loadingCurriculum ? "Preparing subjects..." : "Select subject"} />
                        </SelectTrigger>
                        <SelectContent>
                          {useCurriculumFlow
                            ? curriculumSubjects.map((s) => (
                              <SelectItem key={s.name} value={s.name}>
                                {s.name}
                                {s.depth === 'reinforcement' && ' (Additional)'}
                              </SelectItem>
                            ))
                            : DEFAULT_TOPICS && Object.keys(DEFAULT_TOPICS).map((s) => (
                              <SelectItem key={s} value={s}>{s}</SelectItem>
                            ))
                          }
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

                  {(syllabus || (!useCurriculumFlow && cbseSyllabus.length === 0) || (useCurriculumFlow && needsTopic)) && (
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

                {/* Skill Selector (curriculum-based flow) */}
                {useCurriculumFlow && curriculumSkills.length > 0 && !syllabus && (
                  <div className="pt-2">
                    <SkillSelector
                      skills={curriculumSkills}
                      logicTags={curriculumLogicTags}
                      onSelectionChange={handleSkillSelectionChange}
                    />
                  </div>
                )}

                {/* Advanced Topic Selector (fallback for CBSE syllabus DB) */}
                {!useCurriculumFlow && !syllabus && cbseSyllabus.length > 0 && (
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
            </div>

            {/* Practice Settings */}
            <div>
              <p className="text-[11px] font-semibold text-muted-foreground/70 tracking-wide mb-3">Practice Settings</p>
              <div className="space-y-5">
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

                  <div className="space-y-2">
                    <Label htmlFor="problemStyle" className="text-sm font-semibold">Problem Style</Label>
                    <Select value={problemStyle} onValueChange={setProblemStyle}>
                      <SelectTrigger id="problemStyle" className="bg-background">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {PROBLEM_STYLES.map((s) => (
                          <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="visualTheme" className="text-sm font-semibold">Visual Theme</Label>
                    <Select value={visualTheme} onValueChange={(v) => setVisualTheme(v as 'mono' | 'color')}>
                      <SelectTrigger id="visualTheme" className="bg-background">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {VISUAL_THEMES.map((t) => (
                          <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
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
            </div>

            {/* Action */}
            <div className="pt-2">
            {error && (
              <div role="alert" className="mb-6 p-4 bg-destructive/5 border border-destructive/20 text-destructive text-sm rounded-xl flex items-center gap-3 animate-fade-in font-medium">
                <svg className="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                {error}
              </div>
            )}

            {subscription && !subscription.can_generate ? (
              <Button
                className="w-full py-4 text-lg font-bold shadow-lg shadow-accent/20 transition-all hover:scale-[1.01] active:scale-[0.99] rounded-xl bg-accent hover:bg-accent/90"
                onClick={() => upgrade()}
                size="lg"
              >
                <span className="flex items-center gap-3">
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                  </svg>
                  Upgrade for Unlimited Worksheets
                </span>
              </Button>
            ) : (
              <Button
                className="w-full py-4 text-lg font-bold shadow-lg shadow-primary/20 transition-all hover:scale-[1.01] active:scale-[0.99] rounded-xl"
                onClick={handleGenerate}
                disabled={loading}
                aria-busy={loading}
                size="lg"
              >
                {loading ? (
                  <span className="flex items-center gap-3">
                    <span className="spinner !w-5 !h-5 !border-primary-foreground/30 !border-t-primary-foreground" />
                    Preparing practice aligned to your syllabus...
                  </span>
                ) : (
                  <span className="flex items-center gap-3">
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 001.423 1.423l1.183.394-1.183.394a2.25 2.25 0 00-1.423 1.423z" />
                    </svg>
                    Create today's practice
                  </span>
                )}
              </Button>
            )}
            <p className="mt-3 text-center text-xs text-muted-foreground">
              Uses one worksheet credit. Aligned to CBSE and school standards.
            </p>
            </div>
          </div>
        </div>

        {/* Right Panel — Preview */}
        <div className={`mt-8 lg:mt-0 lg:w-[60%] lg:min-w-0 print:w-full print:mt-0 ${mobileView === 'edit' ? 'hidden lg:block' : ''}`}>
          <div className="lg:sticky lg:top-6 lg:max-h-[calc(100vh-3rem)] lg:overflow-y-auto print:max-h-none print:overflow-visible print:static print:w-full">
            {loading ? (
              <Card className="overflow-hidden border-border/20 shadow-xl bg-white">
                <CardHeader className="pt-12 px-10">
                  <p className="text-sm text-muted-foreground font-medium mb-6">Preparing practice aligned to your syllabus...</p>
                  <Skeleton className="h-10 w-3/4 mb-4" />
                  <div className="flex gap-2">
                    <Skeleton className="h-6 w-16 rounded-md" />
                    <Skeleton className="h-6 w-20 rounded-md" />
                    <Skeleton className="h-6 w-16 rounded-md" />
                  </div>
                </CardHeader>
                <CardContent className="px-10 pb-14 space-y-8">
                  <Skeleton className="h-20 w-full rounded-xl" />
                  {[1, 2, 3].map(i => (
                    <div key={i} className="flex gap-5">
                      <Skeleton className="w-8 h-8 rounded flex-shrink-0" />
                      <div className="flex-grow space-y-3">
                        <Skeleton className="h-6 w-full" />
                        <Skeleton className="h-4 w-2/3" />
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>
            ) : worksheet ? (
              <Card className="print:shadow-none print:border-none paper-texture animate-fade-in border-border/20 shadow-xl bg-white relative overflow-hidden">
                {/* Subtle Academic Header Accent */}
                <div className="absolute top-0 left-0 right-0 h-px bg-primary/15 print:hidden" />

                <CardHeader className="print:pb-4 print:px-0 print:pt-0 pt-12 px-10">
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

                      {/* Multi-skill tabs */}
                      {worksheets && worksheets.length > 1 && (
                        <div className="flex flex-wrap gap-1.5 print:hidden">
                          {worksheets.map((ws, i) => (
                            <button
                              key={i}
                              onClick={() => { setActiveIdx(i); setWorksheet(ws) }}
                              className={`px-3 py-1 rounded-md text-xs font-medium border transition-colors ${
                                i === activeIdx
                                  ? 'bg-primary text-primary-foreground border-primary'
                                  : 'bg-secondary/50 text-muted-foreground border-border/50 hover:bg-secondary'
                              }`}
                            >
                              {ws.topic || ws.title}
                            </button>
                          ))}
                        </div>
                      )}
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

                      <Button
                        onClick={() => setShowAnswers(!showAnswers)}
                        variant={showAnswers ? "default" : "outline"}
                        size="sm"
                        className={showAnswers ? "bg-primary/90 text-primary-foreground" : ""}
                      >
                        {showAnswers ? (
                          <>
                            <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
                              <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                            </svg>
                            Hide Answers
                          </>
                        ) : (
                          <>
                            <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
                            </svg>
                            Show Answers
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
                                Preparing...
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
                                Preparing...
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
                        <Button onClick={() => handleDownloadPdf(showAnswers ? 'full' : 'student')} disabled={downloadingPdf} size="sm" className="bg-primary text-primary-foreground shadow-sm">
                          {downloadingPdf ? (
                            <>
                              <span className="spinner !w-3.5 !h-3.5 mr-2 !border-primary-foreground/30 !border-t-primary-foreground" />
                              Preparing...
                            </>
                          ) : (
                            <>
                              <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
                              </svg>
                              {showAnswers ? 'PDF with Answers' : 'Print or save'}
                            </>
                          )}
                        </Button>
                      )}

                      <Button onClick={handlePrint} variant="outline" size="sm" className="px-3">
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M6.72 13.829c-.24.03-.48.062-.72.096m.72-.096a42.415 42.415 0 0110.56 0m-10.56 0L6.34 18m10.94-4.171c.24.03.48.062.72.096m-.72-.096L17.66 18m0 0l.229 2.523a1.125 1.125 0 01-1.12 1.227H7.231c-.618 0-1.103-.508-1.12-1.227L6.34 18m11.318-8.22L16.5 3a.75.75 0 00-.75-.75h-7.5a.75.75 0 00-.75.75l-1.15 6.756M16.5 9.78h.008v.008H16.5V9.78zm-.45-2.88h.008v.008h-.008V6.9zm-2.25.45h.008v.008h-.008V7.35zm0 1.8h.008v.008h-.008V9.15zm-2.25-2.25h.008v.008h-.008V6.9zm0 1.8h.008v.008h-.008V8.7zm-2.25-1.8h.008V7h-.008V6.9zm0 1.8h.008v.008h-.008V8.7zm2.25 4.5h.008v.008h-.008v-.008zm0-1.8h.008v.008h-.008v-.008zm1.8 1.8h.008v.008h-.008v-.008zm0-1.8h.008v.008h-.008v-.008z" />
                        </svg>
                      </Button>

                      {/* Share buttons — only visible after saving */}
                      {savedWorksheetId && (
                        <>
                          <div className="h-8 w-px bg-border/50 mx-1 hidden sm:block" />
                          <Button
                            onClick={handleShareWhatsApp}
                            disabled={sharing}
                            variant="outline"
                            size="sm"
                            className="text-green-700 border-green-200 hover:bg-green-50"
                          >
                            {sharing ? (
                              <span className="spinner !w-3.5 !h-3.5 mr-2" />
                            ) : (
                              <svg className="w-4 h-4 mr-2" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z" />
                              </svg>
                            )}
                            WhatsApp
                          </Button>
                          <Button
                            onClick={handleCopyLink}
                            disabled={sharing}
                            variant="outline"
                            size="sm"
                            className={copySuccess ? "border-primary text-primary bg-primary/5" : ""}
                          >
                            {copySuccess ? (
                              <>
                                <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                                </svg>
                                Copied!
                              </>
                            ) : (
                              <>
                                <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m9.193-1.124a4.5 4.5 0 00-1.242-7.244l-4.5-4.5a4.5 4.5 0 00-6.364 6.364L4.93 8.128" />
                                </svg>
                                Copy Link
                              </>
                            )}
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                </CardHeader>

                <CardContent className="px-10 pb-14 print:px-0 print:pb-0">
                  {/* Print-only: Name / Date / Score header */}
                  <div className="hidden print:flex print:justify-between print:items-end print:mb-6 print:pb-3 print:border-b print:border-black/20">
                    <span className="text-sm">Name: ______________________________</span>
                    <span className="text-sm">Date: ______________</span>
                    <span className="text-sm">Score: _____ / {worksheet.questions.length}</span>
                  </div>

                  {/* Learning Objectives (Gold-G5) */}
                  {worksheet.learning_objectives && worksheet.learning_objectives.length > 0 && (
                    <div className="mb-8 p-5 border border-primary/20 rounded-xl bg-primary/[0.03] print:border-primary/30 print:rounded-none print:p-4">
                      <p className="font-bold text-primary text-sm mb-2 tracking-tight">Today's Learning Goal</p>
                      <ul className="space-y-1">
                        {worksheet.learning_objectives.map((obj, i) => (
                          <li key={i} className="flex items-start gap-2 text-sm text-foreground/80">
                            <span className="text-primary mt-0.5 text-xs">&#10003;</span>
                            <span>{obj}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Mastery Badge (Gold-G2) — screen only */}
                  {worksheet.mastery_snapshot && (
                    <div className="mb-6 flex items-center gap-3 text-sm print:hidden">
                      <span className={`px-3 py-1 rounded-full text-xs font-semibold ${
                        worksheet.mastery_snapshot.mastery_level === 'mastered' ? 'bg-green-100 text-green-800' :
                        worksheet.mastery_snapshot.mastery_level === 'improving' ? 'bg-blue-100 text-blue-800' :
                        worksheet.mastery_snapshot.mastery_level === 'learning' ? 'bg-amber-100 text-amber-800' :
                        'bg-gray-100 text-gray-600'
                      }`}>
                        {worksheet.mastery_snapshot.mastery_level === 'mastered' ? 'Mastered' :
                         worksheet.mastery_snapshot.mastery_level === 'improving' ? 'Improving' :
                         worksheet.mastery_snapshot.mastery_level === 'learning' ? 'Learning' : 'New Topic'}
                      </span>
                      <span className="text-muted-foreground">
                        Personalised based on {worksheet.mastery_snapshot.total_attempts} previous attempts
                      </span>
                    </div>
                  )}

                  <div className="mb-10 p-5 bg-secondary/30 border border-border/30 rounded-xl print:border-border print:bg-gray-100 print:rounded-none print:p-4">
                    <p className="font-semibold text-foreground/80 flex items-center gap-2 mb-1 text-xs">
                      Instructions for Student
                    </p>
                    <p className="text-sm text-muted-foreground">Read each question carefully. Show your working in the space provided. Answer all questions.</p>
                  </div>

                  {/* Tiered question rendering */}
                  {(() => {
                    const foundationRoles = new Set(['recognition', 'representation'])
                    const applicationRoles = new Set(['application'])
                    const stretchRoles = new Set(['error_detection', 'thinking'])
                    const tiers: { key: string; label: string; desc: string; stars: string; questions: Question[] }[] = []

                    const foundationQs = worksheet.questions.filter(q => foundationRoles.has(q.role || ''))
                    const applicationQs = worksheet.questions.filter(q => applicationRoles.has(q.role || ''))
                    const stretchQs = worksheet.questions.filter(q => stretchRoles.has(q.role || ''))

                    if (foundationQs.length) tiers.push({ key: 'foundation', label: 'Foundation', desc: 'I can recall and recognise', stars: '\u2605', questions: foundationQs })
                    if (applicationQs.length) tiers.push({ key: 'application', label: 'Application', desc: 'I can use what I know', stars: '\u2605\u2605', questions: applicationQs })
                    if (stretchQs.length) tiers.push({ key: 'stretch', label: 'Stretch', desc: 'I can think and reason', stars: '\u2605\u2605\u2605', questions: stretchQs })

                    // Fallback: if no role data, render flat
                    const hasRoles = tiers.length > 0
                    const allQuestions = hasRoles
                      ? tiers.flatMap(t => t.questions)
                      : worksheet.questions

                    let qNum = 0
                    return (
                      <div className="space-y-6 mt-10">
                        {hasRoles ? tiers.map(tier => (
                          <div key={tier.key}>
                            <div className="flex items-baseline gap-3 mb-1 mt-6 print:mt-4">
                              <span className="text-primary font-semibold text-sm">{tier.stars}</span>
                              <h4 className="font-serif text-lg font-bold text-primary tracking-tight">{tier.label}</h4>
                              <span className="text-xs text-muted-foreground italic ml-1">{tier.desc}</span>
                            </div>
                            <div className="border-b border-primary/20 mb-6 print:border-black/15" />

                            <div className="space-y-10">
                              {tier.questions.map((question) => {
                                qNum++
                                const idx = qNum
                                const starCount = tier.key === 'foundation' ? 1 : tier.key === 'application' ? 2 : 3
                                return (
                                  <div key={question.id} className="relative group stagger-item" style={{ breakInside: 'avoid', pageBreakInside: 'avoid' }}>
                                    <div className="flex gap-5">
                                      <div className="flex-shrink-0 flex flex-col items-center gap-0.5 mt-0.5">
                                        <span className="inline-flex items-center justify-center w-7 h-7 rounded-full border-2 border-primary/20 text-primary/70 text-xs font-bold print:border-black/30 print:text-black/60">
                                          {idx}
                                        </span>
                                        <span className="text-[9px] text-amber-500 leading-none print:text-black/40" title={`${tier.label} (${starCount} star${starCount > 1 ? 's' : ''})`}>
                                          {'\u2605'.repeat(starCount)}
                                        </span>
                                      </div>
                                      <div className="flex-grow space-y-4">
                                        <p className="text-lg font-medium text-foreground leading-snug">{question.text}</p>
                                        {question.visual_type && question.visual_data && (
                                          <div className="mt-3">
                                            <VisualProblem visualType={question.visual_type} visualData={question.visual_data} colorMode={visualTheme} studentAnswer={studentAnswers[question.id]} onStudentAnswerChange={(val) => handleStudentAnswer(question.id, val)} />
                                          </div>
                                        )}
                                        {question.options && (
                                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-4">
                                            {question.options.map((option, optIndex) => (
                                              <div key={optIndex} className="flex items-center gap-3 p-3.5 rounded-lg border border-border/40 bg-white/50 print:bg-transparent print:border-black/20 print:rounded-none print:p-2.5">
                                                <span className="w-6 h-6 rounded-full border border-border flex items-center justify-center text-[10px] font-bold text-muted-foreground flex-shrink-0">{String.fromCharCode(65 + optIndex)}</span>
                                                <span className="text-sm text-foreground">{option}</span>
                                              </div>
                                            ))}
                                          </div>
                                        )}
                                        {question.type === 'fill_blank' && (
                                          <div className="mt-4 pt-4"><div className="border-b-2 border-dotted border-border w-2/3 h-6"></div></div>
                                        )}
                                        {question.type === 'short_answer' && (
                                          <div className="mt-4 space-y-4">
                                            <div className="border-b border-border/40 h-8"></div>
                                            <div className="border-b border-border/40 h-8"></div>
                                            <div className="border-b border-border/40 h-8"></div>
                                          </div>
                                        )}
                                        {/* Hint for thinking/error_detection (Gold-G6) */}
                                        {question.explanation && (question.role === 'thinking' || question.role === 'error_detection') && (
                                          <div className="mt-3 print:mt-2">
                                            {revealedHints.has(question.id) ? (
                                              <div className="p-3 bg-amber-50 border border-amber-200/60 rounded-lg text-sm text-amber-900 italic print:bg-gray-50 print:border-gray-300 print:text-gray-600">
                                                <span className="font-semibold not-italic text-amber-700 print:text-gray-700">Hint: </span>
                                                {question.explanation}
                                              </div>
                                            ) : (
                                              <button
                                                onClick={() => setRevealedHints(prev => new Set(prev).add(question.id))}
                                                className="inline-flex items-center gap-1.5 text-xs text-amber-600 hover:text-amber-700 font-medium transition-colors print:hidden"
                                              >
                                                <span>&#128161;</span> Show Hint
                                              </button>
                                            )}
                                          </div>
                                        )}
                                      </div>
                                    </div>
                                  </div>
                                )
                              })}
                            </div>
                          </div>
                        )) : (
                          <div className="space-y-12">
                            {allQuestions.map((question, index) => (
                              <div key={question.id} className="relative group stagger-item" style={{ breakInside: 'avoid', pageBreakInside: 'avoid' }}>
                                <div className="flex gap-5">
                                  <span className="flex-shrink-0 inline-flex items-center justify-center w-7 h-7 rounded-full border-2 border-foreground/15 text-foreground/50 text-xs font-semibold mt-0.5 print:border-black/30 print:text-black/60">{index + 1}</span>
                                  <div className="flex-grow space-y-4">
                                    <p className="text-lg font-medium text-foreground leading-snug">{question.text}</p>
                                    {question.visual_type && question.visual_data && (
                                      <div className="mt-3">
                                        <VisualProblem visualType={question.visual_type} visualData={question.visual_data} colorMode={visualTheme} studentAnswer={studentAnswers[question.id]} onStudentAnswerChange={(val) => handleStudentAnswer(question.id, val)} />
                                      </div>
                                    )}
                                    {question.options && (
                                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-4">
                                        {question.options.map((option, optIndex) => (
                                          <div key={optIndex} className="flex items-center gap-3 p-3.5 rounded-lg border border-border/40 bg-white/50 print:bg-transparent print:border-black/20 print:rounded-none print:p-2.5">
                                            <span className="w-6 h-6 rounded-full border border-border flex items-center justify-center text-[10px] font-bold text-muted-foreground flex-shrink-0">{String.fromCharCode(65 + optIndex)}</span>
                                            <span className="text-sm text-foreground">{option}</span>
                                          </div>
                                        ))}
                                      </div>
                                    )}
                                    {question.type === 'fill_blank' && (
                                      <div className="mt-4 pt-4"><div className="border-b-2 border-dotted border-border w-2/3 h-6"></div></div>
                                    )}
                                    {question.type === 'short_answer' && (
                                      <div className="mt-4 space-y-4">
                                        <div className="border-b border-border/40 h-8"></div>
                                        <div className="border-b border-border/40 h-8"></div>
                                        <div className="border-b border-border/40 h-8"></div>
                                      </div>
                                    )}
                                    {/* Hint for thinking/error_detection (Gold-G6) */}
                                    {question.explanation && (question.role === 'thinking' || question.role === 'error_detection') && (
                                      <div className="mt-3 print:mt-2">
                                        {revealedHints.has(question.id) ? (
                                          <div className="p-3 bg-amber-50 border border-amber-200/60 rounded-lg text-sm text-amber-900 italic print:bg-gray-50 print:border-gray-300 print:text-gray-600">
                                            <span className="font-semibold not-italic text-amber-700 print:text-gray-700">Hint: </span>
                                            {question.explanation}
                                          </div>
                                        ) : (
                                          <button
                                            onClick={() => setRevealedHints(prev => new Set(prev).add(question.id))}
                                            className="inline-flex items-center gap-1.5 text-xs text-amber-600 hover:text-amber-700 font-medium transition-colors print:hidden"
                                          >
                                            <span>&#128161;</span> Show Hint
                                          </button>
                                        )}
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )
                  })()}

                  {/* Answer Key Section — visible when showAnswers is true */}
                  {showAnswers && (
                    <div className="mt-16 pt-10 border-t border-border/30 print:break-before-page print:mt-0 print:pt-0 print:border-none">
                      <h3 className="font-serif text-2xl mb-6 flex items-center gap-2 text-foreground/80">
                        <svg className="w-5 h-5 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 5.25a3 3 0 013 3m3 0a6 6 0 01-7.029 5.912c-.563-.097-1.159.026-1.563.43L10.5 17.25H8.25v2.25H6v2.25H2.25v-2.818c0-.597.237-1.17.659-1.591l6.499-6.499c.404-.404.527-1 .43-1.563A6 6 0 1121.75 8.25z" />
                        </svg>
                        Answer Key Reference
                      </h3>
                      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                        {worksheet.questions.map((question, index) => (
                          <div key={question.id} className="flex items-center gap-3 p-3 bg-secondary/20 rounded-lg text-sm border border-border/50 print:bg-gray-100 print:border-black/15 print:rounded-none">
                            <span className="font-bold text-primary">Q{index + 1}</span>
                            <span className="text-foreground font-medium">{question.correct_answer || '---'}</span>
                          </div>
                        ))}
                      </div>
                      <p className="mt-4 text-[10px] text-muted-foreground italic">Use this section for evaluation or guidance.</p>
                    </div>
                  )}

                  {/* Parent Insight Footer (Gold-G7) — screen only */}
                  {worksheet.mastery_snapshot && (
                    <div className="mt-10 p-5 border border-primary/15 rounded-xl bg-primary/[0.02] print:hidden">
                      <p className="font-bold text-primary text-sm mb-3">For Parents: What to Do Next</p>
                      {worksheet.mastery_snapshot.last_error_type && (
                        <div className="mb-3">
                          <p className="text-xs font-semibold text-foreground/60 mb-1">Watch For</p>
                          <p className="text-sm text-foreground/80">
                            {worksheet.mastery_snapshot.last_error_type === 'carry_tens' && 'Your child may be forgetting to carry when the tens column adds up to more than 9.'}
                            {worksheet.mastery_snapshot.last_error_type === 'carry_ones' && 'Your child may be forgetting to carry from the ones column.'}
                            {worksheet.mastery_snapshot.last_error_type === 'borrow_tens' && 'Your child may struggle with borrowing from the tens column.'}
                            {worksheet.mastery_snapshot.last_error_type === 'borrow_ones' && 'Your child may be confusing when borrowing is needed.'}
                            {worksheet.mastery_snapshot.last_error_type === 'place_value_confusion' && 'Your child may be mixing up the value of digits in different places.'}
                            {worksheet.mastery_snapshot.last_error_type === 'multiplication_facts' && 'Your child needs more practice with multiplication tables.'}
                            {worksheet.mastery_snapshot.last_error_type === 'wrong_operation' && 'Your child may be confusing which operation to use.'}
                            {worksheet.mastery_snapshot.last_error_type === 'calculation_error' && 'Your child understands the concept but makes calculation errors.'}
                          </p>
                        </div>
                      )}
                      <div>
                        <p className="text-xs font-semibold text-foreground/60 mb-1">Next Step</p>
                        <p className="text-sm text-foreground/80">
                          {worksheet.mastery_snapshot.mastery_level === 'mastered' && 'Excellent work! Try a harder difficulty level or move to the next topic.'}
                          {worksheet.mastery_snapshot.mastery_level === 'improving' && 'Good progress! Keep practising at this level. Consistency is key.'}
                          {worksheet.mastery_snapshot.mastery_level === 'learning' && 'Keep going! Try reducing to 5 questions and focus on getting them right.'}
                          {worksheet.mastery_snapshot.mastery_level === 'unknown' && 'This is a new topic. Start with easy difficulty and build confidence.'}
                        </p>
                      </div>
                      <div className="mt-3 flex items-center gap-2">
                        <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              worksheet.mastery_snapshot.mastery_level === 'mastered' ? 'bg-green-500 w-full' :
                              worksheet.mastery_snapshot.mastery_level === 'improving' ? 'bg-blue-500 w-2/3' :
                              worksheet.mastery_snapshot.mastery_level === 'learning' ? 'bg-amber-500 w-1/3' :
                              'bg-gray-400 w-[10%]'
                            }`}
                          />
                        </div>
                        <span className="text-xs text-muted-foreground whitespace-nowrap">
                          Streak: {worksheet.mastery_snapshot.avg_streak.toFixed(0)}
                        </span>
                      </div>
                    </div>
                  )}

                  {/* Watermark */}
                  <p className="mt-14 text-center text-[10px] text-foreground/[0.04] select-none print:text-black/[0.05]">
                    Generated using PracticeCraft
                  </p>
                </CardContent>
              </Card>
            ) : (
              <div className="border border-dashed border-border/40 rounded-2xl p-16 flex flex-col items-center justify-center text-center min-h-[400px] bg-secondary/10">
                <div className="w-20 h-20 rounded-2xl bg-secondary/50 flex items-center justify-center mb-6">
                  <svg className="w-10 h-10 text-muted-foreground/50" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                  </svg>
                </div>
                <p className="text-lg font-semibold text-muted-foreground/70 mb-2">Your practice will appear here</p>
                <p className="text-sm text-muted-foreground/50 max-w-xs">Choose a subject and topic, then click Create today's practice.</p>
              </div>
            )}
          </div>
        </div>
      </div>

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

      {/* Mobile Toggle */}
      {worksheet && !loading && (
        <div className="lg:hidden fixed bottom-6 left-1/2 -translate-x-1/2 z-50 print:hidden">
          <button
            onClick={() => setMobileView(mobileView === 'edit' ? 'preview' : 'edit')}
            className="flex items-center gap-2 px-5 py-2.5 bg-foreground text-background rounded-full shadow-lg text-sm font-semibold transition-all hover:opacity-90 active:scale-95"
          >
            {mobileView === 'edit' ? (
              <>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
                Preview
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" />
                </svg>
                Edit
              </>
            )}
          </button>
        </div>
      )}
    </div>
  )
}
