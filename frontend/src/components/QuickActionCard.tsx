import type { ReactNode } from 'react'

// ─── Types ────────────────────────────────────────────────────────────────────

interface QuickActionCardProps {
  icon: ReactNode
  label: string
  description: string
  badge?: 'active' | 'new' | 'coming'
  disabled?: boolean
  onClick?: () => void
}

// ─── Badge Renderer ───────────────────────────────────────────────────────────

function ActionBadge({ type }: { type: 'active' | 'new' | 'coming' }) {
  if (type === 'new') {
    return (
      <span className="inline-flex items-center px-1.5 py-0.5 rounded-md text-[9px] font-bold uppercase tracking-wider bg-amber-100 text-amber-700 border border-amber-200">
        NEW
      </span>
    )
  }
  if (type === 'coming') {
    return (
      <span className="inline-flex items-center px-1.5 py-0.5 rounded-md text-[9px] font-bold uppercase tracking-wider bg-gray-100 text-gray-400 border border-gray-200">
        COMING SOON
      </span>
    )
  }
  // 'active' — subtle green dot
  return (
    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[9px] font-bold uppercase tracking-wider text-emerald-600">
      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
    </span>
  )
}

// ─── Component ────────────────────────────────────────────────────────────────

export function QuickActionCard({
  icon,
  label,
  description,
  badge,
  disabled = false,
  onClick,
}: QuickActionCardProps) {
  const isComingSoon = badge === 'coming'
  const isDisabled = disabled || isComingSoon

  return (
    <button
      type="button"
      onClick={isDisabled ? undefined : onClick}
      disabled={isDisabled}
      className={`
        group relative flex flex-col items-start gap-3 p-5
        bg-white border border-border/60 rounded-xl
        text-left transition-all duration-200
        ${isDisabled
          ? 'opacity-50 pointer-events-none cursor-default'
          : 'hover:shadow-md hover:border-primary/20 hover:bg-primary/[0.02] cursor-pointer active:scale-[0.98]'
        }
      `}
    >
      {/* Icon + Badge row */}
      <div className="flex items-center justify-between w-full">
        <div
          className={`
            w-10 h-10 rounded-xl flex items-center justify-center shrink-0 transition-colors
            ${isDisabled
              ? 'bg-gray-100 text-gray-400'
              : 'bg-primary/10 text-primary group-hover:bg-primary/15'
            }
          `}
        >
          {icon}
        </div>
        {badge && <ActionBadge type={badge} />}
      </div>

      {/* Label */}
      <p
        className={`
          text-sm font-semibold leading-tight
          ${isDisabled ? 'text-gray-400' : 'text-foreground group-hover:text-primary transition-colors'}
        `}
      >
        {label}
      </p>

      {/* Description */}
      <p
        className={`
          text-xs leading-relaxed -mt-1
          ${isDisabled ? 'text-gray-300' : 'text-muted-foreground'}
        `}
      >
        {description}
      </p>
    </button>
  )
}
