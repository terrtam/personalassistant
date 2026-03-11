import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

export async function askLlm(question, k = 5) {
  try {
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
