import { useState, useEffect } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { Skeleton } from '@/components/ui/skeleton'

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
      } catch {
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
      <div className="space-y-4 pt-4">
        <Skeleton className="h-6 w-48" />
        <div className="grid gap-3">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-16 w-full rounded-2xl" />)}
        </div>
      </div>
    )
  }

  if (error || chapters.length === 0) {
    return null
  }

  return (
    <div className="space-y-6 animate-in fade-in duration-700">
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 border-b border-border/40 pb-5">
        <div className="space-y-1 text-center sm:text-left">
          <h3 className="text-xl font-bold font-fraunces text-foreground">
            {grade} {subject} Syllabus
          </h3>
          <p className="text-[10px] font-black uppercase tracking-widest text-primary bg-primary/5 px-2.5 py-1 rounded-full border border-primary/10 inline-block">
            Official CBSE Alignment &middot; 2025-26 Standard
          </p>
        </div>

        {onGenerateFromSyllabus && (
          <Button
            onClick={onGenerateFromSyllabus}
            className="bg-primary hover:shadow-lg hover:shadow-primary/20 rounded-xl px-6 py-5 h-auto font-black text-xs uppercase tracking-widest transition-all"
          >
            Draft Material from Scope
          </Button>
        )}
      </div>

      <div className="grid grid-cols-1 gap-3 max-h-[500px] overflow-y-auto pr-2 custom-scrollbar">
        {chapters.map((chapter, index) => (
          <Card
            key={chapter.name}
            className={`group transition-all duration-300 border shadow-sm rounded-2xl overflow-hidden ${expandedChapters.has(chapter.name) ? 'border-primary/20 ring-1 ring-primary/5' : 'border-border/40 bg-card/40 hover:bg-card hover:border-border'
              }`}
            style={{ animationDelay: `${index * 0.05}s` }}
          >
            <button
              className={`w-full flex items-center justify-between p-5 text-left transition-colors relative ${expandedChapters.has(chapter.name) ? 'bg-primary/5' : ''
                }`}
              onClick={() => toggleChapter(chapter.name)}
            >
              <div className="flex items-center gap-4">
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center transition-all ${expandedChapters.has(chapter.name) ? 'bg-primary text-primary-foreground scale-105' : 'bg-secondary/50 text-muted-foreground group-hover:bg-secondary group-hover:text-foreground'
                  }`}>
                  <span className="text-xs font-black">{index + 1}</span>
                </div>
                <div>
                  <span className={`text-sm font-bold font-jakarta transition-colors ${expandedChapters.has(chapter.name) ? 'text-primary' : 'text-foreground/80'
                    }`}>{chapter.name}</span>
                  <p className="text-[10px] text-muted-foreground/50 font-medium">{chapter.topics.length} Topic Segments</p>
                </div>
              </div>

              <div className={`w-8 h-8 rounded-xl flex items-center justify-center transition-all ${expandedChapters.has(chapter.name) ? 'bg-primary/10 text-primary rotate-180' : 'text-muted-foreground/30 hover:bg-secondary/60'
                }`}>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                  <path d="M19.5 8.25l-7.5 7.5-7.5-7.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
            </button>

            {expandedChapters.has(chapter.name) && (
              <CardContent className="p-5 pt-0 bg-background/40 animate-in slide-in-from-top-2 duration-300">
                <div className="h-px w-full bg-border/40 mb-5" />
                <ul className="space-y-4">
                  {chapter.topics.map((topic) => (
                    <li key={topic.name} className="flex items-start gap-4 group/topic">
                      <div className="w-5 h-5 rounded-full bg-emerald-500/10 flex items-center justify-center mt-0.5 border border-emerald-500/20 shrink-0">
                        <svg className="w-3 h-3 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={4}>
                          <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      </div>
                      <div className="space-y-2">
                        <span className="text-xs font-bold text-foreground/80 group-hover/topic:text-primary transition-colors">{topic.name}</span>
                        {topic.subtopics && topic.subtopics.length > 0 && (
                          <div className="flex flex-wrap gap-1.5 pl-0.5">
                            {topic.subtopics.map((sub) => (
                              <span key={sub} className="px-2 py-0.5 bg-secondary/40 rounded-lg text-[9px] font-bold text-muted-foreground/70 border border-border/20">
                                {sub}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              </CardContent>
            )}
          </Card>
        ))}
      </div>

      <div className="p-6 bg-primary/5 rounded-3xl border border-primary/10 flex flex-col md:flex-row items-center gap-6">
        <div className="w-16 h-16 rounded-2xl bg-white shadow-xl shadow-primary/5 flex items-center justify-center shrink-0">
          <svg className="w-8 h-8 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z" />
          </svg>
        </div>
        <div className="text-center md:text-left space-y-1 flex-1">
          <h4 className="text-sm font-black uppercase tracking-widest text-primary">Pedagogical Guardrails</h4>
          <p className="text-xs font-medium text-muted-foreground/80 leading-relaxed">
            This module is pinned to the current CBSE framework. All generated practice materials will map strictly to these standardized learning outcomes.
          </p>
        </div>
        <div className="flex items-center gap-2 px-4 py-2 bg-white rounded-xl shadow-sm border border-border/40 shrink-0">
          <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-[10px] font-black uppercase tracking-widest">Compliant</span>
        </div>
      </div>
    </div>
  )
}
