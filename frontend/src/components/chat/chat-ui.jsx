import { ArrowDown, CalendarDays, Sparkles } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { cn } from '../../lib/utils'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { Card, CardContent } from '../ui/card'
import { askLlm } from './chat-api'
import { initialMessages, models, suggestions } from './chat-data'
import { MessageItem } from './message-item'
import { PromptComposer } from './prompt-composer'
import { SuggestionChips } from './suggestion-chips'

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

const STATUS_INFO = {
  ready: { label: 'Ready', className: 'bg-emerald-100 text-emerald-700' },
  submitted: { label: 'Queued', className: 'bg-amber-100 text-amber-700' },
  streaming: { label: 'Streaming', className: 'bg-blue-100 text-blue-700' },
  error: { label: 'Backend error', className: 'bg-rose-100 text-rose-700' },
}

export function ChatUi() {
  const [messages, setMessages] = useState(initialMessages)
  const [branches, setBranches] = useState({})
  const [status, setStatus] = useState('ready')
  const [text, setText] = useState('')
  const [model, setModel] = useState(models[0].id)
  const [useWeb, setUseWeb] = useState(false)
  const [useMic, setUseMic] = useState(false)
  const [micSupported, setMicSupported] = useState(true)
  const [micError, setMicError] = useState('')
  const [attachments, setAttachments] = useState([])
  const [showScrollButton, setShowScrollButton] = useState(false)

  const viewportRef = useRef(null)
  const recognitionRef = useRef(null)
  const baseTranscriptRef = useRef('')
  const capturedTranscriptRef = useRef('')
  const selectedModel = models.find((entry) => entry.id === model)

  useEffect(() => {
    return () => {
      try {
        recognitionRef.current?.stop()
      } catch {
        // no-op
      }
    }
  }, [])

  useEffect(() => {
    const viewport = viewportRef.current
    if (!viewport) return
    viewport.scrollTop = viewport.scrollHeight
  }, [messages])

  const setMessageContent = (versionId, nextContent) => {
    setMessages((prev) =>
      prev.map((entry) => ({
        ...entry,
        versions: entry.versions.map((version) =>
          version.id === versionId ? { ...version, content: nextContent } : version,
        ),
      })),
    )
  }

  const setAssistantMetadata = (messageKey, metadata) => {
    setMessages((prev) =>
      prev.map((entry) => (entry.key === messageKey ? { ...entry, ...metadata } : entry)),
    )
  }

  const streamAssistantText = async (versionId, content) => {
    const words = content.split(' ')
    let built = ''

    for (let i = 0; i < words.length; i += 1) {
      built += `${i === 0 ? '' : ' '}${words[i]}`
      setMessageContent(versionId, built)
      await sleep(Math.floor(Math.random() * 45) + 18)
    }
  }

  const runAssistantReply = async (question, attachmentsForUpload = []) => {
    const assistantKey = `assistant-${Date.now()}`
    const assistantVersionId = `${assistantKey}-v1`
    setMessages((prev) => [
      ...prev,
      { key: assistantKey, from: 'assistant', versions: [{ id: assistantVersionId, content: '' }] },
    ])

    try {
      const result = await askLlm(question, 5, attachmentsForUpload)
      const sources =
        Array.isArray(result?.sources) && result.sources.length
          ? result.sources.map((source, index) => ({
              href:
                typeof source?.metadata?.source === 'string' &&
                source.metadata.source.startsWith('http')
                  ? source.metadata.source
                  : null,
              title:
                source?.metadata?.title ??
                source?.metadata?.source ??
                `Source ${index + 1} (score ${Number(source?.score ?? 0).toFixed(3)})`,
            }))
          : undefined

      setAssistantMetadata(assistantKey, { model: result.model, sources })
      await streamAssistantText(assistantVersionId, String(result.answer ?? ''))
      setStatus('ready')
    } catch (error) {
      setStatus('error')
      setMessageContent(
        assistantVersionId,
        `I could not reach the backend endpoint. ${error instanceof Error ? error.message : 'Unknown error.'}`,
      )
    }
  }

  const sendUserMessage = async (promptText) => {
    const trimmed = promptText.trim()
    if (!trimmed) return

    const userKey = `user-${Date.now()}`
    setStatus('submitted')
    setMessages((prev) => [
      ...prev,
      { key: userKey, from: 'user', versions: [{ id: `${userKey}-v1`, content: trimmed }] },
    ])
    setText('')
    const outgoingAttachments = [...attachments]
    setAttachments([])
    setStatus('streaming')
    await runAssistantReply(trimmed, outgoingAttachments)
  }

  const onConversationScroll = () => {
    const viewport = viewportRef.current
    if (!viewport) return
    const nearBottom = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight < 48
    setShowScrollButton(!nearBottom)
  }

  const mergeTranscript = (base, spoken) => {
    if (base && spoken) return `${base} ${spoken}`.trim()
    return (base || spoken || '').trim()
  }

  const startMicCapture = () => {
    if (typeof window === 'undefined') return

    const SpeechRecognitionApi = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SpeechRecognitionApi) {
      setMicSupported(false)
      setMicError('Voice input is not supported in this browser.')
      return
    }

    setMicSupported(true)
    setMicError('')
    baseTranscriptRef.current = text.trim()
    capturedTranscriptRef.current = ''

    if (!recognitionRef.current) {
      const recognition = new SpeechRecognitionApi()
      recognition.continuous = true
      recognition.interimResults = true
      recognition.lang = 'en-US'

      recognition.onstart = () => {
        setUseMic(true)
      }

      recognition.onresult = (event) => {
        let finalChunk = ''
        let interimChunk = ''

        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          const entry = event.results[i]
          const spoken = entry[0]?.transcript?.trim() ?? ''
          if (!spoken) continue
          if (entry.isFinal) finalChunk += ` ${spoken}`
          else interimChunk += ` ${spoken}`
        }

        if (finalChunk.trim()) {
          capturedTranscriptRef.current = mergeTranscript(capturedTranscriptRef.current, finalChunk.trim())
        }

        const liveTranscript = mergeTranscript(capturedTranscriptRef.current, interimChunk.trim())
        setText(mergeTranscript(baseTranscriptRef.current, liveTranscript))
      }

      recognition.onerror = (event) => {
        if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
          setMicError('Microphone permission is blocked. Allow access and try again.')
        } else {
          setMicError(`Voice input failed: ${event.error}`)
        }
        setUseMic(false)
      }

      recognition.onend = () => {
        setUseMic(false)
      }

      recognitionRef.current = recognition
    }

    try {
      recognitionRef.current.start()
    } catch {
      setMicError('Voice input could not be started. Try again.')
      setUseMic(false)
    }
  }

  const stopMicCapture = () => {
    try {
      recognitionRef.current?.stop()
    } catch {
      // no-op
    }
    setUseMic(false)
  }

  const onMicToggle = () => {
    if (useMic) {
      stopMicCapture()
      return
    }
    startMicCapture()
  }

  const activeStatus = STATUS_INFO[status] ?? STATUS_INFO.ready

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_#e0f2fe_0%,_#f8fafc_50%,_#f1f5f9_100%)] text-slate-900">
      <div className="mx-auto flex min-h-screen max-w-6xl flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8">
        <header className="rounded-3xl border border-white/70 bg-white/70 p-4 shadow-sm backdrop-blur sm:p-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-4">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-900 text-white shadow-sm">
                <CalendarDays size={22} />
              </div>
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.32em] text-slate-500">Calendar Agent</p>
                <h1 className="text-xl font-semibold text-slate-900 sm:text-2xl">
                  Orchestrate schedules, summaries, and follow-ups in one place.
                </h1>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge className={cn('text-xs font-medium', activeStatus.className)}>{activeStatus.label}</Badge>
              <Badge className="border border-slate-200 bg-white text-slate-700">
                {selectedModel?.name ?? 'Model ready'}
              </Badge>
              <Badge className={cn('border', useWeb ? 'border-teal-200 bg-teal-50 text-teal-700' : 'border-slate-200 bg-slate-50 text-slate-600')}>
                {useWeb ? 'Web search on' : 'Web search off'}
              </Badge>
            </div>
          </div>
        </header>

        <Card className="relative flex min-h-0 flex-1 flex-col overflow-hidden border-slate-200/80 bg-white/80 shadow-sm backdrop-blur">
          <CardContent className="flex min-h-0 flex-1 flex-col gap-4 p-4 sm:p-6">
            <div
              className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pr-2"
              onScroll={onConversationScroll}
              ref={viewportRef}
            >
              {messages.map((item) => {
                const branch = branches[item.key] ?? 0
                return (
                  <MessageItem
                    item={item}
                    key={item.key}
                    onNext={() =>
                      setBranches((prev) => ({
                        ...prev,
                        [item.key]: Math.min((prev[item.key] ?? 0) + 1, item.versions.length - 1),
                      }))
                    }
                    onPrev={() =>
                      setBranches((prev) => ({
                        ...prev,
                        [item.key]: Math.max((prev[item.key] ?? 0) - 1, 0),
                      }))
                    }
                    versionIndex={branch}
                  />
                )
              })}
            </div>
          </CardContent>
          {showScrollButton ? (
            <div className="pointer-events-none absolute inset-x-0 bottom-4 flex justify-center">
              <Button
                className="pointer-events-auto rounded-full border border-slate-200 bg-white/90 text-slate-700 shadow-sm hover:bg-white"
                onClick={() => {
                  if (!viewportRef.current) return
                  viewportRef.current.scrollTop = viewportRef.current.scrollHeight
                }}
                size="sm"
                type="button"
                variant="secondary"
              >
                <ArrowDown size={14} />
                Jump to latest
              </Button>
            </div>
          ) : null}
        </Card>

        <Card className="border-slate-200/70 bg-white/90 shadow-sm backdrop-blur">
          <CardContent className="space-y-4 p-4 sm:p-6">
            <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
              <Sparkles size={16} className="text-amber-500" />
              <span className="font-medium">Suggested prompts</span>
            </div>
            <SuggestionChips suggestions={suggestions} onSelect={(suggestion) => void sendUserMessage(suggestion)} />
            <PromptComposer
              attachments={attachments}
              micError={micError}
              micSupported={micSupported}
              model={model}
              models={models}
              onAttachmentsChange={setAttachments}
              onMicToggle={onMicToggle}
              onModelChange={setModel}
              onSubmit={() => void sendUserMessage(text || 'Sent with attachments')}
              onTextChange={setText}
              onWebToggle={() => setUseWeb((prev) => !prev)}
              status={status}
              text={text}
              useMic={useMic}
              useWeb={useWeb}
            />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
