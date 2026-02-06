import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { useChildren, type Child } from '@/lib/children'

const GRADES = ['Class 1', 'Class 2', 'Class 3', 'Class 4', 'Class 5']
const BOARDS = ['CBSE', 'ICSE', 'State Board']

export default function ChildProfiles() {
  const { children, loading, error, createChild, updateChild, deleteChild } = useChildren()
  const [showForm, setShowForm] = useState(false)
  const [editingChild, setEditingChild] = useState<Child | null>(null)
  const [formError, setFormError] = useState('')
  const [saving, setSaving] = useState(false)

  // Form state
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
      <div className="min-h-screen bg-gray-50 py-8 px-4">
        <div className="max-w-4xl mx-auto text-center">
          <p className="text-gray-600">Loading...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 py-8 px-4">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold text-center mb-2">Child Profiles</h1>
        <p className="text-center text-gray-600 mb-8">
          Manage your children's profiles for personalized worksheets
        </p>

        {error && (
          <div className="mb-4 p-3 bg-red-50 text-red-700 rounded-md">
            {error}
          </div>
        )}

        {/* Add/Edit Form */}
        {showForm && (
          <Card className="mb-8">
            <CardHeader>
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
                    <Label htmlFor="name">Name *</Label>
                    <Input
                      id="name"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="Child's name"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="grade">Grade *</Label>
                    <Select value={grade} onValueChange={setGrade}>
                      <SelectTrigger id="grade">
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
                    <Label htmlFor="board">Board</Label>
                    <Select value={board} onValueChange={setBoard}>
                      <SelectTrigger id="board">
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
                    <Label htmlFor="notes">Notes</Label>
                    <Textarea
                      id="notes"
                      value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                      placeholder="Any notes about your child's learning preferences..."
                    />
                  </div>
                </div>

                {formError && (
                  <div className="p-3 bg-red-50 text-red-700 rounded-md">
                    {formError}
                  </div>
                )}

                <div className="flex gap-2">
                  <Button type="submit" disabled={saving}>
                    {saving ? 'Saving...' : editingChild ? 'Update' : 'Add Child'}
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
          <div className="mb-6">
            <Button onClick={openAddForm}>Add Child</Button>
          </div>
        )}

        {/* Children List */}
        {children.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <p className="text-gray-600 mb-4">No child profiles yet.</p>
              <p className="text-sm text-gray-500">
                Add a child profile to generate worksheets tailored to their grade level.
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-4">
            {children.map((child) => (
              <Card key={child.id} className="hover:shadow-md transition-shadow">
                <CardContent className="py-4">
                  <div className="flex justify-between items-start">
                    <div className="flex-1">
                      <h3 className="font-semibold text-lg">{child.name}</h3>
                      <p className="text-sm text-gray-600 mt-1">
                        {child.grade}
                        {child.board && ` • ${child.board}`}
                      </p>
                      {child.notes && (
                        <p className="text-sm text-gray-500 mt-2">{child.notes}</p>
                      )}
                    </div>
                    <div className="flex gap-2">
                      <Button size="sm" variant="outline" onClick={() => openEditForm(child)}>
                        Edit
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleDelete(child)}
                      >
                        Delete
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
