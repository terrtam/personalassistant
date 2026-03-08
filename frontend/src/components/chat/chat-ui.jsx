import { ArrowDown } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { askLlm } from './chat-api'
import { initialMessages, models, suggestions } from './chat-data'
import { MessageItem } from './message-item'
import { PromptComposer } from './prompt-composer'
import { SuggestionChips } from './suggestion-chips'

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
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

  const runAssistantReply = async (question) => {
    const assistantKey = `assistant-${Date.now()}`
    const assistantVersionId = `${assistantKey}-v1`
    setMessages((prev) => [
      ...prev,
      { key: assistantKey, from: 'assistant', versions: [{ id: assistantVersionId, content: '' }] },
    ])

    try {
      const result = await askLlm(question, 5)
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
    setAttachments([])
    setStatus('streaming')
    await runAssistantReply(trimmed)
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

  return (
    <div className="chat-shell">
      <section className="conversation" onScroll={onConversationScroll} ref={viewportRef}>
        <div>
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
      </section>

      {showScrollButton ? (
        <button
          className="scroll-btn"
          onClick={() => {
            if (!viewportRef.current) return
            viewportRef.current.scrollTop = viewportRef.current.scrollHeight
          }}
          type="button"
        >
          <ArrowDown size={14} /> Jump to latest
        </button>
      ) : null}

      <div className="composer-wrap">
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
      </div>
    </div>
  )
}
