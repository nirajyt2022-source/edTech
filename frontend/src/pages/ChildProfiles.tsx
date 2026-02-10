import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { PageHeader } from '@/components/ui/page-header'
import { Section } from '@/components/ui/section'
import { EmptyState } from '@/components/ui/empty-state'
import { Skeleton } from '@/components/ui/skeleton'
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
      <div className="max-w-4xl mx-auto px-4 py-12">
        <PageHeader className="mb-12">
          <Skeleton className="h-10 w-64 mb-4" />
          <Skeleton className="h-6 w-96" />
        </PageHeader>

        <div className="grid gap-6">
          {[1, 2].map((i) => (
            <Skeleton key={i} className="h-32 w-full rounded-2xl" />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-12 pb-24">
      {/* Header */}
      {!showForm && (
        <PageHeader className="mb-12">
          <PageHeader.Title className="text-pretty">Child Profiles</PageHeader.Title>
          <PageHeader.Subtitle className="text-pretty max-w-2xl">
            Create profiles for each child to get personalized practice material tailored to their grade level.
          </PageHeader.Subtitle>
        </PageHeader>
      )}

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
        <Section className="mb-12 animate-in fade-in slide-in-from-top-4 duration-500">
          <Section.Header>
            <Section.Title>{editingChild ? 'Update Profile' : 'New Child Profile'}</Section.Title>
            <p className="text-sm text-muted-foreground mt-1.5">
              {editingChild
                ? `Update details for ${editingChild.name}'s profile.`
                : 'Add your child\'s details to get started with tailored materials.'}
            </p>
          </Section.Header>
          <Section.Content className="pt-6">
            <form onSubmit={handleSubmit} className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-2">
                  <Label htmlFor="name" className="text-sm font-bold text-foreground/80">Full Name *</Label>
                  <Input
                    id="name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Enter child's name"
                    className="h-11 bg-background border-border/60 focus:ring-primary/20 rounded-xl"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="grade" className="text-sm font-bold text-foreground/80">Current Grade *</Label>
                  <Select value={grade} onValueChange={setGrade}>
                    <SelectTrigger id="grade" className="h-11 bg-background border-border/60 focus:ring-primary/20 rounded-xl">
                      <SelectValue placeholder="Select current grade" />
                    </SelectTrigger>
                    <SelectContent className="rounded-xl shadow-xl border-border/40">
                      {GRADES.map((g) => (
                        <SelectItem key={g} value={g}>{g}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="board" className="text-sm font-bold text-foreground/80">Educational Board</Label>
                  <Select value={board} onValueChange={setBoard}>
                    <SelectTrigger id="board" className="h-11 bg-background border-border/60 focus:ring-primary/20 rounded-xl">
                      <SelectValue placeholder="Select board (optional)" />
                    </SelectTrigger>
                    <SelectContent className="rounded-xl shadow-xl border-border/40">
                      {BOARDS.map((b) => (
                        <SelectItem key={b} value={b}>{b}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="notes" className="text-sm font-bold text-foreground/80">Additional Notes</Label>
                  <span className="text-xs text-muted-foreground ml-1">(Optional)</span>
                  <Textarea
                    id="notes"
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="E.g., Any specific topics they need help with or interest areas..."
                    className="min-h-[120px] bg-background border-border/60 focus:ring-primary/20 rounded-xl resize-none p-4"
                  />
                </div>
              </div>

              {formError && (
                <div role="alert" className="p-4 bg-destructive/10 border border-destructive/20 text-destructive rounded-xl text-sm flex items-center gap-3 animate-in shake-1">
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
                      Saving changes
                    </>
                  ) : (
                    <>
                      <svg className="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                      {editingChild ? 'Update Profile' : 'Create Profile'}
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

      {/* Profile List Section */}
      {!showForm && (
        <div className="animate-in fade-in slide-in-from-bottom-4 duration-700">
          <div className="flex items-center justify-between mb-8">
            <h2 className="text-xs font-bold text-muted-foreground/60 uppercase tracking-[0.2em] flex items-center gap-3">
              <span className="shrink-0">Active Profiles</span>
              <div className="h-px w-24 bg-border/40" />
            </h2>

            {canAddChild ? (
              <Button onClick={openAddForm} className="bg-primary/10 text-primary hover:bg-primary hover:text-primary-foreground shadow-sm rounded-xl px-4 py-2 h-auto text-xs font-bold transition-all border border-primary/20">
                <svg className="w-3.5 h-3.5 mr-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
                </svg>
                Add Child
              </Button>
            ) : (
              <div className="flex items-center gap-3 p-1.5 pl-3 bg-secondary/30 border border-border/50 rounded-xl">
                <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Multi-child is Pro</span>
                <Button onClick={() => upgrade()} variant="default" size="sm" className="h-7 px-3 text-[10px] rounded-lg shadow-sm font-bold">
                  Upgrade
                </Button>
              </div>
            )}
          </div>

          {children.length === 0 ? (
            <EmptyState
              icon={
                <svg className="w-full h-full" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
                </svg>
              }
              title="Welcome aboard!"
              description="Start by adding your child's profile to unlock personalized worksheets tailored to their academic level."
              action={
                <Button size="lg" onClick={openAddForm} className="bg-primary text-primary-foreground shadow-lg rounded-xl px-8 py-4 h-auto font-bold">
                  Add First Profile
                </Button>
              }
            />
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {children.map((child, index) => (
                <Card key={child.id} className="card-hover border-border/50 bg-card/40 overflow-hidden rounded-2xl group transition-all duration-300" style={{ animationDelay: `${index * 0.1}s` }}>
                  <CardContent className="p-6">
                    <div className="flex justify-between items-start gap-4">
                      <div className="flex gap-4">
                        <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-primary/10 to-accent/10 flex items-center justify-center flex-shrink-0 border border-primary/10 group-hover:scale-105 transition-transform">
                          <span className="text-2xl font-black text-primary font-jakarta">
                            {child.name[0].toUpperCase()}
                          </span>
                        </div>
                        <div className="flex-1 space-y-1.5">
                          <h3 className="font-bold text-xl text-foreground font-jakarta leading-tight">{child.name}</h3>
                          <div className="flex items-center gap-3">
                            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 bg-secondary/50 rounded-lg text-xs font-bold text-foreground/70 border border-border/40">
                              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                              </svg>
                              {child.grade}
                            </span>
                            {child.board && (
                              <span className="inline-flex gap-1.5 px-2 py-0.5 bg-accent/5 rounded-lg text-xs font-bold text-accent/80 border border-accent/10">
                                {child.board}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>

                      <div className="flex gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity print:hidden">
                        <Button size="sm" variant="ghost" aria-label={`Edit ${child.name}'s profile`} onClick={() => openEditForm(child)} className="w-9 h-9 p-0 rounded-xl hover:bg-primary/5 hover:text-primary transition-colors">
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                          </svg>
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          aria-label={`Delete ${child.name}'s profile`}
                          onClick={() => handleDelete(child)}
                          className="w-9 h-9 p-0 rounded-xl hover:bg-destructive/5 hover:text-destructive transition-colors"
                        >
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </Button>
                      </div>
                    </div>
                    {child.notes && (
                      <div className="mt-5 p-3 bg-secondary/20 rounded-xl border border-border/20">
                        <p className="text-xs text-muted-foreground italic line-clamp-2">"{child.notes}"</p>
                      </div>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
