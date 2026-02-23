import { useState, useRef } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'

interface Question {
  id: string
  type: string
  text: string
  options?: string[]
  correct_answer?: string
  format?: string
}

interface WorksheetData {
  title: string
  grade: string
  subject: string
  topic: string
  questions: Question[]
}

interface QuestionResult {
  question_number: number
  question_format: string
  student_answer: string
  correct_answer: string
  is_correct: boolean
  confidence: number
  needs_review: boolean
  feedback: string
}

interface GradingResults {
  results: QuestionResult[]
  score: number
  total: number
  needs_review_questions: number[]
  summary: string
}

interface GradeFromPhotoProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  worksheet: WorksheetData
  childId?: string
}

export default function GradeFromPhoto({ open, onOpenChange, worksheet, childId }: GradeFromPhotoProps) {
  const [images, setImages] = useState<File[]>([])
  const [previews, setPreviews] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState<GradingResults | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [manualOverrides, setManualOverrides] = useState<Record<number, boolean>>({})
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleImageSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    if (files.length === 0) return

    const newImages = [...images, ...files].slice(0, 5)
    setImages(newImages)

    // Generate previews
    const newPreviews: string[] = []
    newImages.forEach((file) => {
      const reader = new FileReader()
      reader.onload = (ev) => {
        newPreviews.push(ev.target?.result as string)
        if (newPreviews.length === newImages.length) {
          setPreviews([...newPreviews])
        }
      }
      reader.readAsDataURL(file)
    })
  }

  const removeImage = (index: number) => {
    setImages((prev) => prev.filter((_, i) => i !== index))
    setPreviews((prev) => prev.filter((_, i) => i !== index))
  }

  const handleGrade = async () => {
    if (images.length === 0) return

    setLoading(true)
    setError(null)

    try {
      const formData = new FormData()
      images.forEach((img) => formData.append('images', img))
      formData.append('worksheet_json', JSON.stringify(worksheet))
      if (childId) formData.append('child_id', childId)

      const response = await api.post('/api/v1/grading/grade-photo', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 30000,
      })

      setResults(response.data)
    } catch (err: unknown) {
      const msg = err && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined
      setError(msg || 'Grading failed. Please try again with a clearer photo.')
    } finally {
      setLoading(false)
    }
  }

  const handleManualOverride = (questionNumber: number, isCorrect: boolean) => {
    setManualOverrides((prev) => ({ ...prev, [questionNumber]: isCorrect }))
  }

  const handleClose = () => {
    setImages([])
    setPreviews([])
    setResults(null)
    setError(null)
    setManualOverrides({})
    onOpenChange(false)
  }

  // Compute adjusted score with manual overrides
  const adjustedScore = results
    ? results.results.reduce((acc, r) => {
        if (manualOverrides[r.question_number] !== undefined) {
          return acc + (manualOverrides[r.question_number] ? 1 : 0)
        }
        return acc + (r.is_correct ? 1 : 0)
      }, 0)
    : 0

  const scorePercent = results ? Math.round((adjustedScore / results.total) * 100) : 0
  const scoreColor = scorePercent >= 80 ? '#16a34a' : scorePercent >= 50 ? '#d97706' : '#dc2626'

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto p-0">
        <DialogHeader className="px-6 pt-6 pb-0">
          <DialogTitle className="text-lg" style={{ fontFamily: "'Fraunces', serif" }}>
            {results ? 'Grading Results' : 'Grade from Photo'}
          </DialogTitle>
        </DialogHeader>

        <div className="px-6 pb-6 space-y-4">
          {/* Worksheet info */}
          <p className="text-sm text-muted-foreground">
            {worksheet.title} — {worksheet.grade} {worksheet.subject}
          </p>

          {!results && !loading && (
            <>
              {/* Upload area */}
              <div
                className="border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors hover:border-primary/40 hover:bg-primary/5"
                style={{ borderColor: '#e2e8f0' }}
                onClick={() => fileInputRef.current?.click()}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  capture="environment"
                  multiple
                  onChange={handleImageSelect}
                  className="hidden"
                />
                <div className="space-y-2">
                  <div className="mx-auto w-12 h-12 rounded-full flex items-center justify-center" style={{ backgroundColor: '#f1f5f9' }}>
                    <svg className="w-6 h-6" style={{ color: '#64748b' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6.827 6.175A2.31 2.31 0 015.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 00-1.134-.175 2.31 2.31 0 01-1.64-1.055l-.822-1.316a2.192 2.192 0 00-1.736-1.039 48.774 48.774 0 00-5.232 0 2.192 2.192 0 00-1.736 1.039l-.821 1.316z" />
                      <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 12.75a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0z" />
                    </svg>
                  </div>
                  <p className="text-sm font-medium" style={{ color: '#334155' }}>
                    Tap to take a photo or choose from gallery
                  </p>
                  <p className="text-xs" style={{ color: '#94a3b8' }}>
                    Upload 1-5 clear photos of the filled worksheet
                  </p>
                </div>
              </div>

              {/* Image previews */}
              {previews.length > 0 && (
                <div className="flex gap-2 flex-wrap">
                  {previews.map((src, i) => (
                    <div key={i} className="relative group">
                      <img
                        src={src}
                        alt={`Page ${i + 1}`}
                        className="w-20 h-20 object-cover rounded-lg border"
                      />
                      <button
                        onClick={(e) => { e.stopPropagation(); removeImage(i) }}
                        className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full flex items-center justify-center text-xs text-white opacity-0 group-hover:opacity-100 transition-opacity"
                        style={{ backgroundColor: '#dc2626' }}
                      >
                        x
                      </button>
                      <span className="absolute bottom-0.5 left-0.5 text-[9px] font-bold px-1 rounded text-white" style={{ backgroundColor: 'rgba(0,0,0,0.5)' }}>
                        {i + 1}
                      </span>
                    </div>
                  ))}
                  {images.length < 5 && (
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      className="w-20 h-20 rounded-lg border-2 border-dashed flex items-center justify-center text-muted-foreground hover:border-primary/40 transition-colors"
                    >
                      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                      </svg>
                    </button>
                  )}
                </div>
              )}

              {/* Tip */}
              <div className="rounded-lg p-3 text-xs" style={{ backgroundColor: '#fef3c7', color: '#92400e' }}>
                <strong>Tip:</strong> Take a clear, well-lit photo. Make sure all answers are visible and the page is flat.
              </div>

              {error && (
                <div className="rounded-lg p-3 text-sm" style={{ backgroundColor: '#fef2f2', color: '#dc2626' }}>
                  {error}
                </div>
              )}

              {/* Grade button */}
              <Button
                onClick={handleGrade}
                disabled={images.length === 0}
                className="w-full h-11 text-sm font-semibold"
                style={{ backgroundColor: '#1E1B4B', color: '#FFFFFF' }}
              >
                Grade my answers
              </Button>
            </>
          )}

          {/* Loading state */}
          {loading && (
            <div className="py-12 text-center space-y-4">
              <div className="relative mx-auto w-16 h-16">
                <div className="w-16 h-16 border-4 rounded-full animate-spin" style={{ borderColor: 'rgba(30,27,75,0.15)', borderTopColor: '#1E1B4B' }} />
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="text-lg">📝</span>
                </div>
              </div>
              <div>
                <p className="text-sm font-semibold" style={{ color: '#334155' }}>Reading your child's answers...</p>
                <p className="text-xs mt-1" style={{ color: '#94a3b8' }}>This usually takes 5-10 seconds</p>
              </div>
            </div>
          )}

          {/* Results */}
          {results && (
            <div className="space-y-5">
              {/* Score hero */}
              <div className="text-center py-4">
                <div className="relative inline-flex items-center justify-center">
                  <svg className="w-28 h-28" viewBox="0 0 100 100">
                    <circle cx="50" cy="50" r="42" fill="none" stroke="#e2e8f0" strokeWidth="8" />
                    <circle
                      cx="50" cy="50" r="42"
                      fill="none"
                      stroke={scoreColor}
                      strokeWidth="8"
                      strokeLinecap="round"
                      strokeDasharray={`${scorePercent * 2.64} 264`}
                      transform="rotate(-90 50 50)"
                      className="transition-all duration-700"
                    />
                  </svg>
                  <div className="absolute inset-0 flex flex-col items-center justify-center">
                    <span className="text-2xl font-bold" style={{ color: scoreColor, fontFamily: "'Fraunces', serif" }}>
                      {adjustedScore}/{results.total}
                    </span>
                    <span className="text-[10px] font-medium" style={{ color: '#94a3b8' }}>correct</span>
                  </div>
                </div>
                {results.summary && (
                  <p className="text-sm mt-3 max-w-xs mx-auto" style={{ color: '#475569' }}>{results.summary}</p>
                )}
              </div>

              {/* Per-question results */}
              <div className="space-y-2">
                {results.results.map((r) => {
                  const overridden = manualOverrides[r.question_number] !== undefined
                  const isCorrect = overridden ? manualOverrides[r.question_number] : r.is_correct
                  const needsReview = r.needs_review && !overridden

                  return (
                    <div
                      key={r.question_number}
                      className="rounded-lg border p-3 space-y-1"
                      style={{
                        borderColor: needsReview ? '#fbbf24' : isCorrect ? '#86efac' : '#fca5a5',
                        backgroundColor: needsReview ? '#fffbeb' : isCorrect ? '#f0fdf4' : '#fef2f2',
                      }}
                    >
                      <div className="flex items-start gap-2">
                        <span className="text-base mt-0.5">
                          {needsReview ? '⚠️' : isCorrect ? '✅' : '❌'}
                        </span>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-semibold" style={{ color: '#334155' }}>
                              Q{r.question_number}
                            </span>
                            <span className="text-sm" style={{ color: '#64748b' }}>
                              {r.student_answer === 'BLANK' ? '(no answer)' : r.student_answer}
                            </span>
                            {!isCorrect && !needsReview && (
                              <span className="text-xs" style={{ color: '#94a3b8' }}>
                                → {r.correct_answer}
                              </span>
                            )}
                          </div>
                          {r.feedback && (
                            <p className="text-xs mt-0.5" style={{ color: '#64748b' }}>{r.feedback}</p>
                          )}

                          {/* Manual review buttons */}
                          {r.needs_review && !overridden && (
                            <div className="flex items-center gap-2 mt-2">
                              <span className="text-xs" style={{ color: '#92400e' }}>Mark as:</span>
                              <button
                                onClick={() => handleManualOverride(r.question_number, true)}
                                className="text-xs px-2 py-0.5 rounded-full border transition-colors hover:bg-green-100"
                                style={{ borderColor: '#86efac', color: '#16a34a' }}
                              >
                                Correct
                              </button>
                              <button
                                onClick={() => handleManualOverride(r.question_number, false)}
                                className="text-xs px-2 py-0.5 rounded-full border transition-colors hover:bg-red-100"
                                style={{ borderColor: '#fca5a5', color: '#dc2626' }}
                              >
                                Wrong
                              </button>
                            </div>
                          )}
                          {overridden && (
                            <span className="text-xs italic" style={{ color: '#94a3b8' }}>
                              (manually marked as {isCorrect ? 'correct' : 'wrong'})
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>

              {/* Actions */}
              <div className="flex gap-2 pt-2">
                <Button
                  onClick={handleClose}
                  variant="outline"
                  className="flex-1 h-10 text-sm"
                >
                  Done
                </Button>
                <Button
                  onClick={() => {
                    setResults(null)
                    setImages([])
                    setPreviews([])
                    setManualOverrides({})
                    setError(null)
                  }}
                  variant="outline"
                  className="flex-1 h-10 text-sm"
                >
                  Try again
                </Button>
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
