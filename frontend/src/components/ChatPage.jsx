import { useEffect, useRef, useState } from 'react'

import { askLlm } from './chat/chat-api'
import { ChatInput } from './ChatInput'
import { ChatMessage } from './ChatMessage'
import { NotesPanel } from './NotesPanel'
import { ScrollArea } from './ui/scroll-area'
import { Separator } from './ui/separator'

const INITIAL_MESSAGES = [
  {
    id: 'assistant-welcome',
    role: 'assistant',
    content: 'Hi! I can help schedule meetings, summarize notes, and keep your day organized.',
  },
]

function ChatPage() {
  const [messages, setMessages] = useState(INITIAL_MESSAGES)
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [attachments, setAttachments] = useState([])
  const [notesRefreshTick, setNotesRefreshTick] = useState(0)
  const endRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, isLoading])

  const handleSend = async (text, files = []) => {
    const trimmed = text.trim()
    const safeFiles = Array.isArray(files) ? files : []
    if ((!trimmed && safeFiles.length === 0) || isLoading) return

    const userMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: trimmed || 'Sent with attachments.',
      attachments: safeFiles,
    }

    setMessages((prev) => [...prev, userMessage])
    setInput('')
    const outgoingAttachments = [...safeFiles]
    setAttachments([])
    setIsLoading(true)

    try {
      const response = await askLlm(trimmed || 'Sent with attachments.', 5, outgoingAttachments)
      const assistantMessage = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: String(response?.answer ?? 'No response was returned.'),
      }
      setMessages((prev) => [...prev, assistantMessage])
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : 'Something went wrong while contacting the assistant.'
      setMessages((prev) => [
        ...prev,
        { id: `assistant-${Date.now()}`, role: 'assistant', content: `Unable to reach the API. ${errorMessage}` },
      ])
    } finally {
      setIsLoading(false)
      setNotesRefreshTick((prev) => prev + 1)
    }
  }

  return (
    <div className="min-h-screen bg-white text-slate-900">
      <div className="mx-auto flex min-h-screen w-full max-w-7xl flex-col">
        <header className="px-4 pt-6 pb-4">
          <p className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-400">
            AI Personal Assistant
          </p>
          <h1 className="mt-2 text-2xl font-semibold text-slate-900">AI Personal Assistant</h1>
          <p className="mt-1 text-sm text-slate-500">
            A clean, focused space to plan meetings and capture tasks.
          </p>
        </header>

        <Separator />

        <main className="flex min-h-0 flex-1 flex-col gap-6 px-4 py-6 lg:flex-row">
          <section className="flex min-h-0 flex-1 flex-col">
            <div className="flex min-h-0 flex-1 flex-col">
              <ScrollArea className="flex-1">
                <div className="space-y-4 pr-4 scroll-smooth">
                  {messages.map((message) => (
                    <ChatMessage
                      key={message.id}
                      role={message.role}
                      content={message.content}
                      attachments={message.attachments}
                    />
                  ))}
                  {isLoading ? <ChatMessage role="assistant" content="Thinking..." /> : null}
                  <div ref={endRef} />
                </div>
              </ScrollArea>
            </div>
            <div className="mt-6 border-t border-slate-200 bg-white pt-4">
              <ChatInput
                attachments={attachments}
                isLoading={isLoading}
                onAttachmentsChange={setAttachments}
                onChange={setInput}
                onSend={handleSend}
                value={input}
              />
            </div>
          </section>

          <aside className="w-full lg:w-[460px] xl:w-[520px]">
            <NotesPanel refreshSignal={notesRefreshTick} />
          </aside>
        </main>
      </div>
    </div>
  )
}

export { ChatPage }
