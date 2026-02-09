import { useState, useEffect, useCallback } from 'react'
import { api } from '@/lib/api'

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

    const timer = setTimeout(savePreferences, 500)
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
      <div className="p-4 text-sm text-gray-500">
        Loading topic preferences...
      </div>
    )
  }

  if (chapters.length === 0) {
    return null
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <label className="text-sm font-medium text-gray-700">Topics</label>
        <span className="text-xs text-gray-500">
          {selectedTopics.size} of {allTopics.length} selected
        </span>
      </div>

      {/* Select All */}
      <div className="flex items-center gap-2 pb-2 border-b">
        <input
          type="checkbox"
          id="select-all"
          checked={isAllSelected}
          onChange={handleSelectAll}
          className="w-4 h-4 text-blue-600 rounded focus:ring-blue-500"
        />
        <label htmlFor="select-all" className="text-sm font-medium cursor-pointer">
          Select all topics
        </label>
      </div>

      {/* Chapter List */}
      <div className="space-y-2 max-h-64 overflow-y-auto">
        {chapters.map((chapter) => (
          <div key={chapter.name} className="border rounded-lg">
            {/* Chapter Header */}
            <div
              className="flex items-center gap-2 p-2 bg-gray-50 cursor-pointer hover:bg-gray-100"
              onClick={() => toggleChapterExpand(chapter.name)}
            >
              <input
                type="checkbox"
                checked={isChapterFullySelected(chapter)}
                ref={(el) => {
                  if (el) el.indeterminate = isChapterPartiallySelected(chapter)
                }}
                onChange={(e) => {
                  e.stopPropagation()
                  handleChapterToggle(chapter)
                }}
                onClick={(e) => e.stopPropagation()}
                className="w-4 h-4 text-blue-600 rounded focus:ring-blue-500"
              />
              <span className="text-sm font-medium flex-1">{chapter.name}</span>
              <span className="text-xs text-gray-400">
                {expandedChapters.has(chapter.name) ? '▼' : '▶'}
              </span>
            </div>

            {/* Topics */}
            {expandedChapters.has(chapter.name) && (
              <div className="p-2 pl-6 space-y-1 bg-white">
                {chapter.topics.map((topic) => (
                  <div key={topic.name} className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id={`topic-${topic.name}`}
                      checked={selectedTopics.has(topic.name)}
                      onChange={() => handleTopicToggle(topic.name)}
                      className="w-4 h-4 text-blue-600 rounded focus:ring-blue-500"
                    />
                    <label
                      htmlFor={`topic-${topic.name}`}
                      className="text-sm cursor-pointer text-gray-700"
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
        <p className="text-xs text-amber-600">
          Please select at least one topic to generate a worksheet.
        </p>
      )}
    </div>
  )
}
