import { useState, useEffect } from 'react'
import { api } from '@/lib/api'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'

// ─── Types ────────────────────────────────────────────────────────────────────

interface InsightItem {
  skill_tag: string
  display: string
  detail: string
}

interface ChildInsightsData {
  strengths: InsightItem[]
  struggles: InsightItem[]
  improving: InsightItem[]
  weekly_summary: string
  actionable_tip: string
  next_worksheet_suggestion: {
    focus_skill: string
    difficulty: string
    rationale: string
  } | null
}

interface WeeklyDigestData {
  total_sessions: number
  total_questions: number
  overall_accuracy: number
  accuracy_trend: 'improving' | 'declining' | 'stable'
  newly_mastered: string[]
  persistent_struggles: string[]
  summary: string
}

interface DiagnosticInsightsCardProps {
  childId: string
  childName: string
  onNavigate?: (page: string) => void
}

// Module-level regex (Rule 7)
const ACCURACY_RE = /(\d+)%/

// ─── Component ────────────────────────────────────────────────────────────────

export function DiagnosticInsightsCard({
  childId,
  childName,
  onNavigate,
}: DiagnosticInsightsCardProps) {
  const [insights, setInsights] = useState<ChildInsightsData | null>(null)
  const [digest, setDigest] = useState<WeeklyDigestData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!childId) return
    setLoading(true) // eslint-disable-line react-hooks/set-state-in-effect
    Promise.allSettled([
      api.get(`/api/children/${childId}/insights`),
      api.get(`/api/children/${childId}/weekly-digest`),
    ])
      .then(([insRes, digRes]) => {
        if (insRes.status === 'fulfilled') setInsights(insRes.value.data)
        else console.warn('[DiagnosticInsights] insights fetch failed:', insRes.reason)
        if (digRes.status === 'fulfilled') setDigest(digRes.value.data)
        else console.warn('[DiagnosticInsights] digest fetch failed:', digRes.reason)
      })
      .finally(() => setLoading(false))
  }, [childId])

  // ── Loading skeleton ─────────────────────────────────────────────────────

  if (loading) {
    return (
      <Card className="border-amber-100 bg-amber-50/40">
        <CardContent className="p-5 space-y-3">
          <Skeleton className="h-4 w-3/4 rounded-md bg-amber-100" />
          <Skeleton className="h-4 w-full rounded-md bg-amber-100" />
          <Skeleton className="h-4 w-2/3 rounded-md bg-amber-100" />
        </CardContent>
      </Card>
    )
  }

  const hasSkills =
    (insights?.strengths?.length ?? 0) > 0 ||
    (insights?.struggles?.length ?? 0) > 0 ||
    (insights?.improving?.length ?? 0) > 0

  const struggles = insights?.struggles ?? []
  const suggestion = insights?.next_worksheet_suggestion
  const weeklySummary = insights?.weekly_summary ?? ''

  // ── Helpers ──────────────────────────────────────────────────────────────

  function accuracyFromDetail(detail: string): number | null {
    const m = ACCURACY_RE.exec(detail)
    return m ? parseInt(m[1], 10) : null
  }

  function barColor(pct: number): string {
    if (pct < 40) return 'bg-red-500'
    if (pct <= 60) return 'bg-amber-500'
    return 'bg-emerald-500'
  }

  function trendBadge(trend: string) {
    if (trend === 'improving')
      return <Badge className="bg-emerald-100 text-emerald-700 border-emerald-200">Improving</Badge>
    if (trend === 'declining')
      return <Badge className="bg-red-100 text-red-700 border-red-200">Declining</Badge>
    return <Badge className="bg-gray-100 text-gray-600 border-gray-200">Stable</Badge>
  }

  function handlePracticeSuggestion() {
    if (!suggestion || !onNavigate) return
    const params = new URLSearchParams({
      topic_slug: suggestion.focus_skill,
      child_id: childId,
      auto_generate: 'true',
    })
    window.history.pushState({}, '', `?${params.toString()}`)
    onNavigate('generator')
  }

  function handleShareWhatsApp() {
    const name = childName || 'My child'
    const lines = [
      `*${name}'s Weekly Learning Update*`,
      '',
      weeklySummary,
    ]
    if (digest) {
      lines.push('')
      lines.push(`_${digest.total_sessions} sessions | ${digest.total_questions} questions | ${digest.overall_accuracy}% accuracy_`)
    }
    if (insights?.actionable_tip) {
      lines.push('')
      lines.push(`Tip: ${insights.actionable_tip}`)
    }
    lines.push('')
    lines.push('Powered by Skolar')
    const text = encodeURIComponent(lines.join('\n'))
    window.open(`https://wa.me/?text=${text}`, '_blank')
  }

  // ── Skill bucket renderer ────────────────────────────────────────────────

  function renderBucket(
    label: string,
    items: InsightItem[],
    colorClass: string,
    badgeClass: string,
  ) {
    if (items.length === 0) return null
    return (
      <div className="space-y-1.5">
        <p className={`text-xs font-semibold uppercase tracking-wide ${colorClass}`}>
          {label}
        </p>
        <div className="flex flex-wrap gap-2">
          {items.map((item) => (
            <div key={item.skill_tag} className="flex flex-col">
              <Badge variant="outline" className={badgeClass}>
                {item.display}
              </Badge>
              <span className="text-xs text-muted-foreground mt-0.5 pl-1">
                {item.detail}
              </span>
            </div>
          ))}
        </div>
      </div>
    )
  }

  // ── Full render ──────────────────────────────────────────────────────────

  return (
    <Card className="border-amber-200 bg-amber-50/50">
      <CardContent className="p-5 space-y-4">

        {/* A. Skill Buckets */}
        {hasSkills ? (
          <div className="space-y-3">
            {renderBucket('Doing Well', insights?.strengths ?? [], 'text-emerald-600', 'border-emerald-300 text-emerald-700')}
            {renderBucket('Needs Practice', struggles, 'text-red-600', 'border-red-300 text-red-700')}
            {renderBucket('Getting Better', insights?.improving ?? [], 'text-blue-600', 'border-blue-300 text-blue-700')}
          </div>
        ) : (
          <p className="text-sm text-amber-700/70 text-center">
            Complete more worksheets to unlock skill insights.
          </p>
        )}

        {/* B. Accuracy Bars (max 3 struggles) */}
        {struggles.length > 0 && (
          <div className="space-y-2 pt-2 border-t border-amber-200/60">
            {struggles.slice(0, 3).map((s) => {
              const pct = accuracyFromDetail(s.detail)
              if (pct === null) return null
              return (
                <div key={s.skill_tag} className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="text-amber-900 font-medium">{s.display}</span>
                    <span className="text-amber-700">{pct}%</span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-amber-100">
                    <div
                      className={`h-2 rounded-full transition-all ${barColor(pct)}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {/* C. Actionable Tip */}
        {insights?.actionable_tip && (
          <div className="flex gap-2 rounded-lg bg-amber-50 border border-amber-200/80 p-3">
            <svg
              className="w-5 h-5 shrink-0 text-amber-500 mt-0.5"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5.002 5.002 0 117.072 0l.146.146A2 2 0 0115.5 19h-7a2 2 0 01-1.179-3.634l.146-.146z"
              />
            </svg>
            <p className="text-sm text-amber-900 leading-relaxed">
              {insights.actionable_tip}
            </p>
          </div>
        )}

        {/* D. Weekly Digest Strip */}
        {digest && (
          <div className="flex items-center justify-between gap-4 pt-2 border-t border-amber-200/60">
            <div className="flex gap-4 text-center">
              <div>
                <p className="text-lg font-semibold text-amber-900">{digest.total_sessions}</p>
                <p className="text-xs text-amber-700/70">Sessions</p>
              </div>
              <div>
                <p className="text-lg font-semibold text-amber-900">{digest.total_questions}</p>
                <p className="text-xs text-amber-700/70">Questions</p>
              </div>
              <div>
                <p className="text-lg font-semibold text-amber-900">{digest.overall_accuracy}%</p>
                <p className="text-xs text-amber-700/70">Accuracy</p>
              </div>
            </div>
            {trendBadge(digest.accuracy_trend)}
          </div>
        )}

        {/* E. Suggested Worksheet CTA */}
        {suggestion?.focus_skill && onNavigate && (
          <div className="pt-2 border-t border-amber-200/60">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
              <div className="space-y-0.5 min-w-0">
                <p className="text-xs font-semibold uppercase tracking-wide text-amber-600">
                  Suggested Next
                </p>
                <p className="text-sm text-amber-900 leading-snug">
                  {suggestion.rationale}
                </p>
              </div>
              <button
                onClick={handlePracticeSuggestion}
                className={[
                  'shrink-0 inline-flex items-center gap-1.5 px-4 py-2 rounded-lg',
                  'text-sm font-semibold transition-colors',
                  'bg-amber-500 text-white hover:bg-amber-600 active:bg-amber-700',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400 focus-visible:ring-offset-2',
                ].join(' ')}
              >
                Practice {suggestion.focus_skill.replace(/_/g, ' ')}
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
            </div>
          </div>
        )}

        {/* F. Share on WhatsApp */}
        {weeklySummary && weeklySummary.length > 0 && (
          <div className="pt-2 border-t border-amber-200/60">
            <Button
              onClick={handleShareWhatsApp}
              variant="outline"
              size="sm"
              className="text-green-700 border-green-200 hover:bg-green-50"
            >
              <svg className="w-4 h-4 mr-2" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z" />
              </svg>
              Share on WhatsApp
            </Button>
          </div>
        )}

      </CardContent>
    </Card>
  )
}
