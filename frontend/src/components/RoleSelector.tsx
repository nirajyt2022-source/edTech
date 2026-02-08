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
        className="sm:max-w-lg [&>button:last-child]:hidden"
        onInteractOutside={(e) => e.preventDefault()}
        onEscapeKeyDown={(e) => e.preventDefault()}
      >
        <div>
          {step === 1 ? (
            <>
              <DialogHeader>
                <DialogTitle className="text-2xl text-center">
                  Welcome to PracticeCraft!
                </DialogTitle>
                <DialogDescription className="text-center">
                  How will you be using PracticeCraft? You can switch roles anytime.
                </DialogDescription>
              </DialogHeader>

              <div className="grid grid-cols-2 gap-4 mt-4">
                {/* Parent Card */}
                <button
                  onClick={handleParent}
                  disabled={saving}
                  className="flex flex-col items-center gap-3 p-6 rounded-xl border-2 border-border bg-card hover:border-primary hover:bg-primary/5 transition-all text-center group"
                >
                  <div className="w-14 h-14 rounded-full bg-gradient-to-br from-accent/20 to-accent/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                    <svg className="w-7 h-7 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25" />
                    </svg>
                  </div>
                  <div>
                    <h3 className="font-semibold text-foreground text-lg">Parent</h3>
                    <p className="text-sm text-muted-foreground mt-1">
                      Create worksheets for your children at home
                    </p>
                  </div>
                </button>

                {/* Teacher Card */}
                <button
                  onClick={() => setStep(2)}
                  disabled={saving}
                  className="flex flex-col items-center gap-3 p-6 rounded-xl border-2 border-border bg-card hover:border-primary hover:bg-primary/5 transition-all text-center group"
                >
                  <div className="w-14 h-14 rounded-full bg-gradient-to-br from-primary/20 to-primary/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                    <svg className="w-7 h-7 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M4.26 10.147a60.438 60.438 0 00-.491 6.347A48.62 48.62 0 0112 20.904a48.62 48.62 0 018.232-4.41 60.46 60.46 0 00-.491-6.347m-15.482 0a50.636 50.636 0 00-2.658-.813A59.906 59.906 0 0112 3.493a59.903 59.903 0 0110.399 5.84c-.896.248-1.783.52-2.658.814m-15.482 0A50.717 50.717 0 0112 13.489a50.702 50.702 0 017.74-3.342M6.75 15a.75.75 0 100-1.5.75.75 0 000 1.5zm0 0v-3.675A55.378 55.378 0 0112 8.443m-7.007 11.55A5.981 5.981 0 006.75 15.75v-1.5" />
                    </svg>
                  </div>
                  <div>
                    <h3 className="font-semibold text-foreground text-lg">Teacher</h3>
                    <p className="text-sm text-muted-foreground mt-1">
                      Create & share worksheets with your classes
                    </p>
                  </div>
                </button>
              </div>
            </>
          ) : (
            <>
              <DialogHeader>
                <DialogTitle className="text-xl">
                  Set Up Your Teacher Profile
                </DialogTitle>
                <DialogDescription>
                  Tell us about your teaching — this helps us personalise your experience.
                </DialogDescription>
              </DialogHeader>

              <div className="space-y-5 mt-2">
                {/* Subjects */}
                <div>
                  <Label className="text-sm font-medium mb-2 block">
                    Subjects you teach <span className="text-destructive">*</span>
                  </Label>
                  <div className="flex flex-wrap gap-2">
                    {SUBJECTS.map(subject => (
                      <button
                        key={subject}
                        onClick={() => toggleSubject(subject)}
                        className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition-all ${
                          selectedSubjects.includes(subject)
                            ? 'bg-primary text-primary-foreground border-primary'
                            : 'bg-card text-foreground border-border hover:border-primary/50'
                        }`}
                      >
                        {subject}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Grades */}
                <div>
                  <Label className="text-sm font-medium mb-2 block">
                    Grades you teach <span className="text-destructive">*</span>
                  </Label>
                  <div className="flex flex-wrap gap-2">
                    {GRADES.map(grade => (
                      <button
                        key={grade}
                        onClick={() => toggleGrade(grade)}
                        className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition-all ${
                          selectedGrades.includes(grade)
                            ? 'bg-primary text-primary-foreground border-primary'
                            : 'bg-card text-foreground border-border hover:border-primary/50'
                        }`}
                      >
                        {grade}
                      </button>
                    ))}
                  </div>
                </div>

                {/* School Name */}
                <div>
                  <Label htmlFor="school-name" className="text-sm font-medium mb-2 block">
                    School name <span className="text-muted-foreground">(optional)</span>
                  </Label>
                  <Input
                    id="school-name"
                    placeholder="e.g. Delhi Public School"
                    value={schoolName}
                    onChange={(e) => setSchoolName(e.target.value)}
                  />
                </div>
              </div>

              <div className="flex items-center gap-3 mt-4">
                <Button
                  variant="ghost"
                  onClick={() => setStep(1)}
                  disabled={saving}
                >
                  Back
                </Button>
                <Button
                  onClick={handleTeacherSubmit}
                  disabled={saving || selectedSubjects.length === 0 || selectedGrades.length === 0}
                  className="flex-1"
                >
                  {saving ? 'Saving...' : 'Continue as Teacher'}
                </Button>
              </div>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
