import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { useChildren, type Child } from '@/lib/children'
import { useSubscription } from '@/lib/subscription'

const GRADES = ['Class 1', 'Class 2', 'Class 3', 'Class 4', 'Class 5']
const BOARDS = ['CBSE', 'ICSE', 'State Board']

export default function ChildProfiles() {
  const { children, loading, error, createChild, updateChild, deleteChild } = useChildren()
  const { status: subscription, upgrade } = useSubscription()

  const canAddChild = subscription?.can_use_multi_child || children.length === 0
  const [showForm, setShowForm] = useState(false)
  const [editingChild, setEditingChild] = useState<Child | null>(null)
  const [formError, setFormError] = useState('')
  const [saving, setSaving] = useState(false)

  const [name, setName] = useState('')
  const [grade, setGrade] = useState('')
  const [board, setBoard] = useState('')
  const [notes, setNotes] = useState('')

  const resetForm = () => {
    setName('')
    setGrade('')
    setBoard('')
    setNotes('')
    setEditingChild(null)
    setShowForm(false)
    setFormError('')
  }

  const openAddForm = () => {
    resetForm()
    setShowForm(true)
  }

  const openEditForm = (child: Child) => {
    setName(child.name)
    setGrade(child.grade)
    setBoard(child.board || '')
    setNotes(child.notes || '')
    setEditingChild(child)
    setShowForm(true)
    setFormError('')
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!name.trim() || !grade) {
      setFormError('Name and grade are required')
      return
    }

    setSaving(true)
    setFormError('')

    try {
      if (editingChild) {
        await updateChild(editingChild.id, {
          name: name.trim(),
          grade,
          board: board || undefined,
          notes: notes.trim() || undefined,
        })
      } else {
        await createChild({
          name: name.trim(),
          grade,
          board: board || undefined,
          notes: notes.trim() || undefined,
        })
      }
      resetForm()
    } catch (err) {
      setFormError('Failed to save child profile')
      console.error(err)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (child: Child) => {
    if (!confirm(`Are you sure you want to delete ${child.name}'s profile? Worksheets will be preserved.`)) {
      return
    }

    try {
      await deleteChild(child.id)
    } catch (err) {
      console.error('Failed to delete child:', err)
    }
  }

  if (loading) {
    return (
      <div className="py-8 px-4">
        <div className="max-w-4xl mx-auto flex flex-col items-center justify-center py-16">
          <div className="spinner mb-4" />
          <p className="text-muted-foreground">Loading profiles...</p>
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
          <h1 className="text-3xl md:text-4xl mb-3">Child Profiles</h1>
          <p className="text-muted-foreground text-lg">
            Manage your children's profiles for personalized learning
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
              <CardTitle>{editingChild ? 'Edit Child' : 'Add Child'}</CardTitle>
              <CardDescription>
                {editingChild
                  ? 'Update your child\'s profile details'
                  : 'Create a profile for your child'}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="name" className="text-sm font-medium">Name *</Label>
                    <Input
                      id="name"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="Child's name"
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
                    <Label htmlFor="board" className="text-sm font-medium">Board</Label>
                    <Select value={board} onValueChange={setBoard}>
                      <SelectTrigger id="board" className="bg-background/50">
                        <SelectValue placeholder="Select board (optional)" />
                      </SelectTrigger>
                      <SelectContent>
                        {BOARDS.map((b) => (
                          <SelectItem key={b} value={b}>{b}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="notes" className="text-sm font-medium">Notes</Label>
                    <Textarea
                      id="notes"
                      value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                      placeholder="Any notes about your child's learning preferences..."
                      className="bg-background/50"
                    />
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
                        {editingChild ? 'Update' : 'Add Child'}
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
            {canAddChild ? (
              <Button onClick={openAddForm} className="btn-animate">
                <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
                </svg>
                Add Child
              </Button>
            ) : (
              <div className="flex items-center gap-4 p-4 bg-secondary/50 border border-border rounded-xl">
                <Button disabled className="opacity-50">
                  <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
                  </svg>
                  Add Child
                </Button>
                <span className="text-sm text-muted-foreground">
                  Multiple children is a Pro feature.{' '}
                  <button onClick={() => upgrade()} className="text-primary hover:text-primary/80 font-medium transition-colors">
                    Upgrade
                  </button>
                </span>
              </div>
            )}
          </div>
        )}

        {/* Children List */}
        {children.length === 0 ? (
          <Card className="paper-texture animate-fade-in">
            <CardContent className="py-16 text-center">
              <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-secondary/50 flex items-center justify-center">
                <svg className="w-8 h-8 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
                </svg>
              </div>
              <p className="text-foreground font-medium mb-2">No child profiles yet</p>
              <p className="text-sm text-muted-foreground">
                Add a profile to generate worksheets tailored to their grade level
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-4 animate-fade-in">
            {children.map((child, index) => (
              <Card key={child.id} className="card-hover border-border/50" style={{ animationDelay: `${index * 0.05}s` }}>
                <CardContent className="py-5">
                  <div className="flex justify-between items-start">
                    <div className="flex gap-4">
                      <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-primary/20 to-accent/20 flex items-center justify-center flex-shrink-0">
                        <span className="text-lg font-semibold text-primary">
                          {child.name[0].toUpperCase()}
                        </span>
                      </div>
                      <div className="flex-1">
                        <h3 className="font-semibold text-lg text-foreground">{child.name}</h3>
                        <p className="text-sm text-muted-foreground mt-0.5 flex items-center gap-2">
                          <span className="flex items-center gap-1">
                            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                            </svg>
                            {child.grade}
                          </span>
                          {child.board && (
                            <>
                              <span className="w-1 h-1 rounded-full bg-border" />
                              <span>{child.board}</span>
                            </>
                          )}
                        </p>
                        {child.notes && (
                          <p className="text-sm text-muted-foreground mt-2 italic">"{child.notes}"</p>
                        )}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Button size="sm" variant="outline" onClick={() => openEditForm(child)}>
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                        </svg>
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleDelete(child)}
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
