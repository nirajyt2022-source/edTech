import { useState, useCallback, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
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
    <div className="py-8 px-4">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="text-center mb-8 animate-fade-in">
          <div className="decorative-dots mb-4" />
          <h1 className="text-3xl md:text-4xl mb-3">Syllabus Library</h1>
          <p className="text-muted-foreground text-lg">
            Browse official CBSE curriculum or upload your school's syllabus
          </p>
        </div>

        {/* Mode Toggle */}
        <div className="flex justify-center gap-2 mb-8 animate-fade-in-delayed">
          <div className="inline-flex p-1 bg-muted/50 rounded-xl">
            <button
              onClick={() => setMode('cbse')}
              className={`flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium transition-all ${
                mode === 'cbse'
                  ? 'bg-card text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
              </svg>
              CBSE Syllabus
            </button>
            <button
              onClick={() => setMode('custom')}
              className={`flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium transition-all ${
                mode === 'custom'
                  ? 'bg-card text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
              </svg>
              Upload Custom
              {subscription && !subscription.can_upload_syllabus && (
                <span className="text-xs bg-accent/20 text-accent-foreground px-1.5 py-0.5 rounded">Pro</span>
              )}
            </button>
          </div>
        </div>

        {/* CBSE Mode */}
        {mode === 'cbse' && (
          <>
            <Card className="mb-8 paper-texture animate-fade-in">
              <CardHeader>
                <div className="decorative-line mb-3" />
                <CardTitle>Browse CBSE Syllabus</CardTitle>
                <CardDescription>
                  Select grade and subject to view the official CBSE curriculum
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="cbseGrade" className="text-sm font-medium">Grade</Label>
                    <Select value={cbseGrade} onValueChange={setCbseGrade}>
                      <SelectTrigger id="cbseGrade" className="bg-background/50">
                        <SelectValue placeholder="Select grade" />
                      </SelectTrigger>
                      <SelectContent>
                        {GRADES.map((g) => (
                          <SelectItem key={g} value={g}>{g}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="cbseSubject" className="text-sm font-medium">Subject</Label>
                    <Select value={cbseSubject} onValueChange={setCbseSubject}>
                      <SelectTrigger id="cbseSubject" className="bg-background/50">
                        <SelectValue placeholder="Select subject" />
                      </SelectTrigger>
                      <SelectContent>
                        {SUBJECTS.map((s) => (
                          <SelectItem key={s} value={s}>{s}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                {cbseLoading && (
                  <div className="mt-6 flex items-center justify-center gap-3 text-muted-foreground">
                    <div className="spinner" />
                    Loading syllabus...
                  </div>
                )}
              </CardContent>
            </Card>

            {/* CBSE Syllabus Display */}
            {cbseSyllabus && cbseSyllabus.chapters && (
              <Card className="paper-texture animate-fade-in">
                <CardHeader>
                  <div className="flex justify-between items-start">
                    <div>
                      <div className="decorative-line mb-3" />
                      <CardTitle>CBSE {cbseSyllabus.grade} - {cbseSyllabus.subject}</CardTitle>
                      <CardDescription className="mt-1">
                        Official CBSE curriculum syllabus
                      </CardDescription>
                    </div>
                    <span className="trust-badge">
                      <svg viewBox="0 0 20 20" fill="currentColor">
                        <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                      </svg>
                      Official
                    </span>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4 max-h-96 overflow-y-auto pr-2">
                    {cbseSyllabus.chapters.map((chapter, chIdx) => (
                      <div key={chIdx} className="border border-border/50 rounded-xl p-4 bg-card/50">
                        <h3 className="font-semibold text-lg mb-3 text-foreground flex items-center gap-2">
                          <span className="w-6 h-6 rounded-full bg-primary/10 flex items-center justify-center text-sm text-primary font-medium">
                            {chIdx + 1}
                          </span>
                          {chapter.name}
                        </h3>
                        <ul className="space-y-2">
                          {(chapter.topics || []).map((topic, tIdx) => (
                            <li key={tIdx} className="ml-8">
                              <span className="text-muted-foreground">{topic.name}</span>
                              {topic.subtopics && topic.subtopics.length > 0 && (
                                <ul className="ml-4 mt-1.5 space-y-1">
                                  {topic.subtopics.map((sub, sIdx) => (
                                    <li key={sIdx} className="text-sm text-muted-foreground/70 flex items-center gap-2">
                                      <span className="w-1 h-1 rounded-full bg-border" />
                                      {sub}
                                    </li>
                                  ))}
                                </ul>
                              )}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>

                  <div className="mt-6">
                    <Button onClick={handleUseCBSESyllabus} className="w-full btn-animate py-6 text-base">
                      <svg className="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      Use This Syllabus for Worksheets
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}

            {!cbseSyllabus && cbseGrade && cbseSubject && !cbseLoading && (
              <Card className="paper-texture animate-fade-in">
                <CardContent className="py-16 text-center">
                  <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-secondary/50 flex items-center justify-center">
                    <svg className="w-8 h-8 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9 5.25h.008v.008H12v-.008z" />
                    </svg>
                  </div>
                  <p className="text-foreground font-medium mb-2">
                    Syllabus not available for {cbseGrade} - {cbseSubject}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    Try a different combination or upload a custom syllabus
                  </p>
                </CardContent>
              </Card>
            )}
          </>
        )}

        {/* Custom Upload Mode */}
        {mode === 'custom' && (
          <>
            {/* Upgrade Banner for Free Users */}
            {subscription && !subscription.can_upload_syllabus && (
              <Card className="mb-8 border-accent/30 bg-gradient-to-r from-accent/10 via-accent/5 to-transparent animate-fade-in">
                <CardContent className="py-6">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className="w-10 h-10 rounded-full bg-accent/20 flex items-center justify-center">
                        <svg className="w-5 h-5 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                        </svg>
                      </div>
                      <div>
                        <p className="font-semibold text-foreground">Pro Feature</p>
                        <p className="text-sm text-muted-foreground">
                          Custom syllabus upload is available on the Pro plan
                        </p>
                      </div>
                    </div>
                    <Button onClick={() => upgrade()} className="btn-animate bg-accent hover:bg-accent/90 text-accent-foreground">
                      Upgrade to Pro
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Upload Form - Only show for Pro users */}
            {subscription?.can_upload_syllabus && (
              <Card className="mb-8 paper-texture animate-fade-in">
                <CardHeader>
                  <div className="decorative-line mb-3" />
                  <CardTitle>Upload Custom Syllabus</CardTitle>
                  <CardDescription>
                    Upload your school's specific syllabus document
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {/* Drag and Drop Zone */}
                  <div
                    className={`border-2 border-dashed rounded-xl p-10 text-center transition-all ${
                      dragActive
                        ? 'border-primary bg-primary/5'
                        : file
                        ? 'border-primary/50 bg-primary/5'
                        : 'border-border hover:border-primary/50 hover:bg-secondary/30'
                    }`}
                    onDragEnter={handleDrag}
                    onDragLeave={handleDrag}
                    onDragOver={handleDrag}
                    onDrop={handleDrop}
                  >
                    {file ? (
                      <div className="animate-fade-in">
                        <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-primary/10 flex items-center justify-center">
                          <svg className="w-6 h-6 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                          </svg>
                        </div>
                        <p className="text-foreground font-medium">{file.name}</p>
                        <p className="text-sm text-muted-foreground mt-1">
                          {(file.size / 1024).toFixed(1)} KB
                        </p>
                        <Button
                          variant="outline"
                          size="sm"
                          className="mt-3"
                          onClick={() => setFile(null)}
                        >
                          Remove file
                        </Button>
                      </div>
                    ) : (
                      <div>
                        <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-secondary flex items-center justify-center">
                          <svg className="w-6 h-6 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                          </svg>
                        </div>
                        <p className="text-muted-foreground mb-2">
                          Drag and drop your syllabus file here, or
                        </p>
                        <label className="cursor-pointer">
                          <span className="text-primary hover:text-primary/80 font-medium transition-colors">
                            browse to upload
                          </span>
                          <input
                            type="file"
                            className="hidden"
                            accept=".pdf,.jpg,.jpeg,.png,.txt"
                            onChange={handleFileChange}
                          />
                        </label>
                        <p className="text-xs text-muted-foreground mt-3">
                          Supported: PDF, Images (JPG, PNG), Text files
                        </p>
                      </div>
                    )}
                  </div>

                  {/* Optional Hints */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6">
                    <div className="space-y-2">
                      <Label htmlFor="gradeHint" className="text-sm font-medium">Grade (Optional)</Label>
                      <Select value={gradeHint} onValueChange={setGradeHint}>
                        <SelectTrigger id="gradeHint" className="bg-background/50">
                          <SelectValue placeholder="Help identify grade" />
                        </SelectTrigger>
                        <SelectContent>
                          {GRADES.map((g) => (
                            <SelectItem key={g} value={g}>{g}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="subjectHint" className="text-sm font-medium">Subject (Optional)</Label>
                      <Select value={subjectHint} onValueChange={setSubjectHint}>
                        <SelectTrigger id="subjectHint" className="bg-background/50">
                          <SelectValue placeholder="Help identify subject" />
                        </SelectTrigger>
                        <SelectContent>
                          {SUBJECTS.map((s) => (
                            <SelectItem key={s} value={s}>{s}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  {error && (
                    <div className="mt-4 p-4 bg-destructive/10 border border-destructive/20 text-destructive rounded-lg flex items-center gap-3">
                      <svg className="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                      </svg>
                      {error}
                    </div>
                  )}

                  <Button
                    className="w-full mt-6 btn-animate py-6 text-base"
                    onClick={handleUpload}
                    disabled={!file || loading}
                  >
                    {loading ? (
                      <span className="flex items-center gap-2">
                        <span className="spinner !w-5 !h-5 !border-primary-foreground/30 !border-t-primary-foreground" />
                        Parsing Syllabus...
                      </span>
                    ) : (
                      <span className="flex items-center gap-2">
                        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                        </svg>
                        Parse Syllabus
                      </span>
                    )}
                  </Button>
                </CardContent>
              </Card>
            )}

            {/* Parsed Syllabus Display */}
            {syllabus && (
              <Card className="paper-texture animate-fade-in">
                <CardHeader>
                  <div className="flex justify-between items-start">
                    <div>
                      <div className="decorative-line mb-3" />
                      <CardTitle>{syllabus.name}</CardTitle>
                      <CardDescription className="mt-1">
                        {syllabus.board && `${syllabus.board} • `}
                        {syllabus.grade && `${syllabus.grade} • `}
                        {syllabus.subject}
                      </CardDescription>
                    </div>
                    {confidenceScore !== null && (
                      <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${
                        confidenceScore >= 0.8 ? 'bg-primary/10 text-primary' :
                        confidenceScore >= 0.6 ? 'bg-accent/10 text-accent-foreground' :
                        'bg-destructive/10 text-destructive'
                      }`}>
                        {Math.round(confidenceScore * 100)}% confident
                      </span>
                    )}
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4 max-h-96 overflow-y-auto pr-2">
                    {syllabus.chapters.map((chapter, chIdx) => (
                      <div key={chIdx} className="border border-border/50 rounded-xl p-4 bg-card/50">
                        <h3 className="font-semibold text-lg mb-3 text-foreground flex items-center gap-2">
                          <span className="w-6 h-6 rounded-full bg-primary/10 flex items-center justify-center text-sm text-primary font-medium">
                            {chIdx + 1}
                          </span>
                          {chapter.name}
                        </h3>
                        <ul className="space-y-2">
                          {(chapter.topics || []).map((topic, tIdx) => (
                            <li key={tIdx} className="ml-8">
                              <span className="text-muted-foreground">{topic.name}</span>
                              {topic.subtopics && topic.subtopics.length > 0 && (
                                <ul className="ml-4 mt-1.5 space-y-1">
                                  {topic.subtopics.map((sub, sIdx) => (
                                    <li key={sIdx} className="text-sm text-muted-foreground/70 flex items-center gap-2">
                                      <span className="w-1 h-1 rounded-full bg-border" />
                                      {sub}
                                    </li>
                                  ))}
                                </ul>
                              )}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>

                  <div className="mt-6 flex gap-3">
                    <Button onClick={handleUseSyllabus} className="flex-1 btn-animate py-6 text-base">
                      <svg className="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      Use This Syllabus
                    </Button>
                    <Button variant="outline" onClick={() => setSyllabus(null)} className="py-6">
                      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                      </svg>
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}
          </>
        )}
      </div>
    </div>
  )
}
