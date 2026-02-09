import { useState, useCallback, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { PageHeader } from '@/components/ui/page-header'
import { Section } from '@/components/ui/section'
import { EmptyState } from '@/components/ui/empty-state'
import { Skeleton } from '@/components/ui/skeleton'
import { api } from '@/lib/api'
import { useSubscription } from '@/lib/subscription'

const GRADES = ['Class 1', 'Class 2', 'Class 3', 'Class 4', 'Class 5']
const SUBJECTS = ['Maths', 'English', 'EVS', 'Hindi', 'Science', 'Computer']

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

interface CBSESyllabusData {
  grade: string
  subject: string
  chapters: SyllabusChapter[]
}

interface Props {
  onSyllabusReady?: (syllabus: ParsedSyllabus) => void
}

export default function SyllabusUpload({ onSyllabusReady }: Props) {
  const { status: subscription, upgrade } = useSubscription()
  const [mode, setMode] = useState<'cbse' | 'custom'>('cbse')

  const [cbseGrade, setCbseGrade] = useState('')
  const [cbseSubject, setCbseSubject] = useState('')
  const [cbseSyllabus, setCbseSyllabus] = useState<CBSESyllabusData | null>(null)
  const [cbseLoading, setCbseLoading] = useState(false)

  const [file, setFile] = useState<File | null>(null)
  const [gradeHint, setGradeHint] = useState('')
  const [subjectHint, setSubjectHint] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [syllabus, setSyllabus] = useState<ParsedSyllabus | null>(null)
  const [confidenceScore, setConfidenceScore] = useState<number | null>(null)
  const [dragActive, setDragActive] = useState(false)

  useEffect(() => {
    const loadCBSESyllabus = async () => {
      if (!cbseGrade || !cbseSubject) {
        setCbseSyllabus(null)
        return
      }

      setCbseLoading(true)
      try {
        const encodedGrade = encodeURIComponent(cbseGrade)
        const encodedSubject = encodeURIComponent(cbseSubject)
        const response = await api.get(`/api/cbse-syllabus/${encodedGrade}/${encodedSubject}`)
        setCbseSyllabus(response.data)
      } catch (err) {
        console.error('Failed to load CBSE syllabus:', err)
        setCbseSyllabus(null)
      } finally {
        setCbseLoading(false)
      }
    }

    loadCBSESyllabus()
  }, [cbseGrade, cbseSubject])

  const handleUseCBSESyllabus = () => {
    if (cbseSyllabus && onSyllabusReady) {
      onSyllabusReady({
        id: `cbse-${cbseSyllabus.grade}-${cbseSyllabus.subject}`,
        name: `CBSE ${cbseSyllabus.grade} ${cbseSyllabus.subject}`,
        board: 'CBSE',
        grade: cbseSyllabus.grade,
        subject: cbseSyllabus.subject,
        chapters: cbseSyllabus.chapters,
      })
    }
  }

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true)
    } else if (e.type === 'dragleave') {
      setDragActive(false)
    }
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setFile(e.dataTransfer.files[0])
      setError('')
    }
  }, [])

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0])
      setError('')
    }
  }

  const handleUpload = async () => {
    if (!file) {
      setError('Please select a file')
      return
    }

    setLoading(true)
    setError('')
    setSyllabus(null)

    const formData = new FormData()
    formData.append('file', file)
    if (gradeHint) formData.append('grade_hint', gradeHint)
    if (subjectHint) formData.append('subject_hint', subjectHint)

    try {
      const response = await api.post('/api/syllabus/parse', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setSyllabus(response.data.syllabus)
      setConfidenceScore(response.data.confidence_score)
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to parse syllabus'
      setError(errorMessage)
    } finally {
      setLoading(false)
    }
  }

  const handleUseSyllabus = () => {
    if (syllabus && onSyllabusReady) {
      onSyllabusReady(syllabus)
    }
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-12 pb-24">
      {/* Header */}
      <PageHeader className="mb-8">
        <PageHeader.Title className="text-pretty">Syllabus Library</PageHeader.Title>
        <PageHeader.Subtitle className="text-pretty max-w-2xl">
          Establish the foundation for your content. Choose from official CBSE curriculum maps or upload your specific institutional syllabus.
        </PageHeader.Subtitle>
      </PageHeader>

      {/* Mode Toggle */}
      <div className="flex mb-12 animate-in fade-in slide-in-from-top-2 duration-500">
        <div className="inline-flex p-1.5 bg-secondary/30 border border-border/50 rounded-2xl">
          <button
            onClick={() => setMode('cbse')}
            className={`flex items-center gap-2.5 px-6 py-2.5 rounded-xl text-sm font-bold transition-all ${mode === 'cbse'
                ? 'bg-background text-primary shadow-sm border border-border/40'
                : 'text-muted-foreground/60 hover:text-foreground hover:bg-background/40'
              }`}
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
            </svg>
            CBSE Standards
          </button>
          <button
            onClick={() => setMode('custom')}
            className={`flex items-center gap-2.5 px-6 py-2.5 rounded-xl text-sm font-bold transition-all relative ${mode === 'custom'
                ? 'bg-background text-primary shadow-sm border border-border/40'
                : 'text-muted-foreground/60 hover:text-foreground hover:bg-background/40'
              }`}
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
            </svg>
            Custom Upload
            {subscription && !subscription.can_upload_syllabus && (
              <span className="ml-1 text-[10px] bg-accent/10 text-accent px-1.5 py-0.5 rounded-md font-black uppercase tracking-tighter">Pro</span>
            )}
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-destructive/10 border border-destructive/20 text-destructive rounded-xl flex items-center gap-3 animate-in fade-in slide-in-from-top-2">
          <svg className="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <span className="text-sm font-medium">{error}</span>
        </div>
      )}

      {/* CBSE Mode */}
      {mode === 'cbse' && (
        <div className="space-y-12 animate-in fade-in slide-in-from-bottom-4 duration-700">
          <Section>
            <Section.Header>
              <Section.Title>Standardized Curriculum</Section.Title>
              <p className="text-sm text-muted-foreground mt-1.5">Select a grade and subject to explore the mapping of topics and chapters.</p>
            </Section.Header>
            <Section.Content className="pt-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-2">
                  <Label htmlFor="cbseGrade" className="text-sm font-bold text-foreground/80">Grade Level</Label>
                  <Select value={cbseGrade} onValueChange={setCbseGrade}>
                    <SelectTrigger id="cbseGrade" className="h-11 bg-background border-border/60 focus:ring-primary/20 rounded-xl">
                      <SelectValue placeholder="Select class" />
                    </SelectTrigger>
                    <SelectContent className="rounded-xl shadow-xl border-border/40">
                      {GRADES.map((g) => (
                        <SelectItem key={g} value={g}>{g}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="cbseSubject" className="text-sm font-bold text-foreground/80">Academic Subject</Label>
                  <Select value={cbseSubject} onValueChange={setCbseSubject}>
                    <SelectTrigger id="cbseSubject" className="h-11 bg-background border-border/60 focus:ring-primary/20 rounded-xl">
                      <SelectValue placeholder="Select subject" />
                    </SelectTrigger>
                    <SelectContent className="rounded-xl shadow-xl border-border/40">
                      {SUBJECTS.map((s) => (
                        <SelectItem key={s} value={s}>{s}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </Section.Content>
          </Section>

          {cbseLoading ? (
            <div className="space-y-4 pt-4 border-t border-border/40">
              <Skeleton className="h-8 w-64 mb-6" />
              <div className="grid gap-4">
                <Skeleton className="h-32 w-full rounded-2xl" />
                <Skeleton className="h-32 w-full rounded-2xl" />
              </div>
            </div>
          ) : (
            cbseSyllabus && cbseSyllabus.chapters && (
              <div className="space-y-8 pt-10 border-t border-border/40 animate-in fade-in slide-in-from-bottom-4 duration-500">
                <div className="flex justify-between items-end">
                  <div className="space-y-1">
                    <h3 className="text-2xl font-bold font-jakarta text-foreground">Content Structure</h3>
                    <p className="text-sm text-muted-foreground">CBSE {cbseSyllabus.grade} • {cbseSyllabus.subject}</p>
                  </div>
                  <div className="hidden sm:flex items-center gap-1.5 px-3 py-1 bg-primary/10 text-primary border border-primary/20 rounded-full text-[10px] font-bold uppercase tracking-wider">
                    <svg className="w-3 h-3" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                    </svg>
                    Verified Standard
                  </div>
                </div>

                <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-4 custom-scrollbar">
                  {cbseSyllabus.chapters.map((chapter, chIdx) => (
                    <Card key={chIdx} className="border-border/50 bg-card/40 overflow-hidden rounded-2xl">
                      <CardContent className="p-6">
                        <div className="flex gap-5">
                          <div className="w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center font-bold shrink-0 border border-primary/10">
                            {chIdx + 1}
                          </div>
                          <div className="space-y-4 flex-1">
                            <h4 className="font-bold text-lg text-foreground font-jakarta pt-1.5">{chapter.name}</h4>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-12 gap-y-3">
                              {(chapter.topics || []).map((topic, tIdx) => (
                                <div key={tIdx} className="space-y-1.5">
                                  <div className="flex items-center gap-2 text-sm font-semibold text-foreground/80">
                                    <div className="w-1.5 h-1.5 rounded-full bg-primary/40 shrink-0" />
                                    {topic.name}
                                  </div>
                                  {topic.subtopics && topic.subtopics.length > 0 && (
                                    <div className="ml-3.5 flex flex-wrap gap-1.5">
                                      {topic.subtopics.map((sub, sIdx) => (
                                        <span key={sIdx} className="text-[10px] font-medium text-muted-foreground/60 bg-secondary/30 px-2 py-0.5 rounded-md border border-border/30">
                                          {sub}
                                        </span>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>

                <div className="pt-6 sticky bottom-0 bg-background/80 backdrop-blur-sm pb-10">
                  <Button onClick={handleUseCBSESyllabus} className="w-full bg-primary text-primary-foreground shadow-xl shadow-primary/20 py-7 rounded-2xl font-bold text-base h-auto hover:translate-y-[-2px] transition-all">
                    Initiate Worksheet with this Syllabus
                  </Button>
                </div>
              </div>
            )
          )}

          {!cbseSyllabus && cbseGrade && cbseSubject && !cbseLoading && (
            <div className="pt-12 border-t border-border/40">
              <EmptyState
                icon={
                  <svg className="w-full h-full" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
                  </svg>
                }
                title="Curriculum not found"
                description={`We don't have a verified CBSE mapping for ${cbseGrade} ${cbseSubject} yet.`}
                action={
                  <Button onClick={() => setMode('custom')} variant="outline" className="rounded-xl px-8 font-bold">
                    Upload Custom Syllabus Instead
                  </Button>
                }
              />
            </div>
          )}
        </div>
      )}

      {/* Custom Upload Mode */}
      {mode === 'custom' && (
        <div className="space-y-10 animate-in fade-in slide-in-from-bottom-4 duration-700">
          {/* Upgrade Banner for Free Users */}
          {subscription && !subscription.can_upload_syllabus ? (
            <Card className="border-accent/30 bg-gradient-to-br from-accent/10 via-accent/5 to-transparent shadow-xl shadow-accent/5 rounded-2xl overflow-hidden">
              <CardContent className="p-8">
                <div className="flex flex-col md:flex-row items-center justify-between gap-8">
                  <div className="flex items-center gap-6">
                    <div className="w-16 h-16 rounded-2xl bg-accent/20 flex items-center justify-center shrink-0 border border-accent/20">
                      <svg className="w-8 h-8 text-accent" fill="none" viewBox="0 0 16 16">
                        <path d="M8 0L9.854 5.708H15.854L11 9.242L12.854 14.95L8 11.416L3.146 14.95L5 9.242L0.146 5.708H6.146L8 0Z" fill="currentColor" />
                      </svg>
                    </div>
                    <div className="space-y-1">
                      <h4 className="font-bold text-xl text-foreground font-jakarta">Unlock Institutional Workflows</h4>
                      <p className="text-muted-foreground leading-relaxed">Customize learning by uploading your unique school syllabus or textbooks. Exclusive to Pro members.</p>
                    </div>
                  </div>
                  <Button onClick={() => upgrade()} className="bg-accent text-accent-foreground hover:shadow-lg hover:shadow-accent/20 px-8 py-6 h-auto rounded-xl font-bold text-base w-full md:w-auto transition-all">
                    Upgrade to Pro
                  </Button>
                </div>
              </CardContent>
            </Card>
          ) : (
            <>
              <Section>
                <Section.Header>
                  <Section.Title>Upload Interface</Section.Title>
                  <p className="text-sm text-muted-foreground mt-1.5">Provide a document to let our AI map out the required topics and subtopics.</p>
                </Section.Header>
                <Section.Content className="pt-6">
                  {/* Drag and Drop Zone */}
                  <div
                    className={`border-2 border-dashed rounded-3xl p-12 text-center group transition-all duration-300 ${dragActive
                        ? 'border-primary bg-primary/5 scale-[1.01]'
                        : file
                          ? 'border-primary/40 bg-primary/5 shadow-inner'
                          : 'border-border/60 hover:border-primary/40 hover:bg-secondary/20'
                      }`}
                    onDragEnter={handleDrag}
                    onDragLeave={handleDrag}
                    onDragOver={handleDrag}
                    onDrop={handleDrop}
                  >
                    {file ? (
                      <div className="animate-in zoom-in-95 duration-300">
                        <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-primary/10 flex items-center justify-center border border-primary/10 shadow-sm">
                          <svg className="w-8 h-8 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                          </svg>
                        </div>
                        <h4 className="text-foreground font-bold text-lg font-jakarta">{file.name}</h4>
                        <p className="text-xs font-bold text-muted-foreground/50 uppercase tracking-widest mt-1.5">
                          {(file.size / 1024).toFixed(1)} KB • {file.type.split('/')[1]?.toUpperCase() || 'FILE'}
                        </p>
                        <div className="flex justify-center gap-3 mt-6">
                          <Button
                            variant="outline"
                            size="sm"
                            className="rounded-xl border-border/60 font-bold px-5"
                            onClick={() => setFile(null)}
                          >
                            Replace File
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-4">
                        <div className="w-16 h-16 mx-auto rounded-2xl bg-secondary/50 flex items-center justify-center group-hover:bg-primary/5 group-hover:scale-110 transition-all duration-300 shadow-sm border border-border/20">
                          <svg className="w-8 h-8 text-muted-foreground/60 group-hover:text-primary transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                          </svg>
                        </div>
                        <div>
                          <p className="text-foreground font-bold text-lg font-jakarta">Select or drop document</p>
                          <p className="text-sm text-muted-foreground max-w-xs mx-auto mt-1">AI will automatically identify structure, chapters, and required topics.</p>
                        </div>
                        <label className="inline-block pt-2">
                          <span className="bg-primary/10 text-primary border border-primary/20 hover:bg-primary hover:text-primary-foreground px-6 py-2.5 rounded-xl text-sm font-bold cursor-pointer transition-all inline-block shadow-sm">
                            Browse Files
                          </span>
                          <input
                            type="file"
                            className="hidden"
                            accept=".pdf,.jpg,.jpeg,.png,.txt"
                            onChange={handleFileChange}
                          />
                        </label>
                        <p className="text-[10px] font-bold text-muted-foreground/40 uppercase tracking-widest pt-2">
                          PDF, JPG, PNG or TXT
                        </p>
                      </div>
                    )}
                  </div>

                  {/* Optional Hints */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-10">
                    <div className="space-y-2">
                      <Label htmlFor="gradeHint" className="text-sm font-bold text-foreground/80">Contextual Grade (Optional)</Label>
                      <Select value={gradeHint} onValueChange={setGradeHint}>
                        <SelectTrigger id="gradeHint" className="h-11 bg-background border-border/60 rounded-xl">
                          <SelectValue placeholder="Assists AI parsing" />
                        </SelectTrigger>
                        <SelectContent className="rounded-xl">
                          {GRADES.map((g) => (
                            <SelectItem key={g} value={g}>{g}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="subjectHint" className="text-sm font-bold text-foreground/80">Expected Subject (Optional)</Label>
                      <Select value={subjectHint} onValueChange={setSubjectHint}>
                        <SelectTrigger id="subjectHint" className="h-11 bg-background border-border/60 rounded-xl">
                          <SelectValue placeholder="Assists AI parsing" />
                        </SelectTrigger>
                        <SelectContent className="rounded-xl">
                          {SUBJECTS.map((s) => (
                            <SelectItem key={s} value={s}>{s}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <Button
                    className="w-full mt-10 bg-primary text-primary-foreground shadow-xl shadow-primary/20 py-7 rounded-2xl font-bold text-base h-auto hover:translate-y-[-2px] transition-all"
                    onClick={handleUpload}
                    disabled={!file || loading}
                  >
                    {loading ? (
                      <>
                        <span className="spinner !w-5 !h-5 !border-primary-foreground/30 !border-t-primary-foreground mr-3" />
                        Deep Parsing in Progress...
                      </>
                    ) : (
                      <>
                        <svg className="w-5 h-5 mr-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                        </svg>
                        Execute Syllabus Mapping
                      </>
                    )}
                  </Button>
                </Section.Content>
              </Section>

              {/* Parsed Syllabus Display */}
              {loading && !syllabus && (
                <div className="space-y-4 pt-10 border-t border-border/40">
                  <Skeleton className="h-8 w-64 mb-6" />
                  <div className="grid gap-4">
                    <Skeleton className="h-32 w-full rounded-2xl" />
                    <Skeleton className="h-32 w-full rounded-2xl" />
                  </div>
                </div>
              )}

              {syllabus && (
                <div className="space-y-8 pt-10 border-t border-border/40 animate-in fade-in slide-in-from-bottom-6 duration-700">
                  <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-6">
                    <div className="space-y-1">
                      <h3 className="text-3xl font-bold font-jakarta text-foreground">{syllabus.name}</h3>
                      <p className="text-sm text-muted-foreground flex items-center gap-2">
                        {syllabus.board && <><span className="font-bold text-foreground/70">{syllabus.board}</span><span className="w-1 h-1 rounded-full bg-border" /></>}
                        {syllabus.grade && <><span className="font-bold text-foreground/70">{syllabus.grade}</span><span className="w-1 h-1 rounded-full bg-border" /></>}
                        <span className="font-bold text-foreground/70">{syllabus.subject}</span>
                      </p>
                    </div>
                    {confidenceScore !== null && (
                      <div className="flex flex-col items-end gap-2">
                        <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">AI Confidence</span>
                        <span className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-black border tracking-tight ${confidenceScore >= 0.8 ? 'bg-primary/10 text-primary border-primary/20' :
                            confidenceScore >= 0.6 ? 'bg-amber-500/10 text-amber-600 border-amber-500/20' :
                              'bg-destructive/10 text-destructive border-destructive/20'
                          }`}>
                          {Math.round(confidenceScore * 100)}% Match
                        </span>
                      </div>
                    )}
                  </div>

                  <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-4 custom-scrollbar">
                    {syllabus.chapters.map((chapter, chIdx) => (
                      <Card key={chIdx} className="border-border/50 bg-card/40 rounded-2xl shadow-sm">
                        <CardContent className="p-6">
                          <div className="flex gap-5">
                            <div className="w-10 h-10 rounded-xl bg-secondary/60 text-foreground/70 flex items-center justify-center font-bold shrink-0 border border-border/50">
                              {chIdx + 1}
                            </div>
                            <div className="space-y-4 flex-1">
                              <h4 className="font-bold text-lg text-foreground font-jakarta pt-1.5">{chapter.name}</h4>
                              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-12 gap-y-4">
                                {(chapter.topics || []).map((topic, tIdx) => (
                                  <div key={tIdx} className="space-y-2">
                                    <div className="flex items-center gap-2.5 text-sm font-bold text-foreground/80">
                                      <div className="w-2 h-2 rounded-full bg-primary/30 shrink-0" />
                                      {topic.name}
                                    </div>
                                    {topic.subtopics && topic.subtopics.length > 0 && (
                                      <div className="ml-4.5 flex flex-wrap gap-1.5">
                                        {topic.subtopics.map((sub, sIdx) => (
                                          <span key={sIdx} className="text-[10px] font-bold text-muted-foreground/60 bg-background/50 px-2 py-1 rounded-md border border-border/30">
                                            {sub}
                                          </span>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                ))}
                              </div>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>

                  <div className="pt-6 sticky bottom-0 bg-background/80 backdrop-blur-sm pb-10 flex flex-col md:flex-row gap-4">
                    <Button onClick={handleUseSyllabus} className="flex-1 bg-primary text-primary-foreground shadow-xl shadow-primary/20 py-7 rounded-2xl font-bold text-base h-auto hover:translate-y-[-2px] transition-all">
                      Confirm & Use Mapping
                    </Button>
                    <Button variant="outline" onClick={() => setSyllabus(null)} className="md:w-20 py-7 rounded-2xl font-bold h-auto border-border/60 hover:bg-secondary/50">
                      <svg className="w-5 h-5 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
