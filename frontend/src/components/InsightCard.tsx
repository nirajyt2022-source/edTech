import { useState, useEffect } from 'react'
import { api } from '@/lib/api'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { QuickPracticeButton } from '@/components/QuickPracticeButton'

// ─── Types ────────────────────────────────────────────────────────────────────

interface Recommendation {
  topic_slug: string
  topic_name: string
  reason: string
  subject: string
}

interface ReportData {
  child_name: string
  report_text: string
  recommendation: Recommendation | null
}

interface Props {
  childId: string
  /** App-level callback that switches to the worksheet generator page. */
  onNavigate?: () => void
}

// ─── Component ────────────────────────────────────────────────────────────────

export function InsightCard({ childId, onNavigate }: Props) {
  const [report, setReport] = useState<ReportData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!childId) return
    setLoading(true)
    api
      .get(`/api/children/${childId}/graph/report`)
      .then((r) => setReport(r.data))
      .catch((err) => {
        console.warn('[InsightCard] Failed to fetch report:', err)
        setReport(null)
      })
      .finally(() => setLoading(false))
  }, [childId])

  // ── Loading skeleton ───────────────────────────────────────────────────────

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

  // ── Empty / error state ────────────────────────────────────────────────────

  if (!report) {
    return (
      <Card className="border-amber-100 bg-amber-50/40">
        <CardContent className="p-5">
          <p className="text-sm text-amber-700/70 text-center">
            Complete a worksheet to see insights here.
          </p>
        </CardContent>
      </Card>
    )
  }

  const { report_text, recommendation } = report

  // ── Full render ────────────────────────────────────────────────────────────

  return (
    <Card className="border-amber-200 bg-amber-50/50">
      <CardContent className="p-5 space-y-4">

        {/* Report text */}
        <p className="text-sm text-amber-900 leading-relaxed">{report_text}</p>

        {/* Recommendation block */}
        {recommendation ? (
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pt-1 border-t border-amber-200/60">
            <div className="space-y-0.5 min-w-0">
              <p className="text-xs font-semibold uppercase tracking-wide text-amber-600">
                Today's Pick
              </p>
              <p className="text-sm font-semibold text-amber-900 truncate">
                {recommendation.topic_name}
              </p>
              <p className="text-xs text-amber-700/80 leading-snug">
                {recommendation.reason}
              </p>
            </div>

            {onNavigate && (
              <QuickPracticeButton
                topic_slug={recommendation.topic_slug}
                topic_name={recommendation.topic_name}
                subject={recommendation.subject}
                child_id={childId}
                onNavigate={onNavigate}
              />
            )}
          </div>
        ) : (
          <p className="text-xs text-amber-700/60 pt-1 border-t border-amber-200/60">
            Complete a worksheet to get a personalised recommendation.
          </p>
        )}

      </CardContent>
    </Card>
  )
}
