import { useState, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { api } from '@/lib/api'

const GRADES = ['Class 1', 'Class 2', 'Class 3', 'Class 4', 'Class 5']
const SUBJECTS = ['Maths', 'English', 'EVS', 'Science', 'Social Studies']

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
  onSyllabusReady?: (syllabus: ParsedSyllabus) => void
}

export default function SyllabusUpload({ onSyllabusReady }: Props) {
  const [file, setFile] = useState<File | null>(null)
  const [gradeHint, setGradeHint] = useState('')
  const [subjectHint, setSubjectHint] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [syllabus, setSyllabus] = useState<ParsedSyllabus | null>(null)
  const [confidenceScore, setConfidenceScore] = useState<number | null>(null)
  const [dragActive, setDragActive] = useState(false)

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
    <div className="min-h-screen bg-gray-50 py-8 px-4">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold text-center mb-2">Upload Syllabus</h1>
        <p className="text-center text-gray-600 mb-8">
          Upload your child's school syllabus to generate aligned worksheets
        </p>

        {/* Upload Form */}
        <Card className="mb-8">
          <CardHeader>
            <CardTitle>Upload Syllabus Document</CardTitle>
            <CardDescription>
              Supported formats: PDF, Images (JPG, PNG), Text files
            </CardDescription>
          </CardHeader>
          <CardContent>
            {/* Drag and Drop Zone */}
            <div
              className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
                dragActive
                  ? 'border-blue-500 bg-blue-50'
                  : file
                  ? 'border-green-500 bg-green-50'
                  : 'border-gray-300 hover:border-gray-400'
              }`}
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
            >
              {file ? (
                <div>
                  <p className="text-green-700 font-medium">{file.name}</p>
                  <p className="text-sm text-gray-500 mt-1">
                    {(file.size / 1024).toFixed(1)} KB
                  </p>
                  <Button
                    variant="outline"
                    size="sm"
                    className="mt-2"
                    onClick={() => setFile(null)}
                  >
                    Remove
                  </Button>
                </div>
              ) : (
                <div>
                  <p className="text-gray-600 mb-2">
                    Drag and drop your syllabus file here, or
                  </p>
                  <label className="cursor-pointer">
                    <span className="text-blue-600 hover:underline">
                      browse to upload
                    </span>
                    <input
                      type="file"
                      className="hidden"
                      accept=".pdf,.jpg,.jpeg,.png,.txt"
                      onChange={handleFileChange}
                    />
                  </label>
                </div>
              )}
            </div>

            {/* Optional Hints */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6">
              <div className="space-y-2">
                <Label htmlFor="gradeHint">Grade (Optional)</Label>
                <Select value={gradeHint} onValueChange={setGradeHint}>
                  <SelectTrigger id="gradeHint">
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
                <Label htmlFor="subjectHint">Subject (Optional)</Label>
                <Select value={subjectHint} onValueChange={setSubjectHint}>
                  <SelectTrigger id="subjectHint">
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
              <div className="mt-4 p-3 bg-red-50 text-red-700 rounded-md">
                {error}
              </div>
            )}

            <Button
              className="w-full mt-6"
              onClick={handleUpload}
              disabled={!file || loading}
            >
              {loading ? 'Parsing Syllabus...' : 'Parse Syllabus'}
            </Button>
          </CardContent>
        </Card>

        {/* Parsed Syllabus Display */}
        {syllabus && (
          <Card>
            <CardHeader>
              <div className="flex justify-between items-start">
                <div>
                  <CardTitle>{syllabus.name}</CardTitle>
                  <CardDescription className="mt-1">
                    {syllabus.board && `${syllabus.board} • `}
                    {syllabus.grade && `${syllabus.grade} • `}
                    {syllabus.subject}
                  </CardDescription>
                </div>
                {confidenceScore !== null && (
                  <div className={`px-3 py-1 rounded-full text-sm ${
                    confidenceScore >= 0.8 ? 'bg-green-100 text-green-800' :
                    confidenceScore >= 0.6 ? 'bg-yellow-100 text-yellow-800' :
                    'bg-red-100 text-red-800'
                  }`}>
                    {Math.round(confidenceScore * 100)}% confident
                  </div>
                )}
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {syllabus.chapters.map((chapter, chIdx) => (
                  <div key={chIdx} className="border rounded-lg p-4">
                    <h3 className="font-semibold text-lg mb-2">{chapter.name}</h3>
                    <ul className="space-y-2">
                      {chapter.topics.map((topic, tIdx) => (
                        <li key={tIdx} className="ml-4">
                          <span className="text-gray-700">{topic.name}</span>
                          {topic.subtopics && topic.subtopics.length > 0 && (
                            <ul className="ml-4 mt-1 text-sm text-gray-500">
                              {topic.subtopics.map((sub, sIdx) => (
                                <li key={sIdx}>• {sub}</li>
                              ))}
                            </ul>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>

              <div className="mt-6 flex gap-4">
                <Button onClick={handleUseSyllabus} className="flex-1">
                  Use This Syllabus for Worksheets
                </Button>
                <Button variant="outline" onClick={() => setSyllabus(null)}>
                  Upload Different File
                </Button>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
