import { useState, useEffect, useCallback } from "react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface FlashcardItem {
  front: string
  back: string
  category?: string
}

export interface FlashcardSetData {
  title: string
  grade: string
  subject: string
  topic: string
  cards: FlashcardItem[]
}

interface FlashcardPreviewProps {
  cards: FlashcardItem[]
  title: string
  onDownloadPdf: () => void
  downloadingPdf: boolean
}

// ---------------------------------------------------------------------------
// Category emoji
// ---------------------------------------------------------------------------

const CATEGORY_EMOJI: Record<string, string> = {
  concept: "\u2728",
  fact: "\u2139\uFE0F",
  formula: "\uD83D\uDCD0",
  question: "\u2753",
}

function getCategoryEmoji(cat?: string) {
  return CATEGORY_EMOJI[cat || "concept"] || "\u2728"
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function FlashcardPreview({ cards, title, onDownloadPdf, downloadingPdf }: FlashcardPreviewProps) {
  const [currentIndex, setCurrentIndex] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const [gridView, setGridView] = useState(false)

  // Reset state when cards change
  useEffect(() => {
    setCurrentIndex(0)
    setFlipped(false)
    setGridView(false)
  }, [cards])

  // Keyboard navigation
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (gridView) return
    if (e.key === "ArrowLeft") {
      setFlipped(false)
      setCurrentIndex(prev => Math.max(0, prev - 1))
    } else if (e.key === "ArrowRight") {
      setFlipped(false)
      setCurrentIndex(prev => Math.min(cards.length - 1, prev + 1))
    } else if (e.key === " ") {
      e.preventDefault()
      setFlipped(prev => !prev)
    }
  }, [cards.length, gridView])

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [handleKeyDown])

  const current = cards[currentIndex]
  if (!current) return null

  // ── Grid View ──────────────────────────────────────────────────────────
  if (gridView) {
    return (
      <Card className="overflow-hidden border-border/20 shadow-xl bg-white p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-lg font-bold text-[#1B4332]">{title}</h2>
            <p className="text-xs text-muted-foreground">{cards.length} cards &middot; Click any card to expand</p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => setGridView(false)}>
              Single View
            </Button>
            <Button
              size="sm"
              onClick={onDownloadPdf}
              disabled={downloadingPdf}
              className="bg-[#1B4332] hover:bg-[#1B4332]/90 text-white"
            >
              {downloadingPdf ? (
                <span className="flex items-center gap-2">
                  <span className="spinner !w-4 !h-4 !border-white/30 !border-t-white" />
                  Preparing...
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  Download PDF
                </span>
              )}
            </Button>
          </div>
        </div>

        {/* 3×4 Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {cards.map((card, idx) => (
            <button
              key={idx}
              onClick={() => { setCurrentIndex(idx); setFlipped(false); setGridView(false) }}
              className="text-left p-3 rounded-xl border border-dashed border-[#1B4332]/20 bg-[#E8F5E9]/50 hover:bg-[#E8F5E9] transition-colors min-h-[80px] relative group"
            >
              <span className="absolute top-1.5 left-2 text-[10px] opacity-60">
                {getCategoryEmoji(card.category)}
              </span>
              <span className="absolute top-1.5 right-2 text-[10px] text-muted-foreground opacity-60">
                {idx + 1}
              </span>
              <p className="text-xs font-medium text-[#1B4332] mt-3 line-clamp-3">
                {card.front}
              </p>
              <span className="absolute bottom-1.5 right-2 text-[10px] text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity">
                Click to expand
              </span>
            </button>
          ))}
        </div>
      </Card>
    )
  }

  // ── Single Card View ───────────────────────────────────────────────────
  return (
    <Card className="overflow-hidden border-border/20 shadow-xl bg-white p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-bold text-[#1B4332]">{title}</h2>
          <p className="text-xs text-muted-foreground">Tap card to flip &middot; Use arrow keys to navigate</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setGridView(true)}>
            Show All
          </Button>
          <Button
            size="sm"
            onClick={onDownloadPdf}
            disabled={downloadingPdf}
            className="bg-[#1B4332] hover:bg-[#1B4332]/90 text-white"
          >
            {downloadingPdf ? (
              <span className="flex items-center gap-2">
                <span className="spinner !w-4 !h-4 !border-white/30 !border-t-white" />
                Preparing...
              </span>
            ) : (
              <span className="flex items-center gap-2">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                Download PDF
              </span>
            )}
          </Button>
        </div>
      </div>

      {/* Flip Card */}
      <div className="flex justify-center mb-6" style={{ perspective: "1000px" }}>
        <button
          onClick={() => setFlipped(prev => !prev)}
          className="relative w-full max-w-[340px] h-[220px] cursor-pointer focus:outline-none"
          style={{ transformStyle: "preserve-3d" }}
          aria-label={flipped ? "Showing back, click to see front" : "Showing front, click to see back"}
        >
          {/* Front */}
          <div
            className="absolute inset-0 rounded-2xl border-2 border-dashed border-[#1B4332]/30 bg-[#E8F5E9] p-6 flex flex-col justify-center items-center text-center transition-transform duration-500"
            style={{
              backfaceVisibility: "hidden",
              transform: flipped ? "rotateY(180deg)" : "rotateY(0deg)",
            }}
          >
            <span className="absolute top-3 left-4 text-sm opacity-60">
              {getCategoryEmoji(current.category)}
            </span>
            <span className="absolute top-3 right-4 text-xs text-muted-foreground">
              {currentIndex + 1}/{cards.length}
            </span>
            <p className="text-base font-bold text-[#1B4332] leading-relaxed">
              {current.front}
            </p>
            <p className="absolute bottom-3 text-[10px] text-muted-foreground">Tap to flip</p>
          </div>

          {/* Back */}
          <div
            className="absolute inset-0 rounded-2xl border-2 border-dashed border-[#D97706]/30 bg-[#FFF8E1] p-6 flex flex-col justify-center items-center text-center transition-transform duration-500"
            style={{
              backfaceVisibility: "hidden",
              transform: flipped ? "rotateY(0deg)" : "rotateY(-180deg)",
            }}
          >
            <span className="absolute top-3 right-4 text-xs text-muted-foreground">
              {currentIndex + 1}/{cards.length}
            </span>
            <p className="text-sm text-[#1F2937] leading-relaxed">
              {current.back}
            </p>
            <p className="absolute bottom-3 text-[10px] text-muted-foreground">Tap to flip</p>
          </div>
        </button>
      </div>

      {/* Navigation */}
      <div className="flex items-center justify-center gap-4">
        <Button
          variant="outline"
          size="sm"
          disabled={currentIndex === 0}
          onClick={() => { setFlipped(false); setCurrentIndex(prev => prev - 1) }}
        >
          <svg className="w-4 h-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
          Prev
        </Button>
        <span className="text-sm font-medium text-muted-foreground tabular-nums">
          {currentIndex + 1} / {cards.length}
        </span>
        <Button
          variant="outline"
          size="sm"
          disabled={currentIndex === cards.length - 1}
          onClick={() => { setFlipped(false); setCurrentIndex(prev => prev + 1) }}
        >
          Next
          <svg className="w-4 h-4 ml-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </Button>
      </div>

      {/* Progress dots */}
      <div className="flex justify-center gap-1 mt-4">
        {cards.map((_, idx) => (
          <button
            key={idx}
            onClick={() => { setFlipped(false); setCurrentIndex(idx) }}
            className={`w-2 h-2 rounded-full transition-colors ${
              idx === currentIndex ? "bg-[#1B4332]" : "bg-[#1B4332]/20"
            }`}
            aria-label={`Go to card ${idx + 1}`}
          />
        ))}
      </div>
    </Card>
  )
}
