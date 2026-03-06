import { useState, useRef, useEffect, useCallback } from 'react'
import { Brain, FileEdit, BookOpen } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { api } from '@/lib/api'
import { useChildren } from '@/lib/children'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  suggestedTopic?: string | null
  suggestedSubject?: string | null
  suggestedGrade?: string | null
}

interface AskSkolarProps {
  onNavigate: (page: string, preFill?: Record<string, unknown>) => void
  childGrade?: string
}

const GRADES = ['', 'Class 1', 'Class 2', 'Class 3', 'Class 4', 'Class 5']
const SUBJECTS = ['', 'Maths', 'English', 'Hindi', 'Science', 'EVS', 'GK', 'Computer']

const EXAMPLE_QUESTIONS = [
  'What is a fraction?',
  'Why do plants need sunlight?',
  'What is a noun?',
]

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function AskSkolar({ onNavigate, childGrade }: AskSkolarProps) {
  const { activeChild } = useChildren()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [grade, setGrade] = useState(childGrade || activeChild?.grade || '')
  const [subject, setSubject] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Pre-fill grade from active child
  useEffect(() => {
    if (activeChild?.grade) setGrade(activeChild.grade)
  }, [activeChild])

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const handleSend = useCallback(async (questionText?: string) => {
    const text = (questionText || input).trim()
    if (!text || loading) return

    const userMsg: ChatMessage = { role: 'user', content: text }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      const response = await api.post('/api/v1/ask/question', {
        question: text,
        grade,
        subject,
        language: 'English',
        history: messages.slice(-10).map(m => ({ role: m.role, content: m.content })),
      }, { timeout: 30000 })

      const assistantMsg: ChatMessage = {
        role: 'assistant',
        content: response.data.answer,
        suggestedTopic: response.data.suggested_topic,
        suggestedSubject: response.data.suggested_subject,
        suggestedGrade: response.data.suggested_grade,
      }
      setMessages(prev => [...prev, assistantMsg])
    } catch {
      const errorMsg: ChatMessage = {
        role: 'assistant',
        content: "I'm sorry, I couldn't process that right now. Please try again!",
      }
      setMessages(prev => [...prev, errorMsg])
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }, [input, loading, grade, subject, messages])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-6 flex flex-col" style={{ height: 'calc(100vh - 8rem)' }}>
      {/* Header */}
      <div className="mb-4 shrink-0">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-xl bg-[#E8F5E9] flex items-center justify-center">
            <Brain className="w-5 h-5 text-[#1B4332]" aria-hidden="true" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-[#1B4332]">Ask Skolar</h1>
            <p className="text-xs text-muted-foreground">Your AI study helper</p>
          </div>
        </div>

        {/* Filters */}
        <div className="flex gap-2">
          <Select value={grade} onValueChange={setGrade}>
            <SelectTrigger className="w-[130px] h-8 text-xs bg-background" aria-label="Select class">
              <SelectValue placeholder="Class (optional)" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value=" ">All classes</SelectItem>
              {GRADES.filter(Boolean).map(g => (
                <SelectItem key={g} value={g}>{g}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={subject} onValueChange={setSubject}>
            <SelectTrigger className="w-[130px] h-8 text-xs bg-background" aria-label="Select subject">
              <SelectValue placeholder="Subject (optional)" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value=" ">All subjects</SelectItem>
              {SUBJECTS.filter(Boolean).map(s => (
                <SelectItem key={s} value={s}>{s}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto min-h-0 space-y-4 pr-1" role="log" aria-live="polite" aria-label="Chat messages">
        {/* Welcome message when empty */}
        {messages.length === 0 && (
          <div className="flex gap-3 items-start">
            <div className="w-8 h-8 rounded-lg bg-[#E8F5E9] flex items-center justify-center shrink-0 mt-0.5">
              <Brain className="w-4 h-4 text-[#1B4332]" aria-hidden="true" />
            </div>
            <div className="bg-[#F9FAFB] border border-border/30 rounded-2xl rounded-tl-sm px-4 py-3 max-w-[85%]">
              <p className="text-sm text-foreground leading-relaxed">
                Hi! I'm Skolar 👋<br />
                Ask me any question from your school books. I'll explain step-by-step!
              </p>
              <p className="text-sm text-muted-foreground mt-3 mb-2">Try asking:</p>
              <div className="flex flex-wrap gap-2">
                {EXAMPLE_QUESTIONS.map((q, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSend(q)}
                    className="text-xs px-3 py-1.5 bg-white border border-[#1B4332]/15 rounded-full text-[#1B4332] hover:bg-[#E8F5E9] transition-colors"
                  >
                    "{q}"
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Chat messages */}
        {messages.map((msg, idx) => (
          <div key={idx}>
            {msg.role === 'user' ? (
              /* User message — right aligned */
              <div className="flex justify-end">
                <div className="bg-[#1B4332] text-white rounded-2xl rounded-tr-sm px-4 py-3 max-w-[85%]">
                  <p className="text-sm leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                </div>
              </div>
            ) : (
              /* AI message — left aligned */
              <div className="flex gap-3 items-start">
                <div className="w-8 h-8 rounded-lg bg-[#E8F5E9] flex items-center justify-center shrink-0 mt-0.5">
                  <Brain className="w-4 h-4 text-[#1B4332]" aria-hidden="true" />
                </div>
                <div className="max-w-[85%]">
                  <div className="bg-[#F9FAFB] border border-border/30 rounded-2xl rounded-tl-sm px-4 py-3">
                    <p className="text-sm text-foreground leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                  </div>

                  {/* Practice / Revise suggestion buttons */}
                  {msg.suggestedTopic && (
                    <div className="flex flex-wrap gap-2 mt-2 ml-1">
                      <button
                        onClick={() => onNavigate('generator', {
                          grade: msg.suggestedGrade || grade,
                          subject: msg.suggestedSubject,
                          topic: msg.suggestedTopic,
                          mode: 'worksheet',
                        })}
                        className="text-xs px-3 py-1.5 bg-[#E8F5E9] border border-[#1B4332]/15 rounded-full text-[#1B4332] hover:bg-[#1B4332] hover:text-white transition-colors flex items-center gap-1.5"
                      >
                        <FileEdit className="w-3.5 h-3.5" aria-hidden="true" /> Practice {msg.suggestedTopic}
                      </button>
                      <button
                        onClick={() => onNavigate('generator', {
                          grade: msg.suggestedGrade || grade,
                          subject: msg.suggestedSubject,
                          topic: msg.suggestedTopic,
                          mode: 'revision',
                        })}
                        className="text-xs px-3 py-1.5 bg-[#FFF8E1] border border-[#D97706]/15 rounded-full text-[#92400E] hover:bg-[#D97706] hover:text-white transition-colors flex items-center gap-1.5"
                      >
                        <BookOpen className="w-3.5 h-3.5" aria-hidden="true" /> Revise {msg.suggestedTopic}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}

        {/* Loading indicator */}
        {loading && (
          <div className="flex gap-3 items-start" role="status" aria-label="Skolar is thinking">
            <div className="w-8 h-8 rounded-lg bg-[#E8F5E9] flex items-center justify-center shrink-0 mt-0.5">
              <Brain className="w-4 h-4 text-[#1B4332]" aria-hidden="true" />
            </div>
            <div className="bg-[#F9FAFB] border border-border/30 rounded-2xl rounded-tl-sm px-4 py-3">
              <div className="flex gap-1.5">
                <span className="w-2 h-2 rounded-full bg-[#1B4332]/40 animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-2 h-2 rounded-full bg-[#1B4332]/40 animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-2 h-2 rounded-full bg-[#1B4332]/40 animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input bar */}
      <div className="mt-3 shrink-0">
        <div className="flex gap-2 items-end">
          <div className="flex-1 relative">
            <textarea
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Type your question..."
              aria-label="Type your question"
              rows={1}
              className="w-full resize-none rounded-xl border border-border/40 bg-background px-4 py-3 pr-12 text-sm focus:outline-none focus:ring-2 focus:ring-[#1B4332]/20 focus:border-[#1B4332]/40 placeholder:text-muted-foreground"
              style={{ maxHeight: '120px' }}
              disabled={loading}
            />
          </div>
          <Button
            onClick={() => handleSend()}
            disabled={!input.trim() || loading}
            className="h-11 px-4 bg-[#1B4332] hover:bg-[#1B4332]/90 text-white rounded-xl shrink-0"
            aria-label="Send message"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
            </svg>
          </Button>
        </div>
        <p className="text-[10px] text-muted-foreground mt-1.5 text-center">
          Skolar helps with CBSE Class 1-5 subjects. Answers may not always be perfect.
        </p>
      </div>
    </div>
  )
}
