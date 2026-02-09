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
  const [selectedTopics, setSelectedTopics] = useState<Set<string>>(new Set())
  const [expandedChapters, setExpandedChapters] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(false)
  const [preferencesLoaded, setPreferencesLoaded] = useState(false)

  // Get all topic names from chapters
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
        // No child selected, select all by default
        setSelectedTopics(new Set(getAllTopics()))
        setPreferencesLoaded(true)
        return
      }

      setLoading(true)
      try {
        const response = await api.get(`/api/topic-preferences/${childId}/${subject}`)
        if (response.data.has_preferences && response.data.selected_topics) {
          // Load saved preferences
          const savedTopics = new Set<string>()
          response.data.selected_topics.forEach((sel: TopicSelection) => {
            sel.topics.forEach(t => savedTopics.add(t))
          })
          setSelectedTopics(savedTopics)
        } else {
          // No preferences saved, select all
          setSelectedTopics(new Set(getAllTopics()))
        }
      } catch {
        // On error, select all
        setSelectedTopics(new Set(getAllTopics()))
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
      const selections: TopicSelection[] = chapters.map(chapter => ({
        chapter: chapter.name,
        topics: chapter.topics
          .filter(t => selectedTopics.has(t.name))
          .map(t => t.name)
      })).filter(s => s.topics.length > 0)

      try {
        await api.post('/api/topic-preferences/', {
          child_id: childId,
          subject: subject,
          selected_topics: selections
        })
      } catch (err) {
        console.error('Failed to save preferences:', err)
      }
    }

    const timer = setTimeout(savePreferences, 1000)
    return () => clearTimeout(timer)
  }, [selectedTopics, childId, subject, chapters, preferencesLoaded])

  // Notify parent of selection changes
  useEffect(() => {
    onSelectionChange(Array.from(selectedTopics))
  }, [selectedTopics, onSelectionChange])

  const allTopics = getAllTopics()
  const isAllSelected = selectedTopics.size === allTopics.length
  const isNoneSelected = selectedTopics.size === 0

  const handleSelectAll = () => {
    if (isAllSelected) {
      setSelectedTopics(new Set())
    } else {
      setSelectedTopics(new Set(allTopics))
    }
  }

  const getChapterTopics = (chapter: Chapter) => {
    return chapter.topics.map(t => t.name)
  }

  const isChapterFullySelected = (chapter: Chapter) => {
    return getChapterTopics(chapter).every(t => selectedTopics.has(t))
  }

  const isChapterPartiallySelected = (chapter: Chapter) => {
    const topics = getChapterTopics(chapter)
    const selectedCount = topics.filter(t => selectedTopics.has(t)).length
    return selectedCount > 0 && selectedCount < topics.length
  }

  const handleChapterToggle = (chapter: Chapter) => {
    const chapterTopics = getChapterTopics(chapter)
    const newSelected = new Set(selectedTopics)

    if (isChapterFullySelected(chapter)) {
      // Deselect all topics in chapter
      chapterTopics.forEach(t => newSelected.delete(t))
    } else {
      // Select all topics in chapter
      chapterTopics.forEach(t => newSelected.add(t))
    }

    setSelectedTopics(newSelected)
  }

  const handleTopicToggle = (topicName: string) => {
    const newSelected = new Set(selectedTopics)
    if (newSelected.has(topicName)) {
      newSelected.delete(topicName)
    } else {
      newSelected.add(topicName)
    }
    setSelectedTopics(newSelected)
  }

  const toggleChapterExpand = (chapterName: string) => {
    const newExpanded = new Set(expandedChapters)
    if (newExpanded.has(chapterName)) {
      newExpanded.delete(chapterName)
    } else {
      newExpanded.add(chapterName)
    }
    setExpandedChapters(newExpanded)
  }

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

  if (chapters.length === 0) {
    return null
  }

  return (
    <div className="space-y-4 animate-in fade-in duration-500">
      <div className="flex items-center justify-between px-1">
        <label className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/60">Module Scope</label>
        <span className="text-[10px] font-bold text-primary bg-primary/5 px-2 py-0.5 rounded-full border border-primary/10 transition-all">
          {selectedTopics.size} of {allTopics.length} included
        </span>
      </div>

      {/* Select All Toggle */}
      <div className="flex items-center gap-3 p-3 bg-secondary/20 border border-border/40 rounded-xl group hover:border-primary/20 transition-all duration-300">
        <div className="relative flex items-center">
          <input
            type="checkbox"
            id="select-all"
            checked={isAllSelected}
            onChange={handleSelectAll}
            className="peer w-5 h-5 opacity-0 absolute cursor-pointer z-10"
          />
          <div className={`w-5 h-5 rounded-md border-2 flex items-center justify-center transition-all ${isAllSelected ? 'bg-primary border-primary' : 'bg-background border-border group-hover:border-primary/40'
            }`}>
            {isAllSelected && (
              <svg className="w-3.5 h-3.5 text-primary-foreground" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={4}>
                <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            )}
          </div>
        </div>
        <label htmlFor="select-all" className="text-xs font-bold text-foreground/80 cursor-pointer select-none">
          {isAllSelected ? 'Deselect All Broadly' : 'Include All Available Topics'}
        </label>
      </div>

      {/* Chapter List */}
      <div className="space-y-2 max-h-80 overflow-y-auto pr-2 custom-scrollbar">
        {chapters.map((chapter) => (
          <div key={chapter.name} className={`border rounded-2xl transition-all duration-300 ${expandedChapters.has(chapter.name) ? 'border-primary/20 bg-card' : 'border-border/40 bg-card/40'
            }`}>
            {/* Chapter Header */}
            <div
              className={`flex items-center gap-3 p-3 cursor-pointer group rounded-t-2xl ${expandedChapters.has(chapter.name) ? 'bg-primary/5' : 'hover:bg-secondary/40'
                }`}
              onClick={() => toggleChapterExpand(chapter.name)}
            >
              <div className="relative flex items-center" onClick={(e) => e.stopPropagation()}>
                <input
                  type="checkbox"
                  checked={isChapterFullySelected(chapter)}
                  ref={(el) => {
                    if (el) el.indeterminate = isChapterPartiallySelected(chapter)
                  }}
                  onChange={() => handleChapterToggle(chapter)}
                  className="peer w-4.5 h-4.5 opacity-0 absolute cursor-pointer z-10"
                />
                <div className={`w-4.5 h-4.5 rounded-md border-2 flex items-center justify-center transition-all ${isChapterFullySelected(chapter) ? 'bg-primary border-primary' :
                  isChapterPartiallySelected(chapter) ? 'bg-primary/70 border-primary/70' :
                    'bg-background border-border group-hover:border-primary/40'
                  }`}>
                  {isChapterFullySelected(chapter) && (
                    <svg className="w-3 h-3 text-primary-foreground" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={4}>
                      <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                  {!isChapterFullySelected(chapter) && isChapterPartiallySelected(chapter) && (
                    <div className="w-2.5 h-0.5 bg-primary-foreground rounded-full" />
                  )}
                </div>
              </div>

              <span className={`text-sm font-bold flex-1 font-jakarta truncate group-hover:text-primary transition-colors ${expandedChapters.has(chapter.name) ? 'text-primary' : 'text-foreground/80'
                }`}>
                {chapter.name}
              </span>

              <div className={`w-6 h-6 rounded-lg flex items-center justify-center transition-all ${expandedChapters.has(chapter.name) ? 'bg-primary/10 text-primary rotate-180' : 'text-muted-foreground/30 hover:bg-secondary/60'
                }`}>
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                  <path d="M19.5 8.25l-7.5 7.5-7.5-7.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
            </div>

            {/* Topics */}
            {expandedChapters.has(chapter.name) && (
              <div className="p-3 pl-10 space-y-2 bg-background/40 animate-in slide-in-from-top-1 duration-200">
                {chapter.topics.map((topic) => (
                  <div key={topic.name} className="flex items-center gap-3 group/item">
                    <div className="relative flex items-center">
                      <input
                        type="checkbox"
                        id={`topic-${topic.name}`}
                        checked={selectedTopics.has(topic.name)}
                        onChange={() => handleTopicToggle(topic.name)}
                        className="peer w-4 h-4 opacity-0 absolute cursor-pointer z-10"
                      />
                      <div className={`w-4 h-4 rounded-md border-2 flex items-center justify-center transition-all ${selectedTopics.has(topic.name) ? 'bg-primary border-primary' : 'bg-background border-border group-hover/item:border-primary/40'
                        }`}>
                        {selectedTopics.has(topic.name) && (
                          <svg className="w-2.5 h-2.5 text-primary-foreground" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={5}>
                            <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                        )}
                      </div>
                    </div>
                    <label
                      htmlFor={`topic-${topic.name}`}
                      className={`text-xs font-medium cursor-pointer transition-colors ${selectedTopics.has(topic.name) ? 'text-foreground font-bold' : 'text-muted-foreground group-hover/item:text-foreground/80'
                        }`}
                    >
                      {topic.name}
                    </label>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {isNoneSelected && (
        <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-xl flex items-center gap-2 animate-in pulse duration-700">
          <svg className="w-4 h-4 text-amber-600 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
          </svg>
          <p className="text-[10px] font-black uppercase tracking-tighter text-amber-700">
            Resource Mapping Required &middot; Selection empty
          </p>
        </div>
      )}
    </div>
  )
}
