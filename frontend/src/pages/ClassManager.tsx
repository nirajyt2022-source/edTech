import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { useClasses, type TeacherClass } from '@/lib/classes'

const GRADES = ['Class 1', 'Class 2', 'Class 3', 'Class 4', 'Class 5']
const SUBJECTS = ['Maths', 'English', 'EVS', 'Hindi', 'Science', 'Computer']
const BOARDS = ['CBSE', 'ICSE', 'State Board']

export default function ClassManager() {
  const { classes, loading, error, createClass, updateClass, deleteClass } = useClasses()

  const [showForm, setShowForm] = useState(false)
  const [editingClass, setEditingClass] = useState<TeacherClass | null>(null)
  const [formError, setFormError] = useState('')
  const [saving, setSaving] = useState(false)

  const [name, setName] = useState('')
  const [grade, setGrade] = useState('')
  const [subject, setSubject] = useState('')
  const [board, setBoard] = useState('CBSE')

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
      resetForm()
    } catch (err) {
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
    } catch (err) {
      console.error('Failed to delete class:', err)
    }
  }

  // Subject icon colors for visual distinction
  const subjectColor = (sub: string) => {
    const colors: Record<string, string> = {
      Maths: 'from-blue-500/20 to-indigo-500/20 text-blue-700',
      English: 'from-amber-500/20 to-orange-500/20 text-amber-700',
      EVS: 'from-emerald-500/20 to-green-500/20 text-emerald-700',
      Hindi: 'from-rose-500/20 to-pink-500/20 text-rose-700',
      Science: 'from-violet-500/20 to-purple-500/20 text-violet-700',
      Computer: 'from-cyan-500/20 to-sky-500/20 text-cyan-700',
    }
    return colors[sub] || 'from-primary/20 to-accent/20 text-primary'
  }

  const subjectInitial = (sub: string) => {
    const initials: Record<string, string> = {
      Maths: 'M', English: 'En', EVS: 'Ev', Hindi: 'Hi', Science: 'Sc', Computer: 'Co',
    }
    return initials[sub] || sub[0]
  }

  if (loading) {
    return (
      <div className="py-8 px-4">
        <div className="max-w-4xl mx-auto flex flex-col items-center justify-center py-16">
          <div className="spinner mb-4" />
          <p className="text-muted-foreground">Loading classes...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="py-8 px-4">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="text-center mb-8 animate-fade-in">
          <div className="decorative-dots mb-4" />
          <h1 className="text-3xl md:text-4xl mb-3">My Classes</h1>
          <p className="text-muted-foreground text-lg">
            Organize your teaching by class, grade, and subject
          </p>
        </div>

        {error && (
          <div className="mb-6 p-4 bg-destructive/10 border border-destructive/20 text-destructive rounded-lg flex items-center gap-3 animate-fade-in">
            <svg className="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            {error}
          </div>
        )}

        {/* Add/Edit Form */}
        {showForm && (
          <Card className="mb-8 paper-texture animate-fade-in">
            <CardHeader>
              <div className="decorative-line mb-3" />
              <CardTitle>{editingClass ? 'Edit Class' : 'Add Class'}</CardTitle>
              <CardDescription>
                {editingClass
                  ? 'Update your class details'
                  : 'Create a new class for your teaching schedule'}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="className" className="text-sm font-medium">Class Name *</Label>
                    <Input
                      id="className"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="e.g. Class 3A, Section B"
                      className="bg-background/50"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="grade" className="text-sm font-medium">Grade *</Label>
                    <Select value={grade} onValueChange={setGrade}>
                      <SelectTrigger id="grade" className="bg-background/50">
                        <SelectValue placeholder="Select grade" />
                      </SelectTrigger>
                      <SelectContent>
                        {GRADES.map((g) => (
                          <SelectItem key={g} value={g}>{g}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="subject" className="text-sm font-medium">Subject *</Label>
                    <Select value={subject} onValueChange={setSubject}>
                      <SelectTrigger id="subject" className="bg-background/50">
                        <SelectValue placeholder="Select subject" />
                      </SelectTrigger>
                      <SelectContent>
                        {SUBJECTS.map((s) => (
                          <SelectItem key={s} value={s}>{s}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="board" className="text-sm font-medium">Board</Label>
                    <Select value={board} onValueChange={setBoard}>
                      <SelectTrigger id="board" className="bg-background/50">
                        <SelectValue placeholder="Select board" />
                      </SelectTrigger>
                      <SelectContent>
                        {BOARDS.map((b) => (
                          <SelectItem key={b} value={b}>{b}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                {formError && (
                  <div className="p-3 bg-destructive/10 border border-destructive/20 text-destructive rounded-lg text-sm flex items-center gap-2">
                    <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                    {formError}
                  </div>
                )}

                <div className="flex gap-2 pt-2">
                  <Button type="submit" disabled={saving} className="btn-animate">
                    {saving ? (
                      <span className="flex items-center gap-2">
                        <span className="spinner !w-4 !h-4 !border-primary-foreground/30 !border-t-primary-foreground" />
                        Saving...
                      </span>
                    ) : (
                      <span className="flex items-center gap-2">
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                        {editingClass ? 'Update' : 'Add Class'}
                      </span>
                    )}
                  </Button>
                  <Button type="button" variant="outline" onClick={resetForm}>
                    Cancel
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        )}

        {/* Add Button (when form is hidden) */}
        {!showForm && (
          <div className="mb-8 animate-fade-in">
            <Button onClick={openAddForm} className="btn-animate">
              <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
              </svg>
              Add Class
            </Button>
          </div>
        )}

        {/* Classes List */}
        {classes.length === 0 ? (
          <Card className="paper-texture animate-fade-in">
            <CardContent className="py-16 text-center">
              <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-secondary/50 flex items-center justify-center">
                <svg className="w-8 h-8 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4.26 10.147a60.438 60.438 0 00-.491 6.347A48.62 48.62 0 0112 20.904a48.62 48.62 0 018.232-4.41 60.46 60.46 0 00-.491-6.347m-15.482 0a50.636 50.636 0 00-2.658-.813A59.906 59.906 0 0112 3.493a59.903 59.903 0 0110.399 5.84c-.896.248-1.783.52-2.658.814m-15.482 0A50.717 50.717 0 0112 13.489a50.702 50.702 0 017.74-3.342M6.75 15a.75.75 0 100-1.5.75.75 0 000 1.5zm0 0v-3.675A55.378 55.378 0 0112 8.443m-7.007 11.55A5.981 5.981 0 006.75 15.75v-1.5" />
                </svg>
              </div>
              <p className="text-foreground font-medium mb-2">No classes yet</p>
              <p className="text-sm text-muted-foreground mb-6">
                Create your first class to start generating worksheets for your students
              </p>
              <Button onClick={openAddForm} className="btn-animate">
                <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
                </svg>
                Create First Class
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-4 animate-fade-in">
            {classes.map((cls, index) => (
              <Card key={cls.id} className="card-hover border-border/50" style={{ animationDelay: `${index * 0.05}s` }}>
                <CardContent className="py-5">
                  <div className="flex justify-between items-start">
                    <div className="flex gap-4">
                      {/* Subject-colored avatar */}
                      <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${subjectColor(cls.subject)} flex items-center justify-center flex-shrink-0`}>
                        <span className="text-sm font-bold">
                          {subjectInitial(cls.subject)}
                        </span>
                      </div>
                      <div className="flex-1 min-w-0">
                        <h3 className="font-semibold text-lg text-foreground">{cls.name}</h3>
                        <p className="text-sm text-muted-foreground mt-0.5 flex flex-wrap items-center gap-2">
                          <span className="flex items-center gap-1">
                            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                            </svg>
                            {cls.grade}
                          </span>
                          <span className="w-1 h-1 rounded-full bg-border" />
                          <span>{cls.subject}</span>
                        </p>
                        <div className="flex items-center gap-2 mt-2">
                          <Badge variant="secondary" className="text-xs">
                            {cls.board}
                          </Badge>
                          <Badge variant="outline" className="text-xs capitalize">
                            {cls.syllabus_source === 'cbse' ? 'CBSE Syllabus' : 'Custom Syllabus'}
                          </Badge>
                        </div>
                      </div>
                    </div>
                    <div className="flex gap-2 flex-shrink-0">
                      <Button size="sm" variant="outline" onClick={() => openEditForm(cls)}>
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                        </svg>
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleDelete(cls)}
                        className="text-muted-foreground hover:text-destructive hover:border-destructive"
                      >
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
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
      </div>
    </div>
  )
}
