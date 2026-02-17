import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { PageHeader } from '@/components/ui/page-header'
import { Section } from '@/components/ui/section'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { useClasses, type TeacherClass } from '@/lib/classes'
import { useProfile } from '@/lib/profile'
import { fetchSubjects, type CurriculumSubject } from '@/lib/curriculum'
import { notify } from '@/lib/toast'

const GRADES = ['Class 1', 'Class 2', 'Class 3', 'Class 4', 'Class 5']
const FALLBACK_SUBJECTS = ['Maths', 'English', 'EVS', 'Hindi', 'Science', 'Computer']
const BOARDS = ['CBSE', 'ICSE', 'State Board']

export default function ClassManager({ onNavigate }: { onNavigate?: (page: string) => void }) {
  const { classes, loading, error, createClass, updateClass, deleteClass } = useClasses()
  const { region } = useProfile()
  const [curriculumSubjects, setCurriculumSubjects] = useState<CurriculumSubject[]>([])

  const [showForm, setShowForm] = useState(false)
  const [editingClass, setEditingClass] = useState<TeacherClass | null>(null)
  const [formError, setFormError] = useState('')
  const [saving, setSaving] = useState(false)

  const [name, setName] = useState('')
  const [grade, setGrade] = useState('')
  const [subject, setSubject] = useState('')
  const [board, setBoard] = useState('CBSE')

  // Fetch curriculum subjects for region-filtered dropdown
  useEffect(() => {
    if (!grade) {
      setCurriculumSubjects([])
      return
    }
    const gradeNum = parseInt(grade.replace('Class ', ''))
    if (isNaN(gradeNum)) return

    let cancelled = false
    fetchSubjects(gradeNum, region, true).then(subjects => {
      if (!cancelled) setCurriculumSubjects(subjects)
    }).catch(() => {
      if (!cancelled) setCurriculumSubjects([])
    })
    return () => { cancelled = true }
  }, [grade, region])

  const resetForm = () => {
    setName('')
    setGrade('')
    setSubject('')
    setBoard('CBSE')
    setEditingClass(null)
    setShowForm(false)
    setFormError('')
  }

  const openAddForm = () => {
    resetForm()
    setShowForm(true)
  }

  const openEditForm = (cls: TeacherClass) => {
    setName(cls.name)
    setGrade(cls.grade)
    setSubject(cls.subject)
    setBoard(cls.board)
    setEditingClass(cls)
    setShowForm(true)
    setFormError('')
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!name.trim() || !grade || !subject) {
      setFormError('Name, grade, and subject are required')
      return
    }

    setSaving(true)
    setFormError('')

    try {
      if (editingClass) {
        await updateClass(editingClass.id, {
          name: name.trim(),
          grade,
          subject,
          board,
        })
      } else {
        await createClass({
          name: name.trim(),
          grade,
          subject,
          board,
          syllabus_source: 'cbse',
        })
      }
      notify.success(editingClass ? 'Class updated' : 'Class created')
      resetForm()
    } catch (err) {
      notify.error('Failed to save class')
      setFormError('Failed to save class')
      console.error(err)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (cls: TeacherClass) => {
    if (!confirm(`Delete "${cls.name}"? This cannot be undone.`)) return

    try {
      await deleteClass(cls.id)
      notify.success('Class deleted')
    } catch (err) {
      notify.error('Failed to delete class')
      console.error('Failed to delete class:', err)
    }
  }

  // Subject icon colors for visual distinction
  const subjectColor = (sub: string) => {
    const colors: Record<string, string> = {
      Maths: 'from-blue-500/10 to-blue-500/5 text-blue-600 border-blue-200/50',
      English: 'from-amber-500/10 to-orange-500/5 text-amber-600 border-amber-200/50',
      EVS: 'from-emerald-500/10 to-green-500/5 text-emerald-600 border-emerald-200/50',
      Hindi: 'from-rose-500/10 to-pink-500/5 text-rose-600 border-rose-200/50',
      Science: 'from-violet-500/10 to-purple-500/5 text-violet-600 border-violet-200/50',
      Computer: 'from-cyan-500/10 to-sky-500/5 text-cyan-600 border-cyan-200/50',
    }
    return colors[sub] || 'from-primary/10 to-accent/10 text-primary border-primary/20'
  }

  const subjectInitial = (sub: string) => {
    const initials: Record<string, string> = {
      Maths: 'M', English: 'En', EVS: 'Ev', Hindi: 'Hi', Science: 'Sc', Computer: 'Co',
    }
    return initials[sub] || sub[0]
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-12 pb-24 space-y-12">
      {/* Header */}
      <PageHeader className="animate-in fade-in slide-in-from-top-4 duration-500">
        <PageHeader.Title className="text-pretty">Your Classes</PageHeader.Title>
        <PageHeader.Subtitle className="text-pretty max-w-2xl">
          Organize your classes to create worksheets aligned to their grade and subject.
        </PageHeader.Subtitle>
      </PageHeader>

      {error && (
        <div role="alert" className="mb-6 p-4 bg-destructive/10 border border-destructive/20 text-destructive rounded-xl flex items-center gap-3 animate-in fade-in slide-in-from-top-2">
          <svg className="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <span className="text-sm font-medium">{error}</span>
        </div>
      )}

      {/* Add/Edit Form */}
      {showForm && (
        <Section className="animate-in fade-in slide-in-from-top-4 duration-500">
          <Section.Header>
            <Section.Title>{editingClass ? 'Update Class' : 'Add a Class'}</Section.Title>
            <p className="text-sm text-muted-foreground mt-1.5">
              {editingClass
                ? `Update details for ${editingClass.name}.`
                : 'Set up grade, subject, and board for your class.'}
            </p>
          </Section.Header>
          <Section.Content className="pt-8">
            <form onSubmit={handleSubmit} className="space-y-6 bg-card/40 p-6 md:p-8 rounded-2xl border border-border/40">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-2">
                  <Label htmlFor="className" className="text-sm font-bold text-foreground/80">Class Name *</Label>
                  <Input
                    id="className"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. Grade 3-A"
                    className="h-11 bg-background border-border/60 focus:ring-primary/20 rounded-xl"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="grade" className="text-sm font-bold text-foreground/80">Grade *</Label>
                  <Select value={grade} onValueChange={setGrade}>
                    <SelectTrigger id="grade" className="h-11 bg-background border-border/60 rounded-xl">
                      <SelectValue placeholder="Select grade" />
                    </SelectTrigger>
                    <SelectContent className="rounded-xl">
                      {GRADES.map((g) => (
                        <SelectItem key={g} value={g}>{g}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="subject" className="text-sm font-bold text-foreground/80">Subject *</Label>
                  <Select value={subject} onValueChange={setSubject}>
                    <SelectTrigger id="subject" className="h-11 bg-background border-border/60 rounded-xl">
                      <SelectValue placeholder="Select subject" />
                    </SelectTrigger>
                    <SelectContent className="rounded-xl">
                      {curriculumSubjects.length > 0
                        ? curriculumSubjects.map((s) => (
                          <SelectItem key={s.name} value={s.name}>{s.name}</SelectItem>
                        ))
                        : FALLBACK_SUBJECTS.map((s) => (
                          <SelectItem key={s} value={s}>{s}</SelectItem>
                        ))
                      }
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="board" className="text-sm font-bold text-foreground/80">Board</Label>
                  <Select value={board} onValueChange={setBoard}>
                    <SelectTrigger id="board" className="h-11 bg-background border-border/60 rounded-xl">
                      <SelectValue placeholder="Select board" />
                    </SelectTrigger>
                    <SelectContent className="rounded-xl">
                      {BOARDS.map((b) => (
                        <SelectItem key={b} value={b}>{b}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {formError && (
                <div role="alert" className="p-4 bg-destructive/10 border border-destructive/20 text-destructive rounded-xl text-sm flex items-center gap-3">
                  <svg className="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                  <span className="font-medium">{formError}</span>
                </div>
              )}

              <div className="flex gap-3 pt-4 border-t border-border/40">
                <Button type="submit" disabled={saving} className="bg-primary text-primary-foreground shadow-lg px-8 py-4 rounded-xl font-bold h-auto hover:shadow-primary/20 transition-all">
                  {saving ? (
                    <>
                      <span className="spinner !w-4 !h-4 !border-primary-foreground/30 !border-t-primary-foreground mr-2" />
                      Saving...
                    </>
                  ) : (
                    <>
                      <svg className="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                      {editingClass ? 'Save Changes' : 'Create Class'}
                    </>
                  )}
                </Button>
                <Button type="button" variant="ghost" onClick={resetForm} className="px-8 py-4 rounded-xl font-bold h-auto text-muted-foreground hover:bg-secondary/50">
                  Cancel
                </Button>
              </div>
            </form>
          </Section.Content>
        </Section>
      )}

      {/* Classes List */}
      <Section className="animate-in fade-in slide-in-from-bottom-4 duration-700">
        <Section.Header className="flex items-center justify-between border-none pb-0 mb-8">
          <Section.Title as="h2" className="text-2xl font-bold font-jakarta">Your Classes</Section.Title>
          {!showForm && (
            <Button onClick={openAddForm} className="bg-primary hover:shadow-lg hover:shadow-primary/20 rounded-xl px-6 font-bold h-11 transition-all">
              <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
              </svg>
              New Class
            </Button>
          )}
        </Section.Header>
        <Section.Content>
          {loading ? (
            <div className="grid gap-4">
              {[1, 2, 3].map(i => <Skeleton key={i} className="h-32 w-full rounded-2xl" />)}
            </div>
          ) : classes.length === 0 ? (
            <div className="pt-4">
              <EmptyState
                icon={
                  <svg className="w-full h-full" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 21v-8.25M15.75 21v-8.25M8.25 21v-8.25M3 9l9-6 9 6m-1.5 12V10.332A48.36 48.36 0 0012 9.75c-2.551 0-5.056.2-7.5.582V21M3 21h18M12 6.75h.008v.008H12V6.75z" />
                  </svg>
                }
                title="No classes yet"
                description="Add a class to start creating worksheets for your students."
                action={
                  <Button onClick={openAddForm} className="bg-primary hover:shadow-lg hover:shadow-primary/20 rounded-xl px-8 py-4 h-auto font-bold transition-all">
                    Add your first class
                  </Button>
                }
              />
            </div>
          ) : (
            <div className="grid gap-5 animate-in fade-in slide-in-from-bottom-6 duration-700">
              {classes.map((cls, index) => (
                <Card key={cls.id} className="group card-hover border-border/50 bg-card/40 hover:bg-card overflow-hidden rounded-2xl transition-all duration-300" style={{ animationDelay: `${index * 0.1}s` }}>
                  <CardContent className="p-6">
                    <div className="flex flex-col sm:flex-row justify-between items-start gap-6">
                      <div className="flex gap-6 items-start">
                        {/* Subject-colored avatar */}
                        <div className={`w-16 h-16 rounded-2xl bg-gradient-to-br ${subjectColor(cls.subject)} flex items-center justify-center shrink-0 border group-hover:scale-105 transition-transform duration-300`}>
                          <span className="text-xl font-bold font-jakarta">
                            {subjectInitial(cls.subject)}
                          </span>
                        </div>
                        <div className="space-y-2">
                          <h3 className="font-bold text-xl text-foreground font-jakarta leading-tight group-hover:text-primary transition-colors">{cls.name}</h3>
                          <div className="flex flex-wrap items-center gap-3">
                            <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-secondary/50 rounded-lg text-[10px] font-bold uppercase tracking-widest text-foreground/70 border border-border/40">
                              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                              </svg>
                              {cls.grade}
                            </span>
                            <span className="w-1.5 h-1.5 rounded-full bg-border" />
                            <span className="text-[10px] font-bold uppercase tracking-widest text-primary/70">{cls.subject}</span>
                          </div>
                          <div className="flex items-center gap-2 pt-1">
                            <Badge variant="outline" className="text-[9px] font-bold uppercase tracking-tighter px-2 py-0 border-border/60">
                              {cls.board}
                            </Badge>
                            <Badge variant="outline" className="text-[9px] font-bold uppercase tracking-tighter px-2 py-0 border-border/60 bg-secondary/20">
                              {cls.syllabus_source === 'cbse' ? 'CBSE Standard' : 'Custom Mapping'}
                            </Badge>
                          </div>
                        </div>
                      </div>

                      <div className="flex gap-2 self-stretch sm:self-auto opacity-0 group-hover:opacity-100 transition-opacity">
                        {onNavigate && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => onNavigate('generator')}
                            className="rounded-xl text-xs font-semibold h-11 px-4"
                          >
                            Generate worksheet &rarr;
                          </Button>
                        )}
                        <Button
                          size="sm"
                          variant="ghost"
                          aria-label={`Edit ${cls.name}`}
                          onClick={() => openEditForm(cls)}
                          className="w-11 h-11 p-0 rounded-xl hover:bg-primary/5 hover:text-primary transition-colors border border-transparent hover:border-primary/10"
                        >
                          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                          </svg>
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          aria-label={`Delete ${cls.name}`}
                          onClick={() => handleDelete(cls)}
                          className="w-11 h-11 p-0 rounded-xl hover:bg-destructive/5 hover:text-destructive transition-colors border border-transparent hover:border-destructive/10"
                        >
                          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </Section.Content>
      </Section>
    </div>
  )
}
