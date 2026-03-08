const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

export async function askLlm(question, k = 5) {
  const response = await fetch(`${API_BASE}/api/llm/ask`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ question, k }),
  })

  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = typeof data?.detail === 'string' ? data.detail : 'Request failed.'
    throw new Error(detail)
  }
  return data
}
