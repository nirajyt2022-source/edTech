import { useState, useEffect } from 'react'
import { useProfile } from '@/lib/profile'
import { useChildren } from '@/lib/children'
import { fetchSubjects } from '@/lib/curriculum'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const ONBOARDING_KEY = 'skolar_onboarding_complete'

const GRADES = ['Class 1', 'Class 2', 'Class 3', 'Class 4', 'Class 5'] as const

const FALLBACK_SUBJECTS = ['Maths', 'English', 'Science', 'Hindi', 'EVS']

const STARTER_TOPICS: Record<string, string> = {
  Maths: 'Addition',
  Mathematics: 'Addition',
  English: 'Nouns',
  Science: 'Living Things',
  Hindi: 'Varnamala',
  EVS: 'My Family',
}

interface OnboardingWizardProps {
  onNavigate: (page: string, preFill?: { grade?: string; subject?: string; topic?: string }) => void
}

export default function OnboardingWizard({ onNavigate }: OnboardingWizardProps) {
  const { profile } = useProfile()
  const { children, loading: childrenLoading, createChild } = useChildren()

  const [step, setStep] = useState<1 | 2 | 3>(1)
  const [saving, setSaving] = useState(false)

  // Step 1: child form
  const [childName, setChildName] = useState('')
  const [childGrade, setChildGrade] = useState('Class 1')
  const [childBoard, setChildBoard] = useState('')

  // Step 2: subject pick
  const [subjects, setSubjects] = useState<string[]>([])
  const [selectedSubject, setSelectedSubject] = useState('')
  const [loadingSubjects, setLoadingSubjects] = useState(false)

  // Created child info (persisted across steps)
  const [createdChildGrade, setCreatedChildGrade] = useState('')

  // Visibility: only show for parents with no children, not yet completed
  const isComplete = typeof window !== 'undefined' && localStorage.getItem(ONBOARDING_KEY) === 'true'
  const shouldShow =
    profile !== null &&
    profile.role === 'parent' &&
    children.length === 0 &&
    !isComplete &&
    !childrenLoading

  // Fetch subjects when entering step 2
  useEffect(() => {
    if (step !== 2 || !createdChildGrade) return

    const gradeNum = parseInt(createdChildGrade.replace(/\D/g, ''), 10) || 1

    setLoadingSubjects(true)
    fetchSubjects(gradeNum, 'India')
      .then((data) => {
        const names = data.map((s) => s.name).filter(Boolean)
        setSubjects(names.length > 0 ? names : FALLBACK_SUBJECTS)
      })
      .catch(() => {
        setSubjects(FALLBACK_SUBJECTS)
      })
      .finally(() => setLoadingSubjects(false))
  }, [step, createdChildGrade])

  if (!shouldShow) return null

  const dismiss = () => {
    localStorage.setItem(ONBOARDING_KEY, 'true')
    // Force re-render by setting step back (component will return null due to isComplete)
    setStep(1)
  }

  const handleCreateChild = async () => {
    if (!childName.trim()) return
    setSaving(true)
    try {
      await createChild({
        name: childName.trim(),
        grade: childGrade,
        board: childBoard || undefined,
      })
      setCreatedChildGrade(childGrade)
      setStep(2)
    } catch (err) {
      console.error('Failed to create child:', err)
    } finally {
      setSaving(false)
    }
  }

  const handleSubjectSelect = (subject: string) => {
    setSelectedSubject(subject)
    setStep(3)
  }

  const handleGenerate = () => {
    localStorage.setItem(ONBOARDING_KEY, 'true')
    const topic = STARTER_TOPICS[selectedSubject] || STARTER_TOPICS['Maths']
    onNavigate('generator', {
      grade: createdChildGrade,
      subject: selectedSubject,
      topic,
    })
  }

  return (
    <Dialog open>
      <DialogContent
        className="sm:max-w-xl p-0 overflow-hidden border-none shadow-2xl rounded-3xl"
        onInteractOutside={(e) => e.preventDefault()}
        onEscapeKeyDown={(e) => e.preventDefault()}
      >
        <div className="bg-background relative">
          {/* Decorative gradient */}
          <div className="absolute top-0 left-0 w-full h-32 bg-gradient-to-br from-accent/15 via-primary/5 to-transparent -z-10" />

          <div className="p-8 sm:p-10">
            {/* Step indicators */}
            <div className="flex items-center justify-center gap-2 mb-8">
              {[1, 2, 3].map((s) => (
                <div
                  key={s}
                  className="w-2.5 h-2.5 rounded-full transition-all duration-300"
                  style={{
                    backgroundColor: s === step ? '#1E1B4B' : s < step ? '#1E1B4B' : '#e2e8f0',
                    transform: s === step ? 'scale(1.3)' : 'scale(1)',
                  }}
                />
              ))}
            </div>

            {/* Step 1: Add Your Child */}
            {step === 1 && (
              <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-500">
                <DialogHeader className="space-y-3">
                  <DialogTitle className="text-2xl sm:text-3xl text-center font-fraunces text-foreground">
                    Welcome to <span className="text-primary italic">Skolar</span>
                  </DialogTitle>
                  <DialogDescription className="text-center text-sm font-medium text-muted-foreground/70 max-w-sm mx-auto">
                    Let's set up your child's learning profile. This takes about 30 seconds.
                  </DialogDescription>
                </DialogHeader>

                <div className="space-y-5 mt-4">
                  <div className="space-y-2">
                    <Label htmlFor="child-name" className="text-xs font-bold uppercase tracking-widest text-foreground/70 block pl-1">
                      Child's Name <span className="text-destructive ml-1">*</span>
                    </Label>
                    <Input
                      id="child-name"
                      placeholder="e.g. Aarav"
                      value={childName}
                      onChange={(e) => setChildName(e.target.value)}
                      className="h-12 bg-card/40 border-border/60 rounded-xl focus:ring-primary/20 focus:border-primary/30 font-medium"
                      autoFocus
                    />
                  </div>

                  <div className="space-y-2">
                    <Label className="text-xs font-bold uppercase tracking-widest text-foreground/70 block pl-1">
                      Grade
                    </Label>
                    <div className="flex flex-wrap gap-2">
                      {GRADES.map((g) => (
                        <button
                          key={g}
                          type="button"
                          onClick={() => setChildGrade(g)}
                          className={`px-4 py-2.5 rounded-xl text-xs font-bold border transition-all duration-300 ${
                            childGrade === g
                              ? 'bg-primary text-primary-foreground border-primary shadow-lg shadow-primary/20 scale-[1.05]'
                              : 'bg-card/40 text-muted-foreground border-border/60 hover:border-primary/40 hover:bg-card'
                          }`}
                        >
                          {g}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="child-board" className="text-xs font-bold uppercase tracking-widest text-foreground/70 block pl-1">
                      Board <span className="text-muted-foreground/50 lowercase italic ml-1">(Optional)</span>
                    </Label>
                    <Input
                      id="child-board"
                      placeholder="e.g. CBSE, ICSE"
                      value={childBoard}
                      onChange={(e) => setChildBoard(e.target.value)}
                      className="h-12 bg-card/40 border-border/60 rounded-xl focus:ring-primary/20 focus:border-primary/30 font-medium"
                    />
                  </div>
                </div>

                <div className="flex items-center justify-between mt-6 pt-2">
                  <button
                    onClick={dismiss}
                    className="text-xs text-muted-foreground/50 hover:text-muted-foreground transition-colors underline underline-offset-2"
                  >
                    Skip for now
                  </button>
                  <Button
                    onClick={handleCreateChild}
                    disabled={saving || !childName.trim()}
                    className="bg-primary text-primary-foreground shadow-xl shadow-primary/20 px-8 py-3 rounded-2xl font-bold text-sm h-auto hover:translate-y-[-2px] transition-all disabled:opacity-50 disabled:translate-y-0"
                  >
                    {saving ? (
                      <>
                        <span className="w-4 h-4 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin mr-2" />
                        Creating...
                      </>
                    ) : (
                      'Next'
                    )}
                  </Button>
                </div>
              </div>
            )}

            {/* Step 2: Pick a Subject */}
            {step === 2 && (
              <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-500">
                <DialogHeader className="space-y-3">
                  <DialogTitle className="text-2xl sm:text-3xl text-center font-fraunces text-foreground">
                    Pick a <span className="text-primary italic">Subject</span>
                  </DialogTitle>
                  <DialogDescription className="text-center text-sm font-medium text-muted-foreground/70 max-w-sm mx-auto">
                    What should we practice first? You can always explore other subjects later.
                  </DialogDescription>
                </DialogHeader>

                {loadingSubjects ? (
                  <div className="flex items-center justify-center py-12">
                    <div className="w-8 h-8 border-3 rounded-full animate-spin" style={{ borderColor: 'rgba(30,27,75,0.15)', borderTopColor: '#1E1B4B' }} />
                  </div>
                ) : (
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-4">
                    {subjects.map((subject) => (
                      <button
                        key={subject}
                        onClick={() => handleSubjectSelect(subject)}
                        className="flex flex-col items-center gap-2 p-5 rounded-2xl border border-border/60 bg-card/40 hover:bg-card hover:border-primary/30 hover:shadow-lg hover:shadow-primary/5 transition-all duration-300 text-center group"
                      >
                        <span className="text-2xl">
                          {subject === 'Maths' || subject === 'Mathematics' ? '🔢' :
                           subject === 'English' ? '📖' :
                           subject === 'Science' ? '🔬' :
                           subject === 'Hindi' ? '🕉️' :
                           subject === 'EVS' ? '🌿' :
                           '📚'}
                        </span>
                        <span className="text-sm font-bold text-foreground group-hover:text-primary transition-colors">
                          {subject}
                        </span>
                      </button>
                    ))}
                  </div>
                )}

                <div className="flex items-center justify-center mt-4">
                  <button
                    onClick={dismiss}
                    className="text-xs text-muted-foreground/50 hover:text-muted-foreground transition-colors underline underline-offset-2"
                  >
                    Skip for now
                  </button>
                </div>
              </div>
            )}

            {/* Step 3: Confirm & Generate */}
            {step === 3 && (
              <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-500">
                <DialogHeader className="space-y-3">
                  <DialogTitle className="text-2xl sm:text-3xl text-center font-fraunces text-foreground">
                    Ready to <span className="text-primary italic">Practice!</span>
                  </DialogTitle>
                  <DialogDescription className="text-center text-sm font-medium text-muted-foreground/70 max-w-sm mx-auto">
                    We'll generate a {selectedSubject} worksheet for {childName} ({createdChildGrade}).
                  </DialogDescription>
                </DialogHeader>

                <div className="mt-6 p-6 rounded-2xl border border-border/60 bg-card/30 text-center space-y-4">
                  <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-accent/20 to-accent/5 border border-accent/10">
                    <span className="text-3xl">
                      {selectedSubject === 'Maths' || selectedSubject === 'Mathematics' ? '🔢' :
                       selectedSubject === 'English' ? '📖' :
                       selectedSubject === 'Science' ? '🔬' :
                       selectedSubject === 'Hindi' ? '🕉️' :
                       selectedSubject === 'EVS' ? '🌿' :
                       '📚'}
                    </span>
                  </div>
                  <div>
                    <p className="text-lg font-bold text-foreground">{selectedSubject}</p>
                    <p className="text-sm text-muted-foreground mt-1">
                      Topic: {STARTER_TOPICS[selectedSubject] || 'General'}
                    </p>
                  </div>
                </div>

                <div className="flex items-center justify-between mt-6 pt-2">
                  <button
                    onClick={dismiss}
                    className="text-xs text-muted-foreground/50 hover:text-muted-foreground transition-colors underline underline-offset-2"
                  >
                    Skip for now
                  </button>
                  <Button
                    onClick={handleGenerate}
                    className="bg-primary text-primary-foreground shadow-xl shadow-primary/20 px-8 py-3 rounded-2xl font-bold text-sm h-auto hover:translate-y-[-2px] transition-all"
                  >
                    Generate!
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
