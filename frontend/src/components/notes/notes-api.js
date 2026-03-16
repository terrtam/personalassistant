import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

function resolveError(error) {
  if (axios.isAxiosError(error)) {
    const detail =
      typeof error.response?.data?.detail === 'string' ? error.response.data.detail : error.message
    return detail || 'Request failed.'
  }
  return 'Request failed.'
}

export async function listNotes() {
  try {
    const response = await axios.get(`${API_BASE}/api/notes`)
    return response.data
  } catch (error) {
    throw new Error(resolveError(error))
  }
}

export async function createNote(payload) {
  try {
    const response = await axios.post(`${API_BASE}/api/notes`, payload)
    return response.data
  } catch (error) {
    throw new Error(resolveError(error))
  }
}

export async function updateNote(noteId, payload) {
  try {
    const response = await axios.put(`${API_BASE}/api/notes/${noteId}`, payload)
    return response.data
  } catch (error) {
    throw new Error(resolveError(error))
  }
}

export async function deleteNote(noteId) {
  try {
    const response = await axios.delete(`${API_BASE}/api/notes/${noteId}?confirm=true`)
    return response.data
  } catch (error) {
    throw new Error(resolveError(error))
  }
}
