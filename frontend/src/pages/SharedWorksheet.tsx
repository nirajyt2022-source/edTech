import { useState, useEffect } from 'react'
import axios from 'axios'

const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'

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

interface SharedWorksheetData {
  id: string
  title: string
  grade: string
  subject: string
  topic: string
  difficulty: string
  language: string
  questions: Question[]
  learning_objectives?: string[]
}

interface SharedWorksheetProps {
  worksheetId: string
}

export default function SharedWorksheet({ worksheetId }: SharedWorksheetProps) {
  const [worksheet, setWorksheet] = useState<SharedWorksheetData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showAnswers, setShowAnswers] = useState(false)

  useEffect(() => {
    const fetchWorksheet = async () => {
      setLoading(true)
      setError('')
      try {
        const res = await axios.get(`${apiUrl}/api/worksheets/shared/${worksheetId}`)
        setWorksheet(res.data)
      } catch (err: unknown) {
        const axErr = err as { response?: { status?: number } }
        if (axErr.response?.status === 404) {
          setError('This worksheet was not found or may have been removed.')
        } else {
          console.error('Failed to fetch shared worksheet:', err)
          setError('Failed to load worksheet. Please try again later.')
        }
      } finally {
        setLoading(false)
      }
    }

    if (worksheetId) {
      fetchWorksheet()
    }
  }, [worksheetId])

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-stone-50 to-white flex flex-col items-center justify-center gap-6 px-4">
        <div className="relative">
          <div className="w-14 h-14 border-4 border-emerald-200 border-t-emerald-700 rounded-full animate-spin" />
        </div>
        <div className="text-center space-y-2">
          <h2 className="text-xl font-bold text-stone-800" style={{ fontFamily: 'Lora, Georgia, serif' }}>
            Loading worksheet...
          </h2>
          <p className="text-sm text-stone-500">Fetching shared content</p>
        </div>
      </div>
    )
  }

  if (error || !worksheet) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-stone-50 to-white flex flex-col items-center justify-center gap-6 px-4">
        <div className="w-16 h-16 rounded-xl bg-red-50 flex items-center justify-center">
          <svg className="w-8 h-8 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
          </svg>
        </div>
        <div className="text-center space-y-2 max-w-md">
          <h2 className="text-xl font-bold text-stone-800" style={{ fontFamily: 'Lora, Georgia, serif' }}>
            Worksheet not found
          </h2>
          <p className="text-sm text-stone-500">{error || 'This worksheet could not be loaded.'}</p>
        </div>
        <a
          href="/"
          className="mt-4 inline-flex items-center gap-2 px-6 py-2.5 bg-emerald-700 text-white rounded-lg text-sm font-medium hover:bg-emerald-800 transition-colors"
        >
          Generate your own worksheets
        </a>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-stone-50 to-white">
      {/* Header / branding */}
      <header className="bg-white/80 backdrop-blur-sm border-b border-stone-200/60 sticky top-0 z-50">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
          <a href="/" className="flex items-center gap-2.5 group">
            <div className="w-8 h-8 rounded-lg bg-emerald-700 flex items-center justify-center">
              <svg className="w-4.5 h-4.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
              </svg>
            </div>
            <span className="text-lg font-semibold tracking-tight">
              <span className="text-stone-800">Practice</span><span className="text-emerald-700">Craft</span>
            </span>
          </a>
          <a
            href="/"
            className="inline-flex items-center gap-1.5 px-4 py-1.5 bg-emerald-700 text-white rounded-lg text-xs font-semibold hover:bg-emerald-800 transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
            Create yours
          </a>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 sm:px-6 py-8">
        {/* Worksheet card */}
        <div className="bg-white rounded-xl border border-stone-200/60 shadow-sm overflow-hidden">
          {/* Title area */}
          <div className="px-6 sm:px-10 pt-8 pb-6 border-b border-stone-100">
            <h1
              className="text-2xl sm:text-3xl font-bold text-stone-800 mb-3"
              style={{ fontFamily: 'Lora, Georgia, serif' }}
            >
              {worksheet.title}
            </h1>
            <div className="flex flex-wrap gap-2">
              {[worksheet.grade, worksheet.subject, worksheet.topic, worksheet.difficulty].filter(Boolean).map((tag, i) => (
                <span
                  key={i}
                  className="inline-flex items-center px-3 py-1 rounded-md text-[10px] uppercase tracking-wider font-bold bg-stone-100 text-stone-600 border border-stone-200/60"
                >
                  {tag}
                </span>
              ))}
            </div>

            {/* Toggle answers */}
            <button
              onClick={() => setShowAnswers(!showAnswers)}
              className={`mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium border transition-colors ${
                showAnswers
                  ? 'bg-emerald-700 text-white border-emerald-700'
                  : 'bg-white text-stone-600 border-stone-200 hover:bg-stone-50'
              }`}
            >
              {showAnswers ? (
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
              ) : (
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
                </svg>
              )}
              {showAnswers ? 'Hide Answers' : 'Show Answers'}
            </button>
          </div>

          {/* Learning objectives */}
          {worksheet.learning_objectives && worksheet.learning_objectives.length > 0 && (
            <div className="mx-6 sm:mx-10 mt-6 p-5 border border-emerald-200/60 rounded-xl bg-emerald-50/30">
              <p className="font-bold text-emerald-800 text-sm mb-2 tracking-tight">Today's Learning Goal</p>
              <ul className="space-y-1">
                {worksheet.learning_objectives.map((obj, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-stone-700">
                    <span className="text-emerald-600 mt-0.5 text-xs">&#10003;</span>
                    <span>{obj}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Questions */}
          <div className="px-6 sm:px-10 py-8 space-y-6">
            {worksheet.questions.map((q, idx) => (
              <div key={q.id || idx} className="group">
                <div className="flex items-start gap-4">
                  {/* Question number */}
                  <span className="flex-shrink-0 w-8 h-8 rounded-full bg-stone-100 border border-stone-200/60 flex items-center justify-center text-sm font-bold text-stone-600">
                    {idx + 1}
                  </span>

                  <div className="flex-1 min-w-0">
                    {/* Question text */}
                    <p className="text-stone-800 text-sm leading-relaxed whitespace-pre-wrap">
                      {q.text}
                    </p>

                    {/* Options if present */}
                    {q.options && q.options.length > 0 && (
                      <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2">
                        {q.options.map((opt, optIdx) => (
                          <div
                            key={optIdx}
                            className="px-3 py-2 rounded-lg border border-stone-200/60 bg-stone-50/50 text-sm text-stone-700"
                          >
                            <span className="font-medium text-stone-400 mr-2">
                              {String.fromCharCode(65 + optIdx)}.
                            </span>
                            {opt}
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Answer (toggle) */}
                    {showAnswers && (q.correct_answer || q.explanation) && (
                      <div className="mt-3 px-4 py-2.5 rounded-lg bg-emerald-50 border border-emerald-200/60">
                        <span className="text-xs font-bold text-emerald-700 uppercase tracking-wider">Answer: </span>
                        <span className="text-sm text-emerald-900">{q.correct_answer || q.explanation}</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Divider between questions */}
                {idx < worksheet.questions.length - 1 && (
                  <hr className="mt-6 border-stone-100" />
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Branding footer */}
        <div className="mt-12 pt-6 border-t border-stone-200/60 print:hidden">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-lg bg-emerald-700 flex items-center justify-center">
                <svg className="w-3.5 h-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                </svg>
              </div>
              <span className="text-sm font-medium text-stone-700">
                Made with <span className="text-emerald-700 font-semibold">PracticeCraft</span>
              </span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => window.print()}
                className="inline-flex items-center gap-1.5 px-4 py-2 border border-stone-200 rounded-lg text-sm font-medium text-stone-600 hover:bg-stone-50 transition-colors"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6.72 13.829c-.24.03-.48.062-.72.096m.72-.096a42.415 42.415 0 0110.56 0m-10.56 0L6.34 18m10.94-4.171c.24.03.48.062.72.096m-.72-.096L17.66 18m0 0l.229 2.523a1.125 1.125 0 01-1.12 1.227H7.231c-.662 0-1.18-.568-1.12-1.227L6.34 18m11.318 0h1.091A2.25 2.25 0 0021 15.75V9.456c0-1.081-.768-2.015-1.837-2.175a48.055 48.055 0 00-1.913-.247M6.34 18H5.25A2.25 2.25 0 013 15.75V9.456c0-1.081.768-2.015 1.837-2.175a48.041 48.041 0 011.913-.247m10.5 0a48.536 48.536 0 00-10.5 0m10.5 0V3.375c0-.621-.504-1.125-1.125-1.125h-8.25c-.621 0-1.125.504-1.125 1.125v3.659M18.75 7.131H5.25" />
                </svg>
                Print
              </button>
              <a
                href="/"
                className="inline-flex items-center gap-1.5 px-4 py-2 bg-emerald-700 text-white rounded-lg text-sm font-semibold hover:bg-emerald-800 transition-colors"
              >
                Create free &rarr;
              </a>
            </div>
          </div>
        </div>

        {/* CTA section */}
        <div className="mt-8 text-center pb-12 print:hidden">
          <p className="text-sm text-stone-500">
            CBSE-aligned, personalized, and printable. Free to get started.
          </p>
        </div>
      </main>
    </div>
  )
}
