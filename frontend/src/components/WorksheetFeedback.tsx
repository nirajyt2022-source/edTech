import { useState } from 'react'
import { api } from '@/lib/api'

interface WorksheetFeedbackProps {
  worksheetId: string
  childId?: string
}

const RATINGS = [
  { value: 'too_easy', emoji: '😊', label: 'Too Easy' },
  { value: 'just_right', emoji: '👍', label: 'Just Right' },
  { value: 'too_hard', emoji: '😓', label: 'Too Hard' },
] as const

export default function WorksheetFeedback({ worksheetId, childId }: WorksheetFeedbackProps) {
  const [selected, setSelected] = useState<string | null>(null)
  const [showComment, setShowComment] = useState(false)
  const [comment, setComment] = useState('')
  const [submitted, setSubmitted] = useState(false)

  if (submitted) {
    return (
      <div className="rounded-xl p-4 text-center" style={{ backgroundColor: '#f0fdf4', border: '1px solid #bbf7d0' }}>
        <p className="text-sm font-semibold" style={{ color: '#16a34a' }}>
          Thanks for your feedback!
        </p>
      </div>
    )
  }

  const handleSubmit = async () => {
    if (!selected) return
    setSubmitted(true)
    try {
      await api.post(`/api/v2/worksheets/${encodeURIComponent(worksheetId)}/feedback`, {
        child_id: childId || null,
        difficulty_rating: selected,
        comment: comment.trim() || null,
      })
    } catch {
      // Fire-and-forget: still show thanks even on error
      console.error('Feedback submission failed')
    }
  }

  return (
    <div className="rounded-xl border p-4 space-y-3" style={{ borderColor: '#e2e8f0', backgroundColor: '#fafafa' }}>
      <p className="text-xs font-bold uppercase tracking-widest text-center" style={{ color: '#64748b' }}>
        How was this worksheet?
      </p>

      <div className="flex items-center justify-center gap-3">
        {RATINGS.map((r) => (
          <button
            key={r.value}
            onClick={() => setSelected(r.value)}
            className="flex flex-col items-center gap-1 px-4 py-2.5 rounded-xl border transition-all duration-200"
            style={{
              borderColor: selected === r.value ? '#1E1B4B' : '#e2e8f0',
              backgroundColor: selected === r.value ? 'rgba(30,27,75,0.05)' : 'white',
              transform: selected === r.value ? 'scale(1.05)' : 'scale(1)',
            }}
          >
            <span className="text-xl">{r.emoji}</span>
            <span className="text-[10px] font-semibold" style={{ color: selected === r.value ? '#1E1B4B' : '#94a3b8' }}>
              {r.label}
            </span>
          </button>
        ))}
      </div>

      {selected && !showComment && (
        <button
          onClick={() => setShowComment(true)}
          className="block mx-auto text-xs underline underline-offset-2 transition-colors"
          style={{ color: '#94a3b8' }}
        >
          + Add a comment
        </button>
      )}

      {showComment && (
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value.slice(0, 200))}
          placeholder="Any specific feedback? (optional)"
          maxLength={200}
          rows={2}
          className="w-full rounded-lg border p-2.5 text-sm resize-none focus:outline-none focus:ring-2"
          style={{ borderColor: '#e2e8f0' }}
          autoFocus
        />
      )}

      {selected && (
        <button
          onClick={handleSubmit}
          className="w-full py-2 rounded-xl text-sm font-semibold text-white transition-all hover:translate-y-[-1px]"
          style={{ backgroundColor: '#1E1B4B' }}
        >
          Submit Feedback
        </button>
      )}
    </div>
  )
}
