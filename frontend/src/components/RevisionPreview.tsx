import { useState } from "react"
import { Card, CardHeader, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface KeyConcept {
  title: string
  explanation: string
  example: string
}

interface WorkedExample {
  problem: string
  step_by_step: string[]
  answer: string
}

interface CommonMistake {
  mistake: string
  correction: string
  tip: string
}

interface QuizQuestion {
  question: string
  options: string[]
  correct_answer: string
  explanation: string
}

interface RevisionNotes {
  grade: string
  subject: string
  topic: string
  language: string
  introduction: string
  key_concepts: KeyConcept[]
  worked_examples: WorkedExample[]
  common_mistakes: CommonMistake[]
  quick_quiz: QuizQuestion[]
  memory_tips: string[]
}

interface RevisionPreviewProps {
  notes: RevisionNotes
  onDownloadPdf: () => void
  downloadingPdf: boolean
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const DEVANAGARI_RE = /[\u0900-\u097F]/

/** Returns extra class name when the text contains Devanagari characters. */
function devanagariClass(text: string): string {
  return DEVANAGARI_RE.test(text) ? "font-noto-devanagari" : ""
}

/** Map index 0-3 to letter A-D (extends beyond if needed). */
function optionLetter(index: number): string {
  return String.fromCharCode(65 + index) // A, B, C, D, ...
}

// ---------------------------------------------------------------------------
// Inline SVG icons (small, simple)
// ---------------------------------------------------------------------------

function BookIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      xmlns="http://www.w3.org/2000/svg"
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20" />
    </svg>
  )
}

function LightbulbIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      xmlns="http://www.w3.org/2000/svg"
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5" />
      <path d="M9 18h6" />
      <path d="M10 22h4" />
    </svg>
  )
}

function PencilIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      xmlns="http://www.w3.org/2000/svg"
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
    </svg>
  )
}

function AlertTriangleIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      xmlns="http://www.w3.org/2000/svg"
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
      <path d="M12 9v4" />
      <path d="M12 17h.01" />
    </svg>
  )
}

function ClipboardIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      xmlns="http://www.w3.org/2000/svg"
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect width="8" height="4" x="8" y="2" rx="1" ry="1" />
      <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
    </svg>
  )
}

function DownloadIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      xmlns="http://www.w3.org/2000/svg"
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  )
}

function SpinnerIcon({ className }: { className?: string }) {
  return (
    <svg
      className={`animate-spin ${className ?? ""}`}
      xmlns="http://www.w3.org/2000/svg"
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
    >
      <path d="M21 12a9 9 0 1 1-6.219-8.56" />
    </svg>
  )
}

function XCircleIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      xmlns="http://www.w3.org/2000/svg"
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="12" r="10" />
      <path d="m15 9-6 6" />
      <path d="m9 9 6 6" />
    </svg>
  )
}

function CheckCircleIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      xmlns="http://www.w3.org/2000/svg"
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="12" r="10" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  )
}

// ---------------------------------------------------------------------------
// Section header
// ---------------------------------------------------------------------------

function SectionHeader({
  icon,
  title,
}: {
  icon: React.ReactNode
  title: string
}) {
  return (
    <div className="flex items-center gap-2 mb-4">
      {icon}
      <h2 className="text-lg font-semibold">{title}</h2>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function RevisionPreview({
  notes,
  onDownloadPdf,
  downloadingPdf,
}: RevisionPreviewProps) {
  const [revealedAnswers, setRevealedAnswers] = useState<Set<number>>(
    new Set()
  )

  function toggleAnswer(index: number) {
    setRevealedAnswers((prev) => {
      const next = new Set(prev)
      if (next.has(index)) {
        next.delete(index)
      } else {
        next.add(index)
      }
      return next
    })
  }

  const langClass = devanagariClass(
    notes.topic + notes.introduction + (notes.language ?? "")
  )

  return (
    <div className={`space-y-6 ${langClass}`}>
      {/* ----------------------------------------------------------------- */}
      {/* 1. Header bar                                                     */}
      {/* ----------------------------------------------------------------- */}
      <Card className="rounded-xl">
        <CardHeader className="flex flex-row items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3 min-w-0">
            <h1 className="text-xl font-bold truncate">{notes.topic}</h1>
            <span className="shrink-0 inline-flex items-center rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
              {notes.grade} &middot; {notes.subject}
            </span>
          </div>
          <Button
            onClick={onDownloadPdf}
            disabled={downloadingPdf}
            size="sm"
          >
            {downloadingPdf ? (
              <SpinnerIcon className="mr-1" />
            ) : (
              <DownloadIcon className="mr-1" />
            )}
            {downloadingPdf ? "Downloading..." : "Download PDF"}
          </Button>
        </CardHeader>
      </Card>

      {/* ----------------------------------------------------------------- */}
      {/* 2. Introduction                                                   */}
      {/* ----------------------------------------------------------------- */}
      <Card className="rounded-xl bg-muted/40">
        <CardContent className="pt-6">
          <p className="text-sm leading-relaxed text-muted-foreground">
            {notes.introduction}
          </p>
        </CardContent>
      </Card>

      {/* ----------------------------------------------------------------- */}
      {/* 3. Key Concepts                                                   */}
      {/* ----------------------------------------------------------------- */}
      {notes.key_concepts.length > 0 && (
        <section>
          <SectionHeader
            icon={<LightbulbIcon className="text-amber-600" />}
            title="Key Concepts"
          />
          <div className="space-y-3">
            {notes.key_concepts.map((concept, i) => (
              <Card
                key={i}
                className="rounded-xl border-l-4 border-l-amber-500 bg-amber-50/50"
              >
                <CardContent className="pt-5 space-y-1.5">
                  <h3 className="font-bold text-amber-700">{concept.title}</h3>
                  <p className="text-sm leading-relaxed">
                    {concept.explanation}
                  </p>
                  <p className="text-sm italic text-muted-foreground">
                    {concept.example}
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>
      )}

      {/* ----------------------------------------------------------------- */}
      {/* 4. Worked Examples                                                */}
      {/* ----------------------------------------------------------------- */}
      {notes.worked_examples.length > 0 && (
        <section>
          <SectionHeader
            icon={<PencilIcon className="text-green-600" />}
            title="Worked Examples"
          />
          <div className="space-y-3">
            {notes.worked_examples.map((example, i) => (
              <Card
                key={i}
                className="rounded-xl border-l-4 border-l-green-600 bg-green-50/50"
              >
                <CardContent className="pt-5 space-y-3">
                  <p className="font-bold text-sm">{example.problem}</p>
                  <ol className="list-decimal list-inside space-y-1 text-sm pl-1">
                    {example.step_by_step.map((step, si) => (
                      <li key={si} className="leading-relaxed">
                        {step}
                      </li>
                    ))}
                  </ol>
                  <p className="text-sm font-bold text-green-700">
                    Answer: {example.answer}
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>
      )}

      {/* ----------------------------------------------------------------- */}
      {/* 5. Common Mistakes                                                */}
      {/* ----------------------------------------------------------------- */}
      {notes.common_mistakes.length > 0 && (
        <section>
          <SectionHeader
            icon={<AlertTriangleIcon className="text-red-500" />}
            title="Common Mistakes"
          />
          <div className="space-y-3">
            {notes.common_mistakes.map((item, i) => (
              <Card
                key={i}
                className="rounded-xl border-l-4 border-l-red-500 bg-red-50/50"
              >
                <CardContent className="pt-5 space-y-2">
                  <div className="flex items-start gap-2 text-sm">
                    <XCircleIcon className="text-red-500 mt-0.5 shrink-0" />
                    <span>{item.mistake}</span>
                  </div>
                  <div className="flex items-start gap-2 text-sm">
                    <CheckCircleIcon className="text-green-600 mt-0.5 shrink-0" />
                    <span>{item.correction}</span>
                  </div>
                  <p className="text-sm italic text-muted-foreground pl-6">
                    {item.tip}
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>
      )}

      {/* ----------------------------------------------------------------- */}
      {/* 6. Quick Quiz                                                     */}
      {/* ----------------------------------------------------------------- */}
      {notes.quick_quiz.length > 0 && (
        <section>
          <SectionHeader
            icon={<ClipboardIcon className="text-blue-500" />}
            title="Quick Quiz"
          />
          <div className="space-y-3">
            {notes.quick_quiz.map((q, i) => {
              const revealed = revealedAnswers.has(i)
              return (
                <Card
                  key={i}
                  className="rounded-xl border-l-4 border-l-blue-500 bg-blue-50/50"
                >
                  <CardContent className="pt-5 space-y-3">
                    <p className="font-bold text-sm">
                      {i + 1}. {q.question}
                    </p>
                    <ul className="space-y-1 text-sm pl-2">
                      {q.options.map((opt, oi) => (
                        <li key={oi} className="leading-relaxed">
                          <span className="font-medium">
                            {optionLetter(oi)}.
                          </span>{" "}
                          {opt}
                        </li>
                      ))}
                    </ul>

                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => toggleAnswer(i)}
                      className="text-xs"
                    >
                      {revealed ? "Hide Answer" : "Show Answer"}
                    </Button>

                    {revealed && (
                      <div className="rounded-lg bg-white/70 p-3 space-y-1 text-sm border border-blue-100">
                        <p className="font-bold text-green-700">
                          Answer: {q.correct_answer}
                        </p>
                        <p className="text-muted-foreground">
                          {q.explanation}
                        </p>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )
            })}
          </div>
        </section>
      )}

      {/* ----------------------------------------------------------------- */}
      {/* 7. Memory Tips                                                    */}
      {/* ----------------------------------------------------------------- */}
      {notes.memory_tips.length > 0 && (
        <section>
          <SectionHeader
            icon={<BookIcon className="text-amber-600" />}
            title="Memory Tips"
          />
          <Card className="rounded-xl bg-amber-50/30 border-amber-200">
            <CardContent className="pt-5">
              <ul className="space-y-2">
                {notes.memory_tips.map((tip, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-2 text-sm leading-relaxed"
                  >
                    <span className="shrink-0 mt-0.5" aria-hidden="true">
                      💡
                    </span>
                    <span>{tip}</span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </section>
      )}
    </div>
  )
}

export type {
  RevisionNotes,
  RevisionPreviewProps,
  KeyConcept,
  WorkedExample,
  CommonMistake,
  QuizQuestion,
}
