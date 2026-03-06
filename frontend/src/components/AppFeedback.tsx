import { useState, useCallback } from 'react'
import { PartyPopper } from 'lucide-react'
import { api } from '@/lib/api'
import { useProfile } from '@/lib/profile'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'

const CATEGORIES = [
  'Worksheet Quality',
  'App Usability',
  'Topic Coverage',
  'PDF / Print Quality',
  'Hindi / Language Support',
] as const

const THROTTLE_KEY = 'skolar_last_feedback'
const THROTTLE_MS = 24 * 60 * 60 * 1000 // 24 hours

function isThrottled(): boolean {
  const last = localStorage.getItem(THROTTLE_KEY)
  return !!(last && Date.now() - parseInt(last, 10) < THROTTLE_MS)
}

interface AppFeedbackProps {
  currentPage: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

export default function AppFeedback({ currentPage, open, onOpenChange }: AppFeedbackProps) {
  const [rating, setRating] = useState(0)
  const [hoverRating, setHoverRating] = useState(0)
  const [categories, setCategories] = useState<string[]>([])
  const [comment, setComment] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [loading, setLoading] = useState(false)
  const [showFab, setShowFab] = useState(() => !isThrottled())
  const { activeRole } = useProfile()

  const toggleCategory = (cat: string) => {
    setCategories((prev) =>
      prev.includes(cat) ? prev.filter((c) => c !== cat) : [...prev, cat]
    )
  }

  const resetForm = useCallback(() => {
    setSubmitted(false)
    setRating(0)
    setHoverRating(0)
    setCategories([])
    setComment('')
  }, [])

  const handleOpen = useCallback(() => {
    resetForm()
    onOpenChange(true)
  }, [resetForm, onOpenChange])

  const handleOpenChange = useCallback((nextOpen: boolean) => {
    if (nextOpen) {
      resetForm()
    }
    onOpenChange(nextOpen)
  }, [resetForm, onOpenChange])

  const handleSubmit = async () => {
    if (rating === 0) return
    setLoading(true)
    try {
      await api.post('/api/feedback', {
        rating,
        categories,
        comment: comment.trim() || null,
        page: currentPage,
        role: activeRole || null,
      })
    } catch {
      // Fire-and-forget — still show thanks
      console.error('Feedback submission failed')
    }
    setLoading(false)
    setSubmitted(true)
    localStorage.setItem(THROTTLE_KEY, String(Date.now()))
    setShowFab(false)
    setTimeout(() => {
      onOpenChange(false)
      setTimeout(resetForm, 300)
    }, 2000)
  }

  return (
    <>
      {/* Floating Action Button */}
      {showFab && (
        <button
          onClick={handleOpen}
          className="fixed bottom-[7.5rem] right-4 md:bottom-6 md:right-6 z-40 w-12 h-12 rounded-full shadow-lg flex items-center justify-center transition-all hover:scale-110 active:scale-95 print:hidden"
          style={{ backgroundColor: '#1E1B4B' }}
          aria-label="Send feedback"
        >
          <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
        </button>
      )}

      {/* Feedback Dialog */}
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent className="sm:max-w-md rounded-2xl p-0 overflow-hidden">
          {submitted ? (
            <div className="p-8 text-center space-y-3">
              <PartyPopper className="w-10 h-10 text-amber-500 mx-auto" aria-hidden="true" />
              <h3 className="text-lg font-bold font-fraunces" style={{ color: '#1E293B' }}>
                Thank you!
              </h3>
              <p className="text-sm text-muted-foreground">
                Your feedback helps us improve Skolar for every family.
              </p>
            </div>
          ) : (
            <>
              <DialogHeader className="p-6 pb-0">
                <DialogTitle className="text-lg font-bold font-fraunces">
                  How is your experience?
                </DialogTitle>
                <DialogDescription className="text-sm text-muted-foreground">
                  Help us make Skolar better for you and your child.
                </DialogDescription>
              </DialogHeader>

              <div className="p-6 pt-4 space-y-5">
                {/* Star Rating */}
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
                    Overall Rating
                  </p>
                  <div className="flex items-center gap-1">
                    {[1, 2, 3, 4, 5].map((star) => (
                      <button
                        key={star}
                        onClick={() => setRating(star)}
                        onMouseEnter={() => setHoverRating(star)}
                        onMouseLeave={() => setHoverRating(0)}
                        className="p-0.5 transition-transform hover:scale-110"
                        aria-label={`Rate ${star} star${star > 1 ? 's' : ''}`}
                      >
                        <svg
                          className="w-8 h-8 transition-colors"
                          viewBox="0 0 24 24"
                          fill={(hoverRating || rating) >= star ? '#F59E0B' : 'none'}
                          stroke={(hoverRating || rating) >= star ? '#F59E0B' : '#D1D5DB'}
                          strokeWidth={1.5}
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
                        </svg>
                      </button>
                    ))}
                    {rating > 0 && (
                      <span className="ml-2 text-sm font-medium text-muted-foreground">
                        {['', 'Poor', 'Fair', 'Good', 'Great', 'Excellent'][rating]}
                      </span>
                    )}
                  </div>
                </div>

                {/* Category Chips */}
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
                    What can we improve? <span className="font-normal">(optional)</span>
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {CATEGORIES.map((cat) => {
                      const selected = categories.includes(cat)
                      return (
                        <button
                          key={cat}
                          onClick={() => toggleCategory(cat)}
                          className="px-3 py-1.5 rounded-full text-xs font-medium border transition-all"
                          style={{
                            borderColor: selected ? '#1E1B4B' : '#E2E8F0',
                            backgroundColor: selected ? 'rgba(30,27,75,0.08)' : 'white',
                            color: selected ? '#1E1B4B' : '#64748B',
                          }}
                        >
                          {cat}
                        </button>
                      )
                    })}
                  </div>
                </div>

                {/* Comment */}
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
                    Tell us more <span className="font-normal">(optional)</span>
                  </p>
                  <Textarea
                    value={comment}
                    onChange={(e) => setComment(e.target.value.slice(0, 1000))}
                    placeholder="What do you love? What frustrates you? Any feature requests?"
                    maxLength={1000}
                    rows={3}
                    className="resize-none text-sm"
                  />
                  <p className="text-[10px] text-muted-foreground text-right mt-1">
                    {comment.length}/1000
                  </p>
                </div>

                {/* Submit */}
                <Button
                  onClick={handleSubmit}
                  disabled={rating === 0 || loading}
                  className="w-full rounded-xl"
                  style={{ backgroundColor: rating > 0 ? '#1E1B4B' : undefined }}
                >
                  {loading ? 'Sending...' : 'Submit Feedback'}
                </Button>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}

export { type AppFeedbackProps }
