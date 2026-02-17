import { useState, useEffect, useCallback } from 'react'
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

interface TopicSelection {
  chapter: string
  topics: string[]
}

interface Props {
  chapters: Chapter[]
  childId?: string
  subject?: string
  onSelectionChange: (selectedTopics: string[]) => void
}

export default function TopicSelector({ chapters, childId, subject, onSelectionChange }: Props) {
  const [selectedTopic, setSelectedTopic] = useState<string | null>(null)
  const [expandedChapters, setExpandedChapters] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(false)
  const [preferencesLoaded, setPreferencesLoaded] = useState(false)

  const getAllTopics = useCallback(() => {
    const topics: string[] = []
    chapters.forEach(chapter => {
      chapter.topics.forEach(topic => {
        topics.push(topic.name)
      })
    })
    return topics
  }, [chapters])

  // Load saved preferences when child/subject changes
  useEffect(() => {
    const loadPreferences = async () => {
      if (!childId || !subject) {
        setSelectedTopic(null)
        setPreferencesLoaded(true)
        return
      }

      setLoading(true)
      try {
        const response = await api.get(`/api/topic-preferences/${childId}/${subject}`)
        if (response.data.has_preferences && response.data.selected_topics) {
          // Load the first saved topic as the selection
          const firstSel: TopicSelection = response.data.selected_topics[0]
          const firstTopic = firstSel?.topics?.[0] ?? null
          setSelectedTopic(firstTopic)
        } else {
          setSelectedTopic(null)
        }
      } catch {
        setSelectedTopic(null)
      } finally {
        setLoading(false)
        setPreferencesLoaded(true)
      }
    }

    if (chapters.length > 0) {
      loadPreferences()
    }
  }, [childId, subject, chapters, getAllTopics])

  // Save preferences when selection changes (debounced)
  useEffect(() => {
    if (!preferencesLoaded || !childId || !subject) return

    const savePreferences = async () => {
      const selections: TopicSelection[] = selectedTopic
        ? chapters
            .map(chapter => ({
              chapter: chapter.name,
              topics: chapter.topics.filter(t => t.name === selectedTopic).map(t => t.name),
            }))
            .filter(s => s.topics.length > 0)
        : []

      try {
        await api.post('/api/topic-preferences/', {
          child_id: childId,
          subject: subject,
          selected_topics: selections,
        })
      } catch (err) {
        console.error('Failed to save preferences:', err)
      }
    }

    const timer = setTimeout(savePreferences, 1000)
    return () => clearTimeout(timer)
  }, [selectedTopic, childId, subject, chapters, preferencesLoaded])

  // Notify parent — always an array of 0 or 1 items
  useEffect(() => {
    onSelectionChange(selectedTopic ? [selectedTopic] : [])
  }, [selectedTopic, onSelectionChange])

  const handleTopicSelect = (topicName: string) => {
    // Clicking the already-selected topic clears the selection
    setSelectedTopic(prev => (prev === topicName ? null : topicName))
  }

  const toggleChapterExpand = (chapterName: string) => {
    setExpandedChapters(prev => {
      const next = new Set(prev)
      next.has(chapterName) ? next.delete(chapterName) : next.add(chapterName)
      return next
    })
  }

  const chapterHasSelected = (chapter: Chapter) =>
    chapter.topics.some(t => t.name === selectedTopic)

  if (loading) {
    return (
      <div className="space-y-4 pt-4">
        <Skeleton className="h-6 w-32" />
        <div className="space-y-2">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-12 w-full rounded-xl" />)}
        </div>
      </div>
    )
  }

  if (chapters.length === 0) return null

  return (
    <div className="space-y-4 animate-in fade-in duration-500">
      <div className="flex items-center justify-between px-1">
        <label className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/60">
          Topic
        </label>
        {selectedTopic ? (
          <span className="text-[10px] font-bold text-primary bg-primary/5 px-2 py-0.5 rounded-full border border-primary/10">
            1 selected
          </span>
        ) : (
          <span className="text-[10px] font-bold text-muted-foreground/50 bg-secondary/30 px-2 py-0.5 rounded-full border border-border/30">
            None selected
          </span>
        )}
      </div>

      {/* Chapter List */}
      <div className="space-y-2 max-h-80 overflow-y-auto pr-2 custom-scrollbar">
        {chapters.map((chapter) => (
          <div
            key={chapter.name}
            className={`border rounded-2xl transition-all duration-300 ${
              expandedChapters.has(chapter.name)
                ? 'border-primary/20 bg-card'
                : chapterHasSelected(chapter)
                ? 'border-primary/30 bg-primary/5'
                : 'border-border/40 bg-card/40'
            }`}
          >
            {/* Chapter Header — expand/collapse only */}
            <div
              className={`flex items-center gap-3 p-3 cursor-pointer group rounded-t-2xl ${
                expandedChapters.has(chapter.name) ? 'bg-primary/5' : 'hover:bg-secondary/40'
              }`}
              onClick={() => toggleChapterExpand(chapter.name)}
            >
              {/* Dot indicator when chapter has the selected topic */}
              <div className="w-4.5 h-4.5 flex items-center justify-center shrink-0">
                {chapterHasSelected(chapter) ? (
                  <div className="w-2 h-2 rounded-full bg-primary" />
                ) : (
                  <div className="w-2 h-2 rounded-full border border-border/50 group-hover:border-primary/30 transition-colors" />
                )}
              </div>

              <span
                className={`text-sm font-bold flex-1 font-jakarta truncate transition-colors ${
                  expandedChapters.has(chapter.name) || chapterHasSelected(chapter)
                    ? 'text-primary'
                    : 'text-foreground/80 group-hover:text-primary'
                }`}
              >
                {chapter.name}
              </span>

              <div
                className={`w-6 h-6 rounded-lg flex items-center justify-center transition-all ${
                  expandedChapters.has(chapter.name)
                    ? 'bg-primary/10 text-primary rotate-180'
                    : 'text-muted-foreground/30 hover:bg-secondary/60'
                }`}
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                  <path d="M19.5 8.25l-7.5 7.5-7.5-7.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
            </div>

            {/* Topics — radio button style */}
            {expandedChapters.has(chapter.name) && (
              <div className="p-3 pl-10 space-y-1.5 bg-background/40 animate-in slide-in-from-top-1 duration-200">
                {chapter.topics.map((topic) => {
                  const isSelected = selectedTopic === topic.name
                  return (
                    <div
                      key={topic.name}
                      className="flex items-center gap-3 group/item cursor-pointer"
                      onClick={() => handleTopicSelect(topic.name)}
                    >
                      {/* Radio circle */}
                      <div
                        className={`w-4 h-4 rounded-full border-2 flex items-center justify-center shrink-0 transition-all ${
                          isSelected
                            ? 'border-primary bg-primary'
                            : 'border-border bg-background group-hover/item:border-primary/50'
                        }`}
                      >
                        {isSelected && (
                          <div className="w-1.5 h-1.5 rounded-full bg-primary-foreground" />
                        )}
                      </div>

                      <span
                        className={`text-xs font-medium transition-colors select-none ${
                          isSelected
                            ? 'text-foreground font-bold'
                            : 'text-muted-foreground group-hover/item:text-foreground/80'
                        }`}
                      >
                        {topic.name}
                      </span>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        ))}
      </div>

      {!selectedTopic && (
        <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-xl flex items-center gap-2 animate-in pulse duration-700">
          <svg className="w-4 h-4 text-amber-600 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
          </svg>
          <p className="text-[10px] font-black uppercase tracking-tighter text-amber-700">
            Select a topic to generate a worksheet
          </p>
        </div>
      )}
    </div>
  )
}
