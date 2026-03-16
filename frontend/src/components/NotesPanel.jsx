import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { createNote, deleteNote, listNotes, updateNote } from './notes/notes-api'

const EMPTY_FORM = { title: '', content: '' }

function NotesPanel({ refreshSignal = 0 }) {
  const [notes, setNotes] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [form, setForm] = useState(EMPTY_FORM)
  const [isSaving, setIsSaving] = useState(false)
  const [editingId, setEditingId] = useState('')
  const [editDraft, setEditDraft] = useState(EMPTY_FORM)
  const [deleteConfirmId, setDeleteConfirmId] = useState('')
  const [query, setQuery] = useState('')
  const isMountedRef = useRef(true)

  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
    }
  }, [])

  const loadNotes = useCallback(
    async ({ showLoading = false } = {}) => {
      if (showLoading) setIsLoading(true)
      else setIsRefreshing(true)
      setError('')
      try {
        const data = await listNotes()
        if (isMountedRef.current) setNotes(Array.isArray(data) ? data : [])
      } catch (loadError) {
        if (isMountedRef.current) {
          setError(loadError instanceof Error ? loadError.message : 'Failed to load notes.')
        }
      } finally {
        if (isMountedRef.current) {
          setIsLoading(false)
          setIsRefreshing(false)
        }
      }
    },
    [],
  )

  useEffect(() => {
    loadNotes({ showLoading: true })
  }, [loadNotes])

  useEffect(() => {
    if (!refreshSignal) return
    loadNotes()
  }, [refreshSignal, loadNotes])

  useEffect(() => {
    const interval = setInterval(() => {
      loadNotes()
    }, 8000)
    return () => clearInterval(interval)
  }, [loadNotes])

  useEffect(() => {
    const handleFocus = () => loadNotes()
    if (typeof window === 'undefined') return
    window.addEventListener('focus', handleFocus)
    return () => window.removeEventListener('focus', handleFocus)
  }, [loadNotes])

  useEffect(() => {
    if (editingId && !notes.some((note) => note.id === editingId)) {
      setEditingId('')
      setEditDraft(EMPTY_FORM)
    }
    if (deleteConfirmId && !notes.some((note) => note.id === deleteConfirmId)) {
      setDeleteConfirmId('')
    }
  }, [notes, editingId, deleteConfirmId])

  const sortedNotes = useMemo(() => {
    return [...notes].sort((a, b) => {
      const aTime = a?.created_at ? new Date(a.created_at).getTime() : 0
      const bTime = b?.created_at ? new Date(b.created_at).getTime() : 0
      return bTime - aTime
    })
  }, [notes])

  const filteredNotes = useMemo(() => {
    const trimmed = query.trim().toLowerCase()
    if (!trimmed) return sortedNotes
    return sortedNotes.filter((note) => {
      const title = String(note.title ?? '').toLowerCase()
      const content = String(note.content ?? '').toLowerCase()
      return title.includes(trimmed) || content.includes(trimmed)
    })
  }, [query, sortedNotes])

  const handleAddNote = async (event) => {
    event.preventDefault()
    const title = form.title.trim()
    const content = form.content.trim()
    if (!title || !content || isSaving) return
    setIsSaving(true)
    setError('')
    try {
      const created = await createNote({ title, content })
      setNotes((prev) => [created, ...prev])
      setForm(EMPTY_FORM)
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Failed to save note.')
    } finally {
      setIsSaving(false)
    }
  }

  const startEdit = (note) => {
    setEditingId(note.id)
    setEditDraft({ title: note.title ?? '', content: note.content ?? '' })
  }

  const cancelEdit = () => {
    setEditingId('')
    setEditDraft(EMPTY_FORM)
  }

  const handleUpdate = async (noteId) => {
    const title = editDraft.title.trim()
    const content = editDraft.content.trim()
    if (!title || !content || isSaving) return
    setIsSaving(true)
    setError('')
    try {
      const updated = await updateNote(noteId, { title, content })
      setNotes((prev) => prev.map((note) => (note.id === noteId ? updated : note)))
      cancelEdit()
    } catch (updateError) {
      setError(updateError instanceof Error ? updateError.message : 'Failed to update note.')
    } finally {
      setIsSaving(false)
    }
  }

  const handleDelete = async (noteId) => {
    if (isSaving) return
    setIsSaving(true)
    setError('')
    try {
      await deleteNote(noteId)
      setNotes((prev) => prev.filter((note) => note.id !== noteId))
      if (editingId === noteId) cancelEdit()
      if (deleteConfirmId === noteId) setDeleteConfirmId('')
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : 'Failed to delete note.')
    } finally {
      setIsSaving(false)
    }
  }

  const renderDate = (value) => {
    if (!value) return ''
    const parsed = new Date(value)
    if (Number.isNaN(parsed.getTime())) return ''
    return parsed.toLocaleString()
  }

  return (
    <section className="flex h-full flex-col gap-4 rounded-3xl border border-slate-200 bg-slate-50/60 p-4 shadow-sm">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-400">Notes</p>
        <h2 className="mt-2 text-lg font-semibold text-slate-900">Notes</h2>
        <p className="mt-1 text-xs text-slate-500">Add, edit, and track your notes here.</p>
      </div>

      <form className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-3" onSubmit={handleAddNote}>
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold text-slate-900">Add note</p>
          <button
            className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600 transition hover:border-slate-300 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-60"
            type="submit"
            disabled={isSaving || !form.title.trim() || !form.content.trim()}
          >
            {isSaving ? 'Saving...' : 'Add'}
          </button>
        </div>
        <input
          className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-200"
          placeholder="Title"
          value={form.title}
          onChange={(event) => setForm((prev) => ({ ...prev, title: event.target.value }))}
        />
        <textarea
          className="min-h-[90px] w-full resize-none rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-200"
          placeholder="Write the note content..."
          value={form.content}
          onChange={(event) => setForm((prev) => ({ ...prev, content: event.target.value }))}
        />
      </form>

      {error ? <p className="text-xs text-rose-600">{error}</p> : null}

      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden">
        <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
          <span>All notes</span>
          <span>{filteredNotes.length}</span>
        </div>
        <div className="flex items-center gap-2">
          <input
            className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700 outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-200"
            placeholder="Search notes..."
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          {isRefreshing ? (
            <span className="text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-400">
              Syncing
            </span>
          ) : null}
        </div>
        <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pr-1">
          {isLoading ? (
            <div className="rounded-2xl border border-dashed border-slate-200 bg-white/70 p-4 text-sm text-slate-500">
              Loading notes...
            </div>
          ) : null}
          {!isLoading && filteredNotes.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-200 bg-white/70 p-4 text-sm text-slate-500">
              {query.trim() ? 'No matching notes. Try another search.' : 'No notes yet. Add one above.'}
            </div>
          ) : null}
          {filteredNotes.map((note) => {
            const isEditing = editingId === note.id
            const updatedLabel = renderDate(note.updated_at ?? note.created_at)
            return (
              <article
                key={note.id}
                className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm"
              >
                {isEditing ? (
                  <div className="flex flex-col gap-2">
                    <input
                      className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-200"
                      value={editDraft.title}
                      onChange={(event) =>
                        setEditDraft((prev) => ({ ...prev, title: event.target.value }))
                      }
                    />
                    <textarea
                      className="min-h-[80px] w-full resize-none rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-200"
                      value={editDraft.content}
                      onChange={(event) =>
                        setEditDraft((prev) => ({ ...prev, content: event.target.value }))
                      }
                    />
                    <div className="flex flex-wrap gap-2">
                      <button
                        className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600 transition hover:border-slate-300 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-60"
                        type="button"
                        onClick={() => handleUpdate(note.id)}
                        disabled={isSaving || !editDraft.title.trim() || !editDraft.content.trim()}
                      >
                        {isSaving ? 'Saving...' : 'Save'}
                      </button>
                      <button
                        className="rounded-full border border-transparent px-3 py-1 text-xs font-semibold text-slate-500 transition hover:text-slate-900"
                        type="button"
                        onClick={cancelEdit}
                        disabled={isSaving}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-col gap-2">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <h3 className="text-sm font-semibold text-slate-900">{note.title}</h3>
                        {updatedLabel ? (
                          <p className="text-xs text-slate-400">Last updated {updatedLabel}</p>
                        ) : null}
                      </div>
                      <div className="flex gap-2">
                        <button
                          className="text-xs font-semibold text-slate-500 transition hover:text-slate-900"
                          type="button"
                          onClick={() => startEdit(note)}
                          disabled={isSaving}
                        >
                          Edit
                        </button>
                        {deleteConfirmId === note.id ? (
                          <div className="flex items-center gap-2">
                            <button
                              className="text-xs font-semibold text-rose-600 transition hover:text-rose-700"
                              type="button"
                              onClick={() => handleDelete(note.id)}
                              disabled={isSaving}
                            >
                              Confirm
                            </button>
                            <button
                              className="text-xs font-semibold text-slate-500 transition hover:text-slate-900"
                              type="button"
                              onClick={() => setDeleteConfirmId('')}
                              disabled={isSaving}
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <button
                            className="text-xs font-semibold text-rose-600 transition hover:text-rose-700"
                            type="button"
                            onClick={() => setDeleteConfirmId(note.id)}
                            disabled={isSaving}
                          >
                            Delete
                          </button>
                        )}
                      </div>
                    </div>
                    <p className="max-h-32 overflow-y-auto whitespace-pre-wrap text-sm text-slate-600">
                      {note.content}
                    </p>
                  </div>
                )}
              </article>
            )
          })}
        </div>
      </div>
    </section>
  )
}

export { NotesPanel }
