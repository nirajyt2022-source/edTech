import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'

interface Topic {
  name: string
  subtopics?: string[]
}

interface Chapter {
  name: string
  topics: Topic[]
}

interface Props {
  grade: string
  subject: string
  onGenerateFromSyllabus?: () => void
}

export default function CBSESyllabusViewer({ grade, subject, onGenerateFromSyllabus }: Props) {
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [expandedChapters, setExpandedChapters] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const fetchSyllabus = async () => {
      if (!grade || !subject) {
        setChapters([])
        return
      }

      setLoading(true)
      setError('')
      try {
        const response = await api.get(`/api/cbse-syllabus/${grade}/${subject}`)
        if (response.data && response.data.chapters) {
          setChapters(response.data.chapters)
        }
      } catch (err) {
        setError('Syllabus not available')
        setChapters([])
      } finally {
        setLoading(false)
      }
    }

    fetchSyllabus()
  }, [grade, subject])

  const toggleChapter = (chapterName: string) => {
    const newExpanded = new Set(expandedChapters)
    if (newExpanded.has(chapterName)) {
      newExpanded.delete(chapterName)
    } else {
      newExpanded.add(chapterName)
    }
    setExpandedChapters(newExpanded)
  }

  if (!grade || !subject) {
    return null
  }

  if (loading) {
    return (
      <Card className="border-slate-200 bg-slate-50">
        <CardContent className="py-6">
          <p className="text-sm text-slate-500 text-center">Loading CBSE syllabus...</p>
        </CardContent>
      </Card>
    )
  }

  if (error || chapters.length === 0) {
    return null
  }

  return (
    <Card className="border-slate-200 bg-slate-50/50">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base font-medium text-slate-700">
            CBSE Syllabus - {grade} {subject}
          </CardTitle>
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <span className="inline-flex items-center gap-1">
              <svg className="w-3 h-3 text-green-600" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
              </svg>
              Official CBSE
            </span>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        {/* Trust Badges */}
        <div className="flex flex-wrap gap-2 mb-4 text-xs">
          <span className="inline-flex items-center gap-1 px-2 py-1 bg-green-50 text-green-700 rounded">
            <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
            </svg>
            CBSE-aligned
          </span>
          <span className="inline-flex items-center gap-1 px-2 py-1 bg-blue-50 text-blue-700 rounded">
            <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M4 4a2 2 0 012-2h8a2 2 0 012 2v12a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 0v12h8V4H6z" clipRule="evenodd" />
            </svg>
            Printable worksheets
          </span>
          <span className="inline-flex items-center gap-1 px-2 py-1 bg-purple-50 text-purple-700 rounded">
            <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
              <path d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" />
            </svg>
            Built for parents
          </span>
        </div>

        {/* Chapters List */}
        <div className="space-y-2 max-h-80 overflow-y-auto">
          {chapters.map((chapter) => (
            <div key={chapter.name} className="border border-slate-200 rounded bg-white">
              <button
                className="w-full flex items-center justify-between p-3 text-left hover:bg-slate-50 transition-colors"
                onClick={() => toggleChapter(chapter.name)}
              >
                <span className="text-sm font-medium text-slate-700">{chapter.name}</span>
                <span className="text-slate-400 text-xs">
                  {expandedChapters.has(chapter.name) ? '▼' : '▶'}
                </span>
              </button>

              {expandedChapters.has(chapter.name) && (
                <div className="px-3 pb-3 border-t border-slate-100">
                  <ul className="mt-2 space-y-1">
                    {chapter.topics.map((topic) => (
                      <li key={topic.name} className="flex items-start gap-2 text-sm text-slate-600">
                        <span className="text-green-500 mt-0.5">✔</span>
                        <div>
                          <span>{topic.name}</span>
                          {topic.subtopics && topic.subtopics.length > 0 && (
                            <ul className="mt-1 ml-4 text-xs text-slate-500">
                              {topic.subtopics.map((sub) => (
                                <li key={sub}>• {sub}</li>
                              ))}
                            </ul>
                          )}
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Generate CTA */}
        {onGenerateFromSyllabus && (
          <Button
            onClick={onGenerateFromSyllabus}
            className="w-full mt-4"
            variant="outline"
          >
            Generate worksheet from this syllabus
          </Button>
        )}
      </CardContent>
    </Card>
  )
}
