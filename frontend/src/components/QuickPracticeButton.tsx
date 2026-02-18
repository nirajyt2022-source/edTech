interface Props {
  topic_slug: string
  topic_name: string
  subject: string
  child_id: string
  /** App-level callback that switches the page to the generator. */
  onNavigate: () => void
}

/**
 * One-tap shortcut that pre-fills the worksheet generator with a specific
 * topic + child and auto-triggers generation after 600 ms.
 *
 * Navigation strategy: push URL search params (no page reload) then call
 * onNavigate() so App.tsx switches the SPA page to "generator".
 * WorksheetGenerator reads these params on mount and consumes them.
 */
export function QuickPracticeButton({
  topic_slug,
  topic_name,
  subject,
  child_id,
  onNavigate,
}: Props) {
  const handleClick = () => {
    // Encode params so WorksheetGenerator can pre-fill on mount
    const params = new URLSearchParams({
      topic_slug,
      subject,
      child_id,
      auto_generate: 'true',
    })
    // Push without reloading — WorksheetGenerator reads these on mount
    window.history.pushState({}, '', `?${params.toString()}`)
    onNavigate()
  }

  return (
    <button
      onClick={handleClick}
      className={[
        'shrink-0 inline-flex items-center gap-1.5 px-4 py-2 rounded-lg',
        'text-sm font-semibold transition-colors',
        'bg-amber-500 text-white hover:bg-amber-600 active:bg-amber-700',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400 focus-visible:ring-offset-2',
      ].join(' ')}
    >
      Practice {topic_name}
      <svg
        className="w-3.5 h-3.5"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2.5}
        aria-hidden="true"
      >
        <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
      </svg>
    </button>
  )
}
