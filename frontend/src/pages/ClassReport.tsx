/**
 * ClassReport — public shareable class report page.
 *
 * No authentication required. Uses plain axios (no auth interceptor).
 * Renders without any React context providers.
 */
import { useState, useEffect } from 'react'
import axios from 'axios'

const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// ─── Types (match report_generator.py output shape) ──────────────────────────

interface ChildReport {
  child_id: string
  name: string
  report_text: string
  recommendation: string
  mastered_count: number
  improving_count: number
  needs_attention_count: number
}

interface ReportData {
  class_name: string
  grade: string
  subject: string
  generated_at: string
  total_students: number
  children: ChildReport[]
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-IN', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
}

function Logo() {
  return (
    <div className="flex items-center gap-2">
      <div className="w-7 h-7 rounded-lg bg-indigo-950 flex items-center justify-center shrink-0">
        <svg className="w-3.5 h-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
        </svg>
      </div>
      <span className="text-sm font-semibold text-stone-500 tracking-tight">Skolar</span>
    </div>
  )
}

// ─── Loading ──────────────────────────────────────────────────────────────────

function LoadingScreen() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-stone-50 to-white flex flex-col items-center justify-center gap-6 px-4">
      <div className="w-14 h-14 border-4 border-indigo-200 border-t-indigo-950 rounded-full animate-spin" />
      <div className="text-center space-y-1.5">
        <h2
          className="text-xl font-bold text-stone-800 font-fraunces"
        >
          Loading report…
        </h2>
        <p className="text-sm text-stone-500">Preparing your class report</p>
      </div>
    </div>
  )
}

// ─── Error ────────────────────────────────────────────────────────────────────

function ErrorScreen({ message }: { message: string }) {
  return (
    <div className="min-h-screen bg-gradient-to-b from-stone-50 to-white flex flex-col items-center justify-center gap-6 px-4">
      <div className="w-16 h-16 rounded-2xl bg-amber-50 border border-amber-100 flex items-center justify-center">
        <svg
          className="w-8 h-8 text-amber-500"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={1.5}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"
          />
        </svg>
      </div>
      <div className="text-center space-y-3 max-w-sm">
        <h2
          className="text-xl font-bold text-stone-800 font-fraunces"
        >
          Report unavailable
        </h2>
        <p className="text-base text-stone-600 leading-relaxed">{message}</p>
      </div>
      <a
        href="/"
        className="mt-2 inline-flex items-center gap-2 px-6 py-2.5 bg-indigo-950 text-white rounded-xl text-sm font-semibold hover:bg-indigo-900 transition-colors"
      >
        Go to Skolar
      </a>
    </div>
  )
}

// ─── ChildReportCard ──────────────────────────────────────────────────────────

function ChildReportCard({ child }: { child: ChildReport }) {
  // Strip "Practice next: " prefix for a cleaner display label
  const hasRec = Boolean(child.recommendation?.trim())
  const recDisplay = hasRec
    ? child.recommendation.replace(/^Practice next:\s*/i, '').replace(/\.$/, '')
    : ''

  return (
    <article className="bg-white rounded-2xl border border-stone-200/70 shadow-sm overflow-hidden">
      {/* ── Child name header ── */}
      <div className="flex items-center gap-3 px-5 py-4 border-b border-stone-100 bg-stone-50/60">
        <div className="w-10 h-10 rounded-full bg-indigo-950 flex items-center justify-center shrink-0">
          <span className="text-white font-bold text-base select-none">
            {child.name.charAt(0).toUpperCase()}
          </span>
        </div>
        <h3
          className="text-lg font-bold text-stone-800 font-fraunces"
        >
          {child.name}
        </h3>
      </div>

      <div className="px-5 py-5 space-y-4">
        {/* ── Summary text — 17px for legibility ── */}
        <p
          className="text-stone-700 leading-relaxed"
          style={{ fontSize: '17px', lineHeight: '1.65' }}
        >
          {child.report_text}
        </p>

        {/* ── Mastery badges ── */}
        <div className="flex flex-wrap gap-2">
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-semibold bg-indigo-50 text-indigo-800 border border-indigo-200/80">
            <span className="w-2 h-2 rounded-full bg-indigo-500 shrink-0" />
            {child.mastered_count} Mastered
          </span>

          {child.needs_attention_count > 0 && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-semibold bg-amber-50 text-amber-700 border border-amber-200/80">
              <span className="w-2 h-2 rounded-full bg-amber-500 shrink-0" />
              {child.needs_attention_count} Need Practice
            </span>
          )}

          {child.improving_count > 0 && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-semibold bg-blue-50 text-blue-700 border border-blue-200/80">
              <span className="w-2 h-2 rounded-full bg-blue-500 shrink-0" />
              {child.improving_count} Improving
            </span>
          )}
        </div>

        {/* ── Recommendation — "This week" highlight ── */}
        {hasRec && (
          <div className="flex items-start gap-3 px-4 py-3.5 bg-indigo-50/80 border border-indigo-200/60 rounded-xl">
            <svg
              className="shrink-0 w-4 h-4 mt-0.5 text-indigo-600"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z"
              />
            </svg>
            <div className="min-w-0">
              <p className="text-[10px] font-bold text-indigo-800 uppercase tracking-wider mb-1">
                This week
              </p>
              <p className="text-sm text-indigo-900 leading-snug">{recDisplay}</p>
            </div>
          </div>
        )}
      </div>
    </article>
  )
}

// ─── Signup CTA ───────────────────────────────────────────────────────────────

function SignupCTA() {
  return (
    <section className="rounded-2xl bg-gradient-to-br from-indigo-950 to-indigo-900 text-white px-6 py-8 text-center shadow-lg shadow-indigo-950/20">
      <h2
        className="text-xl font-bold mb-2 font-fraunces"
      >
        Want to track your child's daily progress?
      </h2>
      <p className="text-indigo-100 text-sm mb-6 leading-relaxed">
        Get personalised CBSE worksheets, real-time mastery tracking, and weekly
        reports — completely free.
      </p>
      <a
        href="/"
        className="inline-flex items-center gap-2 px-6 py-3 bg-white text-indigo-900 rounded-xl text-sm font-bold hover:bg-indigo-50 active:bg-indigo-100 transition-colors shadow-sm"
      >
        Get started free on Skolar
        <svg
          className="w-4 h-4"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2.5}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
        </svg>
      </a>
    </section>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

interface ClassReportProps {
  token: string
}

export default function ClassReport({ token }: ClassReportProps) {
  const [report, setReport] = useState<ReportData | null>(null)
  const [loading, setLoading] = useState(true)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  useEffect(() => {
    const load = async () => {
      try {
        // Plain axios — no auth token injected
        const res = await axios.get(`${apiUrl}/api/reports/${token}`)
        setReport(res.data)
      } catch (err: unknown) {
        const axErr = err as { response?: { status?: number } }
        const status = axErr.response?.status
        if (status === 410) {
          setErrorMsg('This report has expired. Ask your teacher for the latest report.')
        } else if (status === 404) {
          setErrorMsg('This report was not found. Please check the link and try again.')
        } else {
          setErrorMsg('Could not load the report. Please try again later.')
        }
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [token])

  if (loading) return <LoadingScreen />
  if (errorMsg || !report) {
    return <ErrorScreen message={errorMsg ?? 'Report could not be loaded.'} />
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-stone-50 to-white">

      {/* ── Report header ─────────────────────────────────────────────────── */}
      <header className="bg-white border-b border-stone-200/60">
        <div className="max-w-2xl mx-auto px-4 py-8">
          <Logo />

          <div className="mt-5 mb-3 flex items-center justify-between gap-4">
            <h1
              className="text-3xl font-bold text-stone-800 font-fraunces"
                >
              Weekly Learning Report
            </h1>
            <button
              onClick={() => window.print()}
              className="print:hidden inline-flex items-center gap-2 px-4 py-2 border border-stone-200 rounded-xl text-sm font-semibold text-stone-600 hover:bg-stone-50 transition-colors shrink-0"
              aria-label="Print report"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6.72 13.829c-.24.03-.48.062-.72.096m.72-.096a42.415 42.415 0 0110.56 0m-10.56 0L6.34 18m10.94-4.171c.24.03.48.062.72.096m-.72-.096L17.66 18m0 0l.229 2.523a1.125 1.125 0 01-1.12 1.227H7.231c-.662 0-1.18-.568-1.12-1.227L6.34 18m11.318 0h1.091A2.25 2.25 0 0021 15.75V9.456c0-1.081-.768-2.015-1.837-2.175a48.055 48.055 0 00-1.913-.247M6.34 18H5.25A2.25 2.25 0 013 15.75V9.456c0-1.081.768-2.015 1.837-2.175a48.041 48.041 0 011.913-.247m10.5 0a48.536 48.536 0 00-10.5 0m10.5 0V3.375c0-.621-.504-1.125-1.125-1.125h-8.25c-.621 0-1.125.504-1.125 1.125v3.659M18.75 7.131H5.25" />
              </svg>
              Print
            </button>
          </div>

          {/* Class metadata — class name · subject · grade · date */}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-stone-500">
            <span className="font-semibold text-stone-700">{report.class_name}</span>

            {report.subject && (
              <>
                <span aria-hidden className="w-1 h-1 rounded-full bg-stone-300 shrink-0" />
                <span>{report.subject}</span>
              </>
            )}

            {report.grade && (
              <>
                <span aria-hidden className="w-1 h-1 rounded-full bg-stone-300 shrink-0" />
                <span>Class {report.grade}</span>
              </>
            )}

            <span aria-hidden className="w-1 h-1 rounded-full bg-stone-300 shrink-0" />
            <span>{formatDate(report.generated_at)}</span>
          </div>

          <p className="mt-2 text-sm text-stone-400">
            {report.total_students} student{report.total_students !== 1 ? 's' : ''}&ensp;&middot;&ensp;Weekly progress summary
          </p>
        </div>
      </header>

      {/* ── Child report cards ────────────────────────────────────────────── */}
      <main className="max-w-2xl mx-auto px-4 py-8 space-y-5">
        {report.children.length === 0 ? (
          <div className="py-14 text-center">
            <p className="text-stone-500 text-base">
              No student data is available for this report yet.
            </p>
          </div>
        ) : (
          report.children.map((child) => (
            <ChildReportCard key={child.child_id} child={child} />
          ))
        )}

        {/* ── Signup CTA — not a gate, just a section ── */}
        <div className="pt-4">
          <SignupCTA />
        </div>

        {/* ── Footer ── */}
        <footer className="py-8 text-center">
          <p className="text-xs text-stone-400 tracking-wide">
            Powered by{' '}
            <span className="font-semibold text-stone-500">Skolar</span>{' '}
            &mdash; CBSE Learning for Classes 1&ndash;5
          </p>
        </footer>
      </main>

    </div>
  )
}
