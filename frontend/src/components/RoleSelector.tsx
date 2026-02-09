import { useState } from 'react'
import { useProfile } from '@/lib/profile'
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

const SUBJECTS = [
  'Mathematics', 'Science', 'English', 'Hindi',
  'Social Studies', 'Computer Science', 'Physics',
  'Chemistry', 'Biology', 'EVS',
]

const GRADES = [
  'Grade 1', 'Grade 2', 'Grade 3', 'Grade 4', 'Grade 5',
  'Grade 6', 'Grade 7', 'Grade 8', 'Grade 9', 'Grade 10',
  'Grade 11', 'Grade 12',
]

export default function RoleSelector() {
  const { needsRoleSelection, setRole } = useProfile()
  const [step, setStep] = useState<1 | 2>(1)
  const [selectedSubjects, setSelectedSubjects] = useState<string[]>([])
  const [selectedGrades, setSelectedGrades] = useState<string[]>([])
  const [schoolName, setSchoolName] = useState('')
  const [saving, setSaving] = useState(false)

  if (!needsRoleSelection) return null

  const toggleSubject = (subject: string) => {
    setSelectedSubjects(prev =>
      prev.includes(subject) ? prev.filter(s => s !== subject) : [...prev, subject]
    )
  }

  const toggleGrade = (grade: string) => {
    setSelectedGrades(prev =>
      prev.includes(grade) ? prev.filter(g => g !== grade) : [...prev, grade]
    )
  }

  const handleParent = async () => {
    setSaving(true)
    try {
      await setRole('parent')
    } finally {
      setSaving(false)
    }
  }

  const handleTeacherSubmit = async () => {
    if (selectedSubjects.length === 0 || selectedGrades.length === 0) return
    setSaving(true)
    try {
      await setRole('teacher', {
        subjects: selectedSubjects,
        grades: selectedGrades,
        school_name: schoolName || undefined,
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open>
      <DialogContent
        className="sm:max-w-xl p-0 overflow-hidden border-none shadow-2xl rounded-3xl"
        onInteractOutside={(e) => e.preventDefault()}
        onEscapeKeyDown={(e) => e.preventDefault()}
      >
        <div className="bg-background relative">
          {/* Decorative background element */}
          <div className="absolute top-0 left-0 w-full h-32 bg-gradient-to-br from-primary/10 via-accent/5 to-transparent -z-10" />

          <div className="p-8 sm:p-10">
            {step === 1 ? (
              <div className="space-y-8">
                <DialogHeader className="space-y-3">
                  <DialogTitle className="text-3xl sm:text-4xl text-center font-fraunces text-foreground">
                    Customize your <span className="text-primary italic">Workspace</span>
                  </DialogTitle>
                  <DialogDescription className="text-center text-base font-medium text-muted-foreground/70 max-w-sm mx-auto">
                    Select your primary objective. You can switch between roles effortlessly at any time.
                  </DialogDescription>
                </DialogHeader>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 mt-6">
                  {/* Parent Card */}
                  <button
                    onClick={handleParent}
                    disabled={saving}
                    className="flex flex-col items-center gap-5 p-8 rounded-3xl border border-border/60 bg-card/40 hover:bg-card hover:border-primary/30 hover:shadow-xl hover:shadow-primary/5 transition-all duration-300 text-center group relative overflow-hidden"
                  >
                    <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-accent/20 to-accent/5 flex items-center justify-center group-hover:scale-110 group-hover:-rotate-3 transition-all duration-500 border border-accent/10">
                      <svg className="w-8 h-8 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25" />
                      </svg>
                    </div>
                    <div>
                      <h3 className="font-bold text-xl text-foreground font-jakarta">Individual Parent</h3>
                      <p className="text-xs font-medium text-muted-foreground/60 mt-2 leading-relaxed">
                        Design personal learning paths and practice material for your children at home.
                      </p>
                    </div>
                    <div className="absolute bottom-0 left-0 w-full h-1 bg-accent/20 translate-y-full group-hover:translate-y-0 transition-transform duration-300" />
                  </button>

                  {/* Teacher Card */}
                  <button
                    onClick={() => setStep(2)}
                    disabled={saving}
                    className="flex flex-col items-center gap-5 p-8 rounded-3xl border border-border/60 bg-card/40 hover:bg-card hover:border-primary/30 hover:shadow-xl hover:shadow-primary/5 transition-all duration-300 text-center group relative overflow-hidden"
                  >
                    <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-primary/20 to-primary/5 flex items-center justify-center group-hover:scale-110 group-hover:rotate-3 transition-all duration-500 border border-primary/10">
                      <svg className="w-8 h-8 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M4.26 10.147a60.438 60.438 0 00-.491 6.347A48.62 48.62 0 0112 20.904a48.62 48.62 0 018.232-4.41 60.46 60.46 0 00-.491-6.347m-15.482 0a50.636 50.636 0 00-2.658-.813A59.906 59.906 0 0112 3.493a59.903 59.903 0 0110.399 5.84c-.896.248-1.783.52-2.658.814m-15.482 0A50.717 50.717 0 0112 13.489a50.702 50.702 0 017.74-3.342M6.75 15a.75.75 0 100-1.5.75.75 0 000 1.5zm0 0v-3.675A55.378 55.378 0 0112 8.443m-7.007 11.55A5.981 5.981 0 006.75 15.75v-1.5" />
                      </svg>
                    </div>
                    <div>
                      <h3 className="font-bold text-xl text-foreground font-jakarta">Education Pro</h3>
                      <p className="text-xs font-medium text-muted-foreground/60 mt-2 leading-relaxed">
                        Scale your teaching with bulk worksheet generation and classroom roster management.
                      </p>
                    </div>
                    <div className="absolute bottom-0 left-0 w-full h-1 bg-primary/20 translate-y-full group-hover:translate-y-0 transition-transform duration-300" />
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-8 animate-in fade-in slide-in-from-right-4 duration-500">
                <DialogHeader className="space-y-2">
                  <DialogTitle className="text-2xl font-fraunces text-foreground">
                    Teacher <span className="text-primary italic">Initialization</span>
                  </DialogTitle>
                  <DialogDescription className="text-sm font-medium text-muted-foreground/70">
                    Establish your academic parameters to allow PracticeCraft to curate the most relevant resources for you.
                  </DialogDescription>
                </DialogHeader>

                <div className="space-y-8 mt-2">
                  {/* Subjects */}
                  <div className="space-y-4">
                    <Label className="text-xs font-black uppercase tracking-widest text-foreground/70 block pl-1">
                      Disciplines <span className="text-destructive ml-1">*</span>
                    </Label>
                    <div className="flex flex-wrap gap-2">
                      {SUBJECTS.map(subject => (
                        <button
                          key={subject}
                          onClick={() => toggleSubject(subject)}
                          className={`px-4 py-2 rounded-xl text-xs font-bold border transition-all duration-300 ${selectedSubjects.includes(subject)
                              ? 'bg-primary text-primary-foreground border-primary shadow-lg shadow-primary/20 scale-[1.05]'
                              : 'bg-card/40 text-muted-foreground border-border/60 hover:border-primary/40 hover:bg-card'
                            }`}
                        >
                          {subject}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Grades */}
                  <div className="space-y-4">
                    <Label className="text-xs font-black uppercase tracking-widest text-foreground/70 block pl-1">
                      Grade Levels <span className="text-destructive ml-1">*</span>
                    </Label>
                    <div className="flex flex-wrap gap-2">
                      {GRADES.map(grade => (
                        <button
                          key={grade}
                          onClick={() => toggleGrade(grade)}
                          className={`px-4 py-2 rounded-xl text-xs font-bold border transition-all duration-300 ${selectedGrades.includes(grade)
                              ? 'bg-primary text-primary-foreground border-primary shadow-lg shadow-primary/20 scale-[1.05]'
                              : 'bg-card/40 text-muted-foreground border-border/60 hover:border-primary/40 hover:bg-card'
                            }`}
                        >
                          {grade}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* School Name */}
                  <div className="space-y-3">
                    <Label htmlFor="school-name" className="text-xs font-black uppercase tracking-widest text-foreground/70 block pl-1">
                      Institutional Affiliation <span className="text-muted-foreground/50 lowercase italic ml-1">(Optional)</span>
                    </Label>
                    <Input
                      id="school-name"
                      placeholder="e.g. Modern Academy International"
                      value={schoolName}
                      onChange={(e) => setSchoolName(e.target.value)}
                      className="h-12 bg-card/40 border-border/60 rounded-xl focus:ring-primary/20 focus:border-primary/30 font-medium"
                    />
                  </div>
                </div>

                <div className="flex items-center gap-4 mt-6 pt-4">
                  <Button
                    variant="ghost"
                    onClick={() => setStep(1)}
                    disabled={saving}
                    className="px-6 py-6 h-auto rounded-xl font-bold text-muted-foreground hover:bg-secondary/50"
                  >
                    Back
                  </Button>
                  <Button
                    onClick={handleTeacherSubmit}
                    disabled={saving || selectedSubjects.length === 0 || selectedGrades.length === 0}
                    className="flex-1 bg-primary text-primary-foreground shadow-xl shadow-primary/20 py-6 rounded-2xl font-bold text-base h-auto hover:translate-y-[-2px] transition-all disabled:opacity-50 disabled:translate-y-0"
                  >
                    {saving ? (
                      <>
                        <span className="w-5 h-5 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin mr-3" />
                        Initializing Profile...
                      </>
                    ) : 'Complete Professional Setup'}
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
