import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

async function askLlmWithUpload(question, file, k = 5) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('question', question)
  formData.append('k', String(k))

  const response = await axios.post(`${API_BASE}/api/llm/ask/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return response.data
}

export async function askLlm(question, k = 5, attachments = []) {
  try {
    if (attachments.length && attachments[0]?.file) {
      return await askLlmWithUpload(question, attachments[0].file, k)
    }
    const response = await axios.post(`${API_BASE}/api/llm/ask`, { question, k })
    return response.data
  } catch (error) {
    if (axios.isAxiosError(error)) {
      const detail =
        typeof error.response?.data?.detail === 'string' ? error.response.data.detail : error.message
      throw new Error(detail || 'Request failed.')
    }
    throw new Error('Request failed.')
  }
}
