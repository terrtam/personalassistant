import { Mic, MicOff, Paperclip, SendHorizontal, Upload, X } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'

import { cn } from '../lib/utils'
import { CalendarPicker } from './CalendarPicker'
import { Badge } from './ui/badge'
import { Button } from './ui/button'
import { Input } from './ui/input'

function ChatInput({ value, onChange, onSend, isLoading, attachments, onAttachmentsChange }) {
  const [isListening, setIsListening] = useState(false)
  const [micError, setMicError] = useState('')
  const [isDragging, setIsDragging] = useState(false)
  const recognitionRef = useRef(null)
  const fileRef = useRef(null)
  const fileInputId = useId()
  const baseTextRef = useRef('')
  const capturedRef = useRef('')

  useEffect(() => {
    return () => {
      try {
        recognitionRef.current?.stop()
      } catch {
        // no-op
      }
    }
  }, [])

  const handleSubmit = (event) => {
    event.preventDefault()
    onSend(value, attachments)
  }

  const mergeTranscript = (base, spoken) => {
    if (base && spoken) return `${base} ${spoken}`.trim()
    return (base || spoken || '').trim()
  }

  const startListening = () => {
    if (typeof window === 'undefined') return
    const SpeechRecognitionApi = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SpeechRecognitionApi) {
      setMicError('Voice input is not supported in this browser.')
      return
    }

    setMicError('')
    baseTextRef.current = value.trim()
    capturedRef.current = ''

    if (!recognitionRef.current) {
      const recognition = new SpeechRecognitionApi()
      recognition.continuous = true
      recognition.interimResults = true
      recognition.lang = 'en-US'

      recognition.onstart = () => {
        setIsListening(true)
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
          capturedRef.current = mergeTranscript(capturedRef.current, finalChunk.trim())
        }

        const liveTranscript = mergeTranscript(capturedRef.current, interimChunk.trim())
        onChange(mergeTranscript(baseTextRef.current, liveTranscript))
      }

      recognition.onerror = (event) => {
        if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
          setMicError('Microphone permission is blocked. Allow access and try again.')
        } else {
          setMicError(`Voice input failed: ${event.error}`)
        }
        setIsListening(false)
      }

      recognition.onend = () => {
        setIsListening(false)
      }

      recognitionRef.current = recognition
    }

    try {
      recognitionRef.current.start()
    } catch {
      setMicError('Voice input could not be started. Try again.')
      setIsListening(false)
    }
  }

  const stopListening = () => {
    try {
      recognitionRef.current?.stop()
    } catch {
      // no-op
    }
    setIsListening(false)
  }

  const toggleListening = () => {
    if (isListening) stopListening()
    else startListening()
  }

  const mapAttachments = (fileList) =>
    Array.from(fileList ?? []).map((file) => ({
      id: `${file.name}-${file.lastModified}`,
      name: file.name,
      file,
    }))

  const mergeAttachments = (incoming) => {
    if (!incoming.length) return attachments
    const seen = new Set(attachments.map((file) => file.id))
    const merged = [...attachments]
    incoming.forEach((file) => {
      if (seen.has(file.id)) return
      seen.add(file.id)
      merged.push(file)
    })
    return merged
  }

  const handleFiles = (fileList) => {
    const incoming = mapAttachments(fileList)
    if (!incoming.length) return
    onAttachmentsChange(mergeAttachments(incoming))
  }

  const canSend = Boolean(value.trim().length || attachments.length)

  return (
    <form className="flex flex-col gap-3" onSubmit={handleSubmit}>
      {attachments.length ? (
        <div className="flex flex-wrap gap-2">
          {attachments.map((file) => (
            <Badge className="gap-2 bg-slate-100 text-slate-700" key={file.id}>
              <Paperclip size={12} />
              <span className="text-xs">{file.name}</span>
              <Button
                className="h-5 w-5 p-0 text-slate-500 hover:text-slate-900"
                onClick={() =>
                  onAttachmentsChange(attachments.filter((entry) => entry.id !== file.id))
                }
                size="icon"
                type="button"
                variant="ghost"
              >
                <X size={12} />
              </Button>
            </Badge>
          ))}
        </div>
      ) : null}

      <div
        className={cn(
          'rounded-2xl border border-dashed p-4 transition',
          isDragging
            ? 'border-slate-900 bg-slate-100/90 shadow-sm'
            : 'border-slate-200 bg-white',
        )}
        onDragEnd={() => setIsDragging(false)}
        onDragLeave={() => setIsDragging(false)}
        onDragOver={(event) => {
          event.preventDefault()
          event.dataTransfer.dropEffect = 'copy'
          setIsDragging(true)
        }}
        onDrop={(event) => {
          event.preventDefault()
          setIsDragging(false)
          handleFiles(event.dataTransfer.files)
        }}
      >
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white text-slate-700 shadow-sm">
              <Upload size={18} />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-900">Attach files</p>
              <p className="text-xs text-slate-500">
                Drag and drop or browse to add PDFs, docs, or images.
              </p>
            </div>
          </div>
          <Button onClick={() => fileRef.current?.click()} type="button" variant="secondary">
            Browse files
          </Button>
        </div>
        <Input
          aria-label="Attach files"
          className="sr-only"
          id={fileInputId}
          multiple
          onChange={(event) => {
            handleFiles(event.target.files)
            event.target.value = ''
          }}
          ref={fileRef}
          type="file"
        />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Input
          className="h-11 min-w-[200px] flex-1"
          placeholder="Ask about your schedule, meetings, or notes..."
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
        <CalendarPicker onSelectText={(text) => onChange(text)} />
        <Button
          type="button"
          variant="secondary"
          size="icon"
          className="h-11 w-11"
          aria-label={isListening ? 'Stop voice input' : 'Start voice input'}
          onClick={toggleListening}
        >
          {isListening ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
        </Button>
        <Button type="submit" className="h-11 px-4" disabled={isLoading || !canSend}>
          <SendHorizontal className="h-4 w-4" />
          Send
        </Button>
      </div>
      <p className={micError ? 'text-xs text-rose-600' : 'text-xs text-slate-500'}>
        {micError ? micError : 'Tip: Pick a date to prefill a scheduling request.'}
      </p>
    </form>
  )
}

export { ChatInput }
